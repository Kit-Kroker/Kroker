"""ReflectWorkflow (E-13) — the wrapper that lets a Temporal Schedule reach
the reflect activity. Runs the REAL workflow on a time-skipping worker with a
faked reflect activity, following tests/test_e2e_greenfield.py's pattern."""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.memory.activities import PromoteInput, ReflectInput

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.reflect import ReflectScheduleInput, ReflectWorkflow

pytestmark = pytest.mark.temporal

TASK_QUEUE = "reflect-test"

REFLECTED: list[str] = []
FAIL_BANKS: set[str] = set()
PROMOTED: list[PromoteInput] = []
FAIL_PROMOTE: set[str] = set()
# Both fakes append here, pinning the promote-after-projects /
# reflect-org-after-promote ordering of the one nightly job.
ORDER: list[str] = []


@activity.defn(name="reflect")
async def fake_reflect(inp: ReflectInput) -> None:
    if inp.bank in FAIL_BANKS:
        raise RuntimeError(f"backend unreachable for {inp.bank}")
    REFLECTED.append(inp.bank)
    ORDER.append(f"reflect:{inp.bank}")


@activity.defn(name="promote_org_learnings")
async def fake_promote(inp: PromoteInput) -> int:
    if inp.org_bank in FAIL_PROMOTE:
        raise RuntimeError(f"promotion backend unreachable for {inp.org_bank}")
    PROMOTED.append(inp)
    ORDER.append(f"promote:{inp.org_bank}")
    return 0


@pytest.fixture(autouse=True)
def _reset():
    REFLECTED.clear()
    FAIL_BANKS.clear()
    PROMOTED.clear()
    FAIL_PROMOTE.clear()
    ORDER.clear()
    yield


async def _run(env: WorkflowEnvironment, inp: ReflectScheduleInput) -> int:
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[ReflectWorkflow],
        activities=[fake_reflect, fake_promote],
    ):
        return await env.client.execute_workflow(
            ReflectWorkflow.run, inp, id=f"reflect-{uuid.uuid4()}", task_queue=TASK_QUEUE
        )


@pytest.mark.asyncio
async def test_each_bank_gets_its_own_reflect_execution():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(env, ReflectScheduleInput(banks=["project:a", "project:b", "project:c"]))
    assert count == 3
    assert REFLECTED == ["project:a", "project:b", "project:c"]


@pytest.mark.asyncio
async def test_one_failing_bank_does_not_skip_the_rest():
    FAIL_BANKS.add("project:b")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(WorkflowFailureError):
            await _run(env, ReflectScheduleInput(banks=["project:a", "project:b", "project:c"]))
    # b failed, but a and c still ran — the loop does not abort
    assert REFLECTED == ["project:a", "project:c"]


@pytest.mark.asyncio
async def test_a_failing_bank_fails_the_workflow_visibly():
    # The whole point of FR-404: a failed nightly reflect must be a visibly
    # failed workflow, never a silent no-op (spec: eve's failure mode).
    FAIL_BANKS.add("project:only")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(Exception) as ei:
            await _run(env, ReflectScheduleInput(banks=["project:only"]))
    # temporalio 1.30 wraps the workflow's ApplicationError in a
    # WorkflowFailureError whose str() is the fixed literal "Workflow
    # execution failed"; the bank name lives on the cause. The FR-404
    # guarantee is that the failure is visible and identifies the bank.
    assert ei.value.__cause__ is not None
    assert "project:only" in str(ei.value.__cause__)


@pytest.mark.asyncio
async def test_all_banks_succeeding_returns_full_count():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(env, ReflectScheduleInput(banks=["project:default"]))
    assert count == 1
    assert REFLECTED == ["project:default"]


@pytest.mark.asyncio
async def test_backend_and_base_url_reach_the_activity():
    seen: list[ReflectInput] = []

    @activity.defn(name="reflect")
    async def capturing(inp: ReflectInput) -> None:
        seen.append(inp)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[ReflectWorkflow], activities=[capturing]
        ):
            await env.client.execute_workflow(
                ReflectWorkflow.run,
                ReflectScheduleInput(
                    banks=["project:default"], backend="hindsight", base_url="http://mem:9000"
                ),
                id=f"reflect-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
    assert seen[0].backend == "hindsight"
    assert seen[0].base_url == "http://mem:9000"


@pytest.mark.asyncio
async def test_org_path_promotes_then_reflects_org():
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(
            env, ReflectScheduleInput(banks=["project:a", "project:b"], org_bank="org")
        )
    assert count == 2  # return stays len(banks); the org bank is not counted
    assert PROMOTED[0].org_bank == "org"
    assert PROMOTED[0].project_banks == ["project:a", "project:b"]
    assert PROMOTED[0].min_projects == 2
    # Projects reflect first, then promotion, then the org bank itself.
    assert ORDER == [
        "reflect:project:a",
        "reflect:project:b",
        "promote:org",
        "reflect:org",
    ]
    assert ORDER[-2:] == ["promote:org", "reflect:org"]


@pytest.mark.asyncio
async def test_no_org_bank_runs_no_promotion():
    # Back-compat shape: a pre-change recorded Schedule arg (no org fields)
    # decodes to exactly this input, and the run behaves exactly as before.
    decoded = ReflectScheduleInput.model_validate({"banks": ["project:a", "project:b"]})
    assert decoded.org_bank is None
    assert decoded.promote_min_projects == 2
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        count = await _run(env, ReflectScheduleInput(banks=["project:a", "project:b"]))
    assert count == 2
    assert REFLECTED == ["project:a", "project:b"]
    assert PROMOTED == []
    assert ORDER == ["reflect:project:a", "reflect:project:b"]


@pytest.mark.asyncio
async def test_promotion_failure_fails_the_run():
    FAIL_PROMOTE.add("org")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(WorkflowFailureError) as ei:
            await _run(env, ReflectScheduleInput(banks=["project:a", "project:b"], org_bank="org"))
    assert ei.value.__cause__ is not None
    assert "promote:org" in str(ei.value.__cause__)
    # Both steps are attempted even when promotion fails: the org bank
    # still reflects (after the project banks, which all succeeded).
    assert REFLECTED == ["project:a", "project:b", "org"]


@pytest.mark.asyncio
async def test_org_reflect_failure_fails_the_run():
    # Promotion fine, org reflect backend down -> visible failure naming the bank.
    FAIL_BANKS.add("org")
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with pytest.raises(WorkflowFailureError) as ei:
            await _run(env, ReflectScheduleInput(banks=["project:a", "project:b"], org_bank="org"))
    assert ei.value.__cause__ is not None
    assert "org" in str(ei.value.__cause__)
    # Promotion ran (and succeeded) before the org reflect failed.
    assert len(PROMOTED) == 1
    assert ORDER[-1] == "promote:org"
