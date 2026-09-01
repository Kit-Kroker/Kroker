"""The fleet fan-out (spec 5.1). Generalizes inbox.py's pattern: one run's
failed query becomes an errors[] entry, never an exception that aborts the
page (inbox.py:83)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sdlc.dashboard.fleet import FleetSnapshot, fetch_fleet
from sdlc.models import RunState, RunSummary
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


def _state(run_id, **kw):
    return RunState(
        run_id=run_id,
        title=kw.pop("title", "T"),
        mode=kw.pop("mode", "greenfield"),
        status=kw.pop("status", "running"),
        started_at=AT,
        **kw,
    )


def _summary(run_id):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:ok",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
        title="Closed one",
    )


class _Handle:
    """Scripts one response per query name, or raises."""

    def __init__(self, *, state=None, pending=None, summary=None, error=None):
        self._r = {"run_state": state, "pending_decisions": pending or [], "run_summary": summary}
        self._error = error

    async def query(self, name):
        if self._error is not None:
            raise self._error
        v = self._r[name]
        if isinstance(v, list):
            return [i.model_dump(mode="json") for i in v]
        return v.model_dump(mode="json") if v is not None else None


class _Client:
    def __init__(self, open_handles, closed_handles=None):
        self._open = open_handles
        self._closed = closed_handles or {}
        self.queries = []

    async def list_workflows(self, query):
        self.queries.append(query)
        ids = self._closed if "!=" in query else self._open
        for run_id in ids:
            yield SimpleNamespace(id=run_id)

    def get_workflow_handle(self, run_id):
        return {**self._open, **self._closed}[run_id]


@pytest.mark.asyncio
async def test_fetch_fleet_aggregates_state_and_pending_per_run():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[ARCH]),
            "run-b": _Handle(state=_state("run-b"), pending=[]),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert snap.total_open_runs == 2
    assert {r.run_id for r in snap.runs} == {"run-a", "run-b"}
    # a run with nothing pending is dropped from the inbox, not from runs
    assert [i.run_id for i in snap.inbox] == ["run-a"]


@pytest.mark.asyncio
async def test_one_failing_run_becomes_an_error_not_an_exception():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[Q1]),
            "run-bad": _Handle(error=RuntimeError("workflow not found")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert [r.run_id for r in snap.runs] == ["run-a"]
    assert [e.run_id for e in snap.errors] == ["run-bad"]
    assert "workflow not found" in snap.errors[0].error


@pytest.mark.asyncio
async def test_total_open_runs_counts_every_run_including_failed_ones():
    """'no runs listed' and 'checked 2, none had anything' must stay
    distinguishable (Inbox.total_open_runs' documented reason)."""
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a")),
            "run-bad": _Handle(error=RuntimeError("boom")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert snap.total_open_runs == 2


@pytest.mark.asyncio
async def test_closed_runs_are_rendered_from_run_summary():
    client = _Client(
        {"run-a": _Handle(state=_state("run-a"))}, {"run-old": _Handle(summary=_summary("run-old"))}
    )
    snap = await fetch_fleet(client, now=AT)
    assert [c.run_id for c in snap.closed] == ["run-old"]
    assert snap.closed[0].title == "Closed one"


@pytest.mark.asyncio
async def test_closed_runs_are_capped():
    closed = {f"run-{i}": _Handle(summary=_summary(f"run-{i}")) for i in range(5)}
    client = _Client({}, closed)
    snap = await fetch_fleet(client, now=AT, closed_limit=2)
    assert len(snap.closed) == 2


@pytest.mark.asyncio
async def test_a_closed_run_whose_summary_is_none_is_skipped_not_errored():
    """run_summary() returns None on a run that terminated before retro."""
    client = _Client({}, {"run-old": _Handle(summary=None)})
    snap = await fetch_fleet(client, now=AT)
    assert snap.closed == []
    assert snap.errors == []


@pytest.mark.asyncio
async def test_empty_fleet_is_an_empty_snapshot_not_an_error():
    snap = await fetch_fleet(_Client({}), now=AT)
    assert snap == FleetSnapshot(at=AT)


@pytest.mark.asyncio
async def test_the_closed_pass_is_ordered_newest_first():
    """Past CLOSED_LIMIT closed runs the just-finished run may never appear
    without ORDER BY CloseTime DESC -- Temporal's default order is arbitrary
    (E-10 review B5)."""
    client = _Client({}, {"run-old": _Handle(summary=_summary("run-old"))})
    await fetch_fleet(client, now=AT)
    closed_queries = [q for q in client.queries if "!=" in q]
    assert closed_queries, "the closed pass never ran"
    assert "ORDER BY CloseTime DESC" in closed_queries[0]


@pytest.mark.asyncio
async def test_the_closed_pass_falls_back_when_order_by_is_rejected(monkeypatch):
    """Standard visibility (the dev server this project deploys) rejects the
    ORDER BY clause outright; the fan-out must retry unordered rather than
    fail -- found by the temporal e2e, kept fast here."""
    import sdlc.dashboard.fleet as fleet_mod

    monkeypatch.setattr(fleet_mod, "_ORDER_BY_SUPPORTED", True)

    class _NoOrderBy(_Client):
        async def list_workflows(self, query):
            if "ORDER BY" in query:
                raise RuntimeError("invalid query: operation is not supported: 'ORDER BY' clause")
            async for wf in super().list_workflows(query):
                yield wf

    client = _NoOrderBy({}, {"run-old": _Handle(summary=_summary("run-old"))})
    snap = await fetch_fleet(client, now=AT)
    assert [c.run_id for c in snap.closed] == ["run-old"]
    assert fleet_mod._ORDER_BY_SUPPORTED is False
    # the remembered verdict skips the rejected clause on later fan-outs
    client.queries.clear()
    await fetch_fleet(client, now=AT)
    assert all("ORDER BY" not in q for q in client.queries)


@pytest.mark.asyncio
async def test_a_run_landing_in_both_passes_is_rendered_once():
    """A run completing between the two visibility queries shows up in both
    id lists; the open pass already rendered it, so the closed pass must
    skip it rather than duplicate its row (E-10 review B6)."""
    both = _Handle(state=_state("run-x"), summary=_summary("run-x"))
    client = _Client({"run-x": both}, {"run-x": both})
    snap = await fetch_fleet(client, now=AT)
    assert [r.run_id for r in snap.runs] == ["run-x"]
    assert snap.closed == []
    assert snap.errors == []
