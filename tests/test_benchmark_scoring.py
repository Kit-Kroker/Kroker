from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CompositeWeights,
    CostBag, QualityScore, SpeedBag,
)
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.models import HarnessKind


def _rec(case, harness, model, q, usd, secs):
    return BenchmarkRecord(
        run_id="r", bench_run_id="b", case_id=case,
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=harness, model=model, prompt_sha="",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd, input_tokens=10, output_tokens=5),
        speed=SpeedBag(wall_clock_s=secs,
                       started_at=datetime(2026, 7, 4, 10),
                       ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs)),
        outcome=BenchmarkOutcome.PASS,
    )


def _summarize(records, weights=None):
    return {s.model: s for s in compute_summaries(records, weights)}


def test_composite_ranks_better_quality_higher_even_if_pricier():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus",   q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].composite > s["opus"].composite


def test_cost_axis_dropped_when_fewer_than_two_costed():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=None, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus",   q=0.5, usd=None, secs=50),
    ]
    s = _summarize(recs)
    # both composites still produced; quality + speed only (renormalized)
    assert s["sonnet"].composite is not None
    assert s["opus"].composite is not None


def test_judge_error_records_excluded_from_composite():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus",   q=None, usd=2.0, secs=200),
    ]
    # The opus record had a judge error (q=None). It still appears as a summary
    # row but its composite is None.
    s = _summarize(recs)
    assert s["opus"].composite is None
    assert s["opus"].mean_quality is None


def test_custom_weights_change_ranking():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus",   q=0.5, usd=0.1, secs=10),
    ]
    # weight cost heavily -> cheap opus wins
    s = _summarize(recs, CompositeWeights(quality=0.1, cost=0.8, speed=0.1))
    assert s["opus"].composite > s["sonnet"].composite


def test_multiple_records_averaged_per_cell():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.8, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.6, usd=2.0, secs=200),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus",   q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].n == 2
    assert abs(s["sonnet"].mean_quality - 0.7) < 1e-9
