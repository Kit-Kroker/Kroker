"""Tests for root-cause labels and matrix (round 015, Phase 6, US3, T009)."""

from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.root_cause import (
    ROOT_CAUSES,
    Label,
    build_root_cause,
    load_labels,
    render_root_cause_html,
    render_root_cause_json,
    render_root_cause_markdown,
)
from sdlc.benchmarks.runs import Run, build_runs
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.core.models import HarnessKind


def _make_record(
    run_id: str,
    bench_run_id: str,
    case_id: str,
    scope: BenchmarkScope,
    stage: str,
    *,
    harness: HarnessKind = HarnessKind.OPENCODE,
    arm: str = "zai-coding-plan-glm-5.2",
    task_id: str | None = None,
    score: float | None = None,
    outcome: BenchmarkOutcome = BenchmarkOutcome.PASS,
    oracle_id: str | None = None,
    kroker_commit: str = "commit-test-1",
) -> BenchmarkRecord:
    t0 = datetime(2026, 7, 20, 10, tzinfo=UTC)
    judge = "oracle" if scope == BenchmarkScope.ORACLE else "staged_rubric"
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=bench_run_id,
        case_id=case_id,
        scope=scope,
        stage=stage,
        task_id=task_id,
        role=stage,
        harness=harness,
        arm=arm,
        model="test-model",
        quality=QualityScore(score=score, judge=judge),
        cost=CostBag(),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
        outcome=outcome,
        oracle_id=oracle_id,
        kroker_commit=kroker_commit,
    )


def test_lost_run_planning_stage():
    # A lost run with last stage research, clarify, architecture or plan counts under planning
    for stage in ("research", "clarify", "architecture", "plan"):
        recs = [
            _make_record(
                "r1", "b1", "case-1", BenchmarkScope.STAGE, stage, outcome=BenchmarkOutcome.FAIL
            ),
        ]
        runs = build_runs(recs)
        assert len(runs) == 1
        assert runs[0].status == "lost"

        matrix = build_root_cause("case-1", runs, recs)
        assert len(matrix.rows) == 1
        row = matrix.rows[0]
        assert row.planning.lost_runs == 1
        assert row.planning.numerator == 1
        assert row.planning.denominator == 1
        assert row.execution.lost_runs == 0
        assert row.execution.numerator == 0
        assert row.verification.numerator == 0
        assert row.unattributed.numerator == 0


def test_lost_run_execution_stage():
    # A lost run with last stage code or any task-loop stage counts under execution
    for stage in ("code", "tool_approval", "qa", "review", "adversary", "deep_review", "handoff"):
        recs = [
            _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
            _make_record(
                "r1", "b1", "case-1", BenchmarkScope.STAGE, stage, outcome=BenchmarkOutcome.FAIL
            ),
        ]
        runs = build_runs(recs)
        assert len(runs) == 1
        assert runs[0].status == "lost"

        matrix = build_root_cause("case-1", runs, recs)
        assert len(matrix.rows) == 1
        row = matrix.rows[0]
        assert row.planning.lost_runs == 0
        assert row.planning.numerator == 0
        assert row.execution.lost_runs == 1
        assert row.execution.numerator == 1
        assert row.execution.denominator == 1


def test_lost_run_no_stage_recorded():
    # A lost run with no stage recorded counts under planning and is noted
    run = Run(
        run_id="r-nostage",
        bench_run_id="b1",
        case_id="case-1",
        harness="opencode",
        arm="arm-1",
        arm_recovered=False,
        generation="012",
        commit="commit-1",
        tree_dirty=False,
        started_at=datetime.now(UTC),
        status="lost",
        status_derived=False,
        last_stage=None,
        pipeline_finished=False,
        oracle_passed=None,
        oracle_total=None,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=None,
        wall_clock_s=None,
        records=(),
    )
    matrix = build_root_cause("case-1", [run], [])
    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    assert row.planning.lost_runs == 1
    assert row.planning.numerator == 1
    assert any("r-nostage" in note for note in matrix.notes)


