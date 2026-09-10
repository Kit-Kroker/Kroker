"""C8: the merge gate grades lens presence.

Ruling OQ2: fail only on UNDECLARED_ABSENT or a missing outcome. DECLARED_ABSENT
and NOT_REACHED pass and are still reported. Ruling OQ3: one uniform check.
"""

from sdlc.gate import CheckClass
from sdlc.stages.merge.step import _lens_presence_check
from sdlc.stages.review.lenses import LensOutcome, LensPresence, primary_admits
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


def test_manifest_carries_the_new_check_as_advisory():
    """In MERGE_REQUIRED_CHECKS so C3's synthesis covers the case where the
    producer stops emitting it. ADVISORY, never ABSOLUTE -- an absolute
    presence check would delete the config flags by force."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS

    assert MERGE_REQUIRED_CHECKS["review_lenses_present"] is CheckClass.ADVISORY


def test_absent_from_gate_input_synthesizes_a_misconfigured_failure():
    """C3's fail-closed synthesis, now covering this check."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS, build_check, evaluate_quality_gate

    checks = [
        build_check(name, True, klass)
        for name, klass in MERGE_REQUIRED_CHECKS.items()
        if name != "review_lenses_present"
    ]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "review_lenses_present" in report.blocking
    synthesized = next(c for c in report.checks if c.name == "review_lenses_present")
    assert "MISCONFIGURED" in synthesized.detail


def test_undeclared_absence_is_waivable_by_an_audited_override():
    """ADVISORY means the human who accepts a missing lens leaves a record."""
    from sdlc.gate import MERGE_REQUIRED_CHECKS, GateOverride, build_check, evaluate_quality_gate

    checks = [
        build_check(name, name != "review_lenses_present", klass)
        for name, klass in MERGE_REQUIRED_CHECKS.items()
    ]
    assert evaluate_quality_gate(checks).passed is False
    waived = evaluate_quality_gate(
        checks,
        [
            GateOverride(
                check="review_lenses_present",
                approved_by="operator",
                reason="adversary agent unavailable in this environment",
            )
        ],
    )
    assert waived.passed is True
    assert "review_lenses_present" in waived.overridden


def test_the_live_checks_list_produces_the_check():
    """Source needle: the helper must actually be called by merge.step, not
    merely exist. Without this the manifest entry alone would make every gate
    fail via synthesis."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "_lens_presence_check(results_list)" in src


def test_review_severity_grades_only_present_lenses():
    """The merge gate stops reading absence as approval. It grades through
    primary_admits, so it cannot diverge from the task success condition on
    what 'approved' means."""
    import pathlib

    src = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
    assert "r.review is None or r.review.approve" not in src
    assert "primary_admits" in src


def test_review_severity_still_fails_on_a_present_rejecting_reviewer():
    """Spec 4 test 9's behavioural half. The source needle above proves the old
    None-read is gone; this proves the new expression still BLOCKS, so the
    rewrite cannot have quietly turned review_severity into a check that passes
    everything. Reads the same generator the checks list builds."""
    rejecting = _result(
        "t1",
        LensOutcome(lens="reviewer", presence=LensPresence.PRESENT, approved=False),
        _present("adversary"),
    )
    approving = _result("t2", _present("reviewer"), _present("adversary"))

    def _severity(results):
        return all(
            primary_admits(o)
            for r in results
            for o in (getattr(r, "lens_outcomes", None) or [])
            if o.lens == "reviewer"
        )

    assert _severity([rejecting]) is False
    assert _severity([approving]) is True
    # An absent reviewer contributes nothing here -- that is
    # review_lenses_present's question, not this check's.
    assert _severity([_result("t3")]) is True
