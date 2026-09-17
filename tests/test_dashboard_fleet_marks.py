# tests/test_dashboard_fleet_marks.py
"""E-75 spec §5.3: closed graph rows carry stage marks, queried once per run."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sdlc.core.models import RunState, RunSummary
from sdlc.dashboard.fleet import FleetPoller, fetch_fleet

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _summary(run_id):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="x",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
    )


def _state(run_id, marks):
    return RunState(
        run_id=run_id,
        title="T",
        mode="greenfield",
        status="running",
        started_at=AT,
        stage_marks=marks,
    )


class _Handle:
    def __init__(self, *, summary=None, state=None, error=None):
        self.summary, self.state, self.error = summary, state, error
        self.calls: list[str] = []

    async def query(self, name):
        self.calls.append(name)
        if name == "run_state" and self.error is not None:
            raise self.error
        value = {"run_summary": self.summary, "run_state": self.state, "pending_decisions": None}[
            name
        ]
        return value.model_dump(mode="json") if value is not None else None


class _Client:
    def __init__(self, closed):  # run_id -> (workflow_type, handle)
        self.closed = closed

    async def list_workflows(self, query):
        if "!=" not in query:
            return
        for run_id, (wf_type, _) in self.closed.items():
            yield SimpleNamespace(id=run_id, workflow_type=wf_type)

    def get_workflow_handle(self, run_id):
        return self.closed[run_id][1]


@pytest.mark.asyncio
async def test_closed_graph_rows_get_closed_marks_and_are_queried_once():
    graph = _Handle(
        summary=_summary("g"), state=_state("g", {"intake": "done", "architecture": "blocked"})
    )
    legacy = _Handle(summary=_summary("f"))
    client = _Client({"g": ("GraphWorkflow", graph), "f": ("FeatureWorkflow", legacy)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {"g": {"architecture": "failed", "intake": "done"}}
    assert "run_state" not in legacy.calls  # FeatureWorkflow rows are never asked
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 1


@pytest.mark.asyncio
async def test_failed_marks_query_is_an_error_row_and_retries_next_tick():
    graph = _Handle(summary=_summary("g"), error=RuntimeError("boom"))
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {}
    assert any(e.run_id == "g" for e in snap.errors)
    assert snap.open_errors == []
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 2


@pytest.mark.asyncio
async def test_cache_is_pruned_to_the_current_closed_list():
    graph = _Handle(summary=_summary("g"), state=_state("g", {"intake": "done"}))
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {"gone": {"intake": "done"}}
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert set(cache) == {"g"}


@pytest.mark.asyncio
async def test_a_run_that_never_dispatched_has_no_marks_and_is_not_requeried():
    graph = _Handle(summary=_summary("g"), state=None)
    client = _Client({"g": ("GraphWorkflow", graph)})
    cache: dict = {}
    snap = await fetch_fleet(client, now=AT, marks_cache=cache)
    assert snap.closed_marks == {}
    await fetch_fleet(client, now=AT, marks_cache=cache)
    assert graph.calls.count("run_state") == 1


def test_default_poller_fetch_owns_a_marks_cache():
    poller = FleetPoller(lambda: None)
    assert poller._fetch.keywords["marks_cache"] is poller._marks_cache
