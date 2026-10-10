from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
    WasteBag,
)
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.benchmarks.waste_matrix import (
    WASTE_METRICS,
    build_waste_matrix,
    render_waste_matrix_html,
    render_waste_matrix_json,
)
from sdlc.core.models import (
    HarnessKind,
)

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _rec(
    *, task, bench="b1", run="r1", model="m", harness=HarnessKind.OPENCODE, waste=None, stage="code"
):
    return BenchmarkRecord(
        run_id=run,
        bench_run_id=bench,
        case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage=stage,
        task_id=task,
        role="dev",
        harness=harness,
        model=model,
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
        waste=waste,
    )


def _cell(wm, task, arm, metric):
    return next(
        c for c in wm.cells if c.task_id == task and c.arm_key == arm and c.metric == metric
    )


def test_six_metrics_are_gridded():
    """Volume metrics (file_reads, files_written, model_turns) and the
    boolean `compacted` ride on the record but are not waste grids."""
    assert WASTE_METRICS == [
        "tool_calls",
        "file_rereads",
        "rewrite_churn",
        "failed_commands",
        "denials",
        "escalations",
    ]


def test_attempts_sum_within_a_run():
    """Total thrash on a task is the meaningful quantity, not the
    per-attempt average."""
    recs = [
        _rec(task="t01", waste=WasteBag(tool_calls=10)),
        _rec(task="t01", waste=WasteBag(tool_calls=15)),
    ]
    wm = build_waste_matrix("c1", recs)
    assert _cell(wm, "t01", "opencode#m", "tool_calls").value == 25.0


def test_runs_are_averaged():
    recs = [
        _rec(task="t01", bench="b1", waste=WasteBag(tool_calls=10)),
        _rec(task="t01", bench="b2", run="r2", waste=WasteBag(tool_calls=20)),
    ]
    wm = build_waste_matrix("c1", recs)
    c = _cell(wm, "t01", "opencode#m", "tool_calls")
    assert c.value == 15.0 and c.n_runs == 2


def test_arms_separate_by_harness_and_model():
    recs = [
        _rec(task="t01", harness=HarnessKind.OPENCODE, model="m1", waste=WasteBag(tool_calls=10)),
        _rec(
            task="t01", harness=HarnessKind.CLAUDE_CODE, model="m1", waste=WasteBag(tool_calls=40)
        ),
    ]
    wm = build_waste_matrix("c1", recs)
    assert wm.arms == ["claude_code#m1", "opencode#m1"]
    assert _cell(wm, "t01", "claude_code#m1", "tool_calls").value == 40.0


def test_unmeasured_records_produce_no_cell():
    """waste=None means not measured; a cell would assert zero waste."""
    recs = [_rec(task="t01", waste=None)]
    wm = build_waste_matrix("c1", recs)
    assert wm.cells == []
    assert wm.task_ids == []


def test_rows_come_from_records_without_tasks_yaml():
    """cat-cafe-monitoring has no tasks.yaml and must still get a grid."""
    recs = [
        _rec(task="t02", waste=WasteBag(tool_calls=1)),
        _rec(task="t01", waste=WasteBag(tool_calls=1)),
    ]
    wm = build_waste_matrix("c1", recs, suite=None)
    assert wm.task_ids == ["t01", "t02"]


def test_suite_order_wins_when_present():
    suite = TaskSuite(
        case_id="c1",
        tasks=[
            TaskSpec(id="t02", error_class="functional", oracle_tests=["a::b"]),
            TaskSpec(id="t01", error_class="security", oracle_tests=["a::c"]),
        ],
    )
    recs = [
        _rec(task="t01", waste=WasteBag(tool_calls=1)),
        _rec(task="t02", waste=WasteBag(tool_calls=1)),
    ]
    wm = build_waste_matrix("c1", recs, suite=suite)
    assert wm.task_ids == ["t02", "t01"]


def test_other_cases_are_excluded():
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=5))]
    assert build_waste_matrix("other", recs).cells == []


def test_max_by_metric_scales_each_grid_independently():
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=100, denials=2))]
    wm = build_waste_matrix("c1", recs)
    assert wm.max_by_metric["tool_calls"] == 100.0
    assert wm.max_by_metric["denials"] == 2.0


def test_html_renders_a_section_per_metric_and_blank_for_absent():
    recs = [
        _rec(task="t01", model="m1", waste=WasteBag(tool_calls=7)),
        _rec(task="t02", model="m2", waste=WasteBag(tool_calls=3)),
    ]
    wm = build_waste_matrix("c1", recs)
    html = render_waste_matrix_html(wm)
    assert "<!doctype html>" in html
    for m in WASTE_METRICS:
        assert m in html
    # t01 has no opencode#m2 cell -- it must be blank, never "0"
    assert 'class="empty"></td>' in html


def test_html_is_escaped():
    recs = [_rec(task="<script>", waste=WasteBag(tool_calls=1))]
    html = render_waste_matrix_html(build_waste_matrix("c1", recs))
    assert "<script>" not in html.split("<style>")[1]


def test_json_round_trips():
    import json

    recs = [_rec(task="t01", waste=WasteBag(tool_calls=7))]
    data = json.loads(render_waste_matrix_json(build_waste_matrix("c1", recs)))
    assert data["case_id"] == "c1"
    assert data["cells"][0]["metric"] in WASTE_METRICS


