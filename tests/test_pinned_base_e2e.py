"""DS2: the gate's diff and base come from the setup SHA, never the branch
name and never the advancing integration head."""

from __future__ import annotations

import uuid

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.core.models import GateConfig, GatePolicy
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from sdlc.stages.merge.activities import evaluate_gate
from sdlc.vcs import BaseWorktree, BaseWorktreeInput, DiffInput
from tests.fakes.canned import AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea
from tests.fakes.fake_activities import git_fakes_except

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

DIFFS: list[DiffInput] = []
BASES: list[BaseWorktreeInput] = []


@activity.defn(name="get_task_diff")
async def recording_diff(inp: DiffInput) -> dict:
    DIFFS.append(inp)
    return {"stat": "", "patch": "", "files": ["app/main.py"], "renames": []}


@activity.defn(name="prepare_base_worktree")
async def recording_base(inp: BaseWorktreeInput) -> BaseWorktree:
    BASES.append(inp)
    return BaseWorktree(path="/fake/base")


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


async def test_the_merge_gate_reads_the_setup_sha(tmp_path, monkeypatch):
    DIFFS.clear()
    BASES.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    cfg = e2e_config()
    cfg.gates = {
        n: GateConfig(policy=GatePolicy.OFF)
        for n in ("clarify", "architecture", "plan", "merge", "deploy")
    }
    cfg.default_gate_policy = GatePolicy.OFF
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue="pinned",
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=[
                evaluate_gate,
                export_run_artifacts,
                _noop_notify,
                recording_diff,
                recording_base,
                *git_fakes_except("get_task_diff", "prepare_base_worktree"),
                *fake_agent_activities(AGENT_SPECS),
            ],
            plugins=[PydanticAIPlugin()],
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[greenfield_idea(), cfg, None],
                id=f"pinned-{uuid.uuid4()}",
                task_queue="pinned",
            )
            with env.auto_time_skipping_disabled():
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
            await handle.result()

    integ = [d for d in DIFFS if d.worktree == "/fake/integ"]
    assert integ, "the integration diff was never fetched"
    # fake setup_integration_branch returns head_sha="deadbeef"; the fake merge
    # advances the integration head to "feed0001"; idea.base_branch is "main".
    assert {d.branch_point for d in integ} == {"deadbeef"}
    assert [b.base_sha for b in BASES] == ["deadbeef"]
    assert BASES[0].integration_wt == "/fake/integ"
