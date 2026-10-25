"""Tests for FR-040: judge readers never read None as 0 (T019).

Verifies that readers across src/sdlc/benchmarks/ treat score=None / judge="error"
as not graded / not evaluated, never as zero.
"""

from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.acceptance import separation
from sdlc.benchmarks.calibration import CalibrationFixture, run_calibration
from sdlc.benchmarks.error_matrix import build_error_matrix
from sdlc.benchmarks.judge import JudgeInput
from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.root_cause import build_root_cause
from sdlc.benchmarks.runs import Run, build_runs
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.benchmarks.task_matrix import build_task_matrix
from sdlc.benchmarks.tasks import TaskGrade, TaskSpec, TaskSuite
from sdlc.benchmarks.workflow import _oracle_task_records
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
    judge: str = "staged_rubric",
    outcome: BenchmarkOutcome = BenchmarkOutcome.PASS,
    oracle_id: str | None = "oid-1",
    kroker_commit: str = "commit-test-1",
    cell_status: CellStatus | None = None,
) -> BenchmarkRecord:
    t0 = datetime(2026, 7, 20, 10, tzinfo=UTC)
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
        cell=cell_status,
        quality=QualityScore(score=score, judge=judge),
        cost=CostBag(),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
        outcome=outcome,
        oracle_id=oracle_id,
        kroker_commit=kroker_commit,
        tree_dirty=False,
    )


def test_oracle_task_records_none_score_emits_not_evaluated():
    """FR-040: An oracle-task grade with score=None must emit NOT_EVALUATED, not FAIL."""
    cell = BenchmarkCell(
        case_id="case-1",
        arm_name="arm-a",
        harness=HarnessKind.OPENCODE,
        lead_harness=None,
        prompt_overrides={},
        role_models={},
    )
    grade = OracleGrade(
        score=0.5,
        passed=1,
        total=2,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail="",
        task_grades=[
            TaskGrade(
                task_id="T01",
                error_class="logic",
                score=None,
                judge="error",
                detail="judge did not return a score",
            ),
            TaskGrade(
                task_id="T02",
                error_class="logic",
                score=1.0,
                judge="llm_judge",
                detail="passed",
            ),
        ],
    )
    t0 = datetime(2026, 7, 20, 10, tzinfo=UTC)
    recs = _oracle_task_records(
        cell,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=t0,
        ended=t0 + timedelta(seconds=1),
    )
    assert len(recs) == 2
    r_err, r_pass = recs[0], recs[1]

    # The judge-error task grade must be NOT_EVALUATED, never FAIL
    assert r_err.task_id == "T01"
    assert r_err.quality.score is None
    assert r_err.outcome == BenchmarkOutcome.NOT_EVALUATED

    assert r_pass.task_id == "T02"
    assert r_pass.quality.score == 1.0
    assert r_pass.outcome == BenchmarkOutcome.PASS


def test_root_cause_skips_oracle_task_with_none_score():
    """FR-040: root_cause must skip ORACLE_TASK records where score is None.

    It must neither increment requirements_graded nor fall through to
    failed_by_cause['unattributed'].
    """
    run_id = "r1"
    run = Run(
        run_id=run_id,
        bench_run_id="b1",
        case_id="case-1",
        harness="opencode",
        arm="arm-a",
        arm_recovered=False,
        generation="012",
        commit="c1",
        tree_dirty=False,
        started_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
        status="graded",
        status_derived=False,
        last_stage="merge",
        pipeline_finished=True,
        oracle_passed=1,
        oracle_total=1,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=100,
        wall_clock_s=10.0,
        records=(),
        oracle_id="oid-1",
    )
    # Record with score=None, judge="error"
    ot_rec = _make_record(
        run_id=run_id,
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="T01",
        score=None,
        judge="error",
        outcome=BenchmarkOutcome.NOT_EVALUATED,
    )
    matrix = build_root_cause(
        case_id="case-1",
        runs=[run],
        records=[ot_rec],
    )
    row = matrix.rows[0]
    # Requirements graded should be 0 because T01 was never evaluated/scored
    assert row.unattributed.requirements_graded == 0
    assert row.unattributed.failed_requirements == 0


def test_build_runs_judge_error_cell_is_not_graded():
    """FR-040: A cell whose oracle grade has score=None is grading_failed, not graded."""
    cell_rec = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.CELL,
        stage="cell",
        cell_status=CellStatus(
            completed=True,
            last_stage="code",
            code_finished=True,
            pipeline_finished=True,
            grading="grading_failed",
        ),
    )
    oracle_rec = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.ORACLE,
        stage="oracle",
        score=None,
        judge="error",
        outcome=BenchmarkOutcome.NOT_EVALUATED,
    )
    runs = build_runs([cell_rec, oracle_rec])
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "grading_failed"
    assert run.partial_credit is None


