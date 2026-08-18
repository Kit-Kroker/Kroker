"""E-10 e2e: run_state() answers against a real workflow, and fetch_fleet
aggregates it through a real client. The one part no fake can prove.

Deliberately narrow. run() stashes _idea and _started_at before its first
activity, so the query is answerable from the first completed workflow task
-- no activity fakes are needed and none are registered. Driving a full
pipeline is test_e2e_greenfield.py's job, not this test's.

Marked temporal: each such test spawns its own dev-server subprocess
(pyproject's addopts excludes them from the default run)."""
from datetime import datetime, timezone

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.dashboard.fleet import fetch_fleet
from sdlc.models import IdeaBrief, PipelineConfig, ProjectMode, RunState
from sdlc.workflows.feature import FeatureWorkflow

pytestmark = pytest.mark.temporal


@pytest.mark.asyncio
async def test_run_state_answers_on_a_live_run():
    from temporalio.contrib.pydantic import pydantic_data_converter

    # start_local, not start_time_skipping: fetch_fleet lists workflows, and
    # the time-skipping test service does not implement ListWorkflowExecutions
    # (UNIMPLEMENTED on temporalio 1.31). The dev-server subprocess this
    # env actually spawns serves the full visibility API.
    async with await WorkflowEnvironment.start_local(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue="dash-e2e",
                          workflows=[FeatureWorkflow], activities=[]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[IdeaBrief(title="Add SSO", description="d",
                                mode=ProjectMode.GREENFIELD),
                      PipelineConfig(), None],
                id="feature-add-sso", task_queue="dash-e2e")
            try:
                state = await handle.query("run_state", result_type=RunState)
                assert state is not None
                assert state.title == "Add SSO"
                assert state.run_id == "feature-add-sso"
                # Nothing has been priced yet, and None must not become 0.0.
                assert state.cost_usd_total is None
                # STAGE_STARTED is emitted before the first activity, so
                # the very first workflow task answers with the stage set.
                assert state.current_stage == "intake"

                snap = await fetch_fleet(
                    env.client, now=datetime.now(timezone.utc))
                assert "feature-add-sso" in {r.run_id for r in snap.runs}
            finally:
                await handle.cancel()
