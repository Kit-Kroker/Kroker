"""SC-006 (T027): a run started on the OLD worker completes on the NEW one.

temporalio 1.31 has no history-injection API, so the mixed prefix is proven
as two halves over the frozen architect_research_tool recording
(T005, pre-migration main):

1. DETERMINISM: the truncated prefix -- the old history cut at a
   workflow-task boundary right after the last architect command -- replays
   under the NEW workflow code without a replay failure.
2. COINCIDENCE + COMPLETION: the same scenario run LIVE under the new
   capability mechanism projects the SAME first K commands (K = the cut),
   so the live run's prefix coincides with the old recording and
   replay-of-prefix + continuation is equivalent to this live run -- which
   completes through deploy.

The history itself is never written to (SG-2 family).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.workflows.crew import CrewTaskWorkflow
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.replay.harness import load_history
from tests.replay.projection import command_projection
from tests.replay.scenarios import SCENARIOS

HISTORY_NAME = "architect_research_tool"
QUEUE = "003-inflight-resume"


def _replayer() -> Replayer:
    return Replayer(
        workflows=[FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[SdlcPydanticAIPlugin()],
    )


def _prefix_points(hist: WorkflowHistory) -> tuple[int, int]:
    """(K, boundary) of the cut: K = projection length THROUGH the last
    architect-agent command; boundary = event index of the last
    WorkflowTaskCompleted at or before that ActivityTaskScheduled, so the
    truncated history ends exactly at a workflow-task edge."""
    proj = command_projection(hist)
    architect = [i for i, c in enumerate(proj) if c.startswith("activity:agent__architect_agent__")]
    assert architect, "the recording carries no architect commands"
    k = architect[-1] + 1

    boundary, sched_idx = 0, None
    for i, ev in enumerate(hist.events):
        if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED:
            if sched_idx is None:
                boundary = i
        elif ev.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            name = ev.activity_task_scheduled_event_attributes.activity_type.name
            if name.startswith("agent__architect_agent__"):
                sched_idx = i
    return k, boundary


def _truncated_prefix() -> tuple[WorkflowHistory, int]:
    hist = load_history(HISTORY_NAME)
    k, boundary = _prefix_points(hist)
    return WorkflowHistory(hist.workflow_id, list(hist.events[: boundary + 1])), k


@pytest.mark.asyncio
async def test_old_prefix_replays_on_new_code():
    """The NEW workflow code deterministically reproduces the old-recorded
    prefix: replaying the truncated history raises no replay failure."""
    truncated, _ = _truncated_prefix()
    result = await _replayer().replay_workflow(truncated, raise_on_replay_failure=True)
    assert result.replay_failure is None


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_live_continuation_prefix_matches_and_completes(tmp_path: Path, monkeypatch):
    """The scenario run LIVE on the migrated tree starts with the SAME K
    commands as the old recording (the prefix coincides, so this run IS the
    continuation of that recording) and completes through deploy."""
    _, k = _truncated_prefix()
    captured = command_projection(load_history(HISTORY_NAME))

    scenario = next(s for s in SCENARIOS if s.name == HISTORY_NAME)
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    scenario.before()

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=QUEUE,
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=scenario.activities(),
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            with env.auto_time_skipping_disabled():
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[scenario.idea(), scenario.cfg(), scenario.seeded()],
                    id=f"003-inflight-{uuid.uuid4()}",
                    task_queue=QUEUE,
                )
                driver = asyncio.create_task(scenario.drive(handle, env))
                result = await handle.result()
                await driver
            live = await handle.fetch_history()

    assert result.startswith("deployed:")
    assert command_projection(live)[:k] == captured[:k]
