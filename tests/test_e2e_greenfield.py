"""P1 end-to-end proof (orchestration-level, offline, deterministic).

Runs the REAL FeatureWorkflow on a time-skipping worker with faked model +
activity seams, drives it through every gate via signals, and asserts it
reaches `deployed:`."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate  # pure — reused, not faked
from sdlc.gate import CheckClass
from sdlc.models import GateDecision, GateOutcome
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "e2e"


async def _wait_for_status(handle, target: str, timeout_s: float = 10.0):
    """Poll pending_gate() until it reports `target` (e.g. 'awaiting:plan')."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        gate = await handle.query(FeatureWorkflow.pending_gate)
        if gate == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for status {target!r}")


async def _drive(handle):
    # 1. clarify — answer the one open question
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question,
                            args=[qid, "yes"])
    # 2. architecture, plan, deploy gates — approve each (merge auto-passes
    #    clean, so it never enters awaiting:merge).
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=gate, round=1, outcome=GateOutcome.APPROVE,
                         decided_by="human"))


@pytest.mark.asyncio
async def test_greenfield_run_ships_end_to_end():
    activities = [evaluate_gate, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        # Each architecture/plan/deploy gate opens a real (48h) durable
        # timer via workflow.wait_condition(..., timeout=...). The
        # time-skipping test server auto-advances its clock to the next
        # timer the instant the client goes idle, which can race ahead of
        # our signal delivery over the wire and fire a timeout->REJECT
        # before the driver's `await handle.signal(...)` lands — especially
        # under load (e.g. running alongside the rest of the suite).
        # Disabling auto time-skipping for the whole run (entered before the
        # workflow even starts, so there's no window for the race) keeps the
        # clock still; every gate in this test is serviced explicitly by
        # `_drive`, so no real timeout is ever supposed to fire.
        with env.auto_time_skipping_disabled():
            async with Worker(
                    env.client, task_queue=TASK_QUEUE,
                    workflows=[FeatureWorkflow], activities=activities,
                    plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"e2e-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver

    assert result.startswith("deployed:"), result
