"""US4 proof: GraphWorkflow replays every history re-captured from it.

020 T020 (plan T043). The twin of test_feature_replay.py's main leg, now over
the histories re-baselined from GraphWorkflow (T018). Replays through the
three workflows the production worker hosts for the graph path.

Stop-guard SG-2: red after a src/ change means that change altered
GraphWorkflow's command sequence. Never re-record a history to turn this
green (U6 grace-edit rule, workflows/AGENTS.md).
"""

from __future__ import annotations

import pytest

from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.graph import GraphWorkflow
from tests.replay.harness import load_history, replayer
from tests.replay.scenarios import SCENARIOS


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_graph_workflow_replays_captured_history(scenario):
    result = await replayer(GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow).replay_workflow(
        load_history(scenario.name), raise_on_replay_failure=True
    )
    assert result.replay_failure is None
