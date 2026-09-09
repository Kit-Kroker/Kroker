"""E4: plan drift as a merge-gate advisory check.

Only touched_unhinted drives the threshold -- hinted_untouched (over-hinting)
is harmless and ignored. Single-file tasks never flag (no calibration signal
at n=1). Aggregation across tasks is "any task fires", never averaged.
"""

from sdlc.gate import CheckClass
from sdlc.stages.merge.step import _plan_drift_check, _plan_drift_flags
from sdlc.stages.plan.models import PlanDrift
from sdlc.workflows.models import TaskResult


def _drift(files_touched: int, touched_unhinted: list[str], hinted_untouched=None) -> PlanDrift:
    return PlanDrift(
        files_hinted=files_touched,
        files_touched=files_touched,
        hinted_untouched=hinted_untouched or [],
        touched_unhinted=touched_unhinted,
    )


def _result(task_id: str, drift: PlanDrift | None) -> TaskResult:
    return TaskResult(task_id=task_id, status="done", attempts=1, branch="b", plan_drift=drift)


# -- _plan_drift_flags: per-task predicate --


def test_single_file_task_never_flags():
    drift = _drift(files_touched=1, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is False


def test_two_unhinted_touches_flags():
    drift = _drift(files_touched=2, touched_unhinted=["a.py", "b.py"])
    assert _plan_drift_flags(drift) is True


def test_one_unhinted_of_three_does_not_flag():
    drift = _drift(files_touched=3, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is False


def test_zero_unhinted_never_flags():
    drift = _drift(files_touched=5, touched_unhinted=[])
    assert _plan_drift_flags(drift) is False


def test_ratio_boundary_half_flags_via_ratio_alone():
    # 1 of 2 touched files unhinted: count (1) is below the >=2 arm, so this
    # isolates the ratio arm -- ratio == 0.5, at the threshold, must still flag.
    drift = _drift(files_touched=2, touched_unhinted=["a.py"])
    assert _plan_drift_flags(drift) is True


def test_hinted_untouched_is_ignored():
    # Heavy over-hinting, zero unhinted touches: must not flag.
    drift = _drift(files_touched=2, touched_unhinted=[], hinted_untouched=["x.py", "y.py", "z.py"])
    assert _plan_drift_flags(drift) is False


# -- _plan_drift_check: run-level aggregation and CheckResult shape --


def test_all_clean_passes():
    # _drift(2, ["a.py"]) would itself flag (1/2 = 0.5 ratio) -- use 3-touched
    # tasks so both results genuinely stay under threshold (1/3 = 0.33).
    results = [_result("t1", _drift(3, [])), _result("t2", _drift(3, ["a.py"]))]
    check = _plan_drift_check(results)
    assert check.name == "plan_drift"
    assert check.passed is True
    assert check.classification is CheckClass.ADVISORY


def test_one_drifted_task_fails_the_whole_check():
    results = [
        _result("t1", _drift(3, [])),
        _result("t2", _drift(2, ["a.py", "b.py"])),  # flags
    ]
    check = _plan_drift_check(results)
    assert check.passed is False
    assert "t2" in check.detail


def test_many_tasks_each_below_threshold_pass_by_design():
    """The aggregation is per-task 'any fires', not a fleet-wide average or
    sum -- ten tasks that each individually stay under the threshold pass,
    because none of them individually crosses it. This is the accepted
    shape of the check, not a bug: §5 of the spec chose per-task predicate
    + any-fires aggregation over a fleet-wide accumulator."""
    results = [_result(f"t{i}", _drift(3, ["a.py"])) for i in range(10)]
    # Each task individually: 1 unhinted of 3 touched -> ratio 0.33, count 1 -> no flag.
    check = _plan_drift_check(results)
    assert check.passed is True


def test_one_task_over_threshold_fails_even_among_many_clean_ones():
    """The complementary case: aggregation is 'any fires', so one drifted
    task among many clean ones still fails the check -- confirms failure
    isn't diluted by fleet size either."""
    results = [_result(f"t{i}", _drift(3, ["a.py"])) for i in range(9)]
    results.append(_result("t9", _drift(2, ["x.py", "y.py"])))  # flags
    check = _plan_drift_check(results)
    assert check.passed is False
    assert "t9" in check.detail


def test_unmeasured_drift_does_not_fail_the_check():
    results = [_result("t1", None), _result("t2", None)]
    check = _plan_drift_check(results)
    assert check.passed is True
    assert "unmeasured" in check.detail or "no task" in check.detail


def test_quarantined_task_drift_still_counts():
    """merge/step.py reads results_list unconditionally; a quarantined task's
    drift must not be filtered out (matches the review_severity precedent)."""
    quarantined = TaskResult(
        task_id="t1",
        status="quarantined",
        attempts=3,
        branch="b",
        plan_drift=_drift(2, ["a.py", "b.py"]),
    )
    check = _plan_drift_check([quarantined])
    assert check.passed is False
    assert "t1" in check.detail


# -- manifest membership (C3's fail-closed synthesis must cover plan_drift) --


def test_plan_drift_is_a_required_advisory_check():
    from sdlc.gate import MERGE_REQUIRED_CHECKS

    assert MERGE_REQUIRED_CHECKS["plan_drift"] is CheckClass.ADVISORY


def test_plan_drift_absent_from_gate_input_synthesizes_a_failing_check():
    from sdlc.gate import evaluate_quality_gate

    report = evaluate_quality_gate([])
    blocked = {c.name for c in report.checks if not c.passed}
    assert "plan_drift" in blocked


# -- waiver round-trip: rides the existing audited GateOverride path --


def test_plan_drift_failure_is_waivable_by_an_audited_override():
    from sdlc.gate import GateOverride, evaluate_quality_gate

    drifted = _result("t1", _drift(2, ["a.py"]))  # ratio 0.5 -> flags
    checks = [_plan_drift_check([drifted])]
    report = evaluate_quality_gate(
        checks,
        overrides=[
            GateOverride(check="plan_drift", approved_by="human", reason="known refactor spillover")
        ],
    )
    assert report.passed is False  # other required checks are still absent and unwaived
    assert "plan_drift" in report.overridden
