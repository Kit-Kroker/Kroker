from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CompositeWeights,
    CostBag, QualityScore, SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore
from sdlc.benchmarks.report import aggregate, render_markdown
from sdlc.models import HarnessKind


def _rec(model, q, usd, secs):
    return BenchmarkRecord(
        run_id="r", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.CLAUDE_CODE, model=model, prompt_sha="",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=secs,
                       started_at=datetime(2026, 7, 4, 10),
                       ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs)),
        outcome=BenchmarkOutcome.PASS)


def test_aggregate_reads_store_and_returns_summaries(tmp_path):
    store = RecordStore(root=str(tmp_path), bench_run_id="b1")
    store.append(_rec("sonnet", 0.9, 1.0, 100))
    store.append(_rec("opus", 0.5, 0.5, 50))
    sums = aggregate("b1", CompositeWeights(), root=str(tmp_path))
    assert len(sums) == 2
    by_model = {s.model: s for s in sums}
    assert by_model["sonnet"].composite > by_model["opus"].composite


def test_render_markdown_has_headers_and_rows(tmp_path):
    sums = aggregate("b1", CompositeWeights(), root=str(tmp_path),
                     _records=[_rec("sonnet", 0.9, 1.0, 100),
                               _rec("opus", 0.5, 0.5, 50)])
    md = render_markdown(sums)
    assert "| case" in md or "case" in md
    assert "sonnet" in md and "opus" in md
    assert "composite" in md.lower()


def test_render_markdown_handles_empty():
    md = render_markdown([])
    assert "no records" in md.lower()
