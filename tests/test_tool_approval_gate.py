"""E-17: a deferred tool call raises a real gate, the decision reaches the
resumed session as a grant, and escalating costs neither a fix attempt nor a
session resume."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
)
from sdlc.harness.models import (
    ContainmentLayer,
    DeferredToolUse,
    HarnessRunResult,
    ToolDenial,
)
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.stages.code.activities import CodingTaskInput
from sdlc.stages.merge.activities import evaluate_gate
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES, fake_run_coding_task
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = pytest.mark.temporal

TASK_QUEUE = "toolapproval"

SEEN: list[CodingTaskInput] = []


def _deferral() -> DeferredToolUse:
    return DeferredToolUse(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        reason="Writes are scoped to the task worktree.",
        target="/etc/passwd",
    )


@activity.defn(name="run_coding_task")
async def defer_once(inp: CodingTaskInput) -> HarnessRunResult:
    """First call suspends at a tool call; the resumed call succeeds."""
    SEEN.append(inp)
    base = dict(
        harness=inp.harness,
        session_id="s1",
        exit_code=0,
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )
    if len(SEEN) == 1:
        # summary is "" and there is no commit: the run ENDED at the tool
        # call, exactly as `stop_reason: tool_deferred` reports it.
        return HarnessRunResult(summary="", deferred=_deferral(), **base)
    return HarnessRunResult(summary="implemented", commit_sha="cafe1234", **base)


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    return Results()


def _activities(coding):
    """Swap the canned harness fake for one that defers. Identity filtering,
    matching how test_budget_gate.py swaps price_usage."""
    fakes = [a for a in GIT_FAKES if a is not fake_run_coding_task]
    return [
        evaluate_gate,
        export_run_artifacts,
        coding,
        _noop_notify,
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


async def _drive_to_tasks(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    await _wait_for_status(handle, "awaiting:architecture")
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )
    await _wait_for_status(handle, "awaiting:plan")
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate="plan", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )


@pytest.mark.asyncio
async def test_deferral_raises_a_gate_and_the_grant_reaches_the_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    SEEN.clear()
    cfg = e2e_config()
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
                activities=_activities(defer_once),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"esc-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                            comments="fine, that path is mine",
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                result = await _run_workflow_with_driver(handle, drive())
                summary = await handle.query(FeatureWorkflow.run_summary)

    assert result.startswith("deployed:"), result
    # The gate was real, and used the stable configurable name.
    gates = [g for g in summary.gates if g.gate == "tool_approval"]
    assert len(gates) == 1 and gates[0].round == 1 and gates[0].approved
    # The decision reached the resumed session as a grant, on the SAME session.
    assert len(SEEN) == 2
    assert SEEN[0].grants == []
    assert len(SEEN[1].grants) == 1
    grant = SEEN[1].grants[0]
    assert grant.tool_use_id == "toolu_1"
    assert grant.approved is True
    assert grant.reason == "fine, that path is mine"
    assert SEEN[1].session_id == "s1"
    # Escalating is not failing: one attempt, no extra fix attempt recorded.
    assert SEEN[1].attempt == 1


@pytest.mark.asyncio
async def test_rejection_is_delivered_and_the_task_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    SEEN.clear()
    cfg = e2e_config()
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
                activities=_activities(defer_once),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"esc-rej-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.REJECT,
                            decided_by="human",
                            comments="write inside the worktree",
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                result = await _run_workflow_with_driver(handle, drive())

    # A refusal must be DELIVERED to the harness, not merely recorded.
    assert result.startswith("deployed:"), result
    assert len(SEEN) == 2
    grant = SEEN[1].grants[0]
    assert grant.approved is False
    assert grant.reason == "write inside the worktree"


@pytest.mark.asyncio
async def test_the_cap_stops_asking_and_the_loop_terminates(tmp_path, monkeypatch):
    """An agent that defers forever must not spam a human or hang the run."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    calls: list[CodingTaskInput] = []

    @activity.defn(name="run_coding_task")
    async def always_defer(inp: CodingTaskInput) -> HarnessRunResult:
        calls.append(inp)
        return HarnessRunResult(
            harness=inp.harness,
            session_id="s1",
            exit_code=0,
            summary="",
            input_tokens=10,
            output_tokens=2,
            context_window=200000,
            deferred=_deferral(),
        )

    cfg = e2e_config()
    cfg.max_tool_escalations = 1
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow],
                activities=_activities(always_defer),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, None],
                    id=f"esc-cap-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                        ),
                    )
                    # No second gate is ever raised: the cap refuses instead,
                    # so the next status to appear is the merge gate. (The
                    # fake QA passes, so the task never reaches escalation.)
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                await _run_workflow_with_driver(handle, drive())
                summary = await handle.query(FeatureWorkflow.run_summary)

    # Exactly one gate raised, then a refusal delivered, then no more
    # approval resumes — bounded regardless of how the harness behaves.
    assert len([g for g in summary.gates if g.gate == "tool_approval"]) == 1
    capped = [c for c in calls if c.grants and not c.grants[0].approved]
    assert len(capped) >= 1
    assert capped[0].grants[0].reason == "escalation cap reached"


def test_declined_denials_become_batched_escalation_records():
    """A denial the hook could not escalate must be countable (§6)."""
    from sdlc.workflows.task_host import escalations_from_denials

    denials = [
        ToolDenial(
            tool="Write",
            rule_id="r",
            layer=ContainmentLayer.HOOK,
            reason="escalation unavailable (batched): scoped",
            target="/etc/passwd",
            escalation_declined=True,
        ),
        ToolDenial(
            tool="Bash",
            rule_id="d",
            layer=ContainmentLayer.HOOK,
            reason="Destructive.",
            target="rm -rf /",
        ),
    ]
    out = escalations_from_denials(denials)
    assert len(out) == 1
    assert out[0].outcome.value == "batched"
    assert out[0].decided_by == ""
    assert out[0].round == 0
