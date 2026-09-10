"""C8: the merge gate grades lens presence.

Ruling OQ2: fail only on UNDECLARED_ABSENT or a missing outcome. DECLARED_ABSENT
and NOT_REACHED pass and are still reported. Ruling OQ3: one uniform check.
"""

from sdlc.gate import CheckClass
from sdlc.stages.merge.step import _lens_presence_check
from sdlc.stages.review.lenses import LensOutcome, LensPresence
from sdlc.workflows.models import TaskResult


def _result(task_id: str, *outcomes: LensOutcome) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status="done",
        attempts=1,
        branch="b",
        lens_outcomes=list(outcomes),
    )


def _present(lens: str) -> LensOutcome:
    return LensOutcome(lens=lens, presence=LensPresence.PRESENT, approved=True)


def _absent(lens: str, presence: LensPresence) -> LensOutcome:
    return LensOutcome(lens=lens, presence=presence, reason=f"{lens} {presence.value}")


def test_check_is_advisory_and_uniform_across_both_lenses():
    """OQ3: one check, not a per-lens pair."""
    check = _lens_presence_check([_result("t1", _present("reviewer"), _present("adversary"))])
    assert check.name == "review_lenses_present"
    assert check.classification is CheckClass.ADVISORY
    assert check.passed is True


def test_undeclared_absent_fails_and_names_the_lens():
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT))]
    )
    assert check.passed is False
    assert "adversary" in check.detail
    assert "t1" in check.detail


def test_declared_absent_passes_but_is_still_reported():
    """The operator's declaration is honoured -- and never silent."""
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.DECLARED_ABSENT))]
    )
    assert check.passed is True
    assert "declared_absent" in check.detail
    assert "adversary" in check.detail


def test_not_reached_passes_but_is_still_reported():
    """Reviewer A1: routine pipeline geometry is not broken wiring."""
    check = _lens_presence_check(
        [_result("t1", _present("reviewer"), _absent("adversary", LensPresence.NOT_REACHED))]
    )
    assert check.passed is True
    assert "not_reached" in check.detail


def test_empty_outcomes_list_fails():
    """The empty-list defense. A producer that predates the field has no
    UNDECLARED_ABSENT entry to trip on, so the rule must fail on a MISSING
    outcome too -- otherwise it sails through."""
    check = _lens_presence_check([_result("t-legacy")])
    assert check.passed is False
    assert "no outcome recorded" in check.detail


def test_a_lens_missing_from_a_populated_list_fails():
    check = _lens_presence_check([_result("t1", _present("reviewer"))])
    assert check.passed is False
    assert "adversary" in check.detail


def test_any_task_fires():
    """Aggregation matches plan_drift: one bad task fails the run."""
    good = _result("t1", _present("reviewer"), _present("adversary"))
    bad = _result("t2", _present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT))
    assert _lens_presence_check([good, bad]).passed is False
    assert _lens_presence_check([good, good]).passed is True


def test_quarantined_tasks_are_graded_too():
    """Unfiltered by status, matching review_severity and plan_drift."""
    tr = TaskResult(
        task_id="t-q",
        status="quarantined",
        attempts=2,
        branch="b",
        lens_outcomes=[_present("reviewer"), _absent("adversary", LensPresence.UNDECLARED_ABSENT)],
    )
    assert _lens_presence_check([tr]).passed is False


def test_no_task_results_passes():
    check = _lens_presence_check([])
    assert check.passed is True
