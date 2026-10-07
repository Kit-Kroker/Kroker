"""012 T012 (RED): cell status, grading and the cell record (US2).

The module under test, ``sdlc.benchmarks.cell``, does not exist yet --
its absence fails collection of this file, which IS this task's red
state. Names are data-model §2.4; behaviour is contract §3.1-3.4 and
the section-3 grading table.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from sdlc.benchmarks.cell import (
    CellProgress,
    cell_record,
    grading_status,
    summarize_cell,
)
from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.oracle import OracleGrade
from sdlc.benchmarks.provenance import Provenance
from sdlc.benchmarks.recorder import RecordStore
from sdlc.core.models import HarnessKind

_T0 = datetime(2026, 7, 4, 10)


def _record(stage, *, scope=BenchmarkScope.STAGE, task_id=None, attempt=None):
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id="add-login",
        scope=scope,
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        role=stage,
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=None, judge="contract"),
        cost=CostBag(),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_T0, ended_at=_T0 + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )


def _write_records(tmp_path: Path, cell_id: str, records, bench="b1") -> None:
    store = RecordStore(bench_run_id=bench, cell_id=cell_id, root=str(tmp_path))
    for r in records:
        store.append(r)


def _summarize(tmp_path, monkeypatch, cell_id="add-login#opencode#a1", bench="b1"):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    return asyncio.run(summarize_cell(bench, cell_id))


# --- summarize_cell: last_stage by CELL_STAGE_ORDER, code_finished ----------


def test_summarize_cell_without_a_file(tmp_path, monkeypatch):
    progress = _summarize(tmp_path, monkeypatch)
    assert isinstance(progress, CellProgress)
    assert progress.last_stage is None
    assert progress.code_finished is False


def test_summarize_cell_stopped_in_clarify(tmp_path, monkeypatch):
    _write_records(tmp_path, "add-login#opencode#a1", [_record("research"), _record("clarify")])
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "clarify"
    assert progress.code_finished is False


def test_summarize_cell_through_code_without_post_code_record(tmp_path, monkeypatch):
    _write_records(
        tmp_path,
        "add-login#opencode#a1",
        [
            _record("research"),
            _record("clarify"),
            _record("architecture"),
            _record("plan"),
            _record("code", scope=BenchmarkScope.TASK_ATTEMPT, task_id="t1", attempt=0),
        ],
    )
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "code"
    assert progress.code_finished is False


def test_summarize_cell_through_analyze(tmp_path, monkeypatch):
    _write_records(
        tmp_path,
        "add-login#opencode#a1",
        [
            _record("research"),
            _record("clarify"),
            _record("architecture"),
            _record("plan"),
            _record("code", scope=BenchmarkScope.TASK_ATTEMPT, task_id="t1", attempt=0),
            _record("qa"),
            _record("review"),
            _record("analyze"),
        ],
    )
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "analyze"
    assert progress.code_finished is True


def test_summarize_cell_through_merge(tmp_path, monkeypatch):
    _write_records(
        tmp_path,
        "add-login#opencode#a1",
        [
            _record("research"),
            _record("clarify"),
            _record("plan"),
            _record("code", scope=BenchmarkScope.TASK_ATTEMPT, task_id="t1", attempt=0),
            _record("merge"),
        ],
    )
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "merge"
    assert progress.code_finished is True


def test_summarize_cell_reports_by_order_not_recency(tmp_path, monkeypatch):
    """A research record written AFTER a merge record must not drag
    last_stage back to research: latest by CELL_STAGE_ORDER, not by file
    position."""
    _write_records(
        tmp_path,
        "add-login#opencode#a1",
        [
            _record("merge"),
            _record("research"),  # out of pipeline order on purpose
        ],
    )
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "merge"
    assert progress.code_finished is True


# --- grading_status: every row of the contract section-3 table ---------------


def _grade(score, **kw):
    base = dict(
        score=score,
        passed=1,
        total=2,
        language_manifest="python",
        language_detected="python",
        language_match=True,
        held_out_ok=True,
        detail="1/2",
    )
    base.update(kw)
    return OracleGrade(**base)


def test_grading_status_no_oracle():
    assert grading_status(False, False, None) == "no_oracle"
    assert grading_status(False, True, None) == "no_oracle"


def test_grading_status_code_not_finished_is_not_graded():
    assert grading_status(True, False, None) == "not_graded"


def test_grading_status_score_present_is_graded():
    assert grading_status(True, True, _grade(0.5)) == "graded"
    # a real zero — including the empty-diff zero — is graded, not failed
    assert grading_status(True, True, _grade(0.0)) == "graded"


def test_grading_status_no_score_is_grading_failed():
    assert grading_status(True, True, _grade(None)) == "grading_failed"


# --- cell_record: contract §3.4 ----------------------------------------------


def _status(**kw):
    base = dict(
        pipeline_finished=True,
        code_finished=True,
        completed=True,
        last_stage="merge",
        grading="graded",
        child_result="ok",
    )
    base.update(kw)
    return CellStatus(**base)


_CELL = BenchmarkCell(case_id="add-login", harness=HarnessKind.OPENCODE, arm_name="a1")
_PROV = Provenance(kroker_commit="abc", tree_dirty=False)
_SHA = "a" * 64


def test_cell_record_shape_completed():
    rec = cell_record(
        _CELL,
        _status(),
        "b1",
        "wf/run-1",
        _T0,
        _T0 + timedelta(seconds=90),
        _PROV,
        _SHA,
    )
    assert rec.scope is BenchmarkScope.CELL
    assert rec.stage == "cell"
    assert rec.role == "cell"
    assert rec.quality.score is None
    assert rec.quality.judge == "contract"
    assert rec.outcome is BenchmarkOutcome.PASS  # completed -> pass
    assert rec.error is None
    assert rec.speed.started_at == _T0
    assert rec.speed.ended_at == _T0 + timedelta(seconds=90)
    assert rec.bench_run_id == "b1"
    assert rec.run_id == "wf/run-1"
    assert rec.kroker_commit == "abc"
    assert rec.tree_dirty is False
    assert rec.arm == "a1"
    assert rec.cell_id == _CELL.cell_id
    assert rec.model == "deterministic"
    assert rec.prompt_sha == "none:deterministic"
    assert rec.graph is not None
    assert rec.graph.graph_sha == _SHA
    assert rec.graph.activation_id is None


def test_cell_record_not_completed_fails_with_child_result():
    child = "Temporal failure: workflow raised"
    rec = cell_record(
        _CELL,
        _status(
            pipeline_finished=False,
            completed=False,
            grading="not_graded",
            child_result=child,
        ),
        "b1",
        "wf/run-1",
        _T0,
        _T0 + timedelta(seconds=5),
        _PROV,
        None,
    )
    assert rec.outcome is BenchmarkOutcome.FAIL
    assert rec.error == child
    # no graph sha -> no attribution
    assert rec.graph is None


def test_cell_record_truncates_child_result_to_500_characters():
    rec = cell_record(
        _CELL,
        _status(
            pipeline_finished=False,
            completed=False,
            grading="not_graded",
            child_result="x" * 600,
        ),
        "b1",
        "wf/run-1",
        _T0,
        _T0,
        _PROV,
        None,
    )
    assert rec.error == "x" * 500


# --- chaos seat: adversarial file shapes (012 T012) ---------------------------


def test_summarize_cell_survives_a_corrupt_partial_last_line(tmp_path, monkeypatch):
    """A crashed writer can leave a truncated non-JSON last line; the
    recorder's reader skips it, so summarize_cell must too -- the status
    comes from the VALID records and nothing raises."""
    _write_records(tmp_path, "add-login#opencode#a1", [_record("research"), _record("merge")])
    file = next(tmp_path.rglob("*.jsonl"))
    with open(file, "a", encoding="utf-8") as fh:
        fh.write('{"run_id": "trunc')  # torn write: no newline, no close
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "merge"
    assert progress.code_finished is True


def test_summarize_cell_empty_file_behaves_like_no_file(tmp_path, monkeypatch):
    store = RecordStore(bench_run_id="b1", cell_id="add-login#opencode#a1", root=str(tmp_path))
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("", encoding="utf-8")  # zero bytes
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage is None
    assert progress.code_finished is False


def test_summarize_cell_cell_scope_record_is_not_progress(tmp_path, monkeypatch):
    """The cell record itself (stage 'cell', not in CELL_STAGE_ORDER) never
    counts as the cell's progress."""
    _write_records(tmp_path, "add-login#opencode#a1", [_record("cell", scope=BenchmarkScope.CELL)])
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage is None
    assert progress.code_finished is False


def test_summarize_cell_unknown_stage_does_not_crash_the_ordering(tmp_path, monkeypatch):
    """A stage name outside CELL_STAGE_ORDER ('mystery') is ignored by the
    ordering, not fatal: last_stage stays at the latest KNOWN stage.
    (CELL_STAGE_ORDER's writer inventory test from T002 is the guard that
    no real writer ever produces such a name; this is defence in depth.)"""
    _write_records(
        tmp_path,
        "add-login#opencode#a1",
        [
            _record("mystery"),
            _record("code", scope=BenchmarkScope.TASK_ATTEMPT, task_id="t1", attempt=0),
        ],
    )
    progress = _summarize(tmp_path, monkeypatch)
    assert progress.last_stage == "code"
    assert progress.code_finished is False
