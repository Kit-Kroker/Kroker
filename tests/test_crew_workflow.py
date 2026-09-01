# tests/test_crew_workflow.py
"""E-88 §2/§4. Sequencing is tested through the workflow with time skipping,
following tests/test_assessment_workflow_e2e.py; the decisions themselves are
pure and tested directly."""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.crew.activities import (
    CheckpointInput,
    CrewTurnInput,
    CrewTurnOutput,
    PrepareCrewInput,
    ReadRoundInput,
    RoundReading,
)
from sdlc.crew.models import TurnRecord
from sdlc.models import (
    ArtifactRef,
    HarnessKind,
    HarnessRunResult,
    SessionDigest,
)
from sdlc.workflows.crew import (
    EXIT_BUDGET,
    EXIT_DEADLINE,
    EXIT_PROTOCOL_VIOLATION,
    CrewTaskInput,
    CrewTaskWorkflow,
)

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "crew-test"
_STATE = {"missing": False, "turns": 0}

# What a real turn captures (run_crew_turn -> capture_session): a
# claim-checked transcript ref plus the inline waste digest.
SESSION_REF = ArtifactRef(kind="session", uri="file:///sessions/s-1.jsonl")
SESSION_DIGEST = SessionDigest(model_turns=3, tool_calls=5)


@activity.defn(name="prepare_crew")
async def fake_prepare(inp: PrepareCrewInput) -> str:
    return "/w/.workspace/orchestration/code"


@activity.defn(name="run_crew_turn")
async def fake_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    _STATE["turns"] += 1
    run = HarnessRunResult(
        harness=HarnessKind.OPENCODE,
        exit_code=0,
        summary="ok",
        session_id="s-1",
        cost_usd=0.5,
        input_tokens=100,
        output_tokens=20,
        session_ref=SESSION_REF,
        session_digest=SESSION_DIGEST,
    )
    return CrewTurnOutput(
        run=run,
        record=TurnRecord(
            role=inp.role,
            round=inp.round,
            attempt=inp.attempt,
            harness=inp.harness,
            model=inp.model,
            session_id="s-1",
            cost_usd=0.5,
            exit_code=0,
        ),
    )


@activity.defn(name="read_round")
async def fake_read(inp: ReadRoundInput) -> RoundReading:
    if _STATE["missing"]:
        return RoundReading(deliverable_path=None, note_summary="", missing=True)
    return RoundReading(
        deliverable_path="/w/round-1/notes.md", note_summary="added greet()", missing=False
    )


@activity.defn(name="checkpoint_round")
async def fake_checkpoint(inp: CheckpointInput) -> str | None:
    return "a" * 40


ACTIVITIES = [fake_prepare, fake_turn, fake_read, fake_checkpoint]


def _inp(**kw) -> CrewTaskInput:
    base = dict(
        layout="code",
        lead="coder",
        roles=[
            {
                "name": "coder",
                "harness": "opencode",
                "model": "glm-5.3",
                "writes": True,
                "skill": "coder",
            }
        ],
        prompt="do the thing",
        worktree="/w",
        task_id="t1",
        deliverable_path="notes.md",
        rounds_max=1,
        wall_clock_s=3000,
        turn_timeout_s=1800,
        cost_usd=25.0,
    )
    base.update(kw)
    return CrewTaskInput(**base)


async def _run(inp: CrewTaskInput):
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client, task_queue=TASK_QUEUE, workflows=[CrewTaskWorkflow], activities=ACTIVITIES
        ):
            return await env.client.execute_workflow(
                CrewTaskWorkflow.run, inp, id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE
            )


async def test_a_one_role_crew_completes_one_round():
    _STATE.update(missing=False, turns=0)
    res = await _run(_inp())
    assert res.run.exit_code == 0
    assert res.run.summary == "added greet()"
    assert res.sessions == {"coder": "s-1"}
    assert len(res.rounds) == 1
    assert res.rounds[0].turns[0].attempt == 1
    # The seam: run.session_ref/session_digest must cross the crew->feature
    # boundary (deep review, handoff, retention, WasteBag all read them off
    # `run`), while session_refs keeps the FULL list.
    assert res.run.session_ref == SESSION_REF
    assert res.run.session_digest == SESSION_DIGEST
    assert res.session_refs == [SESSION_REF]


async def test_the_lead_session_travels_on_the_shared_contract():
    """spec §1: run.session_id is the lead's, so feature.py's E-17 loop can
    resume it without knowing crews exist."""
    _STATE.update(missing=False, turns=0)
    res = await _run(_inp())
    assert res.run.session_id == "s-1"


async def test_cost_accumulates_across_rounds():
    _STATE.update(missing=False, turns=0)
    res = await _run(_inp(rounds_max=2))
    assert res.run.cost_usd == pytest.approx(1.0)


async def test_a_missing_deliverable_ends_as_a_protocol_violation():
    """spec §2: the one surviving row of E-87's disagreement table."""
    _STATE.update(missing=True, turns=0)
    res = await _run(_inp())
    assert res.run.exit_code == EXIT_PROTOCOL_VIOLATION


async def test_the_budget_brake_stops_between_rounds():
    """spec §4: an agent is not cut off mid-answer over a cent, but a round
    boundary is an honest decision point. 0.5/round against a 1.2 budget
    means three rounds run and the fourth never starts."""
    _STATE.update(missing=False, turns=0)
    res = await _run(_inp(rounds_max=5, cost_usd=1.2))
    assert res.run.exit_code == EXIT_BUDGET
    assert _STATE["turns"] == 3


async def test_a_deadline_before_round_one_records_no_round():
    """A deadline already spent at round start must not leave a phantom
    empty round behind — that round never started. (The timer-wins path
    below keeps its record: that round DID start.)"""
    _STATE.update(missing=False, turns=0)
    res = await _run(_inp(wall_clock_s=0))
    assert res.run.exit_code == EXIT_DEADLINE
    assert res.rounds == []
