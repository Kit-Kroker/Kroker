from datetime import datetime, timedelta

from sdlc.benchmarks.error_matrix import build_error_matrix
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.models import HarnessKind


def _suite():
    return TaskSuite(case_id="c1", tasks=[
        TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
        TaskSpec(id="t02", error_class="security", rubric="r"),
    ])


def _rec(*, run, model, task_id, score):
    t = datetime(2026, 7, 20, 10)
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{model}", bench_run_id=run, case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id=task_id,
        role="oracle", harness=HarnessKind.OPENCODE, model=model,
        quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                      ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0
        else BenchmarkOutcome.FAIL)


def test_build_error_matrix_averages_failure_mass_over_runs_for_same_arm():
    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),  # 1.0 failure mass
        _rec(run="b2", model="m1", task_id="t01", score=1.0),  # 0.0 failure mass
    ]
    em = build_error_matrix("c1", recs, _suite())
    cell = next(c for c in em.cells if c.arm_key == "opencode#m1"
               and c.error_class == "functional")
    assert cell.avg_failure_mass == 0.5   # (1.0 + 0.0) / 2 runs
    assert cell.n_runs == 2


def test_build_error_matrix_keeps_arms_separate():
    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),
        _rec(run="b1", model="m2", task_id="t01", score=1.0),
    ]
    em = build_error_matrix("c1", recs, _suite())
    assert set(em.arms) == {"opencode#m1", "opencode#m2"}
    m1 = next(c for c in em.cells if c.arm_key == "opencode#m1")
    m2 = next(c for c in em.cells if c.arm_key == "opencode#m2")
    assert m1.avg_failure_mass == 1.0
    assert m2.avg_failure_mass == 0.0


def test_build_error_matrix_none_score_excluded():
    recs = [_rec(run="b1", model="m1", task_id="t01", score=None)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.cells == []


def test_build_error_matrix_unknown_task_id_ignored():
    recs = [_rec(run="b1", model="m1", task_id="not-in-suite", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.cells == []


def test_build_error_matrix_error_classes_in_canonical_order():
    recs = [
        _rec(run="b1", model="m1", task_id="t02", score=0.0),
        _rec(run="b1", model="m1", task_id="t01", score=0.0),
    ]
    em = build_error_matrix("c1", recs, _suite())
    # functional precedes security in ERROR_CLASSES
    assert em.error_classes == ["functional", "security"]


def test_build_error_matrix_empty_records():
    em = build_error_matrix("c1", [], _suite())
    assert em.cells == [] and em.arms == [] and em.max_value == 0.0


def test_build_error_matrix_n_runs_scoped_per_error_class():
    """Test heterogeneous coverage: one arm, two runs with different error classes.

    Run 1: scores only functional (t01), security (t02) gets score=None
    Run 2: scores both functional (t01) and security (t02)

    Expected: functional has n_runs=2 (both runs contributed),
              security has n_runs=1 (only run 2 contributed)
    """
    recs = [
        # Run b1: only functional task scores, security task skipped (score=None)
        _rec(run="b1", model="m1", task_id="t01", score=0.5),
        # Run b2: both functional and security tasks score
        _rec(run="b2", model="m1", task_id="t01", score=0.8),
        _rec(run="b2", model="m1", task_id="t02", score=0.2),
    ]
    em = build_error_matrix("c1", recs, _suite())

    functional = next(c for c in em.cells if c.arm_key == "opencode#m1"
                     and c.error_class == "functional")
    security = next(c for c in em.cells if c.arm_key == "opencode#m1"
                   and c.error_class == "security")

    # Functional: both runs contributed (b1: score=0.5, b2: score=0.8)
    assert functional.n_runs == 2
    assert functional.avg_failure_mass == (0.5 + 0.2) / 2  # (1-0.5 + 1-0.8) / 2

    # Security: only run b2 contributed (b1 had score=None, filtered out)
    assert security.n_runs == 1
    assert security.avg_failure_mass == 0.8  # (1-0.2) / 1
