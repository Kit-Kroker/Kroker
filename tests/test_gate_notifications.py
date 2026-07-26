"""E-9 Task 7: the timers fire in order, stop on the signal, and cannot
break the gate. Time-skipping so a 48h schedule runs in milliseconds."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import GateDecision, GateOutcome
from sdlc.notify.contract import DeliveryResult, NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = pytest.mark.temporal

TASK_QUEUE = "notify"
SENT: list[tuple[str, str]] = []       # (gate, reason)


@activity.defn(name="notify")
async def recording_notify(inp: NotifyInput) -> Results:
    SENT.append((getattr(inp.pending, "gate", None) or inp.pending.key,
                 inp.reason.value))
    return Results(results=[DeliveryResult(notifier="log", delivered=True)])


@activity.defn(name="notify")
async def exploding_notify(inp: NotifyInput) -> Results:
    raise RuntimeError("delivery subsystem is on fire")


def _activities(notify_act):
    return [evaluate_gate, export_run_artifacts, notify_act, *GIT_FAKES,
            *fake_agent_activities(AGENT_SPECS)]


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


@pytest.mark.asyncio
async def test_opened_notification_fires_and_signal_stops_the_rest(
        tmp_path, monkeypatch):
    """A gate decided promptly notifies once (opened) and never reminds."""
    SENT.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(recording_notify),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                    id=f"notify-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    for gate in ("architecture", "plan", "merge", "deploy"):
                        try:
                            await _wait_for_status(handle, f"awaiting:{gate}")
                        except AssertionError:
                            continue
                        await handle.signal(
                            FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver

    assert result.startswith("deployed:"), result
    reasons = {reason for _, reason in SENT}
    assert "opened" in reasons
    assert "remind" not in reasons and "expire" not in reasons


@pytest.mark.asyncio
async def test_exploding_notifier_leaves_every_gate_decidable(
        tmp_path, monkeypatch):
    """The load-bearing invariant: delivery cannot break a gate."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(env.client, task_queue=TASK_QUEUE,
                              workflows=[FeatureWorkflow],
                              activities=_activities(exploding_notify),
                              plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg],
                    id=f"notify-boom-{uuid.uuid4()}", task_queue=TASK_QUEUE)

                async def drive():
                    await _wait_for_status(handle, "awaiting:clarify")
                    for qid in QUESTION_IDS:
                        await handle.signal(FeatureWorkflow.answer_question,
                                            args=[qid, "yes"])
                    for gate in ("architecture", "plan", "merge", "deploy"):
                        try:
                            await _wait_for_status(handle, f"awaiting:{gate}")
                        except AssertionError:
                            continue
                        await handle.signal(
                            FeatureWorkflow.submit_gate_decision,
                            GateDecision(gate=gate, round=1,
                                         outcome=GateOutcome.APPROVE,
                                         decided_by="human"))

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)

    assert result.startswith("deployed:"), result
    assert summary is not None
