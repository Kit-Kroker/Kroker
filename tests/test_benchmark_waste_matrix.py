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
        _rec(task="t01", bench="b2", waste=WasteBag(tool_calls=20)),
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
