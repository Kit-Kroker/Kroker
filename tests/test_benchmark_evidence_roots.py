"""026 T003 (FR-002, FR-004, research R2): every scored run is accounted for.

A run with no summary.json used to vanish from the SC denominator. The cell
record is the authority (keyed on `cell.pipeline_finished`):

    cell record, pipeline_finished False             -> crashed
      ... and child_result names cause=TimeoutError  -> timed_out
    no cell record, other records present            -> terminated
    cell record, pipeline_finished True, no summary  -> summary_missing

Smoke-case runs are excluded from the selection and named in
`Evidence.excluded_smoke`; `selection_runs` counts non-smoke runs only.

Fixtures use the real record writer (RecordStore, the store behind
record_benchmark) and write summary.json the way the export activity does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.corpus import smoke_case
from sdlc.benchmarks.evidence import load_evidence
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.paths import cases_dir
from sdlc.benchmarks.recorder import RecordStore
from sdlc.core.models import HarnessKind, RunSummary

T = datetime(2026, 11, 18, 10, tzinfo=UTC)
BENCH = "bench-026"

SUMMARIZED = "run-summarized"
CRASHED = "run-crashed"
TIMED_OUT = "run-timed-out"
TERMINATED = "run-terminated"
SUMMARY_MISSING = "run-summary-missing"
SMOKE = "run-smoke"
TIMEOUT_FAILURE = "ChildWorkflowError(cause=TimeoutError): Child Workflow execution failed"


@pytest.fixture(scope="module")
def smoke_id() -> str:
    return smoke_case(cases_dir()).case_id


def _rec(run_id, case_id, *, scope=BenchmarkScope.STAGE, stage="code", task=None, cell=None):
    is_cell = scope is BenchmarkScope.CELL
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=BENCH,
        case_id=case_id,
        scope=scope,
        stage="cell" if is_cell else stage,
        task_id=task,
        role="cell" if is_cell else "dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
        arm="arm-1",
        cell_id=f"{case_id}#{run_id}",
        cell=cell,
    )


def _cell(*, finished: bool, child_result: str | None) -> CellStatus:
    return CellStatus(
        pipeline_finished=finished,
        code_finished=finished,
        completed=finished,
        last_stage="deploy" if finished else "code",
        grading="not_graded",
        child_result=child_result,
    )


def _write(root, *records: BenchmarkRecord) -> None:
    for r in records:
        RecordStore(root=str(root), bench_run_id=r.bench_run_id, cell_id=r.cell_id).append(r)


def _write_summary(export_root, run_id) -> None:
    d = export_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    s = RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T,
        ended_at=T,
        duration_s=0.0,
    )
    (d / "summary.json").write_text(s.model_dump_json(indent=2), encoding="utf-8")


def _summarized_run(records, exports, run_id=SUMMARIZED, case="case-a"):
    _write(
        records,
        _rec(run_id, case, stage="plan"),
        _rec(run_id, case, scope=BenchmarkScope.CELL, cell=_cell(finished=True, child_result="ok")),
    )
    _write_summary(exports, run_id)


@pytest.fixture
def fleet(tmp_path, smoke_id):
    """Six runs under one records root and one export root."""
    records, exports = tmp_path / "benchmarks", tmp_path / "pipeline"
    exports.mkdir(parents=True)

    # (1) summarized
    _summarized_run(records, exports)
    # (2) crashed: cell record, pipeline not finished, no summary
    _write(
        records,
        _rec(CRASHED, "case-b", stage="plan"),
        _rec(
            CRASHED,
            "case-b",
            scope=BenchmarkScope.CELL,
            cell=_cell(
                finished=False, child_result="ChildWorkflowError: Child Workflow execution failed"
            ),
        ),
    )
    # (3) timed out: same, with the cause type in the failure string
    _write(
        records,
        _rec(TIMED_OUT, "case-c", stage="plan"),
        _rec(
            TIMED_OUT,
            "case-c",
            scope=BenchmarkScope.CELL,
            cell=_cell(
                finished=False,
                child_result=TIMEOUT_FAILURE,
            ),
        ),
    )
    # (4) terminated: stage and task records only, no cell record, no summary
    _write(
        records,
        _rec(TERMINATED, "case-d", stage="plan"),
        _rec(TERMINATED, "case-d", scope=BenchmarkScope.TASK_ATTEMPT, stage="code", task="T1"),
    )
    # (5) summary missing: the pipeline finished but no summary.json landed
    _write(
        records,
        _rec(SUMMARY_MISSING, "case-e", stage="plan"),
        _rec(
            SUMMARY_MISSING,
            "case-e",
            scope=BenchmarkScope.CELL,
            cell=_cell(finished=True, child_result="deployed:pr"),
        ),
    )
    # (6) smoke: the real smoke case id; no summary (it must not show up as
    # a no-summary run either)
    _write(
        records,
        _rec(SMOKE, smoke_id, stage="plan"),
        _rec(
            SMOKE, smoke_id, scope=BenchmarkScope.CELL, cell=_cell(finished=False, child_result="x")
        ),
    )
    return records, exports


def _load(records, exports, **selector):
    selector = selector or {"all_": True}
    return load_evidence(root=str(records), export_root_=str(exports), **selector)


def _classes(ev) -> dict[str, tuple[str, str]]:
    return {n.run_id: (n.case_id, str(n.terminal_class)) for n in ev.no_summary}


# --- no-summary classification -------------------------------------------


def test_no_summary_classifies_each_run_without_a_summary(fleet):
    ev = _load(*fleet)
    assert _classes(ev) == {
        CRASHED: ("case-b", "crashed"),
        TIMED_OUT: ("case-c", "timed_out"),
        TERMINATED: ("case-d", "terminated"),
        SUMMARY_MISSING: ("case-e", "summary_missing"),
    }


def test_no_summary_lists_each_run_once(fleet):
    ev = _load(*fleet)
    ids = [n.run_id for n in ev.no_summary]
    assert len(ids) == len(set(ids)) == 4


def test_no_summary_omits_the_summarized_run(fleet):
    ev = _load(*fleet)
    assert SUMMARIZED not in _classes(ev)
    assert [s.run_id for s in ev.summaries] == [SUMMARIZED]


def test_no_summary_timeout_cause_beats_crash(fleet):
    """The cause type in child_result is what separates timed_out from crashed."""
    ev = _load(*fleet)
    assert _classes(ev)[TIMED_OUT][1] == "timed_out"
    assert _classes(ev)[CRASHED][1] == "crashed"


def test_no_summary_empty_when_every_run_is_summarized(tmp_path):
    records, exports = tmp_path / "benchmarks", tmp_path / "pipeline"
    _summarized_run(records, exports, "run-1", "case-a")
    _summarized_run(records, exports, "run-2", "case-b")
    ev = _load(records, exports)
    assert ev.no_summary == []
    assert ev.excluded_smoke == []
    assert (ev.selection_runs, ev.summary_runs) == (2, 2)


def test_no_summary_also_under_the_bench_selector(fleet):
    ev = _load(*fleet, bench=BENCH)
    assert set(_classes(ev)) == {CRASHED, TIMED_OUT, TERMINATED, SUMMARY_MISSING}


# --- smoke exclusion ------------------------------------------------------


def test_smoke_run_is_excluded_and_named(fleet):
    ev = _load(*fleet)
    assert ev.excluded_smoke == [SMOKE]


def test_smoke_run_is_not_a_no_summary_run(fleet):
    ev = _load(*fleet)
    assert SMOKE not in _classes(ev)


def test_smoke_selection_runs_counts_non_smoke_runs_only(fleet):
    ev = _load(*fleet)
    assert ev.selection_runs == 5
    assert ev.summary_runs == 1


def test_smoke_accounting_closes(fleet):
    """Every non-smoke run is either summarized or a no-summary run."""
    ev = _load(*fleet)
    assert ev.summary_runs + len(ev.no_summary) == ev.selection_runs


# --- chaos / edge cases (026 T003, chaos QA) --------------------------------


def _bare(tmp_path):
    records, exports = tmp_path / "benchmarks", tmp_path / "pipeline"
    exports.mkdir(parents=True)
    return records, exports


def _cell_run(records, run_id, case, *, finished, child_result):
    _write(
        records,
        _rec(run_id, case, stage="plan"),
        _rec(
            run_id,
            case,
            scope=BenchmarkScope.CELL,
            cell=_cell(finished=finished, child_result=child_result),
        ),
    )


def test_smoke_exclusion_precedes_no_summary_classification(tmp_path, smoke_id):
    """R2 ordering: a failed smoke run with no summary is excluded first and
    never classified (it would otherwise read as `crashed`)."""
    records, exports = _bare(tmp_path)
    _cell_run(
        records, SMOKE, smoke_id, finished=False, child_result="ChildWorkflowError: Child failed"
    )
    ev = _load(records, exports)
    assert ev.excluded_smoke == [SMOKE]
    assert ev.no_summary == []
    assert ev.selection_runs == 0


def test_no_summary_and_smoke_empty_on_an_empty_records_root(tmp_path):
    records, exports = _bare(tmp_path)
    records.mkdir()
    ev = _load(records, exports)
    assert ev.no_summary == []
    assert ev.excluded_smoke == []
    assert (ev.selection_runs, ev.summary_runs) == (0, 0)
    assert any("no benchmark records for selector _all" in n for n in ev.notes), ev.notes


def test_no_summary_and_smoke_empty_when_records_root_is_missing(tmp_path):
    records, exports = _bare(tmp_path)  # records dir never created
    ev = _load(records, exports)
    assert (ev.no_summary, ev.excluded_smoke, ev.selection_runs) == ([], [], 0)


def test_no_summary_mismatched_summary_run_id_is_summary_missing(tmp_path):
    """_summaries_by_run_id already ignores a summary whose run_id disagrees
    (with a note). Fail-closed: the run must then surface as
    summary_missing, not be silently dropped from the accounting."""
    records, exports = _bare(tmp_path)
    run = "run-mismatch"
    _cell_run(records, run, "case-m", finished=True, child_result="deployed:pr")
    _write_summary(exports, "someone-else")
    (exports / "someone-else").rename(exports / run)  # summary.json says run_id=someone-else

    ev = _load(records, exports)

    assert ev.summaries == []
    assert any(f"summary for run {run} reports run_id someone-else" in n for n in ev.notes)
    assert _classes(ev) == {run: ("case-m", "summary_missing")}
    assert ev.summary_runs + len(ev.no_summary) == ev.selection_runs == 1


@pytest.mark.parametrize(
    ("child_result", "want"),
    [
        pytest.param(
            "ChildWorkflowError(cause=TimeoutError): workflow timed out",
            "timed_out",
            id="timeout_cause",
        ),
        pytest.param(
            "ChildWorkflowError(cause=ActivityError): activity failed",
            "crashed",
            id="activity_cause",
        ),
        pytest.param(
            "ChildWorkflowError(cause=ActivityError): activity raised TimeoutError",
            "crashed",
            id="timeout_only_in_message",
        ),
        pytest.param(
            "ChildWorkflowError: Child Workflow execution failed: TimeoutError",
            "crashed",
            id="no_cause_marker",
        ),
        pytest.param(None, "crashed", id="no_child_result"),
    ],
)
def test_no_summary_cause_marker_decides_timed_out(tmp_path, child_result, want):
    """Only the structured `cause=TimeoutError` marker means timed_out; the
    word TimeoutError elsewhere in the message does not."""
    records, exports = _bare(tmp_path)
    _cell_run(records, "run-x", "case-x", finished=False, child_result=child_result)
    assert _classes(_load(records, exports)) == {"run-x": ("case-x", want)}


def test_no_summary_omits_a_finished_run_with_a_summary(tmp_path):
    records, exports = _bare(tmp_path)
    _summarized_run(records, exports, "run-ok", "case-ok")
    ev = _load(records, exports)
    assert ev.no_summary == []
    assert [s.run_id for s in ev.summaries] == ["run-ok"]


def test_no_summary_dedupes_duplicate_records_per_run(tmp_path):
    """An activity retry can append the same records twice."""
    records, exports = _bare(tmp_path)
    for _ in range(2):
        _cell_run(records, "run-dup", "case-d", finished=True, child_result="deployed:pr")
        _write(records, _rec("run-term", "case-t", stage="plan"))
    ev = _load(records, exports)
    assert [n.run_id for n in ev.no_summary] == sorted({n.run_id for n in ev.no_summary})
    assert _classes(ev) == {
        "run-dup": ("case-d", "summary_missing"),
        "run-term": ("case-t", "terminated"),
    }
    assert ev.selection_runs == 2
