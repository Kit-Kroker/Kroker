"""The fleet fan-out (spec 5.1). Generalizes inbox.py's pattern: one run's
failed query becomes an errors[] entry, never an exception that aborts the
page (inbox.py:83)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from sdlc.channels.inbox import InboxError, RunInbox
from sdlc.core.models import (
    RunState,
    RunSummary,
)
from sdlc.dashboard.fleet import (
    FleetCapacityExceeded,
    FleetSnapshot,
    check_fleet_capacity,
    fetch_fleet,
    fleet_pending_cap,
    guard_fleet_capacity,
    pending_run_count,
)
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


@pytest.mark.asyncio
async def test_an_open_run_query_failure_lands_in_both_errors_and_open_errors():
    client = _Client(
        {
            "run-a": _Handle(state=_state("run-a"), pending=[Q1]),
            "run-bad": _Handle(error=RuntimeError("query timeout")),
        }
    )
    snap = await fetch_fleet(client, now=AT)
    assert [e.run_id for e in snap.errors] == ["run-bad"]
    assert [e.run_id for e in snap.open_errors] == ["run-bad"]


@pytest.mark.asyncio
async def test_a_closed_run_query_failure_stays_out_of_open_errors():
    """B4: a closed run owes no human a decision, so its failed run_summary
    query must never consume a fleet cap slot -- it belongs in errors (which
    the dashboard renders) but not in open_errors (which the cap counts)."""
    client = _Client(
        {"run-a": _Handle(state=_state("run-a"), pending=[])},
        {"run-done": _Handle(error=RuntimeError("summary unavailable"))},
    )
    snap = await fetch_fleet(client, now=AT)
    assert [e.run_id for e in snap.errors] == ["run-done"]
    assert snap.open_errors == []


# -- pending_run_count: what the cap actually counts (B4) --


def _snap(*, pending_runs: int = 0, open_errs: int = 0, closed_errs: int = 0) -> FleetSnapshot:
    return FleetSnapshot(
        at=AT,
        total_open_runs=pending_runs + open_errs,
        inbox=[RunInbox(run_id=f"open-{i}", pending=[Q1]) for i in range(pending_runs)],
        open_errors=[InboxError(run_id=f"bad-{i}", error="boom") for i in range(open_errs)],
        errors=(
            [InboxError(run_id=f"bad-{i}", error="boom") for i in range(open_errs)]
            + [InboxError(run_id=f"done-{i}", error="boom") for i in range(closed_errs)]
        ),
    )


def test_an_empty_fleet_has_nothing_pending():
    assert pending_run_count(_snap()) == 0


def test_each_run_with_pending_items_counts_once():
    assert pending_run_count(_snap(pending_runs=2)) == 2


def test_an_unqueryable_open_run_counts_toward_the_cap():
    """Fail-closed: an open run whose query failed has an UNKNOWN pending
    state, not a zero one. C8's shape -- an absence must never read as an
    approval."""
    assert pending_run_count(_snap(open_errs=1)) == 1


def test_a_closed_run_error_counts_for_nothing():
    """The Task 1 regression: three failed closed-run summary fetches are
    visible in errors but owe no decisions, so the cap must ignore them."""
    assert pending_run_count(_snap(closed_errs=3)) == 0


def test_pending_and_unqueryable_open_runs_sum():
    assert pending_run_count(_snap(pending_runs=2, open_errs=1, closed_errs=5)) == 3


def test_a_run_with_three_pending_items_still_counts_once():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=1,
        inbox=[RunInbox(run_id="busy", pending=[Q1, Q1, ARCH])],
    )
    assert pending_run_count(snap) == 1


# -- check_fleet_capacity: the admission decision --


def test_no_cap_configured_always_admits():
    check_fleet_capacity(_snap(pending_runs=99), None)  # must not raise


def test_below_the_cap_admits():
    check_fleet_capacity(_snap(pending_runs=4), 5)  # must not raise


def test_exactly_at_the_cap_refuses():
    """The boundary is >=, not >: cap=5 must mean at most five pending, so a
    sixth start is refused rather than admitted."""
    with pytest.raises(FleetCapacityExceeded):
        check_fleet_capacity(_snap(pending_runs=5), 5)


def test_over_the_cap_refuses():
    with pytest.raises(FleetCapacityExceeded):
        check_fleet_capacity(_snap(pending_runs=7), 5)


def test_the_refusal_carries_the_cap_and_the_count():
    with pytest.raises(FleetCapacityExceeded) as e:
        check_fleet_capacity(_snap(pending_runs=6), 5)
    assert e.value.cap == 5
    assert e.value.pending == 6
    assert "6" in str(e.value) and "5" in str(e.value)


# -- fleet_pending_cap: the env var --


def test_an_unset_cap_means_no_cap(monkeypatch):
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)
    assert fleet_pending_cap() is None


def test_a_set_cap_is_parsed(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "5")
    assert fleet_pending_cap() == 5


def test_a_garbage_cap_fails_loudly_rather_than_disabling_the_check(monkeypatch):
    """A typo'd cap must not silently mean 'no back-pressure' -- the same
    fail-closed posture as counting unqueryable open runs."""
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "lots")
    with pytest.raises(ValueError):
        fleet_pending_cap()


# -- guard_fleet_capacity: fetch + check, for a caller holding a client --


@pytest.mark.asyncio
async def test_the_guard_admits_when_no_cap_is_set(monkeypatch):
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    await guard_fleet_capacity(client)  # must not raise


@pytest.mark.asyncio
async def test_the_guard_never_touches_the_fleet_when_no_cap_is_set(monkeypatch):
    """B4 is opt-in, and opt-in must mean the fetch does not happen at all --
    not merely that its result is ignored. Reading the cap after awaiting the
    fetch (argument evaluation is left to right) would make every un-opted-in
    deployment pay a fan-out per start, and would turn a Temporal visibility
    blip into a failed `start` for operators who never enabled the cap.
    """
    monkeypatch.delenv("SDLC_FLEET_PENDING_CAP", raising=False)

    class _ExplodingClient:
        def list_workflows(self, query):
            raise AssertionError("the guard queried the fleet with no cap configured")

    await guard_fleet_capacity(_ExplodingClient())  # must not raise, must not query


@pytest.mark.asyncio
async def test_the_guard_refuses_when_the_fetched_fleet_is_at_cap(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "1")
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    with pytest.raises(FleetCapacityExceeded) as e:
        await guard_fleet_capacity(client)
    assert e.value.pending == 1


@pytest.mark.asyncio
async def test_the_guard_admits_when_the_fetched_fleet_is_below_cap(monkeypatch):
    monkeypatch.setenv("SDLC_FLEET_PENDING_CAP", "2")
    client = _Client({"run-a": _Handle(state=_state("run-a"), pending=[ARCH])})
    await guard_fleet_capacity(client)  # 1 pending < cap 2
