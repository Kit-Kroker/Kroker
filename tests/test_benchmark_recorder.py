from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CostBag, QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore, records_path


def _record(run_id="r1", bench="b1", case="c1"):
    return BenchmarkRecord(
        run_id=run_id, bench_run_id=bench, case_id=case,
        scope=BenchmarkScope.STAGE, stage="architecture", role="architect",
        model="anthropic:claude-sonnet-4-6",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1),
        speed=SpeedBag(wall_clock_s=1.0,
                       started_at=datetime(2026, 7, 4, 10),
                       ended_at=datetime(2026, 7, 4, 10, 0, 1)),
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
        f.write('{"run_id": "broken"')   # no closing brace / newline
    recs = store.read_all()
    assert len(recs) == 1   # only the valid one


def test_records_path_partitions_by_bench_and_cell(tmp_path):
    p = records_path("bench1", cell_id="c1#claude_code#sonnet",
                     root=str(tmp_path))
    assert "bench1" in str(p)
    assert "c1#claude_code#sonnet" in str(p)
    assert p.suffix == ".jsonl"


def test_records_path_drift_namespace(tmp_path):
    p = records_path("_drift/2026-07-04", cell_id=None, root=str(tmp_path))
    assert "_drift" in str(p)
