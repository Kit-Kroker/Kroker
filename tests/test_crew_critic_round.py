# tests/test_crew_critic_round.py
"""E-88 step 2 §B. The critic runs after the lead, inside the same round, and
its findings reach the NEXT round's brief -- which is the only thing that can
read them. At rounds.max 1 a critic is spend with no consumer, which is why
this step also raises the shipped layout to 2."""
from __future__ import annotations

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
from sdlc.models import HarnessKind, HarnessRunResult
from sdlc.workflows.crew import CrewTaskInput, CrewTaskWorkflow

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "crew-critic"
TURNS: list[CrewTurnInput] = []

ROLES = [
    {"name": "coder", "harness": "opencode", "model": "zai-coding-plan/glm-5.3",
     "writes": True, "skill": "coder"},
    {"name": "critic", "harness": "claude_code", "model": "anthropic:opus-5",
     "writes": False, "skill": "critic"},
]


@activity.defn(name="prepare_crew")
async def fake_prepare(inp: PrepareCrewInput) -> str:
    return "/w/.workspace/orchestration/code"


@activity.defn(name="run_crew_turn")
async def fake_turn(inp: CrewTurnInput) -> CrewTurnOutput:
    TURNS.append(inp)
    run = HarnessRunResult(harness=inp.harness, exit_code=0, summary="ok",
                           session_id=f"s-{inp.role}", cost_usd=0.5,
                           input_tokens=100, output_tokens=20)
    return CrewTurnOutput(run=run, record=TurnRecord(
        role=inp.role, round=inp.round, attempt=inp.attempt,
        harness=inp.harness, model=inp.model, session_id=f"s-{inp.role}",
        cost_usd=0.5, input_tokens=100, output_tokens=20, exit_code=0))


@activity.defn(name="read_round")
async def fake_read(inp: ReadRoundInput) -> RoundReading:
    return RoundReading(deliverable_path="/w/notes.md",
                        note_summary="added greet()", missing=False,
                        critique="[major] api.py:20: no timeout",
                        verdict="needs_work")


@activity.defn(name="checkpoint_round")
async def fake_checkpoint(inp: CheckpointInput) -> str | None:
    return "a" * 40


def _inp(**kw) -> CrewTaskInput:
    base = dict(layout="code", lead="coder", roles=ROLES,
                prompt="do the thing", worktree="/w", task_id="t1",
                deliverable_path="notes.md", rounds_max=2,
                wall_clock_s=3000, turn_timeout_s=1800, cost_usd=25.0)
    base.update(kw)
    return CrewTaskInput(**base)


async def _run(inp: CrewTaskInput):
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        async with Worker(env.client, task_queue=TASK_QUEUE,
                          workflows=[CrewTaskWorkflow],
                          activities=[fake_prepare, fake_turn, fake_read,
                                      fake_checkpoint]):
            return await env.client.execute_workflow(
                CrewTaskWorkflow.run, inp,
                id=f"crew-{uuid.uuid4()}", task_queue=TASK_QUEUE)


async def test_the_critic_turn_follows_the_lead_in_the_same_round():
    TURNS.clear()
    res = await _run(_inp(rounds_max=1))
    assert [t.role for t in TURNS] == ["coder", "critic"]
    # The critic is fenced by its own role file, not by the lead's run knobs.
    critic = TURNS[1]
    assert critic.writes is False
    assert critic.harness is HarnessKind.CLAUDE_CODE
    assert critic.model == "anthropic:opus-5"
    # Both turns are on the round's record, so an abandoned attempt and a
    # per-role cost stay countable.
    assert len(res.rounds[0].turns) == 2


async def test_round_two_carries_round_ones_critique():
    """The whole reason the critic exists: the lead must SEE the criticism."""
    TURNS.clear()
    await _run(_inp(rounds_max=2))
    lead_r2 = [t for t in TURNS if t.role == "coder" and t.round == 2][0]
    assert "no timeout" in lead_r2.prompt
    assert "api.py:20" in lead_r2.prompt


async def test_the_critique_is_delivered_as_labelled_data():
    """Untrusted input: a model's findings enter another model's prompt, so
    they must arrive fenced and labelled rather than as free instructions."""
    TURNS.clear()
    await _run(_inp(rounds_max=2))
    lead_r2 = [t for t in TURNS if t.role == "coder" and t.round == 2][0]
    assert "BEGIN CRITIC OUTPUT" in lead_r2.prompt
    assert "END CRITIC OUTPUT" in lead_r2.prompt


async def test_the_critic_gets_its_own_session_not_the_leads():
    """Two roles, two conversations. Sharing one session id would resume the
    critic into the lead's context and destroy the decorrelation ADR-6 is
    protecting."""
    TURNS.clear()
    res = await _run(_inp(rounds_max=2))
    assert res.sessions["coder"] == "s-coder"
    assert res.sessions["critic"] == "s-critic"
    r2 = [t for t in TURNS if t.round == 2]
    assert {t.role: t.session_id for t in r2} == {
        "coder": "s-coder", "critic": "s-critic"}


async def test_the_verdict_lands_on_the_round_record():
    TURNS.clear()
    res = await _run(_inp(rounds_max=1))
    assert res.rounds[0].verdict == "needs_work"
    assert "no timeout" in res.rounds[0].critique
