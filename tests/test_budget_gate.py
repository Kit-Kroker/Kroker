"""E-33: the run-budget gate — crossings re-gate per increment, approve
extends, reject terminates with retro intact, default-off changes nothing
(the whole existing suite is that last proof)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.activities import evaluate_gate
from sdlc.core.models import (
    GateDecision,
    GateOutcome,
)
from sdlc.observability.activities import export_run_artifacts
from sdlc.pricing import PriceUsageInput
from sdlc.pricing import price_usage as real_price_usage
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

TASK_QUEUE = "budget"


@activity.defn(name="price_usage")
async def fixed_price(inp: PriceUsageInput) -> float | None:
    return 1.0  # every proposer call costs exactly $1


def _activities():
    fakes = [a for a in GIT_FAKES if a is not real_price_usage]
    return [
        evaluate_gate,
        export_run_artifacts,
        fixed_price,
        *fakes,
        *DEPLOY_FAKES,
        *fake_agent_activities(AGENT_SPECS),
    ]


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _run_workflow_with_driver(handle, drive_coro):
    driver = asyncio.create_task(drive_coro)
    wf_task = asyncio.ensure_future(handle.result())
    done, pending = await asyncio.wait(
        [driver, wf_task],
        return_when=asyncio.FIRST_EXCEPTION,
    )
    for t in done:
        if t.exception() is not None:
            for p in pending:
                p.cancel()
            raise t.exception()
    result = await wf_task
    await driver
    return result


async def _signal_gate(handle, gate, round, outcome):
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate=gate, round=round, outcome=outcome, decided_by="human"),
    )


@pytest.mark.asyncio
async def test_budget_crossings_regate_and_approve_extends(tmp_path, monkeypatch):
    """budget=$1.50, $1/call. Happy-path metered calls in order: clarify,
    architect, planner, qa, reviewer, analyst (merge_verdict skipped —
    merge gate is HARD not SOFT; fake dev harness carries no dollars).
    Crossings: $2>=1.5 (r1, after architecture), $3>=3.0 (r2, after plan),
    $5>=4.5 (r3, task loop), $6>=6.0 (r4, after analyst)."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.run_budget_usd = 1.5
    cfg.deploy.enabled = True
    reset_deploy()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=_activities(),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"budget-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
                    await _wait_for_status(handle, "awaiting:architecture")
                    await _signal_gate(handle, "architecture", 1, GateOutcome.APPROVE)
                    for rnd in (1, 2):
                        await _wait_for_status(handle, "awaiting:budget")
                        await _signal_gate(handle, "budget", rnd, GateOutcome.APPROVE)
                        if rnd == 1:
                            await _wait_for_status(handle, "awaiting:plan")
                            await _signal_gate(handle, "plan", 1, GateOutcome.APPROVE)
                    for rnd in (3, 4):
                        await _wait_for_status(handle, "awaiting:budget")
                        await _signal_gate(handle, "budget", rnd, GateOutcome.APPROVE)
                    await _wait_for_status(handle, "awaiting:deploy")
                    await _signal_gate(handle, "deploy", 1, GateOutcome.APPROVE)

                result = await _run_workflow_with_driver(handle, drive())
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result.startswith("deployed:"), result
    budget_gates = [g for g in summary.gates if g.gate == "budget"]
    assert {g.round for g in budget_gates} == {1, 2, 3, 4}
    assert all(g.approved for g in budget_gates)


@pytest.mark.asyncio
async def test_budget_reject_terminates_with_retro(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.run_budget_usd = 0.5  # first metered call ($1, clarify) crosses
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow],
                activities=_activities(),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"budget-rej-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
                    await _wait_for_status(handle, "awaiting:budget")
                    await _signal_gate(handle, "budget", 1, GateOutcome.REJECT)

                result = await _run_workflow_with_driver(handle, drive())
                summary = await handle.query(FeatureWorkflow.run_summary)
    assert result == "rejected:budget", result
    assert summary is not None  # retro ran on the budget path
    assert summary.outcome == "rejected:budget"
