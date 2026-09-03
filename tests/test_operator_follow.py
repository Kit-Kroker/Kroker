"""follow: run-scoped fingerprints, early return, clamping, and the brake."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import pytest

from sdlc.channels.inbox import RunInbox
from sdlc.core.models import (
    RunState,
)
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
GATE = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")


def a_run(run_id="r1", stage="dev", status="running", cost=None):
    return RunState(
        run_id=run_id,
        title="Add SSO",
        mode="brownfield",
        status=status,
        started_at=AT,
        current_stage=stage,
        cost_usd_total=cost,
    )


def _a_summary(run_id):
    """A closed-run entry, for asserting that closures elsewhere in the fleet
    do not end a run-scoped wait."""
    from sdlc.core.models import (
        RunSummary,
    )

    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed",
        terminal_stage="deploy",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
    )


def snap(runs, inbox=(), at=AT):
    return FleetSnapshot(at=at, total_open_runs=len(runs), runs=list(runs), inbox=list(inbox))


class ScriptedPoller:
    """Feeds a fixed list of snapshots to every subscriber, then idles."""

    def __init__(self, first, rest):
        self.first = first
        self.rest = list(rest)

    async def snapshot(self):
        return self.first

    @contextlib.asynccontextmanager
    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        for s in self.rest:
            q.put_nowait(s)
        yield q


def deps_for(poller, **kw):
    return OperatorDeps(poller=poller, board=None, starter=None, **kw)


@pytest.mark.asyncio
async def test_returns_when_the_followed_run_advances_a_stage():
    p = ScriptedPoller(snap([a_run(stage="dev")]), [snap([a_run(stage="qa")])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "qa" in got.detail
    assert any("stage" in c for c in got.changed)


@pytest.mark.asyncio
async def test_returns_immediately_on_a_new_pending_decision():
    p = ScriptedPoller(snap([a_run()]), [snap([a_run()], [RunInbox(run_id="r1", pending=[GATE])])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "architecture" in got.detail


@pytest.mark.asyncio
async def test_returns_when_the_run_leaves_the_open_set():
    p = ScriptedPoller(snap([a_run()]), [snap([])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is False
    assert "closed" in got.detail.lower()


@pytest.mark.asyncio
async def test_another_runs_movement_does_not_end_a_scoped_follow():
    p = ScriptedPoller(
        snap([a_run("r1"), a_run("r2")]), [snap([a_run("r1"), a_run("r2", stage="qa")])]
    )
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_unscoped_follow_reports_any_runs_movement():
    p = ScriptedPoller(
        snap([a_run("r1"), a_run("r2")]), [snap([a_run("r1"), a_run("r2", stage="qa")])]
    )
    got = await tools.follow(deps_for(p), timeout_s=5)
    assert got.timed_out is False
    assert "r2" in got.detail


@pytest.mark.asyncio
async def test_a_clock_only_snapshot_is_not_a_change():
    later = AT + timedelta(seconds=30)
    p = ScriptedPoller(snap([a_run()]), [snap([a_run()], at=later)])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_timeout_is_clamped_to_the_floor_and_ceiling():
    assert tools._clamp(1) == tools.MIN_TIMEOUT_S
    assert tools._clamp(9999) == tools.MAX_TIMEOUT_S
    assert tools._clamp(60) == 60


@pytest.mark.asyncio
async def test_unknown_run_is_refused_before_waiting():
    p = ScriptedPoller(snap([a_run("r1")]), [])
    with pytest.raises(ToolError) as e:
        await tools.follow(deps_for(p), run_id="nope", timeout_s=5)
    assert "nope" in e.value.message


@pytest.mark.asyncio
async def test_eleventh_consecutive_follow_is_refused():
    p = ScriptedPoller(snap([a_run()]), [])
    d = deps_for(p, max_follow_calls=2)
    d.note_follow()
    d.note_follow()
    with pytest.raises(ToolError) as e:
        await tools.follow(d, run_id="r1", timeout_s=5)
    assert "report to the operator" in e.value.message


@pytest.mark.asyncio
async def test_a_cost_only_change_is_not_a_change():
    """The fingerprint must move only in ways _describe_change can name.

    Serialising the whole RunState folded in `roles` and `cost_usd_total`,
    which move on almost every poll tick of an active run: every wait then
    returned within seconds reporting "something changed that this report
    does not name", burning a model round trip toward the brake.
    """
    p = ScriptedPoller(snap([a_run()]), [snap([a_run(cost=99.99)])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_an_unrelated_run_closing_does_not_end_a_scoped_follow():
    """`closed` was the one part of the projection left unscoped, so any
    other run finishing -- or ageing out of CLOSED_LIMIT -- ended the wait
    with an empty change list."""
    before = snap([a_run("r1")])
    after = snap([a_run("r1")])
    after.closed = [_a_summary("r2")]
    p = ScriptedPoller(before, [after])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.timed_out is True


@pytest.mark.asyncio
async def test_every_reported_change_can_be_named():
    """No return should ever carry the 'cannot name it' fallback."""
    p = ScriptedPoller(snap([a_run(stage="dev")]), [snap([a_run(stage="qa")])])
    got = await tools.follow(deps_for(p), run_id="r1", timeout_s=5)
    assert got.changed
    assert "does not name" not in got.detail
