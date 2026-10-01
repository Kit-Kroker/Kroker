"""U2 proof: FeatureWorkflow replays every history captured from pre-change code.

Stop-guard SG-2: red after a src/ change means that change altered
FeatureWorkflow's command sequence. Never re-record a history to turn this
green (U6 grace-edit rule, workflows/AGENTS.md).
"""

from __future__ import annotations

import pytest
from pydantic import PydanticUserError
from pydantic_ai.exceptions import AgentRunError, UserError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Replayer
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.workflows.assessment import AssessmentWorkflow
from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.triage import TriageWorkflow
from tests.replay.harness import load_history
from tests.replay.scenarios import ASSESSMENT_SCENARIOS, SCENARIOS


def replayer(*workflows: type) -> Replayer:
    return Replayer(
        workflows=list(workflows) or [FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[SdlcPydanticAIPlugin()],
    )


def test_replayer_matches_the_production_worker_effect():
    config = replayer().config(active_config=True)
    runner = config["workflow_runner"]
    assert isinstance(runner, SandboxedWorkflowRunner)
    assert "pydantic_ai" in runner.restrictions.passthrough_modules
    assert {UserError, PydanticUserError, AgentRunError} <= set(
        config["workflow_failure_exception_types"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_feature_workflow_replays_captured_history(scenario):
    result = await replayer().replay_workflow(
        load_history(scenario.name), raise_on_replay_failure=True
    )
    assert result.replay_failure is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ASSESSMENT_SCENARIOS, ids=[s.name for s in ASSESSMENT_SCENARIOS]
)
async def test_assessment_workflow_replays_captured_history(scenario):
    """003 T007: the assessment capture (discover + risk proposer activities)
    replays through the migrated capability path; the gate's workflow pair is
    replayed together, mirroring what the worker hosts."""
    result = await replayer(AssessmentWorkflow, TriageWorkflow).replay_workflow(
        load_history(scenario.name), raise_on_replay_failure=True
    )
    assert result.replay_failure is None
