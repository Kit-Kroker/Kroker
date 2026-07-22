"""E-32 retro stage: fires on every terminal path, populates run_summary(),
and never lets an export failure change the run's outcome."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "retro"


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _drive(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    for gate in ("architecture", "plan", "deploy"):
        await _wait_for_status(handle, f"awaiting:{gate}")
        await handle.signal(FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))


@pytest.mark.asyncio
async def test_retro_populates_run_summary_on_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    activities = [evaluate_gate, export_run_artifacts, *GIT_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow], activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config()],
                    id=f"retro-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result
    assert summary is not None
    assert summary.outcome == result
    assert summary.terminal_stage == "deploy"
    assert any(c.answered_by == "human" for c in summary.clarifications)
    assert any(g.gate == "architecture" for g in summary.gates)
    # export wrote the files
    run_dirs = list(tmp_path.iterdir())
    assert run_dirs and (run_dirs[0] / "report.html").exists()
