"""render_constitution: the bounded downstream prompt block (FR-112, Task 8).

The three post-constitution proposer stages import this helper from the
constitution slice (producer owns its artifacts — the render_for_prompt
precedent), so its contract is pinned here at the producer:

- a constitution with no principles renders to "" (FR-010: a run that never
  saw a constitution must build byte-identical prompts to one handed the
  flag-off empty artifact);
- each principle renders as one numbered line: id, normative, statement,
  and source_ref when present;
- truncation is deterministic and the result never exceeds max_chars.
"""

from __future__ import annotations

from sdlc.stages.constitution.models import Constitution, Principle
from sdlc.stages.constitution.prompts import render_constitution


def _constitution(n: int, statement: str) -> Constitution:
    principles = [
        Principle(
            id=f"CP-{i + 1}",
            statement=f"{statement} #{i + 1}",
            normative="MUST" if i % 2 == 0 else "SHOULD",
            rationale="why",
            source_ref="AGENTS.md" if i == 0 else None,
        )
        for i in range(n)
    ]
    return Constitution(principles=principles, digest="d" * 64, drafted_by="agent")


def test_empty_constitution_renders_empty_string():
    """The flag-off / nothing-survived artifact has no principles; its block
    must be "" so default-path prompts stay byte-identical (FR-010)."""
    empty = Constitution(principles=[], digest="", drafted_by="empty")
    assert render_constitution(empty) == ""


def test_lines_carry_id_normative_statement_and_source_ref():
    block = render_constitution(_constitution(2, "Be bounded."))
    assert "CP-1" in block and "CP-2" in block
    assert "MUST" in block and "SHOULD" in block
    assert "Be bounded. #1" in block and "Be bounded. #2" in block
    assert "[AGENTS.md]" in block  # source_ref present -> rendered
    assert "[]" not in block  # absent source_ref -> no empty bracket


def test_truncation_never_exceeds_max_chars():
    big = _constitution(6, "x" * 500)
    for limit in (300, 120, 40):
        block = render_constitution(big, max_chars=limit)
        assert len(block) <= limit, limit
        assert block.endswith("…"), limit


def test_truncation_is_deterministic():
    big = _constitution(6, "x" * 500)
    assert render_constitution(big, max_chars=300) == render_constitution(big, max_chars=300)


def test_small_constitution_is_not_truncated():
    small = _constitution(1, "Be nice.")
    block = render_constitution(small)
    assert "Be nice." in block
    assert not block.endswith("…")
