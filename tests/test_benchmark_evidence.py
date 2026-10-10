from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sdlc.benchmarks.evidence import Evidence, load_evidence, load_run_summaries
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore
from sdlc.core.models import (
    HarnessKind,
    RunSummary,
)

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _rec(bench="b1", case="c1", run="r1"):
    return BenchmarkRecord(
        run_id=run,
        bench_run_id=bench,
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )


def _write_summary(export_root, run_id, outcome="deployed:pr"):
    d = export_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    s = RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome=outcome,
        terminal_stage="deploy",
        started_at=T,
        ended_at=T,
        duration_s=0.0,
    )
    (d / "summary.json").write_text(s.model_dump_json(), encoding="utf-8")


def test_bench_selector_reads_only_that_bench_run(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2"))
    ev = load_evidence(bench="b1", root=str(tmp_path), export_root_=str(tmp_path / "exports"))
    assert {r.bench_run_id for r in ev.records} == {"b1"}
    assert ev.selector == "b1"


def test_case_selector_scans_every_bench_run(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b3").append(_rec("b3", "other"))
    ev = load_evidence(case="c1", root=str(tmp_path), export_root_=str(tmp_path / "exports"))
    assert {r.bench_run_id for r in ev.records} == {"b1", "b2"}
    assert ev.selector == "_case/c1"


def test_all_selector_reads_everything(tmp_path):
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1", "c1"))
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(_rec("b2", "c2"))
    ev = load_evidence(all_=True, root=str(tmp_path), export_root_=str(tmp_path / "exports"))
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
    ev = load_evidence(all_=True, root=str(tmp_path), export_root_=str(tmp_path / "exports"))
    assert isinstance(ev, Evidence)
    assert ev.records == []


def test_report_is_imported_lazily_not_at_module_scope():
    """report.py does `from temporalio import activity` for
    finalize_benchmark_report. evidence.py must not pay that at import
    time, so the report import lives inside load_evidence."""
    import pathlib

    src = pathlib.Path("src/sdlc/benchmarks/evidence.py").read_text(encoding="utf-8")
    head = src.split("def load_run_summaries")[0]
    assert "from .report import" not in head


def test_default_export_root_reads_runs_pipeline(tmp_path, monkeypatch):
    """Layout contract: with no explicit export root the SC rollup reads
    summaries from runs/pipeline/ relative to the CWD."""
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(_rec("b1"))
    summary = RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T,
        ended_at=T,
        duration_s=0.0,
    )
    run_dir = tmp_path / "runs" / "pipeline" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(summary.model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    ev = load_evidence(bench="b1", root=str(tmp_path))
    assert [s.run_id for s in ev.summaries] == ["r1"]


# --- 013 T010 (RED): summaries by run id (contract §9, research R-12) --------


def _selection_records(tmp_path, run_ids, case="c1", bench="b1"):
    """One code record per run id, stored through the real RecordStore."""
    store = RecordStore(root=str(tmp_path), bench_run_id=bench)
    for run in run_ids:
        store.append(_rec(bench, case, run))


def test_summaries_are_read_by_run_id_for_the_selection(tmp_path):
    """§9.1: `export_root / run_id / 'summary.json'` for each run of the
    selection and nowhere else -- exact membership cannot admit a
    `bf-e2e-*` summary sitting beside them (R-12)."""
    exports = tmp_path / "exports"
    _write_summary(exports, "r1")
    _write_summary(exports, "r2")
    _write_summary(exports, "bf-e2e-x")
    _selection_records(tmp_path, ["r1", "r2"])
    ev = load_evidence(case="c1", root=str(tmp_path), export_root_=str(exports))
    assert {s.run_id for s in ev.summaries} == {"r1", "r2"}
    assert ev.summary_runs == 2
    assert ev.selection_runs == 2
    assert ev.notes == []


def test_summary_declaring_a_different_run_id_is_ignored_with_a_note(tmp_path):
    """§9.1: the file lives at the run's path but claims another run --
    ignored, noted, never counted."""
    exports = tmp_path / "exports"
    d = exports / "r1"
    d.mkdir(parents=True)
    other = RunSummary(
        run_id="someone-else",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T,
        ended_at=T,
        duration_s=0.0,
    )
    (d / "summary.json").write_text(other.model_dump_json(), encoding="utf-8")
    _selection_records(tmp_path, ["r1"])
    ev = load_evidence(case="c1", root=str(tmp_path), export_root_=str(exports))
    assert ev.summaries == []
    assert ev.summary_runs == 0
    assert ev.selection_runs == 1
    assert len(ev.notes) == 1 and "r1" in ev.notes[0]


def test_missing_malformed_and_unopenable_summaries_are_no_summary_with_a_note(
    tmp_path, monkeypatch
):
    """§9.2: a missing file, a malformed file and a path that cannot be
    opened each degrade their one run to 'no summary'; nothing raises."""
    exports = tmp_path / "exports"
    _write_summary(exports, "r2")  # the good one
    bad = exports / "r3"
    bad.mkdir(parents=True)
    (bad / "summary.json").write_text("{not json", encoding="utf-8")
    _write_summary(exports, "r4")  # exists, but cannot be opened
    real_read_text = Path.read_text

    def _locked(self, *args, **kwargs):
        if self.parent.name == "r4" and self.name == "summary.json":
            raise PermissionError("locked")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _locked)
    _selection_records(tmp_path, ["r1", "r2", "r3", "r4"])  # r1: no file at all
    ev = load_evidence(case="c1", root=str(tmp_path), export_root_=str(exports))
    assert [s.run_id for s in ev.summaries] == ["r2"]
    assert ev.summary_runs == 1
    assert ev.selection_runs == 4
    assert len(ev.notes) == 3
    assert any("r1" in n for n in ev.notes)
    assert any("r3" in n for n in ev.notes)
    assert any("r4" in n for n in ev.notes)


def test_all_selector_reads_no_summary_outside_the_selections_run_ids(tmp_path):
    exports = tmp_path / "exports"
    _write_summary(exports, "r1")
    _write_summary(exports, "bf-e2e-x")
    _selection_records(tmp_path, ["r1"])
    ev = load_evidence(all_=True, root=str(tmp_path), export_root_=str(exports))
    assert {s.run_id for s in ev.summaries} == {"r1"}
    assert ev.summary_runs == 1
    assert ev.selection_runs == 1
