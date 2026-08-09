"""E-9 Task 1: per-gate timeout semantics. Only `merge` changes default
behaviour; every other gate keeps today's reject.

E-9 Task 8 (appended): the workflow honours on_timeout -- REJECT stays reject,
HOLD keeps the gate pending past its nominal deadline."""
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
from sdlc.models import (
    GateConfig, GateDecision, GateOutcome, GatePolicy, PipelineConfig,
    TimeoutAction,
)
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities


def test_default_on_timeout_is_reject():
    """Preserves today's behaviour for any gate that does not opt out."""
    assert GateConfig().on_timeout is TimeoutAction.REJECT


def test_timer_overrides_default_to_none():
    cfg = GateConfig()
    assert cfg.remind_after_hours is None
    assert cfg.escalate_after_hours is None


def test_merge_defaults_to_hold_every_other_gate_rejects():
    gates = PipelineConfig().gates
    assert gates["merge"].on_timeout is TimeoutAction.HOLD
    for name in ("clarify", "architecture", "plan", "deploy"):
        assert gates[name].on_timeout is TimeoutAction.REJECT, name


def test_bare_policy_string_still_coerces():
    """GateConfig._coerce is unchanged: existing configs keep parsing and
    keep today's timeout behaviour."""
    cfg = PipelineConfig(gates={"architecture": "hard"})
    assert cfg.gates["architecture"].policy is GatePolicy.HARD
    assert cfg.gates["architecture"].on_timeout is TimeoutAction.REJECT


def test_overrides_round_trip_through_dict_coercion():
    cfg = PipelineConfig(gates={
        "merge": {"policy": "hard", "on_timeout": "approve",
                  "remind_after_hours": 4, "escalate_after_hours": 8},
    })
    g = cfg.gates["merge"]
    assert g.on_timeout is TimeoutAction.APPROVE
    assert (g.remind_after_hours, g.escalate_after_hours) == (4, 8)


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_architecture_gate_timeout_still_rejects(tmp_path, monkeypatch):
    """Today's behaviour, preserved. Time-skipping runs the 48h in ms."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue="timeout",
                          workflows=[FeatureWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      *GIT_FAKES,
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg, None],
                id=f"timeout-{uuid.uuid4()}", task_queue="timeout")
            with env.auto_time_skipping_disabled():
                await _wait_for_status(handle, "awaiting:clarify")
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question,
                                        args=[qid, "yes"])
                await _wait_for_status(handle, "awaiting:architecture")
            result = await handle.result()
    assert "architecture" in result and result.startswith("rejected:"), result


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_hold_keeps_the_gate_pending_past_its_nominal_deadline(
        tmp_path, monkeypatch):
    """A HOLD gate outlives gate_timeout_hours and stays decidable."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gate_timeout_hours = 1
    cfg.gates["architecture"] = GateConfig(policy=GatePolicy.HARD,
                                           on_timeout=TimeoutAction.HOLD)
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue="hold",
                          workflows=[FeatureWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      *GIT_FAKES,
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg, None],
                id=f"hold-{uuid.uuid4()}", task_queue="hold")
            with env.auto_time_skipping_disabled():
                await _wait_for_status(handle, "awaiting:clarify")
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question,
                                        args=[qid, "yes"])
                await _wait_for_status(handle, "awaiting:architecture")
            await env.sleep(7200)      # 2h -- twice the nominal timeout
            assert await handle.query(
                FeatureWorkflow.pending_gate) == "awaiting:architecture"
            pending = await handle.query(FeatureWorkflow.pending_decisions)
            assert any(p.gate == "architecture" for p in pending)
            await handle.signal(
                FeatureWorkflow.submit_gate_decision,
                GateDecision(gate="architecture", round=1,
                             outcome=GateOutcome.REJECT,
                             decided_by="human"))
            result = await handle.result()
    assert result.startswith("rejected:"), result
