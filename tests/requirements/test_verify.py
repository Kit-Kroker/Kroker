"""Deterministic partial-freeze tests for the requirements stage (FR-113,
plan Task 2): the model proposes, code validates — noise drops, ids assign
in surviving order, the artifact caps, and an empty survivor set degrades
instead of raising."""

from sdlc.stages.requirements.models import DraftOutput, DraftStory
from sdlc.stages.requirements.verify import freeze


def draft(*stories: DraftStory) -> DraftOutput:
    """A draft output from positional stories."""
    return DraftOutput(stories=list(stories))


def story(
    narrative: str = "As a user, I want X, so that Y",
    functional: tuple[str, ...] = ("The app saves the note",),
    success_criteria: tuple[str, ...] = ("The note persists across reload",),
    source_ref: str | None = None,
) -> DraftStory:
    """A draft story with defaults, so a test names only its deltas."""
    return DraftStory(
        narrative=narrative,
        functional=list(functional),
        success_criteria=list(success_criteria),
        source_ref=source_ref,
    )


def test_freeze_all_dropped_degrades():
    result = freeze(draft(story(narrative="   ")), mode="greenfield")
    assert result.degraded is True
    assert result.capped is False
    assert result.frozen.drafted_by == "empty"
    assert result.frozen.stories == []
    assert result.frozen.digest == ""
    # The empty draft degrades identically — nothing survived either way.
    empty = freeze(draft(), mode="greenfield")
    assert empty.degraded is True
    assert empty.frozen.drafted_by == "empty"
    assert empty.frozen.digest == ""


def test_global_dedup_across_stories():
    result = freeze(
        draft(
            story(functional=("Save the note", "Autosave drafts")),
            story(functional=("Save the note", "Export to PDF")),
        ),
        mode="greenfield",
    )
    # The duplicate keeps its first home only; the dedup is artifact-wide, so
    # it crosses the story boundary.
    first, second = result.frozen.stories
    assert [fr.text for fr in first.functional] == ["Save the note", "Autosave drafts"]
    assert [fr.text for fr in second.functional] == ["Export to PDF"]
    # Survivors renumber densely FR-1..FR-3 across the artifact.
    assert [fr.id for fr in first.functional] == ["FR-1", "FR-2"]
    assert [fr.id for fr in second.functional] == ["FR-3"]
    assert "Save the note" in result.dropped
    assert result.degraded is False


def test_brownfield_whitespace_source_ref_dropped():
    result = freeze(
        draft(
            story(source_ref="docs/prd.md"),
            story(source_ref="   "),  # whitespace-only ref counts as missing
            story(source_ref=None),
            story(),  # default ref is None
        ),
        mode="brownfield",
    )
    # Only the grounded story survives, as US-1 with dense renumber.
    assert [s.id for s in result.frozen.stories] == ["US-1"]
    assert result.frozen.stories[0].source_ref == "docs/prd.md"
    # One audit entry per dropped story (its narrative).
    assert len(result.dropped) == 3
    assert result.degraded is False


def test_greenfield_allows_missing_source_ref():
    result = freeze(
        draft(
            story(
                narrative="As a user, I want A",
                functional=("Save",),
                success_criteria=("Note stored",),
                source_ref=None,
            ),
            story(
                narrative="As a user, I want B",
                functional=("Load",),
                success_criteria=("Note shown",),
                source_ref="",
            ),
        ),
        mode="greenfield",
    )
    assert result.degraded is False
    assert [s.id for s in result.frozen.stories] == ["US-1", "US-2"]
    assert result.dropped == []


def test_ids_assigned_global_across_stories():
    result = freeze(
        draft(
            story(functional=("a", "b"), success_criteria=("x",)),
            story(functional=("c",), success_criteria=("y", "z")),
        ),
        mode="greenfield",
    )
    first, second = result.frozen.stories
    # US ids run per story; FR and SC ids continue across stories — the
    # counters are artifact-global, never reset per story.
    assert [s.id for s in result.frozen.stories] == ["US-1", "US-2"]
    assert [fr.id for fr in first.functional] == ["FR-1", "FR-2"]
    assert [fr.id for fr in second.functional] == ["FR-3"]
    assert [sc.id for sc in first.success_criteria] == ["SC-1"]
    assert [sc.id for sc in second.success_criteria] == ["SC-2", "SC-3"]


def test_cap_keeps_first_and_flags():
    stories = [
        story(narrative=f"As a user, I want {i}", functional=(f"Behavior {i}",)) for i in range(3)
    ]
    result = freeze(draft(*stories), mode="greenfield", max_stories=2)
    assert result.capped is True
    assert result.degraded is False
    assert [s.narrative for s in result.frozen.stories] == [
        "As a user, I want 0",
        "As a user, I want 1",
    ]
    assert [s.id for s in result.frozen.stories] == ["US-1", "US-2"]
    # No cap argument means no cap…
    assert freeze(draft(*stories), mode="greenfield").capped is False
    # …and a cap the draft never reaches is invisible.
    assert freeze(draft(*stories), mode="greenfield", max_stories=5).capped is False


def test_story_without_functional_dropped():
    result = freeze(
        draft(
            story(narrative="No behavior", functional=("   ", "")),
            story(narrative="Has behavior", functional=("Works",)),
        ),
        mode="greenfield",
    )
    # A story left with zero surviving functional entries is not a story.
    assert [s.id for s in result.frozen.stories] == ["US-1"]
    assert result.frozen.stories[0].narrative == "Has behavior"
    assert result.frozen.stories[0].functional[0].id == "FR-1"  # dense renumber
    assert "No behavior" in result.dropped
    # The same drop via dedup: every FR is an earlier story's FR.
    dup_only = freeze(
        draft(story(functional=("Works",)), story(functional=("Works",))),
        mode="greenfield",
    )
    assert [s.id for s in dup_only.frozen.stories] == ["US-1"]
    assert dup_only.degraded is False


def test_zero_sc_survives_with_all_stories_intact():
    result = freeze(
        draft(
            story(narrative="As a user, I want A", functional=("Save",), success_criteria=()),
            story(narrative="As a user, I want B", functional=("Load",)),
        ),
        mode="greenfield",
    )
    # Zero criteria on a story is NOT a drop — the artifact-level "≥1 SC"
    # pin is a caller warning, never verify's decision.
    assert result.degraded is False
    assert [s.id for s in result.frozen.stories] == ["US-1", "US-2"]
    assert result.frozen.stories[0].success_criteria == []
    # The artifact-level miss itself is not a drop either.
    none_at_all = freeze(draft(story(success_criteria=())), mode="greenfield")
    assert [s.id for s in none_at_all.frozen.stories] == ["US-1"]
    assert none_at_all.degraded is False
