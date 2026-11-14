"""Shared fakes for the operator bridge and MCP parity tests (022 T009).

A helper module, NOT a test module (no test_ prefix): pytest test files and
the subprocess fake bridge (tests/mcp_fake_bridge.py) both import it, so it
must never import pytest — a subprocess has to be able to load it cold.

The transport shapes mirror sdlc.channels.transport exactly:
query(PENDING_QUERY) returns the JSON list fetch_pending validates, and
signal(...) records itself then removes the addressed pending item the way
a real workflow signal handler does, so submit()'s re-query sees the item
gone and reports confirmed=True. Set handle.drop_on_signal = False to keep
the item pending (the confirmed=false race, FR-006).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdlc.artifacts.store import LocalFileStore
from sdlc.board.store import BoardStore
from sdlc.channels.inbox import RunInbox
from sdlc.channels.transport import PENDING_QUERY
from sdlc.core.models import RunState, RunSummary
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.operator.deps import OperatorDeps
from sdlc.pending import ClarifyPending, StageGatePending
from sdlc.stages.plan.models import DevTask

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
RUN_A = "feature-add-sso"
RUN_B = "feature-fix-cache"

GATE = StageGatePending(
    key="architecture#2", gate="architecture", round=2, spec_summary="the spec is stable"
)
Q1 = ClarifyPending(key="Q1", question="which cache?", why_it_matters="pick before the plan stage")

BIG_BYTES = ("x" * (100 * 1024)).encode("utf-8")


class FakeHandle:
    """A workflow handle speaking the real FR-302 query/signal protocol."""

    def __init__(self, run_id: str, pending: list[Any]) -> None:
        self.id = run_id
        self._pending = list(pending)
        self.signals: list[tuple[str, Any]] = []
        self.drop_on_signal = True

    async def query(self, name: str):
        if name == PENDING_QUERY:
            return [d.model_dump(mode="json") for d in self._pending]
        raise LookupError(f"no query {name!r} on the fake handle")

    async def signal(self, name: str, *args: Any, **kw: Any) -> None:
        payload = args if args else kw.get("args")
        self.signals.append((name, payload))
        if not self.drop_on_signal:
            return
        self._pending = [d for d in self._pending if not self._addresses(name, payload, d)]

    @staticmethod
    def _addresses(name: str, payload: Any, pending: Any) -> bool:
        if name == "answer_question":
            key = payload[0] if isinstance(payload, (list, tuple)) else None
            return pending.key == key
        decision = payload[0] if isinstance(payload, (list, tuple)) else payload
        return getattr(pending, "gate", None) == getattr(decision, "gate", None) and getattr(
            pending, "round", None
        ) == getattr(decision, "round", None)


class FakeClient:
    def __init__(self, handles: dict[str, FakeHandle]) -> None:
        self._handles = handles

    def get_workflow_handle(self, run_id: str) -> FakeHandle:
        return self._handles[run_id]


class FakePoller:
    """FleetPoller's read surface: snapshot, client, subscriptions, close."""

    def __init__(self, snapshot: FleetSnapshot, handles: dict[str, FakeHandle]) -> None:
        self._snapshot = snapshot
        self._handles = handles
        self.subscriptions: set[asyncio.Queue] = set()
        self.aclosed = False

    async def snapshot(self) -> FleetSnapshot:
        return self._snapshot

    async def _client_or_connect(self) -> FakeClient:
        return FakeClient(self._handles)

    def subscribe(self):
        poller = self

        class _Sub:
            async def __aenter__(self) -> asyncio.Queue:
                self._q: asyncio.Queue = asyncio.Queue()
                poller.subscriptions.add(self._q)
                return self._q

            async def __aexit__(self, *exc: object) -> None:
                poller.subscriptions.discard(self._q)

        return _Sub()

    async def aclose(self) -> None:
        self.aclosed = True


