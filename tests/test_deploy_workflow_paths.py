"""Spec section 8: the six stage-13 paths, driven through the real
FeatureWorkflow with mocked deploy activities. No Docker, no fake adapter --
the adapters themselves are never involved."""
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
from sdlc.artifacts.retention import RetentionInput
from sdlc.models import (
    GateConfig, GateDecision, GateOutcome, GatePolicy, SmokeState,
)
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_deploy import DEPLOY_FAKES, reset

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]


@activity.defn(name="apply_session_retention")
async def _noop_retention(inp: RetentionInput) -> str:
    # Retro calls this; without it the workflow blocks on the activity and the
    # run_summary query never resolves. A no-op lets retro complete so the
    # summary (built before this call) is queryable.
    return "kept:0"


async def _wait_for_status(handle, target, timeout_s=15.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


def _cfg(**deploy_over):
    """Every gate OFF so the run reaches stage 13 unattended; tests that need
    a human decision re-arm the one gate they care about."""
    cfg = e2e_config()
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF) for name in cfg.gates}
    # deploy_failed is not a default gate, and the stage passes
    # default_policy=HARD -- so it must be set OFF explicitly for the
    # unattended paths to resolve APPROVE.
    cfg.gates["deploy_failed"] = GateConfig(policy=GatePolicy.OFF)
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.deploy.enabled = True
    for k, v in deploy_over.items():
        setattr(cfg.deploy, k, v)
    return cfg


async def _run(cfg, tmp_path, monkeypatch, tag, driver=None):
    """Run the workflow and return (result, deploy_stage_outcome). The
    run_summary query is issued INSIDE the worker block -- querying after the
    worker/environment close is an RPC error (F3 behavioral read)."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=tag,
                          workflows=[FeatureWorkflow, DeploymentWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      _noop_retention,
                                      *GIT_FAKES, *DEPLOY_FAKES,
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg, None],
                id=f"{tag}-{uuid.uuid4()}", task_queue=tag)
            if driver is not None:
                with env.auto_time_skipping_disabled():
                    await driver(handle)
            result = await handle.result()
            summary = await handle.query(FeatureWorkflow.run_summary)
            deploy = [s for s in summary.stages if s.stage == "deploy"]
            outcome = deploy[-1].outcome if deploy else None
            return result, outcome


async def test_1_all_checks_pass_deploys(tmp_path, monkeypatch):
    script = reset(smoke_states=[SmokeState.PASSED])
    result, outcome = await _run(_cfg(), tmp_path, monkeypatch, "d1")
    assert result.startswith("deployed:"), result
    assert script.rollbacks == 0
    assert outcome == "pass"


async def test_2_failed_check_rolls_back_and_gates(tmp_path, monkeypatch):
    script = reset(smoke_states=[SmokeState.FAILED])
    result, outcome = await _run(_cfg(), tmp_path, monkeypatch, "d2")
    # deploy_failed resolves through default_gate_policy OFF => APPROVE
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1
    # F3 behavioral: a rolled-back deploy records FAIL, never the gate's
    # premature PASS (SC-5 / E-40).
    assert outcome == "fail"


async def test_3_errored_check_rolls_back_too(tmp_path, monkeypatch):
    """The load-bearing case (D-3). A service we could not reach must take
    the same path as one we proved broken -- most deploy tooling passes this
    silently."""
    script = reset(smoke_states=[SmokeState.ERRORED])
    result, _ = await _run(_cfg(), tmp_path, monkeypatch, "d3")
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1


async def test_4_revise_retries_with_a_second_child(tmp_path, monkeypatch):
    """Attempt 1 fails smoke, the human says retry, attempt 2 passes."""
    script = reset(smoke_states=[SmokeState.FAILED, SmokeState.PASSED])
    cfg = _cfg()
    cfg.gates["deploy_failed"] = GateConfig(policy=GatePolicy.HARD)
    cfg.max_gate_rounds = 2

    async def driver(handle):
        await _wait_for_status(handle, "awaiting:deploy_failed")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate="deploy_failed", round=1,
                         outcome=GateOutcome.REVISE, decided_by="human",
                         guidance="retry it"))

    result, _ = await _run(cfg, tmp_path, monkeypatch, "d4", driver)
    assert result.startswith("deployed:"), result
    assert script.applies == 2


async def test_5_exhausted_rollback_is_deploy_broken(tmp_path, monkeypatch):
    """Never rolled-back: -- nothing was actually restored."""
    reset(smoke_states=[SmokeState.FAILED], rollback_fails=True)
    result, _ = await _run(_cfg(), tmp_path, monkeypatch, "d5")
    assert result.startswith("deploy-broken:"), result


async def test_6_disabled_deploy_starts_no_child(tmp_path, monkeypatch):
    script = reset()
    cfg = _cfg()
    cfg.deploy.enabled = False
    result, _ = await _run(cfg, tmp_path, monkeypatch, "d6")
    assert result.startswith("merged-not-deployed:"), result
    assert script.applies == 0


async def test_apply_failure_also_rolls_back(tmp_path, monkeypatch):
    """Spec section 7: a partially-applied stack is why rollback runs on
    apply failure, not only on smoke failure."""
    script = reset(apply_fails=True)
    result, _ = await _run(_cfg(), tmp_path, monkeypatch, "d7")
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1


async def test_first_ever_deploy_cannot_roll_back(tmp_path, monkeypatch):
    """No previous version: the report says so and the run is deploy-broken,
    because nothing was restored."""
    script = reset(previous_version=None, smoke_states=[SmokeState.FAILED])
    result, _ = await _run(_cfg(), tmp_path, monkeypatch, "d8")
    assert result.startswith("deploy-broken:"), result
    assert script.rollbacks == 0
