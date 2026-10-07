from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.task_matrix import build_task_matrix
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.core.models import (
    HarnessKind,
)


def _suite():
    return TaskSuite(
        case_id="c1",
        tasks=[
            TaskSpec(id="t01", error_class="functional", oracle_tests=["x::y"]),
            TaskSpec(id="t02", error_class="security", rubric="r"),
        ],
    )


def _rec(*, run="b1", cell_model="m1", task_id, score, started):
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{cell_model}",
        bench_run_id=run,
        case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id=task_id,
        role="oracle",
        harness=HarnessKind.OPENCODE,
        model=cell_model,
        quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(
            wall_clock_s=1.0, started_at=started, ended_at=started + timedelta(seconds=1)
        ),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0 else BenchmarkOutcome.FAIL,
    )


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
        run_id="b1/x",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m1",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )
    tm = build_task_matrix("c1", [other_case, stage_rec], _suite())
    assert tm.columns == []


def test_build_task_matrix_empty_records_gives_empty_columns():
    tm = build_task_matrix("c1", [], _suite())
    assert tm.task_ids == ["t01", "t02"]
    assert tm.columns == []


# --- 012 T010b (chaos seat): immunity, keying, pre-012 line -------------------


def _cell_rec(*, bench="b1", case="c1", cell_id="c1#opencode#a1", arm="a1"):
    from sdlc.benchmarks.models import CellStatus

    t0 = datetime(2026, 7, 20, 10)
    return BenchmarkRecord(
        run_id=f"{bench}/{cell_id}",
        bench_run_id=bench,
        case_id=case,
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=HarnessKind.OPENCODE,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
        kroker_commit="abc",
        tree_dirty=False,
        arm=arm,
        cell_id=cell_id,
        cell=CellStatus(
            pipeline_finished=True,
            code_finished=False,
            completed=False,
            last_stage="clarify",
            grading="not_graded",
            child_result=None,
        ),
    )


def _rec012(*, run="b1", model="m1", arm="a1", task_id="t01", score=1.0, started):
    r = _rec(run=run, cell_model=model, task_id=task_id, score=score, started=started)
    return r.model_copy(
        update={
            "kroker_commit": "abc",
            "tree_dirty": False,
            "arm": arm,
            "cell_id": f"c1#opencode#{arm}",
        }
    )


def test_cell_record_and_not_evaluated_change_no_column():
    """Contract 7.6/7.8: a cell-scope record adds no column; a not_evaluated
    ORACLE_TASK-shaped record with score None changes no mean."""
    t0 = datetime(2026, 7, 20, 10)
    base = [
        _rec(run="b1", task_id="t01", score=1.0, started=t0),
        _rec(run="b1", task_id="t02", score=0.0, started=t0),
    ]
    tm = build_task_matrix("c1", base, _suite())
    not_evaluated = _rec(run="b1", task_id="t01", score=None, started=t0)
    not_evaluated = not_evaluated.model_copy(update={"outcome": BenchmarkOutcome.NOT_EVALUATED})
    tm2 = build_task_matrix("c1", base + [_cell_rec(), not_evaluated], _suite())
    assert [c.model_dump() for c in tm2.columns] == [c.model_dump() for c in tm.columns]
    assert tm2.scores == tm.scores


def test_012_record_is_keyed_by_cell_id_and_labeled_by_arm():
    """Contract 7.7: a 012 oracle-task record lands in the column its
    cell_id names (today the key is case#harness#model, so a record whose
    arm differs from its model would land in the wrong column) and the
    column's model label is arm_label."""
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec012(run="b1", model="m1", arm="a1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    assert len(tm.columns) == 1
    assert tm.columns[0].cell_id == "c1#opencode#a1"
    assert tm.columns[0].model == "a1"
    key = f"{tm.columns[0].bench_run_id}#{tm.columns[0].cell_id}"
    assert tm.scores["t01"][key] == 1.0


def test_pre012_record_keeps_base_key_and_label():
    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec(run="b1", cell_model="m1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    assert tm.columns[0].cell_id == "c1#opencode#m1"
    assert tm.columns[0].model == "m1"


def test_task_matrix_carries_the_pre012_count_when_present():
    from sdlc.benchmarks.task_matrix import render_task_matrix_html, render_task_matrix_json

    t0 = datetime(2026, 7, 20, 10)
    recs = [
        _rec(run="b1", cell_model="m1", task_id="t01", score=1.0, started=t0),
        _rec012(run="b1", model="m2", arm="a1", task_id="t01", score=1.0, started=t0),
        _cell_rec(),  # cell-scope records are not counted
    ]
    tm = build_task_matrix("c1", recs, _suite())
    assert "includes 1 pre-012 records (untrusted)" in render_task_matrix_html(tm)
    import json

    assert json.loads(render_task_matrix_json(tm))["pre012_records"] == 1


def test_task_matrix_has_no_pre012_line_when_count_is_zero():
    from sdlc.benchmarks.task_matrix import render_task_matrix_html, render_task_matrix_json

    t0 = datetime(2026, 7, 20, 10)
    recs = [_rec012(run="b1", model="m1", arm="a1", task_id="t01", score=1.0, started=t0)]
    tm = build_task_matrix("c1", recs, _suite())
    assert "pre-012" not in render_task_matrix_html(tm)
    import json

    assert json.loads(render_task_matrix_json(tm))["pre012_records"] == 0
