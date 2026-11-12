"""Artifact-model tests for the requirements stage (FR-113, plan Task 1)."""

from sdlc.stages.requirements.models import (
    DraftStory,
    FunctionalRequirement,
    Story,
    SuccessCriterion,
    requirements_digest,
)


def story(
    narrative: str,
    functional: list[str],
    success_criteria: list[str],
) -> Story:
    """A story with code-style ids — the digest must never see them."""
    return Story(
        id="US-1",
        narrative=narrative,
        functional=[
            FunctionalRequirement(id=f"FR-{i}", text=text) for i, text in enumerate(functional, 1)
        ],
        success_criteria=[
            SuccessCriterion(id=f"SC-{i}", text=text) for i, text in enumerate(success_criteria, 1)
        ],
    )


def test_digest_empty_is_sentinel():
    assert requirements_digest([]) == ""


def test_digest_stable_and_order_insensitive():
    a = requirements_digest(
        [
            story("As a user, I want A", ["f1", "f2"], ["s1"]),
            story("As a user, I want B", ["g1"], ["s2", "s3"]),
        ]
    )
    # Same stories, story order swapped.
    b = requirements_digest(
        [
            story("As a user, I want B", ["g1"], ["s2", "s3"]),
            story("As a user, I want A", ["f1", "f2"], ["s1"]),
        ]
    )
    # Same stories, text order shuffled within each story.
    c = requirements_digest(
        [
            story("As a user, I want A", ["f2", "f1"], ["s1"]),
            story("As a user, I want B", ["g1"], ["s3", "s2"]),
        ]
    )
    assert a == b == c and len(a) == 64


def test_draft_output_has_no_ids():
    # DraftStory must not carry an id field — ids are code-assigned.
    assert "id" not in DraftStory.model_fields
    # Its nested shapes are bare strings, so no id can hide there either.
    assert DraftStory.model_fields["functional"].annotation == list[str]
    assert DraftStory.model_fields["success_criteria"].annotation == list[str]
