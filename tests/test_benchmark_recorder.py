import asyncio
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore, record_benchmark, records_path
from sdlc.models import HarnessKind


def _record(run_id="r1", bench="b1", case="c1"):
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=bench,
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1),
        speed=SpeedBag(
            wall_clock_s=1.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, 1),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def test_append_then_read_round_trip(tmp_path):
    store = RecordStore(root=str(tmp_path))
    store.append(_record())
    store.append(_record(run_id="r2"))
    recs = store.read_all()
    assert len(recs) == 2
    assert recs[0].run_id == "r1"
    assert recs[1].run_id == "r2"


def test_read_all_skips_partial_last_line(tmp_path):
    store = RecordStore(root=str(tmp_path))
    store.append(_record())
    # corrupt: append a partial line
    with open(store.path, "a") as f:
        f.write('{"run_id": "broken"')  # no closing brace / newline
    recs = store.read_all()
    assert len(recs) == 1  # only the valid one


def test_records_path_partitions_by_bench_and_cell(tmp_path):
    p = records_path("bench1", cell_id="c1#claude_code#sonnet", root=str(tmp_path))
    assert "bench1" in str(p)
    assert "c1#claude_code#sonnet" in str(p)
    assert p.suffix == ".jsonl"


def test_records_path_drift_namespace(tmp_path):
    p = records_path("_drift/2026-07-04", cell_id=None, root=str(tmp_path))
    assert "_drift" in str(p)


def test_record_benchmark_routes_production_to_flat_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    rec = _record(run_id="r1", bench="_drift/2026-07-04", case="_production")
    asyncio.run(record_benchmark(rec))
    # drift/production records go to <root>/<bench_run_id>/records.jsonl
    expected = tmp_path / "_drift" / "2026-07-04" / "records.jsonl"
    assert expected.exists()
    store = RecordStore(bench_run_id="_drift/2026-07-04", cell_id=None, root=str(tmp_path))
    recs = store.read_all()
    assert len(recs) == 1
    assert recs[0].case_id == "_production"


def test_record_benchmark_separates_crew_cells_by_lead_harness(tmp_path, monkeypatch):
    """spec §5: crew:claude_code and crew:opencode are different cells --
    without lead_harness in the file key they'd both land in
    c1#crew#glm.jsonl and the lead sweep couldn't be told apart."""
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    for lead in (HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE):
        rec = _record(run_id=f"r-{lead.value}", bench="b1", case="c1")
        rec = rec.model_copy(
            update={"harness": HarnessKind.CREW, "lead_harness": lead, "model": "glm"}
        )
        asyncio.run(record_benchmark(rec))
    files = sorted(p.name for p in tmp_path.rglob("*.jsonl"))
    assert len(files) == 2
    assert any("claude_code" in f for f in files)
    assert any("opencode" in f for f in files)


def test_record_benchmark_sanitizes_colon_in_model_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    rec = _record(run_id="r1", bench="b1", case="c1")
    rec = rec.model_copy(update={"harness": HarnessKind.CLAUDE_CODE})
    asyncio.run(record_benchmark(rec))
    # the cell filename must contain no ':' — sanitized to '_'
    files = list(tmp_path.rglob("*.jsonl"))
    assert len(files) == 1
    assert ":" not in files[0].name
    assert "_" in files[0].name
    # sanitization touches only the filename, not the stored payload
    store = RecordStore(
        bench_run_id="b1", cell_id="c1#claude_code#anthropic:claude-sonnet-4-6", root=str(tmp_path)
    )
    recs = store.read_all()
    assert len(recs) == 1
    assert recs[0].model == "anthropic:claude-sonnet-4-6"
