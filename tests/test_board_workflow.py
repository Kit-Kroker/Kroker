"""Temporal integration test: FeatureWorkflow writes through the REAL board.

The rest of the temporal suite registers no-op board fakes (so it can assert
on return strings without a DB). This file is the one place a workflow
actually runs against BoardStore + claim-check blobs end-to-end, which is the
only level that can catch: a stage that forgets to publish, a task sync that
drops rows, a rejected gate that moves the pointer, or a non-idempotent write
that a Temporal re-execution would corrupt.
"""
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
from sdlc.board.activities import (attach_task_evidence,
                                   publish_artifact_version,
                                   set_task_authoritative, sync_plan_tasks)
from sdlc.board.models import ArtifactStatus, TaskStatus
from sdlc.board.store import BoardStore
from sdlc.models import GateConfig, GateDecision, GateOutcome, GatePolicy
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.artifacts.retention import RetentionInput
from temporalio import activity
from tests.fakes.canned import AGENT_SPECS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import BOARD_FAKES, GIT_FAKES
from tests.fakes.fake_deploy import DEPLOY_FAKES, reset as reset_deploy

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

PROJECT = "default"   # PipelineConfig.project_key default

# The real board activities, swapped in for the no-op fakes GIT_FAKES carries.
BOARD_REAL = [publish_artifact_version, sync_plan_tasks,
              set_task_authoritative, attach_task_evidence]


@activity.defn(name="apply_session_retention")
async def _noop_retention(inp: RetentionInput) -> str:
    return "kept:0"


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    # Hardening: notify is only called on certain gate paths, but if gate
    # timing ever shifts this test should fail on an assertion, not on a
    # confusing "activity not registered" error.
    return Results()


def _git_fakes_without_board():
    """GIT_FAKES minus the board fakes â€” otherwise registering both the fake
    and the real under the same Temporal name is a duplicate-registration
    error."""
    return [a for a in GIT_FAKES if a not in BOARD_FAKES]


def _unattended_cfg():
    """Every gate OFF so the run ships without a human driver (matches the
    deploy-path suite's _cfg)."""
    cfg = e2e_config()
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF)
                 for name in cfg.gates}
    cfg.gates["deploy_failed"] = GateConfig(policy=GatePolicy.OFF)
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.deploy.enabled = True
    return cfg


async def _wait_for_status(handle, target, timeout_s=20.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


@pytest.fixture
def board_env(tmp_path, monkeypatch):
    """Point the board DB + blob store at a throwaway dir so the real
    activities are isolated from any runs/ left by other tests."""
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path / "runs"))
    return tmp_path


async def test_shipped_run_publishes_artifacts_tasks_and_evidence(board_env):
    reset_deploy()
    cfg = _unattended_cfg()
    tag = f"board-ship-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(
                env.client, task_queue=tag,
                workflows=[FeatureWorkflow, DeploymentWorkflow],
                activities=[evaluate_gate, export_run_artifacts,
                            _noop_retention, _noop_notify,
                            *_git_fakes_without_board(), *DEPLOY_FAKES,
                            *fake_agent_activities(AGENT_SPECS),
                            *BOARD_REAL],
                plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), cfg, None],
                id=tag, task_queue=tag)
            result = await handle.result()

    assert result.startswith("deployed:"), result

    store = BoardStore(db=str(board_env / "board.sqlite3"))
    try:
        # 1. Three project artifacts, all CURRENT (gates all approved).
        for key in ("requirements", "architecture", "plan"):
            art = store.get_artifact(PROJECT, key)
            assert art.status is ArtifactStatus.CURRENT, \
                f"{key}: {art.status}"
            assert art.current_version is not None, key
            assert len(store.list_versions(PROJECT, key)) >= 1, key

        # 2. Task rows exist for the current plan, all in a terminal or
        #    pre-terminal authoritative status (a shipped run leaves none
        #    PENDING).
        plan_v = store.get_artifact(PROJECT, "plan").current_version
        tasks = store.list_tasks(PROJECT, plan_v)
        assert len(tasks) >= 1
        assert all(t.authoritative_status is not TaskStatus.PENDING
                   for t in tasks), \
            "a shipped run must not leave tasks PENDING on the board"

        # 3. At least one piece of evidence landed for the run's tasks.
        total_evidence = sum(
            len(store.list_evidence(PROJECT, plan_v, t.task_id))
            for t in tasks)
        assert total_evidence >= 1, "no evidence attached for any task"
    finally:
        store.close()


async def test_rejected_architecture_records_rejected_and_keeps_pointer(
        board_env):
    """A rejected design is still written as history, but the pointer must not
    move â€” status='rejected', current_version stays None, and no tasks are
    synced (the run ends at the architecture gate)."""
    reset_deploy()
    cfg = _unattended_cfg()
    # Re-arm ONLY architecture: clarify auto-answers (OFF), the rest stay OFF,
    # and we explicitly reject architecture.
    cfg.gates["architecture"] = GateConfig(policy=GatePolicy.HARD)
    tag = f"board-rej-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                    env.client, task_queue=tag,
                    workflows=[FeatureWorkflow, DeploymentWorkflow],
                    activities=[evaluate_gate, export_run_artifacts,
                                _noop_retention, _noop_notify,
                                *_git_fakes_without_board(), *DEPLOY_FAKES,
                                *fake_agent_activities(AGENT_SPECS),
                                *BOARD_REAL],
                    plugins=[PydanticAIPlugin()]):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run, args=[greenfield_idea(), cfg, None],
                    id=tag, task_queue=tag)

                async def reject_arch(h):
                    await _wait_for_status(h, "awaiting:architecture")
                    await h.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(gate="architecture", round=1,
                                     outcome=GateOutcome.REJECT,
                                     decided_by="human"))

                await reject_arch(handle)
                result = await handle.result()

    assert result == "rejected:architecture", result

    store = BoardStore(db=str(board_env / "board.sqlite3"))
    try:
        # Requirements was published (clarify completed) and is CURRENT.
        assert store.get_artifact(PROJECT, "requirements").status \
            is ArtifactStatus.CURRENT

        # Architecture was recorded as REJECTED history, pointer unmoved.
        arch = store.get_artifact(PROJECT, "architecture")
        assert arch.status is ArtifactStatus.REJECTED
        assert arch.current_version is None, \
            "a rejected design must not become the current pointer"

        # No plan was published, so no task rows exist for any plan version.
        try:
            plan = store.get_artifact(PROJECT, "plan")
        except Exception:
            plan = None
        assert plan is None, \
            "rejecting architecture must not reach the plan stage"
    finally:
        store.close()
