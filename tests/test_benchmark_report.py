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


def test_aggregate_sort_is_deterministic_on_model_tie():
    recs = [_rec("beta", None, 1.0, 100), _rec("alpha", None, 1.0, 100)]
    sums = aggregate("b1", CompositeWeights(), _records=recs)
    assert [s.model for s in sums] == ["alpha", "beta"]


def test_render_markdown_surfaces_stage_failures():
    """A degraded stage (research grounding rejected, pipeline continues
    per the 2026-07-20 decision) still leaves a trace in the human-facing
    report instead of vanishing silently."""
    failed = BenchmarkRecord(
        run_id="r", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="research", role="research",
        model="google:gemini-3.5-flash", prompt_sha="",
        quality=QualityScore(score=None, judge="error"),
        speed=SpeedBag(wall_clock_s=1.0,
                       started_at=datetime(2026, 7, 4, 10),
                       ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
        error="rejected:research.grounding: quote_not_found: https://x/1: 'q'")
    sums = aggregate("b1", CompositeWeights(), _records=[failed])
    md = render_markdown(sums)
    assert "Stage failures" in md
    assert "c1 / research" in md
    assert "rejected:research.grounding" in md


def test_resolve_language_map_reads_case_manifests(tmp_path):
    from sdlc.benchmarks.report import resolve_language_map
    (tmp_path / "c1").mkdir()
    (tmp_path / "c1" / "case.yaml").write_text(
        "case_id: c1\nlanguage: python\n", encoding="utf-8")
    (tmp_path / "c2").mkdir()          # no case.yaml
    m = resolve_language_map(["c1", "c2"], cases_dir=tmp_path)
    assert m == {"c1": "python", "c2": ""}


def test_write_heatmap_emits_both_files(tmp_path):
    from sdlc.benchmarks.report import write_heatmap
    recs = [_rec("sonnet", 0.9, 1.0, 100)]
    html_p, json_p = write_heatmap(recs, tmp_path, {"c1": "python"})
    assert html_p.exists() and json_p.exists()
    assert html_p.name == "heatmap.html" and json_p.name == "heatmap.json"
    assert "<!doctype html>" in html_p.read_text(encoding="utf-8")
