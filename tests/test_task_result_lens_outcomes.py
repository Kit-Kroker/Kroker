"""C8: TaskResult carries lens tombstones through to the merge gate."""

from sdlc.stages.review.lenses import LensOutcome, LensPresence
from sdlc.workflows.models import TaskResult


def test_task_result_defaults_to_no_lens_outcomes():
    """A producer that predates the field -- or an in-flight workflow crossing
    a deploy -- deserializes with an empty list. The merge gate grades that as
    a failure (Task 6); it must never read as 'all lenses fine'."""
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.lens_outcomes == []


def test_task_result_carries_lens_outcomes():
    outcomes = [
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT, approved=True),
        LensOutcome(
            lens="adversary",
            presence=LensPresence.NOT_REACHED,
            reason="adversary run site was never reached on this task",
        ),
    ]
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b", lens_outcomes=outcomes)
    assert [o.lens for o in tr.lens_outcomes] == ["reviewer", "adversary"]
    assert tr.lens_outcomes[1].presence is LensPresence.NOT_REACHED


def test_task_result_round_trips_lens_outcomes_through_json():
    """Temporal serializes this model; the tombstone must survive the trip."""
    tr = TaskResult(
        task_id="t1",
        status="quarantined",
        attempts=2,
        branch="b",
        lens_outcomes=[
            LensOutcome(
                lens="adversary",
                presence=LensPresence.UNDECLARED_ABSENT,
                reason="adversary ran but produced no report",
            )
        ],
    )
    restored = TaskResult.model_validate_json(tr.model_dump_json())
    assert restored.lens_outcomes[0].presence is LensPresence.UNDECLARED_ABSENT
    assert restored.lens_outcomes[0].approved is None