def test_empty_records_render_without_raising():
    wm = build_waste_matrix("c1", [])
    assert "No waste records" in render_waste_matrix_html(wm)


# --- 012 T010b (chaos seat): immunity, keying, pre-012 line -------------------


def _cell_rec(*, arm="a1"):
    from sdlc.benchmarks.models import CellStatus

    return BenchmarkRecord(
        run_id=f"b1/c1#opencode#{arm}",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        harness=HarnessKind.OPENCODE,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T),
        outcome=BenchmarkOutcome.FAIL,
        kroker_commit="abc",
        tree_dirty=False,
        arm=arm,
        cell_id=f"c1#opencode#{arm}",
        cell=CellStatus(
            pipeline_finished=True,
            code_finished=False,
            completed=False,
            last_stage="clarify",
            grading="not_graded",
            child_result=None,
        ),
    )


def _rec012(*, task, model="m", arm="a1", bench="b1"):
    r = _rec(task=task, bench=bench, model=model, waste=WasteBag(tool_calls=5))
    return r.model_copy(
        update={
            "kroker_commit": "abc",
            "tree_dirty": False,
            "arm": arm,
            "cell_id": f"c1#opencode#{arm}",
        }
    )


def test_not_evaluated_record_changes_no_waste_value():
    """Contract 7.8: a not_evaluated record with the SAME task and arm as
    an existing record enters no mean and no run count -- even when it
    carries a WasteBag."""
    base = [
        _rec(task="t01", bench="b1", waste=WasteBag(tool_calls=10)),
        _rec(task="t01", bench="b2", waste=WasteBag(tool_calls=20)),
    ]
    wm = build_waste_matrix("c1", base)
    polluter = _rec(task="t01", bench="b1", waste=WasteBag(tool_calls=999)).model_copy(
        update={
            "outcome": BenchmarkOutcome.NOT_EVALUATED,
            "quality": QualityScore(score=None, judge="contract"),
        }
    )
    wm2 = build_waste_matrix("c1", base + [polluter, _cell_rec()])
    assert _cell(wm2, "t01", "opencode#m", "tool_calls") == _cell(
        wm, "t01", "opencode#m", "tool_calls"
    )


def test_012_arm_key_uses_the_arm_label():
    r = _rec012(task="t01", model="m1", arm="a1")
    wm = build_waste_matrix("c1", [r])
    assert wm.arms == ["opencode#a1"]
    assert _cell(wm, "t01", "opencode#a1", "tool_calls").arm_key == "opencode#a1"


def test_pre012_arm_key_stays_harness_model_byte_identical():
    wm = build_waste_matrix("c1", [_rec(task="t01", model="m1", waste=WasteBag(tool_calls=1))])
    assert wm.arms == ["opencode#m1"]


def test_waste_matrix_carries_the_pre012_count_when_present():
    import json

    recs = [
        _rec(task="t01", bench="b1", waste=WasteBag(tool_calls=1)),
        _rec012(task="t01", bench="b2", model="m2", arm="a1"),
        _cell_rec(),  # cell-scope records are not counted
    ]
    wm = build_waste_matrix("c1", recs)
    assert "includes 1 pre-012 records (untrusted)" in render_waste_matrix_html(wm)
    assert json.loads(render_waste_matrix_json(wm))["pre012_records"] == 1


def test_waste_matrix_has_no_pre012_line_when_count_is_zero():
    import json

    wm = build_waste_matrix("c1", [_rec012(task="t01")])
    assert "pre-012" not in render_waste_matrix_html(wm)
    assert json.loads(render_waste_matrix_json(wm))["pre012_records"] == 0


# --- 013 T014 (R-15): the not-measured rule and runs by run_id -----------------


def test_unmeasured_records_enter_no_sum_and_are_counted():
    """Contract 10.2: a stored-shape bag (opencode, unmarked, zero tool
    calls) enters no sum and no run count; not_measured counts it."""
    recs = [
        _rec(task="t01", waste=WasteBag(capture_rev=1)),
        _rec(task="t01", waste=WasteBag(tool_calls=10, capture_rev=1)),
        _rec(task="t01", waste=WasteBag()),
    ]
    wm = build_waste_matrix("c1", recs)
    assert _cell(wm, "t01", "opencode#m", "tool_calls").value == 10.0
    assert wm.not_measured == 1


def test_all_unmeasured_case_renders_the_not_measured_line():
    recs = [_rec(task="t01", waste=WasteBag())]
    wm = build_waste_matrix("c1", recs)
    assert wm.cells == []
    assert wm.not_measured == 1
    assert "1 attempts not measured (captured before tool events were parsed)" in (
        render_waste_matrix_html(wm)
    )


def test_html_has_no_not_measured_line_when_all_measured():
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=1, capture_rev=1))]
    html = render_waste_matrix_html(build_waste_matrix("c1", recs))
    assert "not measured" not in html


def test_runs_are_counted_by_run_id():
    """Contract 10.2: two attempts of one bench run are two runs -- the
    run count is by run_id, not bench_run_id."""
    recs = [
        _rec(task="t01", bench="b1", run="r1", waste=WasteBag(tool_calls=10, capture_rev=1)),
        _rec(task="t01", bench="b1", run="r2", waste=WasteBag(tool_calls=20, capture_rev=1)),
    ]
    wm = build_waste_matrix("c1", recs)
    c = _cell(wm, "t01", "opencode#m", "tool_calls")
    assert c.value == 15.0 and c.n_runs == 2
