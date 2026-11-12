"""render_requirements: the bounded downstream prompt block (FR-113, Task 7).

Clarify imports this helper from the requirements slice (producer owns its
artifacts — the render_constitution precedent), so its contract is pinned
here at the producer:

- a requirements artifact with no stories renders to "" (FR-010: a run
  that never saw a requirements draft must build byte-identical prompts
  to one handed the flag-off empty artifact);
- each story renders as one US line — id, narrative, source_ref in
  brackets when present — with its FR and SC lines nested beneath it;
- truncation is deterministic and the result never exceeds max_chars.
"""

from __future__ import annotations

from sdlc.stages.requirements.models import (
    FunctionalRequirement,
    Requirements,
    Story,
    SuccessCriterion,
)
from sdlc.stages.requirements.prompts import render_requirements


def _requirements(n: int, narrative: str) -> Requirements:
    stories = [
        Story(
            id=f"US-{i + 1}",
            narrative=f"{narrative} #{i + 1}",
            functional=[FunctionalRequirement(id=f"FR-{i + 1}", text=f"behaves {i + 1}")],
            success_criteria=[SuccessCriterion(id=f"SC-{i + 1}", text=f"checks {i + 1}")],
            source_ref="src/app.py" if i == 0 else None,
        )
        for i in range(n)
    ]
    return Requirements(stories=stories, digest="d" * 64, drafted_by="agent")


def test_empty_requirements_renders_empty_string():
    """The flag-off / nothing-survived-freeze artifact has no stories; its
    block must be "" so default-path prompts stay byte-identical (FR-010)."""
    empty = Requirements(stories=[], digest="", drafted_by="empty")
    assert render_requirements(empty) == ""


def test_lines_carry_us_fr_sc_and_source_ref():
    block = render_requirements(_requirements(2, "Slice a feature."))
    assert "US-1" in block and "US-2" in block
    assert "FR-1" in block and "FR-2" in block
    assert "SC-1" in block and "SC-2" in block
    assert "Slice a feature. #1" in block and "Slice a feature. #2" in block
    assert "[src/app.py]" in block  # source_ref present -> rendered
    assert "[]" not in block  # absent source_ref -> no empty bracket


def test_fr_and_sc_lines_nest_under_the_story_line():
    """One US header line per story; its FR/SC lines indented beneath it —
    the block format the design pins (spec §7 prompts.py)."""
    block = render_requirements(_requirements(1, "Slice."))
    lines = block.splitlines()
    assert lines[0] == "Requirements — drafted user stories:"
    assert lines[1] == "- US-1 Slice. #1 [src/app.py]"
    assert lines[2] == "  - FR-1 behaves 1"
    assert lines[3] == "  - SC-1 checks 1"


def test_truncation_never_exceeds_max_chars():
    big = _requirements(6, "x" * 500)
    for limit in (300, 120, 40):
        block = render_requirements(big, max_chars=limit)
        assert len(block) <= limit, limit
        assert block.endswith("…"), limit


def test_truncation_is_deterministic():
    big = _requirements(6, "x" * 500)
    assert render_requirements(big, max_chars=300) == render_requirements(big, max_chars=300)


def test_small_requirements_is_not_truncated():
    small = _requirements(1, "Be nice.")
    block = render_requirements(small)
    assert "Be nice." in block
    assert not block.endswith("…")
