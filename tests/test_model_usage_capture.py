"""E-33: every proposer call and every harness attempt emits a MODEL_USAGE
event, visible in the exported events.jsonl."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.activities import evaluate_gate
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
)
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = pytest.mark.temporal

TASK_QUEUE = "usage"


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
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=gate, round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
        )


@pytest.mark.asyncio
async def test_model_usage_events_exported(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    reset_deploy()
    cfg = e2e_config()
    cfg.deploy.enabled = True
    activities = [
        evaluate_gate,
        export_run_artifacts,
        *GIT_FAKES,
        *DEPLOY_FAKES,
        *fake_agent_activities(AGENT_SPECS),
    ]
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=activities,
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"usage-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
                driver = asyncio.create_task(_drive(handle))
                result = await handle.result()
                await driver
    assert result.startswith("deployed:"), result
    run_dir = next(tmp_path.iterdir())
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    usage = [e for e in events if e["kind"] == "model_usage"]
    roles = {e["data"]["role"] for e in usage}
    # every proposer the happy path exercises, plus the harness join
    assert {"clarify", "architect", "planner", "qa", "reviewer", "analyst", "dev"} <= roles, roles
    for e in usage:
        assert e["data"]["calls"] == "1"
        int(e["data"]["input_tokens"])  # stringified ints parse
        int(e["data"]["output_tokens"])
    dev = next(e for e in usage if e["data"]["role"] == "dev")
    # fake_run_coding_task reports 1000/200
    assert dev["data"]["input_tokens"] == "1000"
    assert dev["data"]["output_tokens"] == "200"