def test_graded_run_unlabelled_failed_requirement():
    # A graded run's oracle-task record with score below 1 and no label counts under unattributed
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "code"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=0.5),
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t1", score=0.0
        ),
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t2", score=1.0
        ),
    ]
    runs = build_runs(recs)
    assert len(runs) == 1
    assert runs[0].status == "graded"

    matrix = build_root_cause("case-1", runs, recs)
    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    assert row.unattributed.failed_requirements == 1
    assert row.unattributed.numerator == 1
    assert row.unattributed.requirements_graded == 2
    assert row.unattributed.denominator == 2
    assert matrix.labelled == 0
    assert matrix.unlabelled == 1


def test_graded_run_labelled_failed_requirement():
    # With a label it counts under the label's cause and labelled rises by one
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "code"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=0.5),
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t1", score=0.0
        ),
    ]
    runs = build_runs(recs)
    labels = [Label(run_id="r1", task_id="t1", cause="planning", note="spec misunderstood")]

    matrix = build_root_cause("case-1", runs, recs, labels=labels)
    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    assert row.planning.failed_requirements == 1
    assert row.planning.lost_runs == 0
    assert row.planning.numerator == 0
    assert row.planning.denominator == 1
    assert row.planning.requirements_graded == 1
    assert row.unattributed.failed_requirements == 0
    assert matrix.labelled == 1
    assert matrix.unlabelled == 0


def test_mixed_lost_runs_and_labelled_requirements():
    # Planning carries (lost_runs, runs_started) for numerator/denominator,
    # while preserving failed_requirements and requirements_graded
    recs = [
        # lost run in planning
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify", outcome=BenchmarkOutcome.FAIL
        ),
        # graded run with a planning-labelled failed requirement and a passed requirement
        _make_record("r2", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r2", "b1", "case-1", BenchmarkScope.STAGE, "code"),
        _make_record("r2", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r2", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=0.5),
        _make_record(
            "r2", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t1", score=0.0
        ),
        _make_record(
            "r2", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t2", score=1.0
        ),
    ]
    runs = build_runs(recs)
    labels = [Label(run_id="r2", task_id="t1", cause="planning", note="bad plan")]
    matrix = build_root_cause("case-1", runs, recs, labels=labels)
    row = matrix.rows[0]

    # planning cell: lost_runs = 1, runs_started = 2 -> numerator 1, denominator 2
    assert row.planning.lost_runs == 1
    assert row.planning.runs_started == 2
    assert row.planning.numerator == 1
    assert row.planning.denominator == 2
    # but failed_requirements and requirements_graded are also recorded
    assert row.planning.failed_requirements == 1
    assert row.planning.requirements_graded == 2

    # unattributed cell: failed_requirements = 0, requirements_graded = 2
    assert row.unattributed.failed_requirements == 0
    assert row.unattributed.requirements_graded == 2
    assert row.unattributed.numerator == 0
    assert row.unattributed.denominator == 2


def test_requirement_with_score_1_counts_nowhere():
    # A requirement with score 1 counts nowhere
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "code"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=1.0),
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t1", score=1.0
        ),
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.ORACLE_TASK, "oracle", task_id="t2", score=1.0
        ),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    row = matrix.rows[0]
    for cause in ROOT_CAUSES:
        assert row.cells[cause].failed_requirements == 0
        assert row.cells[cause].numerator == 0
    assert matrix.labelled == 0
    assert matrix.unlabelled == 0


def test_graded_run_no_oracle_task_records():
    # A graded run with no oracle-task record adds one to no_requirement_results
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "code"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=1.0),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    assert matrix.no_requirement_results == 1


