# tests/test_crew_feature_wiring.py
"""The feature.py <-> crew seam, EXECUTED (E-88 §3).

Two ship-blocking bugs lived on this seam with the suite all green,
because no test drove FeatureWorkflow's dev stage through the crew
branch -- test_crew_workflow.py exercised CrewTaskWorkflow alone:

* the load site unpacked the single `LoadedCrew` dataclass into two
  names (`TypeError: cannot unpack non-iterable LoadedCrew`), and
* the child-workflow call read `crew.protocol` out of the very `crew`
  result it was about to assign (`UnboundLocalError` on the first
  crew task).

So this module runs the REAL FeatureWorkflow with the dev role
configured harness=CREW: the REAL load_crew reads the real shipped
crew/ tree (exercising the real dataclass over the wire), fake crew
activities stand in for the subprocess side effects, and the test
asserts the run completes and that the lead's SKILL.md protocol
reaches the round brief handed to run_crew_turn.
"""
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
from sdlc.crew.activities import (
    CheckpointInput, CrewTurnInput, CrewTurnOutput, PrepareCrewInput,
    ReadRoundInput, RoundReading, load_crew,
)
from sdlc.crew.models import TurnRecord
from sdlc.models import (
    GateConfig, GatePolicy, HarnessKind, HarnessRunResult, RoleConfig,
)
from sdlc.notify.contract import NotifyInput, Results
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS, QUESTION_IDS, e2e_config, greenfield_idea,
)
from tests.fakes.fake_activities import git_fakes_except

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.crew import CrewTaskWorkflow
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "crew-wiring"

# The round briefs the fake lead received; the protocol assertion reads
# these (the fake_deploy.DeployScript pattern: module state, reset per test).
BRIEFS: list[str] = []


@activity.defn(name="prepare_crew")
async def fake_prepare(inp: PrepareCrewInput) -> str:
    return "/w/.workspace/orchestration/code"


@activity.defn(name="run_crew_turn")
async def fake_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    BRIEFS.append(inp.prompt)
    run = HarnessRunResult(harness=inp.harness, exit_code=0,
                           summary="ok", session_id="s-1", cost_usd=0.5,
                           input_tokens=100, output_tokens=20)
    return CrewTurnOutput(run=run, record=TurnRecord(
        role=inp.role, round=inp.round, attempt=inp.attempt,
        harness=inp.harness, model=inp.model, session_id="s-1",
        cost_usd=0.5, exit_code=0))


@activity.defn(name="read_round")
async def fake_read(inp: ReadRoundInput) -> RoundReading:
    return RoundReading(deliverable_path="/w/round-1/notes.md",
                        note_summary="added greet()", missing=False)


@activity.defn(name="checkpoint_round")
async def fake_checkpoint(inp: CheckpointInput) -> str | None:
    return "a" * 40


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    # Registered so an unexpected escalation surfaces as the test's own
    # assertion rather than a confusing activity NotFoundError (the hazard
    # test_board_workflow.py records).
    return Results(results=[])


def _cfg():
    """Every gate OFF: the point is the dev stage's crew wiring, not gate
    driving. The dev role goes CREW with the shipped `code` layout."""
    cfg = e2e_config()
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF)
                 for name in ("clarify", "architecture", "plan", "merge",
                              "deploy")}
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.roles["dev"] = RoleConfig(harness=HarnessKind.CREW, layout="code",
                                  model="zai-coding-plan/glm-5.3")
    return cfg


async def _finish(handle, slice_s: float = 5.0, rounds: int = 30):
    """Await a workflow's result in bounded slices, going idle between them.

    Why not a bare `await handle.result()`: while a result long-poll is
    in flight the time-skipping server never sees the client idle, so it
    never auto-advances its clock — and a workflow stuck in workflow-task
    retry backoff (a deterministic workflow-CODE error, i.e. exactly the
    class of seam bug this module exists to catch) then surfaces only
    after real-world backoff minutes. The idle gaps between slices let
    the server skip time to the failure (or the completion).
    """
    for _ in range(rounds):
        try:
            return await asyncio.wait_for(
                asyncio.shield(handle.result()), timeout=slice_s)
        except asyncio.TimeoutError:
            continue
    raise AssertionError(
        "workflow did not finish; likely stuck in workflow-task retries")


async def test_the_crew_dev_task_carries_the_protocol_to_the_round_brief(
        tmp_path, monkeypatch):
    BRIEFS.clear()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[FeatureWorkflow, DeploymentWorkflow,
                                     CrewTaskWorkflow],
                          activities=[evaluate_gate, export_run_artifacts,
                                      _noop_notify,
                                      # Real tree, real dataclass, real
                                      # name binding.
                                      load_crew,
                                      fake_prepare, fake_turn, fake_read,
                                      fake_checkpoint,
                                      # run_coding_task deliberately NOT
                                      # registered: if the crew guard
                                      # regresses, the run must fail loudly
                                      # here instead of silently shipping
                                      # the plain coding path.
                                      *git_fakes_except("run_coding_task"),
                                      *fake_agent_activities(AGENT_SPECS)],
                          plugins=[PydanticAIPlugin()]):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run, args=[greenfield_idea(), _cfg(), None],
                id=f"{TASK_QUEUE}-{uuid.uuid4()}", task_queue=TASK_QUEUE)
            # Signals, not a gate driver: with every gate OFF the run needs
            # only its one open question answered.
            with env.auto_time_skipping_disabled():
                for qid in QUESTION_IDS:
                    await handle.signal(FeatureWorkflow.answer_question,
                                        args=[qid, "yes"])
            result = await _finish(handle)

    # Primary regression: the workflow completes at all. Bug B died at the
    # load site (TypeError), Bug A at the child-workflow call
    # (UnboundLocalError) -- either leaves the dev task unrunnable.
    assert not result.startswith("failed"), result
    assert BRIEFS, "the crew child workflow never ran a turn"
    # The protocol is the lead's SKILL.md; `notes-v1` is its distinctive
    # shipped substring. Without it nothing tells the agent to write its
    # notes.md (the E-88 step-1 finding).
    assert any("notes-v1" in b for b in BRIEFS), (
        "the lead's SKILL.md protocol must reach the round brief run_crew_turn "
        "receives; it was loaded, dropped, or read before its first binding")
