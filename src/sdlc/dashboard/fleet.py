"""Fleet fan-out and snapshot for the dashboard backend (E-10).

Imports no web framework: the fan-out and the poller are where the interesting
failures live, so they must be testable without an HTTP client -- the same
reason channels/transport.py is testable without a CLI.

Generalizes channels/inbox.py's pattern to two queries per handle, and adds
a capped second pass over recently CLOSED runs. That second pass is why the
dashboard needs no database (spec D7): Temporal keeps closed workflows
queryable for its retention period, so Temporal is the store. The bound is
real -- history reaches back only as far as that retention.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, TypeAdapter

from ..channels.inbox import InboxError, RunInbox, list_open_run_ids
from ..models import RunState, RunSummary
from ..pending import PendingDecision

CLOSED_LIMIT = 20

_CLOSED_QUERY = ("WorkflowType='FeatureWorkflow' AND "
                 "ExecutionStatus!='Running'")

_PENDING_LIST = TypeAdapter(list[PendingDecision])


class FleetSnapshot(BaseModel):
    """One fan-out's result. Everything the dashboard serves derives from
    this -- both REST reads and every SSE event."""
    at: datetime
    total_open_runs: int = 0
    runs: list[RunState] = Field(default_factory=list)
    closed: list[RunSummary] = Field(default_factory=list)
    inbox: list[RunInbox] = Field(default_factory=list)
    errors: list[InboxError] = Field(default_factory=list)


async def _fetch_open(client, run_id: str):
    """Never raises: an exception becomes the return value, so one run's
    failure can't take down asyncio.gather for the rest (inbox.py:83)."""
    try:
        handle = client.get_workflow_handle(run_id)
        raw_state, raw_pending = await asyncio.gather(
            handle.query("run_state"), handle.query("pending_decisions"))
        state = (RunState.model_validate(raw_state)
                 if raw_state is not None else None)
        return state, _PENDING_LIST.validate_python(raw_pending or [])
    except Exception as e:      # noqa: BLE001 -- captured into errors[]
        return e


async def _fetch_closed(client, run_id: str):
    try:
        handle = client.get_workflow_handle(run_id)
        raw = await handle.query("run_summary")
        # None is ordinary: a run that terminated before retro has no
        # summary. That is a skip, not an error.
        return RunSummary.model_validate(raw) if raw is not None else None
    except Exception as e:      # noqa: BLE001
        return e


async def _closed_run_ids(client, limit: int) -> list[str]:
    ids: list[str] = []
    async for wf in client.list_workflows(_CLOSED_QUERY):
        ids.append(wf.id)
        if len(ids) >= limit:
            break
    return ids


async def fetch_fleet(client, *, now: datetime,
                      closed_limit: int = CLOSED_LIMIT) -> FleetSnapshot:
    """Discover open and recently-closed runs and fan out over both."""
    open_ids = await list_open_run_ids(client)
    closed_ids = await _closed_run_ids(client, closed_limit)

    open_results, closed_results = await asyncio.gather(
        asyncio.gather(*(_fetch_open(client, r) for r in open_ids)),
        asyncio.gather(*(_fetch_closed(client, r) for r in closed_ids)))

    snap = FleetSnapshot(at=now, total_open_runs=len(open_ids))
    for run_id, outcome in zip(open_ids, open_results):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=str(outcome)))
            continue
        state, pending = outcome
        if state is not None:
            snap.runs.append(state)
        if pending:
            # A run with nothing pending is dropped from the inbox, not from
            # runs -- it is still live, it just owes no decision.
            snap.inbox.append(RunInbox(run_id=run_id, pending=pending))

    for run_id, outcome in zip(closed_ids, closed_results):
        if isinstance(outcome, Exception):
            snap.errors.append(InboxError(run_id=run_id, error=str(outcome)))
        elif outcome is not None:
            snap.closed.append(outcome)
    return snap


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FleetPoller:
    """One shared fan-out multiplexed to every subscriber (spec D5/D6).

    Why shared: a per-request fan-out costs N_clients x N_runs because each
    browser tab polls independently. One poller costs N_runs regardless of
    how many tabs are open.

    Why lazy: an operator tool left open overnight should stop querying
    Temporal when nobody is watching. It starts on the first subscriber or
    a cold read and stops grace_s after the last unsubscribe.

    Why snapshot() can still fan out inline: REST correctness must never
    depend on the poller being up.

    `clock` and `fetch` are injectable for tests only; production uses the
    module defaults.
    """

    def __init__(self, client_factory, *, interval: float = 2.0,
                 grace_s: float = 30.0, clock=None, fetch=None) -> None:
        self._client_factory = client_factory
        self._interval = interval
        self._grace_s = grace_s
        self._clock = clock or _utcnow
        self._fetch = fetch or fetch_fleet
        self._client = None
        self._snapshot: FleetSnapshot | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop_handle: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _client_or_connect(self):
        if self._client is None:
            self._client = self._client_factory()
            if asyncio.iscoroutine(self._client):
                self._client = await self._client
        return self._client

    async def _fan_out(self) -> FleetSnapshot:
        client = await self._client_or_connect()
        snap = await self._fetch(client, now=self._clock())
        self._snapshot = snap
        return snap

    def _fresh(self) -> bool:
        if self._snapshot is None:
            return False
        age = (self._clock() - self._snapshot.at).total_seconds()
        return age < 2 * self._interval

    async def snapshot(self) -> FleetSnapshot:
        """The cached snapshot when fresh, otherwise an inline fan-out."""
        async with self._lock:
            if self._fresh():
                return self._snapshot
            return await self._fan_out()

    async def _loop(self) -> None:
        while True:
            try:
                async with self._lock:
                    snap = await self._fan_out()
                for q in list(self._subscribers):
                    q.put_nowait(snap)
            except asyncio.CancelledError:
                raise
            except Exception:       # noqa: BLE001 -- a poll failure must
                pass                # never kill the loop; next tick retries
            await asyncio.sleep(self._interval)

    def _cancel_pending_stop(self) -> None:
        if self._stop_handle is not None:
            self._stop_handle.cancel()
            self._stop_handle = None

    def _schedule_stop(self) -> None:
        loop = asyncio.get_running_loop()
        self._cancel_pending_stop()
        self._stop_handle = loop.call_later(
            self._grace_s,
            lambda: asyncio.ensure_future(self._stop_if_idle()))

    async def _stop_if_idle(self) -> None:
        if not self._subscribers:
            await self.aclose()

    @contextlib.asynccontextmanager
    async def subscribe(self):
        """Yields a queue receiving every new snapshot while subscribed."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        self._cancel_pending_stop()
        if not self.running:
            self._task = asyncio.create_task(self._loop())
        try:
            yield q
        finally:
            self._subscribers.discard(q)
            if not self._subscribers:
                self._schedule_stop()

    async def aclose(self) -> None:
        """Stop the poll loop now. Idempotent."""
        self._cancel_pending_stop()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