def test_rows_per_case_harness_arm_generation_identity():
    # Rows are per case, harness, arm, generation and identity
    recs = [
        _make_record(
            "r1",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE,
            "oracle",
            harness=HarnessKind.OPENCODE,
            arm="arm-a",
            oracle_id="sha256:aaa",
        ),
        _make_record(
            "r2",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE,
            "oracle",
            harness=HarnessKind.OPENCODE,
            arm="arm-b",
            oracle_id="sha256:aaa",
        ),
        _make_record(
            "r3",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE,
            "oracle",
            harness=HarnessKind.OPENCODE,
            arm="arm-a",
            oracle_id="sha256:bbb",
        ),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    assert len(matrix.rows) == 3


def test_cell_low_n_flag():
    # A cell under MIN_OBSERVATIONS (5) is flagged low-n
    recs_low = [
        _make_record(
            f"r{i}", "b1", "case-1", BenchmarkScope.STAGE, "clarify", outcome=BenchmarkOutcome.FAIL
        )
        for i in range(3)
    ]
    runs_low = build_runs(recs_low)
    matrix_low = build_root_cause("case-1", runs_low, recs_low)
    assert matrix_low.rows[0].planning.denominator == 3
    assert matrix_low.rows[0].planning.low_n is True

    recs_high = [
        _make_record(
            f"r{i}", "b1", "case-1", BenchmarkScope.STAGE, "clarify", outcome=BenchmarkOutcome.FAIL
        )
        for i in range(5)
    ]
    runs_high = build_runs(recs_high)
    matrix_high = build_root_cause("case-1", runs_high, recs_high)
    assert matrix_high.rows[0].planning.denominator == 5
    assert matrix_high.rows[0].planning.low_n is False


def test_load_labels_validation(tmp_path):
    labels_root = tmp_path / "labels"
    case_dir = labels_root / "case-1"
    case_dir.mkdir(parents=True)

    suite = TaskSuite(
        case_id="case-1",
        tasks=[
            TaskSpec(id="t1", error_class="functional", oracle_tests=["test_1.py"]),
            TaskSpec(id="t2", error_class="functional", oracle_tests=["test_2.py"]),
        ],
    )
    recs = [
        _make_record("r1", "b-100", "case-1", BenchmarkScope.STAGE, "clarify"),
        _make_record("r2", "b-100", "case-2", BenchmarkScope.STAGE, "clarify"),
    ]

    # 1. Directory absent returns empty
    empty_labels = load_labels("case-nonexistent", labels_root=labels_root)
    assert empty_labels == []

    # 2. Unknown cause raises naming the entry
    yaml_bad_cause = case_dir / "b-100.yaml"
    yaml_bad_cause.write_text(
        "labels:\n  - run_id: r1\n    task_id: t1\n    cause: bogus_cause\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert "bogus_cause" in str(excinfo.value)
    assert "r1" in str(excinfo.value)

    # 3. task_id not in case mapping raises
    yaml_bad_task = case_dir / "b-100.yaml"
    yaml_bad_task.write_text(
        "labels:\n  - run_id: r1\n    task_id: t_unknown\n    cause: planning\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert "t_unknown" in str(excinfo.value)
    assert "case-1" in str(excinfo.value)

    # 4. run_id not among bench run records raises
    yaml_bad_run = case_dir / "b-100.yaml"
    yaml_bad_run.write_text(
        "labels:\n  - run_id: r_missing\n    task_id: t1\n    cause: planning\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert "r_missing" in str(excinfo.value)

    # 5. run_id of another case raises
    yaml_other_case = case_dir / "b-100.yaml"
    yaml_other_case.write_text(
        "labels:\n  - run_id: r2\n    task_id: t1\n    cause: planning\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert "r2" in str(excinfo.value)
    assert "case-2" in str(excinfo.value)
    yaml_other_case.unlink()

    # 5b. run_id in bench run with no records raises
    yaml_empty_bench = case_dir / "b-empty.yaml"
    yaml_empty_bench.write_text(
        "labels:\n  - run_id: r1\n    task_id: t1\n    cause: planning\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert "r1" in str(excinfo.value)
    assert "b-empty" in str(excinfo.value)
    yaml_empty_bench.unlink()

    # 6. Valid label loads successfully
    yaml_valid = case_dir / "b-100.yaml"
    yaml_valid.write_text(
        "labels:\n  - run_id: r1\n    task_id: t1\n    cause: planning\n    note: verified\n",
        encoding="utf-8",
    )
    loaded = load_labels("case-1", labels_root=labels_root, suite=suite, records=recs)
    assert len(loaded) == 1
    assert loaded[0].run_id == "r1"
    assert loaded[0].task_id == "t1"
    assert loaded[0].cause == "planning"
    assert loaded[0].note == "verified"


def test_render_root_cause_html():
    recs = [
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.STAGE, "research", outcome=BenchmarkOutcome.FAIL
        ),
        _make_record("r2", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record(
            "r2",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE_TASK,
            "oracle",
            task_id="t1",
            score=0.5,
        ),
        _make_record(
            "r2",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE,
            "oracle",
            score=0.5,
        ),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    html = render_root_cause_html(matrix)

    # 4 columns in order of ROOT_CAUSES
    for c in ROOT_CAUSES:
        assert f"<th>{c}</th>" in html
    assert (
        html.index("planning")
        < html.index("execution")
        < html.index("verification")
        < html.index("unattributed")
    )

    # value and denominator in every cell
    assert ">1/2</td>" in html  # planning: 1 lost run / 2 runs started
    assert ">0/2</td>" in html  # execution: 0 lost / 2 started
    assert ">0/1</td>" in html  # verification: 0 failed / 1 requirement graded
    assert ">1/1</td>" in html  # unattributed: 1 failed / 1 requirement graded

    # class low_n when cell.low_n is True
    assert 'class="low_n"' in html

    # lines: N failed requirements labelled by a person, M not labelled
    assert "0 failed requirements labelled by a person, 1 not labelled" in html


def test_render_root_cause_html_with_no_requirement_results():
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=1.0),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    html = render_root_cause_html(matrix)
    assert "1 graded runs have no requirement results" in html


def test_render_root_cause_markdown():
    recs = [
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.STAGE, "research", outcome=BenchmarkOutcome.FAIL
        ),
        _make_record("r2", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record(
            "r2",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE_TASK,
            "oracle",
            task_id="t1",
            score=0.5,
        ),
        _make_record(
            "r2",
            "b1",
            "case-1",
            BenchmarkScope.ORACLE,
            "oracle",
            score=0.5,
        ),
    ]
    runs = build_runs(recs)
    labels = [Label(run_id="r2", task_id="t1", cause="verification")]
    matrix = build_root_cause("case-1", runs, recs, labels=labels)
    md = render_root_cause_markdown(matrix)

    # Markdown is ASCII
    assert md.isascii()

    # Columns in order
    assert "| arm | planning | execution | verification | unattributed |" in md
    assert "1/2" in md
    assert "1/1" in md

    # Line: labelled / not labelled
    assert "1 failed requirements labelled by a person, 0 not labelled" in md


def test_render_root_cause_markdown_with_no_requirement_results():
    recs = [
        _make_record("r1", "b1", "case-1", BenchmarkScope.STAGE, "analyze"),
        _make_record("r1", "b1", "case-1", BenchmarkScope.ORACLE, "oracle", score=1.0),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    md = render_root_cause_markdown(matrix)
    assert md.isascii()
    assert "1 graded runs have no requirement results" in md


def test_render_root_cause_json():
    recs = [
        _make_record(
            "r1", "b1", "case-1", BenchmarkScope.STAGE, "research", outcome=BenchmarkOutcome.FAIL
        ),
    ]
    runs = build_runs(recs)
    matrix = build_root_cause("case-1", runs, recs)
    raw = render_root_cause_json(matrix)
    assert '"case_id": "case-1"' in raw
    assert '"planning"' in raw
    assert '"numerator": 1' in raw