def test_separation_excludes_grading_failed_run():
    """FR-040: separation() skips runs with status != 'graded'."""
    r_failed = Run(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        harness="opencode",
        arm="strong",
        arm_recovered=False,
        generation="012",
        commit="c1",
        tree_dirty=False,
        started_at=None,
        status="grading_failed",
        status_derived=False,
        last_stage="code",
        pipeline_finished=True,
        oracle_passed=None,
        oracle_total=None,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=100,
        wall_clock_s=10.0,
        records=(),
        oracle_id="oid-1",
    )
    sep = separation([r_failed], strong="strong", weak="weak", oracle_id="oid-1")
    assert sep.strong is not None
    assert sep.strong.run_ids == []
    assert sep.strong.scores == []
    assert sep.strong.mean is None


def test_separation_language_mismatch_zero_total_pin():
    """PIN per advisor-unlock-23: A graded run with oracle_total=0 (language mismatch)

    enters separation as 0.0 via 'else 0.0'.
    """
    r_lang_mismatch = Run(
        run_id="r-lm",
        bench_run_id="b1",
        case_id="case-1",
        harness="opencode",
        arm="strong",
        arm_recovered=False,
        generation="012",
        commit="c1",
        tree_dirty=False,
        started_at=None,
        status="graded",
        status_derived=False,
        last_stage="merge",
        pipeline_finished=True,
        oracle_passed=0,
        oracle_total=0,
        discarded_oracle_records=0,
        tasks=(),
        qa_is_copy=False,
        tokens=100,
        wall_clock_s=10.0,
        records=(),
        oracle_id="oid-1",
    )
    sep = separation([r_lang_mismatch], strong="strong", weak=None, oracle_id="oid-1")
    assert sep.strong is not None
    assert sep.strong.run_ids == ["r-lm"]
    assert sep.strong.scores == [0.0]
    assert sep.strong.mean == 0.0


def test_task_matrix_excludes_none_score():
    """FR-040: build_task_matrix excludes records with score=None."""
    suite = TaskSuite(
        case_id="case-1",
        tasks=(
            TaskSpec(id="T01", description="task 1", error_class="functional", rubric="r1"),
            TaskSpec(id="T02", description="task 2", error_class="functional", rubric="r2"),
        ),
    )
    # One record with NOT_EVALUATED and score=None
    r_none = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="T01",
        score=None,
        judge="error",
        outcome=BenchmarkOutcome.NOT_EVALUATED,
    )
    # One legacy record with outcome=FAIL but score=None
    r_legacy_none = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="T02",
        score=None,
        judge="error",
        outcome=BenchmarkOutcome.FAIL,
    )
    matrix = build_task_matrix(
        case_id="case-1",
        records=[r_none, r_legacy_none],
        suite=suite,
    )
    col = matrix.columns[0]
    # mean_score must be None, not 0.0
    assert col.mean_score is None


def test_error_matrix_excludes_none_score():
    """FR-040: build_error_matrix excludes records with score=None."""
    suite = TaskSuite(
        case_id="case-1",
        tasks=(TaskSpec(id="T01", description="task 1", error_class="functional", rubric="r1"),),
    )
    r_none = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="T01",
        score=None,
        judge="error",
        outcome=BenchmarkOutcome.NOT_EVALUATED,
    )
    matrix = build_error_matrix(
        case_id="case-1",
        records=[r_none],
        suite=suite,
    )
    # No failure mass accumulated for un-evaluated / unscored tasks
    assert len(matrix.cells) == 0


def test_calibration_excludes_none_score():
    """FR-040: run_calibration excludes fixtures where judge score is None."""
    fx = CalibrationFixture(
        stage="architecture",
        case_id="case-1",
        human_score=1.0,
        author_model="author-a",
        artifact_json='{"key": "val"}',
        rubric_text="rubric text",
        rubric_sha="sha1",
        rubric_ref="rubric-1",
    )
    called = []

    def mock_judge(inp: JudgeInput) -> QualityScore:
        called.append(inp)
        return QualityScore(score=None, judge="error")

    report = run_calibration(
        fixtures=[fx],
        rubric="architecture",
        judge_model="judge-b",
        judge=mock_judge,
    )
    assert len(called) == 1
    # Fixture with None judge score is excluded from pairs
    assert report.n_fixtures == 0


def test_rubric_scoring_excludes_none_score():
    """FR-040: compute_summaries excludes rubric records where score is None."""
    rec_none = _make_record(
        run_id="r1",
        bench_run_id="b1",
        case_id="case-1",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        score=None,
        judge="staged_rubric",
    )
    summaries = compute_summaries([rec_none])
    assert len(summaries) == 1
    assert summaries[0].mean_quality is None
