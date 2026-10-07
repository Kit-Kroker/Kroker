from datetime import datetime, timedelta

from sdlc.benchmarks.error_matrix import build_error_matrix
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
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


def _rec(*, run, model, task_id, score):
    t = datetime(2026, 7, 20, 10)
    return BenchmarkRecord(
        run_id=f"{run}/c1#opencode#{model}",
        bench_run_id=run,
        case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id=task_id,
        role="oracle",
        harness=HarnessKind.OPENCODE,
        model=model,
        quality=QualityScore(score=score, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS if (score or 0) >= 1.0 else BenchmarkOutcome.FAIL,
    )


def test_build_error_matrix_averages_failure_mass_over_runs_for_same_arm():
    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),  # 1.0 failure mass
        _rec(run="b2", model="m1", task_id="t01", score=1.0),  # 0.0 failure mass
    ]
    em = build_error_matrix("c1", recs, _suite())
    cell = next(c for c in em.cells if c.arm_key == "opencode#m1" and c.error_class == "functional")
    assert cell.avg_failure_mass == 0.5  # (1.0 + 0.0) / 2 runs
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

    functional = next(
        c for c in em.cells if c.arm_key == "opencode#m1" and c.error_class == "functional"
    )
    security = next(
        c for c in em.cells if c.arm_key == "opencode#m1" and c.error_class == "security"
    )

    # Functional: both runs contributed (b1: score=0.5, b2: score=0.8)
    assert functional.n_runs == 2
    assert functional.avg_failure_mass == (0.5 + 0.2) / 2  # (1-0.5 + 1-0.8) / 2

    # Security: only run b2 contributed (b1 had score=None, filtered out)
    assert security.n_runs == 1
    assert security.avg_failure_mass == 0.8  # (1-0.2) / 1


# --- 012 T010b (chaos seat): immunity, keying, pre-012 line -------------------


def _cell_rec():
    from datetime import timedelta

    from sdlc.benchmarks.models import CellStatus

    t = datetime(2026, 7, 20, 10)
    return BenchmarkRecord(
        run_id="b1/c1#opencode#a1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=HarnessKind.OPENCODE,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
        kroker_commit="abc",
        tree_dirty=False,
        arm="a1",
        cell_id="c1#opencode#a1",
        cell=CellStatus(
            pipeline_finished=True,
            code_finished=False,
            completed=False,
            last_stage="clarify",
            grading="not_graded",
            child_result=None,
        ),
    )


def _rec012(*, run, model, arm, task_id, score):
    r = _rec(run=run, model=model, task_id=task_id, score=score)
    return r.model_copy(
        update={
            "kroker_commit": "abc",
            "tree_dirty": False,
            "arm": arm,
            "cell_id": f"c1#opencode#{arm}",
        }
    )


def test_cell_and_not_evaluated_records_change_no_cell():
    """Contract 7.6/7.8: a cell-scope record and a not_evaluated record
    (same task_id and model as an existing record) change no cell's average
    failure mass or run count."""
    recs = [_rec(run="b1", model="m1", task_id="t01", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    not_evaluated = _rec(run="b1", model="m1", task_id="t01", score=None)
    not_evaluated = not_evaluated.model_copy(update={"outcome": BenchmarkOutcome.NOT_EVALUATED})
    em2 = build_error_matrix("c1", recs + [_cell_rec(), not_evaluated], _suite())
    assert [c.model_dump() for c in em2.cells] == [c.model_dump() for c in em.cells]
    assert em2.arms == em.arms
    assert em2.max_value == em.max_value


def test_012_arm_key_uses_the_arm_label():
    """Contract 7.7: a 012 record's arm key is harness + the ARM, so two
    cells of one arm share a column across bench runs even when their
    model strings differ."""
    recs = [_rec012(run="b1", model="m1", arm="a1", task_id="t01", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.arms == ["opencode#a1"]
    cell = next(c for c in em.cells if c.error_class == "functional")
    assert cell.arm_key == "opencode#a1"
    assert cell.avg_failure_mass == 1.0


def test_pre012_arm_key_stays_harness_model_byte_identical():
    recs = [_rec(run="b1", model="m1", task_id="t01", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    assert em.arms == ["opencode#m1"]


def test_error_matrix_carries_the_pre012_count_when_present():
    import json

    from sdlc.benchmarks.error_matrix import render_error_matrix_html, render_error_matrix_json

    recs = [
        _rec(run="b1", model="m1", task_id="t01", score=0.0),
        _rec012(run="b1", model="m2", arm="a1", task_id="t01", score=0.5),
        _cell_rec(),  # cell-scope records are not counted
    ]
    em = build_error_matrix("c1", recs, _suite())
    assert "includes 1 pre-012 records (untrusted)" in render_error_matrix_html(em)
    assert json.loads(render_error_matrix_json(em))["pre012_records"] == 1


def test_error_matrix_has_no_pre012_line_when_count_is_zero():
    import json

    from sdlc.benchmarks.error_matrix import render_error_matrix_html, render_error_matrix_json

    recs = [_rec012(run="b1", model="m1", arm="a1", task_id="t01", score=0.0)]
    em = build_error_matrix("c1", recs, _suite())
    assert "pre-012" not in render_error_matrix_html(em)
    assert json.loads(render_error_matrix_json(em))["pre012_records"] == 0
