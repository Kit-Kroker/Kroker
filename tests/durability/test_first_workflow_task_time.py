"""FR-020(d) (T031): the first workflow task stays under the deadlock
detector on the REAL registry, sandboxed, with the mitigated runner.

R9: capability-bound agents made the first workflow task trip TMPRL1101
(2 s) in a cold worker; the sanctioned mitigation is SdlcPydanticAIPlugin
(`sdlc.agents` passthrough + host-side provider warm-up) — the worker here
runs the SANDBOXED runner through that plugin, no UnsandboxedWorkflowRunner,
because the sandbox path is the thing being measured.

Temporal tier: spawns an ephemeral dev server.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.workflows.deployment import DeploymentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from tests.replay.scenarios import SCENARIOS

QUEUE = "003-first-task-time"
_DEADLOCK_THRESHOLD_S = 2.0
_MARGIN_S = 0.5  # assert below 1.5 s: the 2 s TMPRL1101 budget with margin


def _failure_messages(history) -> list[str]:
    out: list[str] = []
    for ev in history.events:
        if ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED:
            failure = ev.workflow_task_failed_event_attributes.failure
            if failure and failure.message:
                out.append(failure.message)
        elif ev.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            failure = ev.workflow_execution_failed_event_attributes.failure
            if failure and failure.message:
                out.append(failure.message)
    return out


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_first_workflow_task_completes_under_the_deadlock_threshold(tmp_path, monkeypatch):
    """Wall-clock from start_workflow to the FIRST WorkflowTaskCompleted on
    the real (import-time-built) registry must stay under 1.5 s, and no
    workflow task may fail with TMPRL1101 before the run is torn down. The
    measured value travels in the assert message for the FR-020(d) record."""
    scenario = next(s for s in SCENARIOS if s.name == "greenfield_happy")
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    scenario.before()

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        # Deliberately NO workflow_runner override: the sandboxed runner via
        # the mitigated plugin IS the production-shaped path under test.
        async with Worker(
            env.client,
            task_queue=QUEUE,
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=scenario.activities(),
            plugins=[SdlcPydanticAIPlugin()],
        ):
            with env.auto_time_skipping_disabled():
                start = time.perf_counter()
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[scenario.idea(), scenario.cfg(), scenario.seeded()],
                    id=f"003-first-task-{uuid.uuid4()}",
                    task_queue=QUEUE,
                )
                first_task_at: float | None = None
                while time.perf_counter() - start < 30.0:
                    history = await handle.fetch_history()
                    if any(
                        ev.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_COMPLETED
                        for ev in history.events
                    ):
                        first_task_at = time.perf_counter()
                        break
                    await asyncio.sleep(0.01)

                assert first_task_at is not None, (
                    "no WorkflowTaskCompleted within 30s — the cold-worker "
                    "deadlock family (TMPRL1101) reproduced"
                )
                elapsed = first_task_at - start
                messages = _failure_messages(await handle.fetch_history())
                await handle.terminate("003 first-task timing done")

    assert elapsed < _DEADLOCK_THRESHOLD_S - _MARGIN_S, (
        f"first workflow task took {elapsed:.3f}s — over the "
        f"{_DEADLOCK_THRESHOLD_S - _MARGIN_S}s budget (2s TMPRL1101 "
        f"threshold minus margin); FR-020(d) hazard reproduced"
    )
    assert not any("TMPRL1101" in m for m in messages), (
        f"workflow task failed with the deadlock detector before teardown: {messages}"
    )
