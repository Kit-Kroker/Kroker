"""task x arm split-rate grid (spec 4.4)."""

from datetime import UTC, datetime

from sdlc.benchmarks.agreement_matrix import build_agreement_matrix
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.models import HarnessKind

_T = datetime(2026, 8, 5, tzinfo=UTC)


def _rec(stage, outcome, task_id="t1", usd=0.02, run_id="r1", case_id="c1"):
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id="b1",
        case_id=case_id,
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage=stage,
        task_id=task_id,
        role=stage,
        harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:x",
        quality=QualityScore(score=1.0, judge="adversary"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_T, ended_at=_T),
        outcome=outcome,
        fix_attempts=0,
    )


def test_split_rate_counts_only_adversary_records():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL),
            _rec("adversary", BenchmarkOutcome.PASS),
            _rec("code", BenchmarkOutcome.FAIL),  # must not count
        ],
    )
    cell = next(c for c in am.cells if c.metric == "split_rate")
    assert cell.value == 0.5


def test_cost_per_split_sums_adversary_spend():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL, usd=0.02),
            _rec("adversary", BenchmarkOutcome.PASS, usd=0.02),
        ],
    )
    cell = next(c for c in am.cells if c.metric == "cost_per_split")
    assert cell.value == 0.04  # total adversary spend / 1 split


def test_no_adversary_records_yields_no_cells():
    """Not measured is not zero -- a blank cell, never a 0.0 (waste_matrix)."""
    am = build_agreement_matrix("c1", [_rec("code", BenchmarkOutcome.PASS)])
    assert am.cells == []


def test_zero_splits_yields_a_rate_but_no_cost_per_split():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.PASS),
        ],
    )
    metrics = {c.metric for c in am.cells}
    assert "split_rate" in metrics
    assert "cost_per_split" not in metrics


def test_other_cases_are_excluded():
    am = build_agreement_matrix(
        "c1",
        [
            _rec("adversary", BenchmarkOutcome.FAIL, case_id="c2"),
            _rec("adversary", BenchmarkOutcome.PASS, case_id="c1"),
        ],
    )
    cell = next(c for c in am.cells if c.metric == "split_rate")
    assert cell.value == 0.0
