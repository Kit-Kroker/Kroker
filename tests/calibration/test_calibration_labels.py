"""C7: realized-outcome labels (ruling OQ9).

The label is the quantity the whole verdict is a function of, so each formula
is pinned exactly rather than described. Both labels are "1 - badness", so a
clean run labels near 1.0 and a bad one near 0.0, on the same [0, 1] scale the
self-reported confidence uses.
"""

from sdlc.calibration.labels import fix_attempt_label, plan_drift_label, unhinted_ratio
from sdlc.stages.plan.models import PlanDrift


def _drift(hinted: int, touched: int, unhinted: list[str]) -> PlanDrift:
    return PlanDrift(
        files_hinted=hinted,
        files_touched=touched,
        hinted_untouched=[],
        touched_unhinted=unhinted,
    )


def test_unhinted_ratio_is_touched_unhinted_over_files_touched():
    """Ruling OQ9(1): the CONTINUOUS ratio, not merge's binary threshold flag."""
    assert unhinted_ratio(_drift(4, 4, ["a.py", "b.py"])) == 0.5


def test_unhinted_ratio_of_a_perfectly_hinted_task_is_zero():
    assert unhinted_ratio(_drift(3, 3, [])) == 0.0


def test_unhinted_ratio_guards_zero_files_touched():
    """compute_plan_drift never emits files_touched=0 (plan/models.py:52-54
    returns None first), but the ratio must not be the one place a future
    caller discovers that by ZeroDivisionError."""
    assert unhinted_ratio(_drift(2, 0, [])) == 0.0


def test_plan_drift_label_inverts_the_mean_ratio():
    assert plan_drift_label([0.0, 0.5]) == 0.75


def test_plan_drift_label_clamps_to_zero():
    """touched_unhinted can exceed files_touched only if a caller builds an
    inconsistent PlanDrift, but the label's contract is [0, 1] regardless."""
    assert plan_drift_label([1.5]) == 0.0


def test_plan_drift_label_of_no_measured_tasks_is_none():
    """None means UNLABELLABLE, which means no sample -- not a 1.0 that would
    silently vote 'the plan was perfect' for a run that measured nothing."""
    assert plan_drift_label([]) is None


def test_fix_attempt_label_is_one_minus_the_capped_mean():
    """max_fix_attempts=2: one stage took 0 attempts, one took 2 (capped).
    mean(0/2, 2/2) = 0.5 -> label 0.5."""
    assert fix_attempt_label([0, 2], max_fix_attempts=2) == 0.5


def test_fix_attempt_label_caps_runaway_attempts():
    assert fix_attempt_label([99], max_fix_attempts=2) == 0.0


def test_fix_attempt_label_of_a_clean_run_is_one():
    assert fix_attempt_label([0, 0, 0], max_fix_attempts=2) == 1.0


def test_fix_attempt_label_of_no_stages_is_none():
    assert fix_attempt_label([], max_fix_attempts=2) is None


def test_fix_attempt_label_guards_a_zero_cap():
    """cfg.max_fix_attempts is 2 by default (core/models.py:362) but is
    operator-settable; 0 must not divide."""
    assert fix_attempt_label([0], max_fix_attempts=0) is None
