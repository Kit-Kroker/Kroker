"""Freeze/verify tests for the constitution stage (FR-112, plan Task 2)."""

from sdlc.stages.constitution.models import DraftOutput, DraftPrinciple, constitution_digest
from sdlc.stages.constitution.verify import freeze


def p(statement: str, source_ref: str | None = None) -> DraftPrinciple:
    """A minimal valid draft: MUST normative, optional source ref."""
    return DraftPrinciple(
        statement=statement, normative="MUST", rationale="because", source_ref=source_ref
    )


def test_brownfield_missing_source_ref_dropped():
    result = freeze(
        DraftOutput(principles=[p("A", source_ref="AGENTS.md"), p("B")]),
        mode="brownfield",
    )
    assert [pr.id for pr in result.frozen.principles] == ["CP-1"]
    assert result.frozen.principles[0].statement == "A"
    assert result.dropped == ["B"]
    assert not result.degraded


def test_greenfield_allows_missing_source_ref():
    result = freeze(DraftOutput(principles=[p("A"), p("B")]), mode="greenfield")
    assert [pr.id for pr in result.frozen.principles] == ["CP-1", "CP-2"]
    assert result.dropped == []
    assert result.frozen.digest == constitution_digest(result.frozen.principles)
    assert result.frozen.drafted_by == "agent"
    assert not result.degraded


def test_ids_assigned_and_duplicates_dropped():
    # Exact duplicates collapse to the first occurrence; case variants are not
    # duplicates ("a" survives beside "A") and ids follow surviving order.
    result = freeze(
        DraftOutput(principles=[p("A"), p("A"), p("B"), p("a")]),
        mode="greenfield",
    )
    assert [pr.id for pr in result.frozen.principles] == ["CP-1", "CP-2", "CP-3"]
    assert result.frozen.principles[0].statement == "A"
    assert result.dropped == ["A"]


def test_freeze_all_dropped_degrades():
    result = freeze(DraftOutput(principles=[p("A")]), mode="brownfield")
    assert result.degraded
    assert result.frozen.principles == []
    assert result.frozen.digest == ""
    assert result.frozen.drafted_by == "empty"
    assert result.dropped == ["A"]


def test_empty_draft_degrades():
    result = freeze(DraftOutput(), mode="greenfield")
    assert result.degraded
    assert result.frozen.principles == []
    assert result.frozen.digest == ""
    assert result.frozen.drafted_by == "empty"
    assert result.dropped == []


def test_empty_statement_dropped_as_noise():
    # Empty/whitespace-only statements are model noise: dropped, never raised.
    result = freeze(DraftOutput(principles=[p(""), p("A"), p("  ")]), mode="greenfield")
    assert [pr.id for pr in result.frozen.principles] == ["CP-1"]
    assert result.frozen.principles[0].statement == "A"
    assert result.dropped == ["", "  "]
