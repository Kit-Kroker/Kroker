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
from datetime import datetime

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
