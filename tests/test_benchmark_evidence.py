from datetime import datetime, timedelta, timezone

import pytest

from sdlc.benchmarks.evidence import Evidence, load_evidence, load_run_summaries
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.recorder import RecordStore
from sdlc.models import HarnessKind, RunSummary

T = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


def _rec(bench="b1", case="c1", run="r1"):
    return BenchmarkRecord(
        run_id=run, bench_run_id=bench, case_id=case,
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.OPENCODE, model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T,
                       ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)


def _write_summary(export_root, run_id, outcome="deployed:pr"):
    d = export_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    s = RunSummary(run_id=run_id, mode="greenfield", outcome=outcome,
                   terminal_stage="deploy", started_at=T, ended_at=T,
                   duration_s=0.0)
    (d / "summary.json").write_text(s.model_dump_json(), encoding="utf-8")


def test_bench_selector_reads_only_that_bench_run(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2"))
    ev = load_evidence(bench="b1", root=str(tmp_path),
                       export_root_=str(tmp_path / "exports"))
    assert {r.bench_run_id for r in ev.records} == {"b1"}
    assert ev.selector == "b1"


def test_case_selector_scans_every_bench_run(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b3").append(_rec("b3", "other"))
    ev = load_evidence(case="c1", root=str(tmp_path),
                       export_root_=str(tmp_path / "exports"))
    assert {r.bench_run_id for r in ev.records} == {"b1", "b2"}
    assert ev.selector == "_case/c1"


def test_all_selector_reads_everything(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2", "c2"))
    ev = load_evidence(all_=True, root=str(tmp_path),
                       export_root_=str(tmp_path / "exports"))
    assert {r.case_id for r in ev.records} == {"c1", "c2"}
    assert ev.selector == "_all"


def test_exactly_one_selector_required(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        load_evidence(root=str(tmp_path))
    with pytest.raises(ValueError, match="exactly one"):
        load_evidence(bench="b1", all_=True, root=str(tmp_path))


def test_summaries_loaded_from_export_root(tmp_path):
    exports = tmp_path / "exports"
    _write_summary(exports, "run-1")
    _write_summary(exports, "run-2")
    summaries, notes = load_run_summaries(str(exports))
    assert {s.run_id for s in summaries} == {"run-1", "run-2"}
    assert notes == []


def test_malformed_summary_is_noted_not_raised(tmp_path):
    """Degrade and report: one broken export must not blind the whole
    rollup."""
    exports = tmp_path / "exports"
    _write_summary(exports, "run-good")
    bad = exports / "run-bad"
    bad.mkdir(parents=True)
    (bad / "summary.json").write_text("{not json", encoding="utf-8")
    summaries, notes = load_run_summaries(str(exports))
    assert [s.run_id for s in summaries] == ["run-good"]
    assert len(notes) == 1 and "run-bad" in notes[0]


def test_missing_export_root_yields_no_summaries_and_a_note(tmp_path):
    summaries, notes = load_run_summaries(str(tmp_path / "nope"))
    assert summaries == []
    assert len(notes) == 1


def test_empty_corpus_is_a_fact_not_an_error(tmp_path):
    ev = load_evidence(all_=True, root=str(tmp_path),
                       export_root_=str(tmp_path / "exports"))
    assert isinstance(ev, Evidence)
    assert ev.records == []


def test_report_is_imported_lazily_not_at_module_scope():
    """report.py does `from temporalio import activity` for
    finalize_benchmark_report. evidence.py must not pay that at import
    time, so the report import lives inside load_evidence."""
    import pathlib
    src = pathlib.Path("src/sdlc/benchmarks/evidence.py").read_text(
        encoding="utf-8")
    head = src.split("def load_run_summaries")[0]
    assert "from .report import" not in head
