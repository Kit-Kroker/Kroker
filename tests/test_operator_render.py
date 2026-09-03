"""Compact ASCII rendering; the agent never sees a raw model dump."""

from datetime import UTC, datetime

from sdlc.channels.inbox import RunInbox
from sdlc.core.models import (
    RunState,
)
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.operator import render
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
GATE = StageGatePending(
    key="architecture#2", gate="architecture", round=2, spec_summary="two services, one queue"
)
Q1 = ClarifyPending(key="Q1", question="Which auth provider?", why_it_matters="drives the schema")


def a_run(run_id="feature-add-sso", **kw):
    base = dict(
        run_id=run_id,
        title="Add SSO",
        mode="brownfield",
        status="awaiting:architecture",
        started_at=AT,
        current_stage="architecture",
        cost_usd_total=4.12,
    )
    base.update(kw)
    return RunState(**base)


def test_run_line_is_ascii_only():
    line = render.run_line(a_run(), [GATE])
    assert line.isascii(), line


def test_run_line_names_run_stage_status_pending_and_cost():
    line = render.run_line(a_run(), [GATE])
    assert "feature-add-sso" in line
    assert "architecture" in line
    assert "awaiting:architecture" in line
    assert "round 2" in line
    assert "4.12" in line


def test_run_line_without_pending_says_so():
    assert "none" in render.run_line(a_run(), []).lower()


def test_missing_cost_is_not_reported_as_free():
    line = render.run_line(a_run(cost_usd_total=None), [])
    assert "0.00" not in line
    assert "unknown" in line.lower()


def test_pending_block_carries_key_title_and_reply_kind():
    block = render.pending_block(GATE)
    assert "architecture#2" in block
    assert "Gate: architecture (round 2)" in block
    assert "gate" in block


def test_pending_block_for_a_question_offers_the_suggestion_slot():
    assert "text" in render.pending_block(Q1)


def test_orientation_lists_one_line_per_open_run():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=2,
        runs=[a_run("r1"), a_run("r2")],
        inbox=[RunInbox(run_id="r1", pending=[GATE])],
    )
    out = render.orientation(snap)
    assert out.count("\n") >= 1
    assert "r1" in out and "r2" in out
    assert "round 2" in out  # r1's pending item is attached


def test_orientation_degrades_to_a_count_past_the_cap():
    snap = FleetSnapshot(at=AT, total_open_runs=30, runs=[a_run(f"r{i}") for i in range(30)])
    out = render.orientation(snap, cap=20)
    assert "30 open runs" in out
    assert "r29" not in out


def test_orientation_with_no_open_runs_says_so():
    assert "no open runs" in render.orientation(FleetSnapshot(at=AT)).lower()


def test_runs_view_open_excludes_closed_runs():
    snap = FleetSnapshot(at=AT, total_open_runs=1, runs=[a_run("r1")])
    assert "r1" in render.runs_view(snap, "open")


def test_inbox_view_groups_by_run():
    snap = FleetSnapshot(
        at=AT,
        total_open_runs=1,
        runs=[a_run("r1")],
        inbox=[RunInbox(run_id="r1", pending=[GATE, Q1])],
    )
    out = render.inbox_view(snap)
    assert "r1" in out
    assert "architecture#2" in out and "Q1" in out


def test_inbox_view_empty_is_explicit_about_having_checked():
    snap = FleetSnapshot(at=AT, total_open_runs=3, runs=[a_run("r1")])
    out = render.inbox_view(snap)
    assert "3" in out
    assert "nothing pending" in out.lower()
