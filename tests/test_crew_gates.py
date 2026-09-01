# tests/test_crew_gates.py
"""E-88 §6: the gate is hosted by the CHILD. Returning `deferred` upward
would mean rebuilding every round's state on the retry -- exactly the
reattach machinery this design exists to delete -- so the gate stays where
the state is."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.crew.activities import (
    CheckpointInput, CrewTurnInput, CrewTurnOutput, PrepareCrewInput,
    ReadRoundInput, RoundReading,
)
from sdlc.crew.models import TurnRecord
from sdlc.models import (
    DeferredToolUse, GateConfig, GateDecision, GateOutcome, GatePolicy,
    GateSettings, HarnessKind, HarnessRunResult,
)
from sdlc.notify.contract import NotifyInput, Results
from sdlc.workflows.crew import CrewTaskInput, CrewTaskWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "crew-gates"
TURNS: list[CrewTurnInput] = []
# How many more lead turns should come back suspended at a tool call.
DEFER = {"left": 0}
ASK = {"left": 0}

DEFERRAL = DeferredToolUse(tool_use_id="tu-1", tool="Bash",
                           target="/etc/hosts", rule_id="no-out-of-worktree-write",
                           reason="Writes are scoped to the task worktree.",
                           input_digest="d1")


@activity.defn(name="prepare_crew")
async def fake_prepare(inp: PrepareCrewInput) -> str:
    return "/w/.workspace/orchestration/code"


@activity.defn(name="run_crew_turn")
async def fake_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    TURNS.append(inp)
    deferred = None
    if inp.role == "coder" and DEFER["left"] > 0:
        DEFER["left"] -= 1
        deferred = DEFERRAL
    run = HarnessRunResult(harness=inp.harness, exit_code=0, summary="ok",
                           session_id=f"s-{inp.role}", cost_usd=0.5,
                           input_tokens=100, output_tokens=20,
                           deferred=deferred)
    return CrewTurnOutput(run=run, record=TurnRecord(
        role=inp.role, round=inp.round, attempt=inp.attempt,
        harness=inp.harness, model=inp.model, session_id=f"s-{inp.role}",
        cost_usd=0.5, input_tokens=100, output_tokens=20, exit_code=0))


@activity.defn(name="read_round")
async def fake_read(inp: ReadRoundInput) -> RoundReading:
    q = ""
    if ASK["left"] > 0:
        ASK["left"] -= 1
        q = "which database? | the schema cannot be written without it"
    return RoundReading(deliverable_path="/w/notes.md", note_summary="done",
                        missing=False, question=q)


@activity.defn(name="checkpoint_round")
async def fake_checkpoint(inp: CheckpointInput) -> str | None:
    return "a" * 40


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    return Results(results=[])


ACTIVITIES = [fake_prepare, fake_turn, fake_read, fake_checkpoint, fake_notify]

ROLES = [{"name": "coder", "harness": "opencode",
          "model": "zai-coding-plan/glm-5.3", "writes": True,
          "skill": "coder"}]


def _inp(policy=GatePolicy.OFF, **kw) -> CrewTaskInput:
    base = dict(layout="code", lead="coder", roles=ROLES, prompt="do it",
                worktree="/w", task_id="t1", deliverable_path="notes.md",
                rounds_max=1, wall_clock_s=3000, turn_timeout_s=1800,
                cost_usd=25.0,
                gate_settings=GateSettings(default_gate_policy=policy))
    base.update(kw)
    return CrewTaskInput(**base)


async def test_a_deferral_is_gated_and_the_turn_resumes_with_the_grant():
    """Explicit tool_approval policy OFF auto-approves, so this exercises
    the whole loop without a human: suspend -> gate -> resume the SAME session
    carrying the grant."""
    TURNS.clear()
    DEFER["left"] = 1
    settings = GateSettings(
        default_gate_policy=GatePolicy.OFF,
        gates={"tool_approval": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            res = await env.client.execute_workflow(
                CrewTaskWorkflow.run, _inp(gate_settings=settings),
                id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE)
    lead = [t for t in TURNS if t.role == "coder"]
    assert len(lead) == 2, "the turn was never resumed after the gate"
    assert lead[1].session_id == "s-coder", "the resume started a new session"
    assert [g.tool_use_id for g in lead[1].grants] == ["tu-1"]
    assert lead[1].grants[0].approved is True
    assert res.run.exit_code == 0


async def test_the_escalation_cap_ends_with_one_resume_that_denies():
    """E-17's rule, unchanged: the cap does not abandon the agent mid-call --
    it spends one final resume purely to deliver the denial."""
    TURNS.clear()
    DEFER["left"] = 5
    settings = GateSettings(
        default_gate_policy=GatePolicy.OFF,
        gates={"tool_approval": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            await env.client.execute_workflow(
                CrewTaskWorkflow.run,
                _inp(gate_settings=settings, max_tool_escalations=2),
                id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE)
    lead = [t for t in TURNS if t.role == "coder"]
    # first turn + 2 gated resumes + 1 capped resume carrying the denial
    assert len(lead) == 4
    assert lead[-1].grants[0].approved is False


async def test_tool_escalations_do_not_burn_question_budget():
    """Tool approvals and crew questions have separate counters: tool approvals
    must not deplete the 2-question intent gap budget."""
    TURNS.clear()
    DEFER["left"] = 2
    ASK["left"] = 1
    settings = GateSettings(
        default_gate_policy=GatePolicy.OFF,
        gates={"tool_approval": GateConfig(policy=GatePolicy.OFF),
               "crew_question": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            res = await env.client.execute_workflow(
                CrewTaskWorkflow.run,
                _inp(gate_settings=settings, max_tool_escalations=5,
                     rounds_max=2),
                id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE)
    assert res.run.exit_code == 0
    assert len(res.rounds) == 2


async def test_tool_approval_defaults_to_hard_even_under_default_policy_off():
    """Tool approval gates default to HARD unless explicitly overridden, matching
    FeatureWorkflow behavior and preserving the ADR-17 containment fence."""
    TURNS.clear()
    DEFER["left"] = 1
    wf_id = f"crew-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                CrewTaskWorkflow.run,
                _inp(policy=GatePolicy.OFF),  # default_gate_policy is OFF
                id=wf_id, task_queue=TASK_QUEUE)
            with env.auto_time_skipping_disabled():
                for _ in range(100):
                    pending = await handle.query(
                        CrewTaskWorkflow.pending_decisions)
                    if pending:
                        break
                    await asyncio.sleep(0.1)
                assert pending and pending[0].gate == "tool_approval"
                await handle.signal(
                    CrewTaskWorkflow.submit_gate_decision,
                    GateDecision(gate=pending[0].gate,
                                 round=pending[0].round,
                                 outcome=GateOutcome.APPROVE,
                                 decided_by="human"))
            await handle.result()
    lead = [t for t in TURNS if t.role == "coder"]
    assert len(lead) == 2
    assert lead[1].grants[0].approved is True


async def test_a_human_decision_reaches_the_child_workflow():
    """The operator signals the CREW's handle, not the parent's -- that is
    what hosting the gate in the child means, and what the inbox disjunct
    later exists to make discoverable."""
    TURNS.clear()
    DEFER["left"] = 1
    wf_id = f"crew-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                CrewTaskWorkflow.run, _inp(policy=GatePolicy.HARD),
                id=wf_id, task_queue=TASK_QUEUE)
            with env.auto_time_skipping_disabled():
                for _ in range(100):
                    pending = await handle.query(
                        CrewTaskWorkflow.pending_decisions)
                    if pending:
                        break
                    await asyncio.sleep(0.1)
                assert pending, "the crew never opened a gate"
                await handle.signal(
                    CrewTaskWorkflow.submit_gate_decision,
                    GateDecision(gate=pending[0].gate,
                                 round=pending[0].round,
                                 outcome=GateOutcome.REJECT,
                                 decided_by="human",
                                 comments="not on this box"))
            await handle.result()
    lead = [t for t in TURNS if t.role == "coder"]
    assert lead[-1].grants[0].approved is False
    assert lead[-1].grants[0].reason == "not on this box"


async def test_a_question_opens_a_gate_and_the_answer_reaches_the_next_round():
    """The addendum's departure from parent §6: answer_question lives on
    FeatureWorkflow, not GateHost, so a question opens a GATE and the human's
    answer arrives as decision.comments."""
    TURNS.clear()
    DEFER["left"] = 0
    ASK["left"] = 1
    wf_id = f"crew-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                CrewTaskWorkflow.run,
                _inp(policy=GatePolicy.HARD, rounds_max=2),
                id=wf_id, task_queue=TASK_QUEUE)
            with env.auto_time_skipping_disabled():
                for _ in range(100):
                    pending = await handle.query(
                        CrewTaskWorkflow.pending_decisions)
                    if pending:
                        break
                    await asyncio.sleep(0.1)
                assert pending and pending[0].gate == "crew_question"
                await handle.signal(
                    CrewTaskWorkflow.submit_gate_decision,
                    GateDecision(gate="crew_question", round=pending[0].round,
                                 outcome=GateOutcome.APPROVE,
                                 decided_by="human", comments="use sqlite"))
            await handle.result()
    lead_r2 = [t for t in TURNS if t.role == "coder" and t.round == 2][0]
    assert "use sqlite" in lead_r2.prompt


async def test_the_escalation_budget_ends_the_crew_as_an_intent_gap():
    """§6: two per crew. Exhaustion is journalled as a metric because a lead
    hitting an intent gap is evidence clarify under-performed on this task."""
    from sdlc.workflows.crew import EXIT_INTENT_GAP
    TURNS.clear()
    DEFER["left"] = 0
    ASK["left"] = 9
    settings = GateSettings(
        default_gate_policy=GatePolicy.OFF,
        gates={"crew_question": GateConfig(policy=GatePolicy.OFF)})
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            res = await env.client.execute_workflow(
                CrewTaskWorkflow.run,
                _inp(gate_settings=settings, rounds_max=9),
                id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE)
    assert res.run.exit_code == EXIT_INTENT_GAP


async def test_answer_survives_tool_resumptions_in_next_round():
    """An answer delivered into round N+1 must survive multiple tool resumptions
    within that round without being dropped, and must not leak into round N+2."""
    TURNS.clear()
    DEFER["left"] = 0
    ASK["left"] = 1
    wf_id = f"crew-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow], activities=ACTIVITIES):
            handle = await env.client.start_workflow(
                CrewTaskWorkflow.run,
                _inp(policy=GatePolicy.HARD, rounds_max=3,
                     gate_settings=GateSettings(
                         default_gate_policy=GatePolicy.HARD,
                         gates={"tool_approval": GateConfig(policy=GatePolicy.OFF)})),
                id=wf_id, task_queue=TASK_QUEUE)
            with env.auto_time_skipping_disabled():
                for _ in range(100):
                    pending = await handle.query(
                        CrewTaskWorkflow.pending_decisions)
                    if pending and pending[0].gate == "crew_question":
                        break
                    await asyncio.sleep(0.1)
                assert pending and pending[0].gate == "crew_question"
                # Schedule tool deferral for round 2
                DEFER["left"] = 1
                await handle.signal(
                    CrewTaskWorkflow.submit_gate_decision,
                    GateDecision(gate="crew_question", round=pending[0].round,
                                 outcome=GateOutcome.APPROVE,
                                 decided_by="human", comments="use postgres"))
            await handle.result()
    lead_r2_turns = [t for t in TURNS if t.role == "coder" and t.round == 2]
    # Round 2 has 2 turns: the initial turn (which suspended) and the resumed turn
    assert len(lead_r2_turns) == 2
    assert "use postgres" in lead_r2_turns[0].prompt
    assert "use postgres" in lead_r2_turns[1].prompt

    # Round 3 must NOT repeat round 1's answer
    lead_r3_turns = [t for t in TURNS if t.role == "coder" and t.round == 3]
    assert len(lead_r3_turns) == 1
    assert "use postgres" not in lead_r3_turns[0].prompt


from temporalio import workflow as temporal_workflow


@temporal_workflow.defn
class DummyParentWorkflow:
    @temporal_workflow.run
    async def run(self, inp: CrewTaskInput) -> None:
        await temporal_workflow.execute_child_workflow(
            CrewTaskWorkflow.run, inp,
            id=f"{temporal_workflow.info().workflow_id}-child",
            task_queue=TASK_QUEUE)


async def test_a_crews_pending_item_names_its_parent_run():
    """§E: an operator must see a crew item as part of its run, not as an
    orphan. A FIELD, not a parse of the workflow-id prefix -- the prefix is a
    fact about ids, not a contract for display."""
    TURNS.clear()
    DEFER["left"] = 1
    ASK["left"] = 0
    parent_id = f"parent-{uuid.uuid4()}"
    child_id = f"{parent_id}-child"
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow, DummyParentWorkflow],
                          activities=ACTIVITIES):
            parent_handle = await env.client.start_workflow(
                DummyParentWorkflow.run, _inp(policy=GatePolicy.HARD),
                id=parent_id, task_queue=TASK_QUEUE)
            child_handle = env.client.get_workflow_handle(child_id)
            pending = []
            for _ in range(100):
                try:
                    pending = await child_handle.query(
                        CrewTaskWorkflow.pending_decisions)
                    if pending:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            assert pending, "the child crew never opened a gate"
            # Started as child: parent_run_id must equal the parent workflow id!
            assert pending[0].parent_run_id == parent_id
            await child_handle.signal(
                CrewTaskWorkflow.submit_gate_decision,
                GateDecision(gate=pending[0].gate, round=pending[0].round,
                             outcome=GateOutcome.APPROVE,
                             decided_by="human"))
            await parent_handle.result()

