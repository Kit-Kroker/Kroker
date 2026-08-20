"""Live-run read verbs over a fake poller. No Temporal, no server, no model."""
from datetime import datetime, timezone

import pytest

from sdlc.channels.inbox import RunInbox
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
GATE = StageGatePending(key="architecture#2", gate="architecture", round=2,
                        spec_summary="two services")
Q1 = ClarifyPending(key="Q1", question="Which auth provider?",
                    why_it_matters="drives the schema")


class FakePoller:
    def __init__(self, snap):
        self.snap = snap

    async def snapshot(self):
        return self.snap


def a_run(run_id="feature-add-sso"):
    return RunState(run_id=run_id, title="Add SSO", mode="brownfield",
                    status="awaiting:architecture", started_at=AT,
                    current_stage="architecture", cost_usd_total=4.12)


@pytest.fixture
def deps():
    snap = FleetSnapshot(at=AT, total_open_runs=1, runs=[a_run()],
                         inbox=[RunInbox(run_id="feature-add-sso",
                                         pending=[GATE, Q1])])
    return OperatorDeps(poller=FakePoller(snap), board=None, starter=None)


@pytest.mark.asyncio
async def test_list_runs_renders_text_not_json(deps):
    out = await tools.list_runs(deps)
    assert "feature-add-sso" in out
    assert "{" not in out


@pytest.mark.asyncio
async def test_list_runs_rejects_an_unknown_status(deps):
    with pytest.raises(ToolError) as e:
        await tools.list_runs(deps, status="sideways")
    assert "open" in e.value.message and "closed" in e.value.message


@pytest.mark.asyncio
async def test_get_run_includes_every_pending_item(deps):
    out = await tools.get_run(deps, "feature-add-sso")
    assert "architecture#2" in out
    assert "Q1" in out


@pytest.mark.asyncio
async def test_get_run_unknown_id_is_a_tool_error_naming_the_id(deps):
    with pytest.raises(ToolError) as e:
        await tools.get_run(deps, "feature-nope")
    assert "feature-nope" in e.value.message


@pytest.mark.asyncio
async def test_inbox_reuses_the_snapshot(deps):
    out = await tools.inbox(deps)
    assert "architecture#2" in out


@pytest.mark.asyncio
async def test_reads_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.list_runs(deps)
    assert deps.follow_calls == 0