def fleet() -> FleetSnapshot:
    """Two open runs (one gate, one clarify question) and one closed run."""
    return FleetSnapshot(
        at=AT,
        total_open_runs=2,
        runs=[
            RunState(
                run_id=RUN_A,
                title="Add SSO",
                mode="greenfield",
                status="waiting",
                current_stage="architecture",
                started_at=AT,
            ),
            RunState(
                run_id=RUN_B,
                title="Fix the cache",
                mode="brownfield",
                status="waiting",
                current_stage="clarify",
                started_at=AT,
            ),
        ],
        closed=[
            RunSummary(
                run_id="feature-old-thing",
                mode="greenfield",
                title="Old thing",
                outcome="completed",
                terminal_stage="reflect",
                started_at=AT,
                ended_at=AT,
                duration_s=60.0,
            )
        ],
        inbox=[RunInbox(run_id=RUN_A, pending=[GATE]), RunInbox(run_id=RUN_B, pending=[Q1])],
    )


def seed_board(tmp_path: Path) -> Callable[[], BoardStore]:
    """One project, one plan artifact, one 100 KB blob, two tasks.

    Built the way tests/test_operator_tools_board.py and
    tests/test_operator_read_artifact.py build theirs: a zero-arg factory
    over a temp sqlite db + blob root, because tools._board opens and
    closes a store per call. The durable event timeline is whatever these
    seed writes record; the parity tests only need it deterministic.
    """
    db = tmp_path / "board.db"
    blobs = tmp_path / "runs"
    seed = BoardStore(db, blobs=LocalFileStore(root=blobs))
    seed.ensure_project("kroker", repo="git@example.com:kroker.git")
    _, plan_version = seed.publish_artifact_version(
        "kroker", "plan", run_id=RUN_A, content=b'{"tasks": []}', actor=f"workflow:{RUN_A}"
    )
    seed.publish_artifact_version(
        "kroker", "spec", run_id=RUN_A, content=BIG_BYTES, actor=f"workflow:{RUN_A}"
    )
    seed.sync_plan_tasks(
        "kroker",
        plan_version,
        RUN_A,
        [
            DevTask(id="T01", title="wire sso", description="d", acceptance_criteria=["c"]),
            DevTask(id="T02", title="test sso", description="d", acceptance_criteria=["c"]),
        ],
        actor=f"workflow:{RUN_A}",
    )
    seed.close()

    def factory() -> BoardStore:
        return BoardStore(db, blobs=LocalFileStore(root=blobs))

    return factory


def _jsonify(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    return value


class Recorder:
    """What the fake fleet saw: every signal, every start attempt."""

    def __init__(self, handles: dict[str, FakeHandle]) -> None:
        self.handles = handles
        self.started: list[dict[str, Any]] = []

    def dump(self) -> dict[str, Any]:
        return {
            "signals": [
                {"run_id": h.id, "name": name, "args": _jsonify(args)}
                for h in self.handles.values()
                for name, args in h.signals
            ],
            "started": list(self.started),
        }


# The subprocess fake bridge (one build per process) registers its recorder
# here so record_to(path) can dump on demand without pytest in scope.
_STATE: Recorder | None = None


def record_to(path: str | Path) -> None:
    """Dump the current build's signals + starts as JSON to path."""
    if _STATE is None:
        raise RuntimeError("build_fake_deps has not run in this process")
    Path(path).write_text(json.dumps(_STATE.dump(), indent=2), encoding="utf-8")


def build_fake_deps(tmp_path: Path, actor: str = "mcp:test") -> OperatorDeps:
    """Deps over the fake fleet + seeded board, with a recording starter.

    deps.recorder exposes the handles (their .signals) and .started for
    write-path assertions; deps.poller.subscriptions shows live follow
    subscriptions.
    """
    global _STATE
    handles = {
        RUN_A: FakeHandle(RUN_A, [GATE]),
        RUN_B: FakeHandle(RUN_B, [Q1]),
    }
    recorder = Recorder(handles)
    _STATE = recorder

    async def starter(idea: Any, cfg: Any, wf_id: str) -> str:
        mode = getattr(idea.mode, "value", idea.mode)
        recorder.started.append(
            {"wf_id": wf_id, "title": idea.title, "mode": mode, "description": idea.description}
        )
        return wf_id

    deps = OperatorDeps(
        poller=FakePoller(fleet(), handles),
        board=seed_board(tmp_path),
        starter=starter,
        actor=actor,
    )
    deps.recorder = recorder  # type: ignore[attr-defined]
    return deps
