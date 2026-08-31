# tests/test_crew_protocol.py
"""E-88 step 1: the round protocol must be DELIVERED, not just validated.
`CrewRole.skill` is boot-checked and then dropped; unless the lead's
SKILL.md is rendered into the round brief, nothing ever tells the agent to
write `.workspace/orchestration/<layout>/round-<n>/notes.md` as notes-v1."""
from __future__ import annotations

import asyncio

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.crew.activities import LoadCrewInput, load_crew
from sdlc.workflows.crew import CrewTaskInput, CrewTaskWorkflow

_CODE_MODEL = "zai-coding-plan/glm-5.3"       # crew/roles/coder.yaml


def _brief_inp(**kw):
    base = dict(
        layout="code", lead="coder",
        roles=[{"name": "coder", "harness": "opencode", "model": "glm-5.3",
                "writes": True, "skill": "coder"}],
        prompt="do the thing", worktree="/w",
        deliverable_path="notes.md")
    base.update(kw)
    return CrewTaskInput(**base)


def test_load_crew_returns_the_leads_protocol():
    """The shipped SKILL.md's notes-v1 JSON block rides on LoadedCrew."""
    crew = asyncio.run(load_crew(LoadCrewInput(
        layout="code", lead_model=_CODE_MODEL)))
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
    brief = CrewTaskWorkflow()._round_brief(
        _brief_inp(protocol="You are the lead of a crew..."), 1)
    assert brief.startswith("You are the lead of a crew...")
    assert "do the thing" in brief
    assert ".workspace/orchestration/code/round-1/notes.md" in brief


def test_the_round_brief_prepends_the_protocol_round_2():
    brief = CrewTaskWorkflow()._round_brief(
        _brief_inp(protocol="You are the lead of a crew..."), 2)
    assert brief.startswith("You are the lead of a crew...")
    assert "This is round 2." in brief
    assert ".workspace/orchestration/code/round-2/notes.md" in brief


def test_an_empty_protocol_still_carries_the_round_path():
    """No protocol: the brief is the assignment plus the round line — the
    agent must learn its round number and exact note path even when the
    skill text never loaded."""
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 1) == (
        "do the thing\n\nThis is round 1. Write your round note to "
        ".workspace/orchestration/code/round-1/notes.md.")
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 2) == (
        "do the thing\n\nThis is round 2. Your previous round's note is at "
        "round-1/notes.md. Continue from it; do not restate it. Write this "
        "round's note to .workspace/orchestration/code/round-2/notes.md.")


def test_the_round_path_follows_the_layout():
    """The path is composed from the input's layout, not the skill's
    hardcoded `code` example (spec §5: layouts are the crew's axis)."""
    brief = CrewTaskWorkflow()._round_brief(_brief_inp(layout="infra"), 1)
    assert ".workspace/orchestration/infra/round-1/notes.md" in brief
