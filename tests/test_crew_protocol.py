# tests/test_crew_protocol.py
"""E-88 step 1: the round protocol must be DELIVERED, not just validated.
`CrewRole.skill` is boot-checked and then dropped; unless the lead's
SKILL.md is rendered into the round brief, nothing ever tells the agent to
write `.workspace/orchestration/<layout>/round-<n>/notes.md` as notes-v1."""
from __future__ import annotations

import asyncio

from sdlc.crew.activities import LoadCrewInput, load_crew
from sdlc.workflows.crew import CrewTaskInput, CrewTaskWorkflow


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
    crew = asyncio.run(load_crew(LoadCrewInput(layout="code")))
    assert crew.protocol
    assert "notes-v1" in crew.protocol


def test_the_round_brief_prepends_the_protocol_round_1():
    brief = CrewTaskWorkflow()._round_brief(
        _brief_inp(protocol="You are the lead of a crew..."), 1)
    assert brief.startswith("You are the lead of a crew...")
    assert "do the thing" in brief


def test_the_round_brief_prepends_the_protocol_round_2():
    brief = CrewTaskWorkflow()._round_brief(
        _brief_inp(protocol="You are the lead of a crew..."), 2)
    assert brief.startswith("You are the lead of a crew...")
    assert "This is round 2." in brief


def test_an_empty_protocol_keeps_the_old_brief_shape():
    """No protocol -> byte-identical to the pre-step-1 brief."""
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 1) == "do the thing"
    assert CrewTaskWorkflow()._round_brief(_brief_inp(), 2) == (
        "do the thing\n\nThis is round 2. Your previous round's note is at "
        "round-1/notes.md. Continue from it; do not restate it.")
