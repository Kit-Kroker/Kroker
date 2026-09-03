"""D1: a seeded run skips stages 0-3 and keeps everything from _dev_task down.

The unit tests here pin the contract and the skip predicate; the end-to-end
'no proposer was called' assertion is the temporal test at the bottom.
"""

import inspect

import pytest

from sdlc.models import (
    ArchitectureDecision,
    ArchitectureSpec,
    DevTask,
    ImplementationPlan,
    ValidationContract,
)
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.models import SeededWork


def _seeded():
    return SeededWork(
        arch=ArchitectureSpec(
            overview="Tidy-up: add .env to .gitignore",
            decisions=[
                ArchitectureDecision(
                    id="D1",
                    decision="Edit .gitignore only",
                    rationale="triage finding baseline/gitignore_missing_env",
                )
            ],
        ),
        plan=ImplementationPlan(
            tasks=[
                DevTask(
                    id="T01",
                    title="gitignore_missing_env in .gitignore",
                    description="Add .env to .gitignore.",
                    acceptance_criteria=["triage no longer reports the rule"],
                    files_hint=[".gitignore"],
                    contract=ValidationContract(
                        task_id="T01", assertions=[".env is ignored"], frozen=True
                    ),
                )
            ]
        ),
    )


def test_seeded_work_carries_an_arch_and_a_plan():
    s = _seeded()
    assert s.arch.overview.startswith("Tidy-up")
    assert [t.id for t in s.plan.tasks] == ["T01"]


def test_seeded_work_round_trips_through_json():
    """It crosses a Temporal child-workflow boundary, so it must serialize."""
    s = _seeded()
    assert SeededWork.model_validate_json(s.model_dump_json()) == s


def test_run_accepts_seeded_as_a_third_argument():
    sig = inspect.signature(FeatureWorkflow.run)
    params = list(sig.parameters)
    assert params[1:] == ["idea", "cfg", "seeded"], (
        "Task 7 starts children with args=[idea, cfg, seeded]; the order and names are the contract"
    )
    assert sig.parameters["seeded"].default is None


def test_seeded_plan_must_carry_at_least_one_task():
    with pytest.raises(ValueError):
        SeededWork(arch=_seeded().arch, plan=ImplementationPlan(tasks=[]))


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_seeded_run_skips_clarify_architect_and_planner():
    """E-44 D1: a seeded run enters at stage 4. The clarifier, architect and
    planner are never invoked -- proved by registering NONE of their fakes: a
    call to an unregistered activity fails the workflow. So reaching a PR is
    sufficient evidence the skip held. Follows test_e2e_greenfield.py's worker
    setup verbatim, passing the SeededWork as the third run argument."""
    import asyncio
    import uuid

    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
    from temporalio.contrib.pydantic import pydantic_data_converter
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from sdlc.activities import evaluate_gate
    from sdlc.core.models import (
        GateDecision,
        GateOutcome,
    )
    from tests.fakes.canned import AGENT_SPECS, ARCH, PLAN, e2e_config, greenfield_idea
    from tests.fakes.fake_activities import GIT_FAKES
    from tests.fakes.fake_agents import fake_agent_activities

    # Omit the three proposers a seeded run must not call. The remaining fakes
    # (qa/reviewer/analyst/merge_verdict) cover stages 4-6; GIT_FAKES covers
    # git/worktree/coding activities exactly as the greenfield e2e.
    omitted = {"clarify_agent", "architect_agent", "planner_agent"}
    specs = [s for s in AGENT_SPECS if s[0] not in omitted]
    activities = [evaluate_gate, *GIT_FAKES, *fake_agent_activities(specs)]

    seeded = SeededWork(arch=ARCH, plan=PLAN)
    cfg = e2e_config()  # every gate HARD; merge auto-passes clean

    async def _wait_for_status(handle, target, timeout_s=15.0):
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            if await handle.query(FeatureWorkflow.pending_gate) == target:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"timed out waiting for status {target!r}")

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue="seeded",
                workflows=[FeatureWorkflow],
                activities=activities,
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg, seeded],
                    id=f"seeded-{uuid.uuid4()}",
                    task_queue="seeded",
                )

                # A seeded run skips clarify/architecture/plan; service only
                # the deploy gate (merge auto-passes against the clean fakes).
                async def _drive():
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                driver = asyncio.create_task(_drive())
                result = await handle.result()
                await driver

    # Reaching a PR (deployed: or merged-not-deployed:) is only possible after
    # the merge gate, which runs in stage 5 -- past every stage a seeded run
    # skips. That proves clarifier/architect/planner were never invoked, since
    # none of their activities were even registered.
    assert result.startswith(("deployed:", "merged-not-deployed:")), result
