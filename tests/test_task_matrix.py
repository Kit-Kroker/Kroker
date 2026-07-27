from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.task_matrix import build_task_matrix
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.models import HarnessKind


def _suite():
    return TaskSuite(case_id="c1", tasks=[
        TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
        TaskSpec(id="t02", error_class="security", rubric="r"),
    ])


def _rec(*, run="b1", cell_model="m1", task_id, score, started):
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{cell_model}", bench_run_id=run,
        case_id="c1", scope=BenchmarkScope.ORACLE_TASK, stage="oracle",
        task_id=task_id, role="oracle", harness=HarnessKind.OPENCODE,
        model=cell_model, quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=started,
                      ended_at=started + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0
        else BenchmarkOutcome.FAIL)


def test_build_task_matrix_one_column_per_run_cell():
    t0 = datetime(2026, 7, 20, 10)
    t1 = datetime(2026, 7, 21, 10)
    recs = [
        _rec(run="b1", task_id="t01", score=1.0, started=t0),
        _rec(run="b1", task_id="t02", score=0.0, started=t0),
        _rec(run="b2", task_id="t01", score=0.5, started=t1),
    ]
    tm = build_task_matrix("c1", recs, _suite())
    assert tm.task_ids == ["t01", "t02"]
    assert len(tm.columns) == 2
    assert [c.bench_run_id for c in tm.columns] == ["b1", "b2"]  # chronological


def test_build_task_matrix_missing_task_is_none_not_zero():
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec(run="b1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    key = f"{tm.columns[0].bench_run_id}#{tm.columns[0].cell_id}"
    assert tm.scores["t01"][key] == 1.0
    assert tm.scores["t02"][key] is None


def test_build_task_matrix_mean_score_excludes_none():
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec(run="b1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    # only t01 has a score in this column; t02 is missing -> mean == t01's
    assert tm.columns[0].mean_score == 1.0


def test_build_task_matrix_filters_other_case_and_scope():
    t0 = datetime(2026, 7, 20, 10)
    other_case = _rec(run="b1", task_id="t01", score=1.0, started=t0)
    other_case.case_id = "other"
    stage_rec = BenchmarkRecord(
        run_id="b1/x", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.OPENCODE, model="m1",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0,
                      ended_at=t0 + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    tm = build_task_matrix("c1", [other_case, stage_rec], _suite())
    assert tm.columns == []


def test_build_task_matrix_empty_records_gives_empty_columns():
    tm = build_task_matrix("c1", [], _suite())
    assert tm.task_ids == ["t01", "t02"]
    assert tm.columns == []
