# tests/test_crew_protocol.py
"""E-88 step 1: the round protocol must be DELIVERED, not just validated.
`CrewRole.skill` is boot-checked and then dropped; unless the lead's
SKILL.md is rendered into the round brief, nothing ever tells the agent to
write `.workspace/orchestration/<layout>/round-<n>/notes.md` as notes-v1."""

from __future__ import annotations

import asyncio
import json

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.crew.activities import (
    CrewProtocolError,
    LoadCrewInput,
    ReadRoundInput,
    load_crew,
    read_round,
)
from sdlc.crew.worktree import round_dir
from sdlc.workflows.crew import CrewTaskInput, CrewTaskWorkflow

_CODE_MODEL = "zai-coding-plan/glm-5.3"  # crew/roles/coder.yaml


def _brief_inp(**kw):
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
        deliverable_path="notes.md",
    )
    base.update(kw)
    return CrewTaskInput(**base)


def test_load_crew_returns_the_leads_protocol():
    """The shipped SKILL.md's notes-v1 JSON block rides on LoadedCrew."""
    crew = asyncio.run(load_crew(LoadCrewInput(layout="code", lead_model=_CODE_MODEL)))
    assert crew.protocol
    assert "notes-v1" in crew.protocol


def test_load_crew_fails_closed_without_a_lead_model():
    """ADR-6 guard (spec §5, finding 5): the crew role file's model never
    enters check_adr6_families, so a run that named no lead model in a
    validated layer (registry role, benchmark arm, run override) must not
    start."""
    with pytest.raises(ApplicationError) as exc:
        asyncio.run(load_crew(LoadCrewInput(layout="code")))
    assert exc.value.type == "crew_model_unresolved"
    assert exc.value.non_retryable


def test_the_round_brief_prepends_the_protocol_round_1():
    brief = CrewTaskWorkflow()._round_brief(_brief_inp(protocol="You are the lead of a crew..."), 1)
    assert brief.startswith("You are the lead of a crew...")
    assert "do the thing" in brief
    assert ".workspace/orchestration/code/round-1/notes.md" in brief


def test_the_round_brief_prepends_the_protocol_round_2():
    brief = CrewTaskWorkflow()._round_brief(_brief_inp(protocol="You are the lead of a crew..."), 2)
    assert brief.startswith("You are the lead of a crew...")
    assert "This is round 2." in brief
    assert ".workspace/orchestration/code/round-2/notes.md" in brief


def test_an_empty_protocol_still_carries_the_round_path():
    """No protocol: the brief is the assignment plus the round line — the
    agent must learn its round number and exact note path even when the
    skill text never loaded."""
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 1) == (
        "do the thing\n\nThis is round 1. Write your round note to "
        ".workspace/orchestration/code/round-1/notes.md."
    )
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 2) == (
        "do the thing\n\nThis is round 2. Your previous round's note is at "
        "round-1/notes.md. Continue from it; do not restate it.\n\nWrite this "
        "round's note to .workspace/orchestration/code/round-2/notes.md."
    )


def test_the_round_path_follows_the_layout():
    """The path is composed from the input's layout, not the skill's
    hardcoded `code` example (spec §5: layouts are the crew's axis)."""
    brief = CrewTaskWorkflow()._round_brief(_brief_inp(layout="infra"), 1)
    assert ".workspace/orchestration/infra/round-1/notes.md" in brief


@pytest.mark.asyncio
async def test_read_round_returns_the_critics_advisory_and_verdict(tmp_path):
    """The critic's output is what round N+1 has to react to; unread, the
    critic is spend with no consumer."""
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    (d / "advisor.md").write_text(
        json.dumps(
            {
                "schema": "advisor-v1",
                "assessment": "the retry path is untested",
                "risks": "a flake would look like a bug",
            }
        ),
        encoding="utf-8",
    )
    (d / "review.json").write_text(
        json.dumps(
            {
                "schema": "review-v1",
                "verdict": "needs_work",
                "findings": [
                    {
                        "severity": "major",
                        "where": "api.py:20",
                        "what": "no timeout on the outbound call",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = await read_round(
        ReadRoundInput(worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.missing is False
    assert out.verdict == "needs_work"
    assert "the retry path is untested" in out.critique
    assert "no timeout on the outbound call" in out.critique
    assert "api.py:20" in out.critique


@pytest.mark.asyncio
async def test_read_round_is_fine_with_no_critic_output(tmp_path):
    """A one-role crew writes neither file, and that is the shipped step-1
    layout -- absence is not a protocol violation."""
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    out = await read_round(
        ReadRoundInput(worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md")
    )
    assert out.critique == ""
    assert out.verdict is None


@pytest.mark.asyncio
async def test_an_unknown_advisory_schema_is_an_error(tmp_path):
    """Untrusted input: an unknown schema is refused, never parsed
    best-effort."""
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    (d / "advisor.md").write_text(
        json.dumps({"schema": "advisor-v2", "assessment": "x"}), encoding="utf-8"
    )
    with pytest.raises(CrewProtocolError, match="advisor-v1"):
        await read_round(
            ReadRoundInput(
                worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md"
            )
        )


@pytest.mark.asyncio
async def test_an_unknown_review_verdict_is_an_error(tmp_path):
    """'verdict' drives a control decision, so it is a closed set. A free
    string would let a model invent an outcome the workflow never planned
    for."""
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    (d / "review.json").write_text(
        json.dumps({"schema": "review-v1", "verdict": "ship it", "findings": []}), encoding="utf-8"
    )
    with pytest.raises(CrewProtocolError):
        await read_round(
            ReadRoundInput(
                worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md"
            )
        )


@pytest.mark.asyncio
async def test_a_question_needs_a_class_and_evidence(tmp_path):
    """E-87 §7's guard, kept: a question carrying neither a class nor
    evidence is not a question, and forwarding it would spend a human's
    attention on an agent that did not do its reading."""
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    (d / "question.json").write_text(
        json.dumps(
            {
                "schema": "question-v1",
                "question": "which database?",
                "why_it_matters": "",
                "evidence": "",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CrewProtocolError, match="evidence"):
        await read_round(
            ReadRoundInput(
                worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md"
            )
        )


@pytest.mark.asyncio
async def test_a_well_formed_question_is_returned(tmp_path):
    d = round_dir(tmp_path, "code", 1)
    d.mkdir(parents=True)
    (d / "notes.md").write_text(
        json.dumps({"schema": "notes-v1", "what_changed": "c", "why": "w", "verification": "v"}),
        encoding="utf-8",
    )
    (d / "question.json").write_text(
        json.dumps(
            {
                "schema": "question-v1",
                "question": "which database?",
                "why_it_matters": "the schema module cannot be written without it",
                "evidence": "the brief names no store; grep found no config",
            }
        ),
        encoding="utf-8",
    )
    out = await read_round(
        ReadRoundInput(worktree=str(tmp_path), layout="code", round=1, deliverable_path="notes.md")
    )
    assert "which database?" in out.question
    assert "grep found no config" in out.question
