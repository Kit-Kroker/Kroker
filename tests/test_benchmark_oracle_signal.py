"""Tests for oracle collection-error signal and components (017 FR-025, D-8)."""

from datetime import UTC, datetime

from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkScope,
    HarnessKind,
)
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.workflow import _oracle_record

_START = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)
_END = datetime(2026, 10, 25, 12, 0, 10, tzinfo=UTC)

_BASE_CELL = BenchmarkCell(
    case_id="case-1",
    harness=HarnessKind.OPENCODE,
    arm_name="arm-1",
)


def _make_grade(
    score: float | None = 0.5,
    passed: int = 5,
    total: int = 10,
    exit_code: int | None = 0,
    errors: int = 0,
    detail: str = "oracle test run",
) -> OracleGrade:
    return OracleGrade(
        score=score,
        passed=passed,
        total=total,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail=detail,
        exit_code=exit_code,
        errors=errors,
    )


def test_oracle_record_exit_code_2_sets_collection_detail():
    """Exit code 2 (pytest command line / collection error) triggers collection detail."""
    grade = _make_grade(
        score=None, passed=0, total=0, exit_code=2, errors=0, detail="pytest exit 2"
    )
    record = _oracle_record(
        _BASE_CELL,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )

    assert record.scope is BenchmarkScope.ORACLE
    assert record.outcome is BenchmarkOutcome.NOT_EVALUATED
    assert record.error == "pytest exit 2"
    assert record.quality.score is None
    assert record.quality.components["exit_code"] == 2.0
    assert record.quality.components["errors"] == 0.0
    assert record.quality.detail == "collection/import errors: 0 of 0"


def test_oracle_record_exit_code_4_score_none_path_unchanged():
    """Exit code 4 triggers collection detail with score None unchanged."""
    grade = _make_grade(
        score=None, passed=0, total=0, exit_code=4, errors=0, detail="pytest exit 4"
    )
    record = _oracle_record(
        _BASE_CELL,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )

    assert record.outcome is BenchmarkOutcome.NOT_EVALUATED
    assert record.error == "pytest exit 4"
    assert record.quality.score is None
    assert record.quality.components["exit_code"] == 4.0
    assert record.quality.components["errors"] == 0.0
    assert record.quality.detail == "collection/import errors: 0 of 0"


def test_oracle_record_errors_ratio_threshold():
    """Errors ratio: 2*errors >= total > 0 sets collection detail, 2*errors < total does not."""
    # 2*E = N (5 errors of 10 total) -> fires
    grade_half = _make_grade(score=0.5, passed=5, total=10, exit_code=1, errors=5)
    rec_half = _oracle_record(
        _BASE_CELL,
        grade_half,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )
    assert rec_half.quality.components["exit_code"] == 1.0
    assert rec_half.quality.components["errors"] == 5.0
    assert rec_half.quality.detail == "collection/import errors: 5 of 10"

    # 2*E = N-1 (4 errors of 10 total, 8 < 10) -> does not fire
    grade_below = _make_grade(score=0.6, passed=6, total=10, exit_code=1, errors=4)
    rec_below = _oracle_record(
        _BASE_CELL,
        grade_below,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )
    assert rec_below.quality.components["exit_code"] == 1.0
    assert rec_below.quality.components["errors"] == 4.0
    assert rec_below.quality.detail is None


def test_oracle_record_exit_code_none_omits_keys():
    """Advisor-unlock-22: when exit_code is None (never ran), omit exit_code and errors keys."""
    grade = _make_grade(
        score=None, passed=0, total=0, exit_code=None, errors=0, detail="env failed"
    )
    record = _oracle_record(
        _BASE_CELL,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )

    assert "exit_code" not in record.quality.components
    assert "errors" not in record.quality.components
    assert record.quality.detail is None
    assert record.outcome is BenchmarkOutcome.NOT_EVALUATED


def test_oracle_record_timeout_minus_one_recorded_no_detail():
    """Timeout returns exit_code=-1. Recorded in components, but does not trip collection detail."""
    grade = _make_grade(score=None, passed=0, total=0, exit_code=-1, errors=0, detail="timeout")
    record = _oracle_record(
        _BASE_CELL,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )

    assert record.quality.components["exit_code"] == -1.0
    assert record.quality.components["errors"] == 0.0
    assert record.quality.detail is None


def test_oracle_record_r1_amended_mode_does_not_trip_signal():
    """T003 pin: R1's 55 failures, 0 errors, exit 1 does not trip collection error signal."""
    grade = _make_grade(score=1 / 56, passed=1, total=56, exit_code=1, errors=0)
    record = _oracle_record(
        _BASE_CELL,
        grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )

    assert record.quality.components["exit_code"] == 1.0
    assert record.quality.components["errors"] == 0.0
    assert record.quality.detail is None
    assert record.outcome is BenchmarkOutcome.FAIL


def test_oracle_record_normal_grade_pin():
    """PIN: normal grade's score and outcome are byte-identical to base."""
    pass_grade = _make_grade(score=1.0, passed=10, total=10, exit_code=0, errors=0)
    rec_pass = _oracle_record(
        _BASE_CELL,
        pass_grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )
    assert rec_pass.outcome is BenchmarkOutcome.PASS
    assert rec_pass.quality.score == 1.0
    assert rec_pass.quality.detail is None

    fail_grade = _make_grade(score=0.5, passed=5, total=10, exit_code=1, errors=0)
    rec_fail = _oracle_record(
        _BASE_CELL,
        fail_grade,
        bench_run_id="b1",
        run_id="r1",
        started=_START,
        ended=_END,
    )
    assert rec_fail.outcome is BenchmarkOutcome.FAIL
    assert rec_fail.quality.score == 0.5
    assert rec_fail.quality.detail is None
