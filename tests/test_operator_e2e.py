"""E-86 e2e: the verbs answer against a real workflow through a real poller.

The part no fake can prove for this module is that OperatorDeps' collaborators
are the real ones -- FleetPoller fanning out over a live client, and _handle
resolving a real workflow handle. Signal TRANSLATION is pinned by
tests/test_operator_writes.py and by transport's own suite; driving
FeatureWorkflow to a pending gate would need the full activity fake set, which
is test_e2e_greenfield.py's job and not this test's.

Marked temporal: each such test spawns its own dev-server subprocess
(pyproject's addopts excludes them from the default run).
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.dashboard.fleet import FleetPoller
from sdlc.models import IdeaBrief, MemoryConfig, PipelineConfig, ProjectMode
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.workflows.feature import FeatureWorkflow

pytestmark = pytest.mark.temporal


@pytest.mark.asyncio
async def test_verbs_answer_against_a_live_run():
    from temporalio.contrib.pydantic import pydantic_data_converter

    async with await WorkflowEnvironment.start_local(data_converter=pydantic_data_converter) as env:
        async with Worker(
            env.client, task_queue="chat-e2e", workflows=[FeatureWorkflow], activities=[]
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[
                    IdeaBrief(title="Add SSO", description="d", mode=ProjectMode.GREENFIELD),
                    PipelineConfig(memory=MemoryConfig(enabled=False)),
                    None,
                ],
                id="feature-add-sso",
                task_queue="chat-e2e",
            )
            # Wait for the first workflow task to complete so stage is initialized to intake
            await handle.query("run_state")
            poller = FleetPoller(lambda: env.client)
            deps = OperatorDeps(poller=poller, board=None, starter=None, actor="chat:test")

            try:
                listed = await tools.list_runs(deps)
                assert "feature-add-sso" in listed

                detail = await tools.get_run(deps, "feature-add-sso")
                assert "Add SSO" in detail
                assert "intake" in detail
                # None must not become 0.00: nothing has been priced yet.
                assert "cost unknown" in detail

                # _handle reaches a real workflow handle through the poller's
                # client -- the path every write verb takes before signalling.
                live = await tools._handle(deps, "feature-add-sso")
                assert live.id == "feature-add-sso"

                # Nothing is pending on a run parked at intake, so a scoped
                # wait must time out rather than report a phantom change.
                report = await tools.follow(deps, run_id="feature-add-sso", timeout_s=5)
                assert report.timed_out is True
            finally:
                await poller.aclose()
                await handle.cancel()
