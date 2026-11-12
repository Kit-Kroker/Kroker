"""Artifact-model tests for the constitution stage (FR-112, plan Task 1)."""

from sdlc.stages.constitution.models import DraftPrinciple, constitution_digest


def p(statement: str) -> DraftPrinciple:
    """A minimal valid draft: MUST normative, no source ref."""
    return DraftPrinciple(statement=statement, normative="MUST", rationale="because")


def test_digest_empty_is_sentinel():
    assert constitution_digest([]) == ""


def test_digest_stable_and_order_insensitive():
    a = constitution_digest([p("A"), p("B")])
    b = constitution_digest([p("B"), p("A")])
    assert a == b and len(a) == 64


def test_draft_output_has_no_ids():
    # DraftPrinciple must not carry an id field — ids are code-assigned.
    assert "id" not in DraftPrinciple.model_fields
