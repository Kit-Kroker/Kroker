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
from sdlc.artifacts.retention import RetentionInput
from sdlc.observability.activities import RunExportInput, export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES, git_fakes_except
from tests.fakes.fake_deploy import DEPLOY_FAKES, reset as reset_deploy

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = pytest.mark.temporal

TASK_QUEUE = "retro"

from temporalio import activity as _activity


@_activity.defn(name="export_run_artifacts")
async def _boom_export(inp: RunExportInput) -> str:  # same name, always fails
    raise RuntimeError("disk full")


# E-38: records the retention activity's input so a test can assert the
# workflow invoked it and with what policy. Reset per-test via del [...].
_RECORDED_RETENTION: list[RetentionInput] = []


@_activity.defn(name="apply_session_retention")
async def _record_retention(inp: RetentionInput) -> str:
    _RECORDED_RETENTION.append(inp)
    return "kept:0"


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
    reset_deploy()
    cfg = e2e_config()
    cfg.deploy.enabled = True
    activities = [evaluate_gate, export_run_artifacts, *GIT_FAKES,
                  *DEPLOY_FAKES, *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow, DeploymentWorkflow],
                              activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
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


async def _drive_reject_arch(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    await _wait_for_status(handle, "awaiting:architecture")
    await handle.signal(FeatureWorkflow.submit_gate_decision,
                        GateDecision(gate="architecture", round=1,
                                     outcome=GateOutcome.REJECT,
                                     decided_by="human"))


@pytest.mark.asyncio
async def test_retro_fires_on_rejected_path(tmp_path, monkeypatch):
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
                    args=[greenfield_idea(), e2e_config(), None],
                    id=f"retro-rej-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive_reject_arch(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result == "rejected:architecture", result
    assert summary is not None and summary.outcome == result
    assert summary.terminal_stage in ("clarify", "architecture")


@pytest.mark.asyncio
async def test_export_failure_does_not_change_outcome(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    reset_deploy()
    cfg = e2e_config()
    cfg.deploy.enabled = True
    activities = [evaluate_gate, _boom_export, *GIT_FAKES, *DEPLOY_FAKES,
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow, DeploymentWorkflow],
                              activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"retro-boom-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result   # export failed, run didn't
    assert summary is not None                       # summary still built


@pytest.mark.asyncio
async def test_retention_invoked_keep_full_on_rejected_path(tmp_path, monkeypatch):
    """E-38: the retro stage invokes apply_session_retention on a terminal
    path, and a non-deployed outcome keeps full transcripts (OQ-B7). Mirrors
    the export_run_artifacts fake-activity idiom used above."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    del _RECORDED_RETENTION[:]
    # _record_retention REPLACES the GIT_FAKES no-op: this test asserts on
    # what apply_session_retention received, so the recorder must be the one
    # that runs -- and registering both is a Worker construction error.
    activities = [evaluate_gate, export_run_artifacts, _record_retention,
                  *git_fakes_except("apply_session_retention"),
                  *fake_agent_activities(AGENT_SPECS)]
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow], activities=activities,
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), e2e_config(), None],
                    id=f"retro-ret-{uuid.uuid4()}", task_queue=TASK_QUEUE)
                driver = asyncio.create_task(_drive_reject_arch(handle))
                await handle.result()
                await driver
    assert _RECORDED_RETENTION, "apply_session_retention was not invoked"
    assert _RECORDED_RETENTION[-1].keep_full is True
