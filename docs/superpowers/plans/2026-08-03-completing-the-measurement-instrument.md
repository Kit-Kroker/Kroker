# Completing the Measurement Instrument Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the benchmark instrument so tool-call waste, success-criteria rates, a fast one-command re-score, and a committed experiment log all exist before the next feature is coded.

**Architecture:** Execution writes evidence to disk (`records.jsonl`, `summary.json`); scoring reads it through a pure reader and renders grids. No module in the scoring path imports `temporalio`, so `sdlc benchmark score` runs from a shell in seconds with no worker and no server.

**Tech Stack:** Python 3.11+, pydantic v2, temporalio, PyYAML, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md`

## Global Constraints

- **Backward compatibility is an invariant.** Every `records.jsonl` line already on disk must keep parsing after the schema change. New fields are optional with defaults.
- **Pure core, I/O at the edges.** `waste_matrix.py`, `sc_rollup.py`, and `experiments.py` are pure `build_*` + `render_*` with no filesystem access. Only `score.py` and the CLI write files. This mirrors `heatmap.py:1-6` and `error_matrix.py:1-6`.
- **No Temporal *client* on the scoring path.** Precisely: `sdlc benchmark score` must need no server, no worker, and no connection. It does **not** mean avoiding the `temporalio` package — that is a hard dependency (`pyproject.toml:6`) and `report.py` imports `from temporalio import activity` for `finalize_benchmark_report`. The invariant to guard is that `Client` is never imported at module scope in `benchmarks/cli.py`, and that `evidence.py` imports `report` lazily so the cost is paid only when records are actually read.
- **Never render an unmeasured value as zero.** An absent harness session is `None`, not an all-zero bag. Blank cell, never `0`.
- **Degrade and report, never crash** — with one exception: `experiment compare` against a missing `bench_id` is a hard error (a comparison against nothing is a wrong answer, not a degraded one).
- **ASCII only in rendered Markdown.** `report.py:70-74` documents why: a Windows console's cp1252 codepage mangles em dashes when the report is printed.
- **Test invocation:** `pytest` runs fast unit tests only (`addopts = "-q -m 'not slow and not temporal'"`, `pyproject.toml:34`). No task in this plan needs a Temporal server.
- **Commit style:** conventional commits, ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

### Deviation from the spec, applied throughout

The spec (§3.1) says `WasteBag.from_digest` returns an empty bag when the
digest is `None`. That conflicts with §3.3/§7, which require an unmeasured
stage to render **blank, never `0`** — an all-zero bag is indistinguishable
from a genuinely clean run. This plan resolves it the only way that satisfies
both: `from_digest` returns `WasteBag | None`, and the record field is
`waste: WasteBag | None = None`. Task 1 Step 7 updates the spec text to match.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/sdlc/benchmarks/evidence.py` | All reads. Loads records + run summaries for a selector into a typed `Evidence` bundle. |
| `src/sdlc/benchmarks/waste_matrix.py` | Pure: task x arm waste aggregation + HTML/JSON rendering. |
| `src/sdlc/benchmarks/sc_rollup.py` | Pure: SC-1/3/4/6 rate computation + HTML/JSON/Markdown rendering. |
| `src/sdlc/benchmarks/score.py` | The only writer. Turns an `Evidence` bundle into an output directory. |
| `src/sdlc/benchmarks/experiments.py` | Pure: experiment-log models, delta computation, YAML load/save. |
| `tests/test_benchmark_waste_bag.py` | `WasteBag` + record backward compatibility. |
| `tests/test_waste_population_wiring.py` | Source-wiring assertions for `feature.py`. |
| `tests/test_benchmark_evidence.py` | Selector semantics + degradation notes. |
| `tests/test_benchmark_score.py` | Output set, degradation, weights. |
| `tests/test_benchmark_waste_matrix.py` | Aggregation, row derivation, blank-vs-zero. |
| `tests/test_benchmark_sc_rollup.py` | One test per rate + the denominator floor. |
| `tests/test_benchmark_experiments.py` | Scaffold, deltas, noise floor, hard error. |
| `benchmarks/experiments/.gitkeep` | Makes the committed log directory exist. |

**Modified:**

| File | Change |
|---|---|
| `src/sdlc/benchmarks/models.py` | Add `WasteBag`; add `waste` field to `BenchmarkRecord`. |
| `src/sdlc/workflows/feature.py:379` and `:1035` | `_stage_record` gains `waste`; the `stage="code"` call site passes it. |
| `src/sdlc/observability/activities.py:24` | Also write `summary.json`. |
| `src/sdlc/benchmarks/cli.py` | Lazy Temporal import; `dispatch_score`; `dispatch_experiment_*`. |
| `src/sdlc/cli.py:120-130`, `:191-208` | Replace `report`/`history` parsers and dispatch with `score` + `experiment`. |
| `tests/test_e36_imports.py` | Extend the import-purity guard to the new modules. |
| `docs/superpowers/specs/2026-08-03-...-design.md` | Reconcile §3.1 with the `None` decision. |

---

## Phase 1 — Evidence: the record can carry waste

### Task 1: `WasteBag` model and the record field

**Files:**
- Modify: `src/sdlc/benchmarks/models.py:15` (imports), append `WasteBag`, extend `BenchmarkRecord`
- Modify: `docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md`
- Test: `tests/test_benchmark_waste_bag.py`

**Interfaces:**
- Consumes: `SessionDigest` from `sdlc.models` (fields at `src/sdlc/models.py:103-119`)
- Produces: `WasteBag` with fields `tool_calls, file_reads, file_rereads, files_written, rewrite_churn, failed_commands, model_turns, denials, escalations, compacted`; classmethod `WasteBag.from_digest(d: SessionDigest | None) -> WasteBag | None`; field `BenchmarkRecord.waste: WasteBag | None = None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_waste_bag.py`:

```python
from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag,
    WasteBag,
)
from sdlc.models import HarnessKind, SessionDigest

T = datetime(2026, 8, 3, 10)


def _digest(**kw):
    base = dict(tool_calls=12, file_reads=8, file_rereads=3, files_written=4,
                rewrite_churn=2, failed_commands=1, model_turns=6,
                denials=1, escalations=2, compacted=True,
                input_tokens=100, output_tokens=20,
                decision_skeleton=["Read a.py", "Edit a.py"])
    base.update(kw)
    return SessionDigest(**base)


def test_from_digest_copies_every_waste_field():
    bag = WasteBag.from_digest(_digest())
    assert bag == WasteBag(
        tool_calls=12, file_reads=8, file_rereads=3, files_written=4,
        rewrite_churn=2, failed_commands=1, model_turns=6,
        denials=1, escalations=2, compacted=True)


def test_from_digest_drops_skeleton_and_tokens():
    """decision_skeleton is up to 200 strings and tokens live on CostBag;
    neither belongs in a file scanned repeatedly."""
    bag = WasteBag.from_digest(_digest())
    assert not hasattr(bag, "decision_skeleton")
    assert not hasattr(bag, "input_tokens")


def test_from_digest_returns_none_when_unmeasured():
    """An absent session is 'not measured', never 'measured zero'."""
    assert WasteBag.from_digest(None) is None


def test_record_waste_defaults_to_none():
    rec = _record()
    assert rec.waste is None


def test_record_written_before_this_change_still_parses():
    """Backward-compatibility invariant: a records.jsonl line with no
    `waste` key must keep parsing."""
    legacy = (
        '{"run_id":"r1","bench_run_id":"b1","case_id":"c1","scope":"stage",'
        '"stage":"code","role":"dev","harness":"opencode","model":"m",'
        '"prompt_sha":"","quality":{"score":1.0,"judge":"contract"},'
        '"cost":{},"speed":{"wall_clock_s":1.0,'
        '"started_at":"2026-08-03T10:00:00","ended_at":"2026-08-03T10:00:01"},'
        '"outcome":"pass","fix_attempts":0}'
    )
    rec = BenchmarkRecord.model_validate_json(legacy)
    assert rec.waste is None
    assert rec.model == "m"


def test_record_round_trips_waste():
    rec = _record(waste=WasteBag(tool_calls=5))
    again = BenchmarkRecord.model_validate_json(rec.model_dump_json())
    assert again.waste is not None and again.waste.tool_calls == 5


def _record(**kw):
    base = dict(
        run_id="r1", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.OPENCODE, model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T,
                       ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    base.update(kw)
    return BenchmarkRecord(**base)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_waste_bag.py -v`
Expected: FAIL — `ImportError: cannot import name 'WasteBag' from 'sdlc.benchmarks.models'`

- [ ] **Step 3: Add `WasteBag` to `src/sdlc/benchmarks/models.py`**

Extend the existing import at line 16 to include `SessionDigest`:

```python
from ..models import GatePolicy, HarnessKind, SessionDigest
```

Insert `WasteBag` immediately after `SpeedBag` (after line 66):

```python
class WasteBag(BaseModel):
    """BENCHMARK.md §4.3 coordination-and-waste aggregates for one coding
    attempt: activity that did not advance the goal. Projected from
    SessionDigest, minus the unbounded decision_skeleton and the token
    fields CostBag already owns.

    A record carries `waste=None` when no harness session was captured --
    proposer stages have no transcript at all. None means NOT MEASURED and
    must render blank; an all-zero bag would be indistinguishable from a
    genuinely clean run.
    """
    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0      # same path read more than once
    files_written: int = 0     # distinct paths written
    rewrite_churn: int = 0     # paths written more than once
    failed_commands: int = 0   # command events with non-zero exit
    model_turns: int = 0
    denials: int = 0           # E-16: blocked tool calls
    escalations: int = 0       # E-17: tool calls that raised a gate
    compacted: bool = False

    @classmethod
    def from_digest(cls, d: SessionDigest | None) -> "WasteBag | None":
        if d is None:
            return None
        return cls(
            tool_calls=d.tool_calls, file_reads=d.file_reads,
            file_rereads=d.file_rereads, files_written=d.files_written,
            rewrite_churn=d.rewrite_churn,
            failed_commands=d.failed_commands, model_turns=d.model_turns,
            denials=d.denials, escalations=d.escalations,
            compacted=d.compacted)
```

- [ ] **Step 4: Add the field to `BenchmarkRecord`**

In `BenchmarkRecord`, directly after the `speed: SpeedBag` line:

```python
    waste: WasteBag | None = None           # None = no session captured
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_waste_bag.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full fast suite for regressions**

Run: `pytest`
Expected: PASS — the new optional field must not disturb any existing test.

- [ ] **Step 7: Reconcile the spec**

In `docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md` §3.1, replace the `from_digest` docstring block:

```python
    @classmethod
    def from_digest(cls, d: SessionDigest | None) -> "WasteBag | None":
        """None when d is None. An absent session is 'not measured', never
        'measured zero' -- an all-zero bag is indistinguishable from a
        genuinely clean run, which §3.3's blank-not-zero rule forbids."""
```

and change the field declaration sentence to read
`` `BenchmarkRecord` gains `waste: WasteBag | None = None`. ``

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/benchmarks/models.py tests/test_benchmark_waste_bag.py \
        docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md
git commit -m "feat(benchmarks): carry harness waste on BenchmarkRecord

WasteBag projects SessionDigest's bounded aggregates onto the record so
the heatmaps never depend on transcript retention (OQ-B7). None means
not-measured, so proposer stages render blank rather than zero.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Populate waste at the coding-task record

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (imports, `_stage_record` at :379, call site at :1035)
- Test: `tests/test_waste_population_wiring.py`

**Interfaces:**
- Consumes: `WasteBag.from_digest` (Task 1); `run.session_digest` on `HarnessRunResult` (`src/sdlc/models.py:316`), already in scope at `feature.py:1035` beside `cost_usd=run.cost_usd`
- Produces: `FeatureWorkflow._stage_record(..., waste: WasteBag | None = None)`

**Why a source-wiring test:** `_stage_record` calls `workflow.info()`, so it cannot be invoked outside a Temporal context. `tests/test_pending_wiring.py` establishes the codebase pattern — assert the signature via `inspect`, assert the call site via source text. No Temporal server required.

- [ ] **Step 1: Write the failing test**

Create `tests/test_waste_population_wiring.py`:

```python
"""_stage_record calls workflow.info(), so it cannot run outside a Temporal
context. Following tests/test_pending_wiring.py, assert the signature and
the call-site wiring from source instead of spinning up a server."""
from __future__ import annotations

import inspect
import pathlib

from sdlc.workflows.feature import FeatureWorkflow

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_stage_record_accepts_waste():
    sig = inspect.signature(FeatureWorkflow._stage_record)
    assert "waste" in sig.parameters
    assert sig.parameters["waste"].default is None


def test_feature_imports_waste_bag():
    assert "WasteBag" in SRC.read_text(encoding="utf-8")


def test_code_stage_record_passes_the_session_digest():
    """The stage='code' record is the ONE site where a HarnessRunResult with
    a digest exists per task attempt."""
    src = SRC.read_text(encoding="utf-8")
    assert "waste=WasteBag.from_digest(run.session_digest)" in src


def test_only_one_call_site_passes_waste():
    """Proposer stages have no transcript; passing waste anywhere else would
    fabricate a measurement."""
    src = SRC.read_text(encoding="utf-8")
    assert src.count("waste=WasteBag.from_digest") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_waste_population_wiring.py -v`
Expected: FAIL — `assert 'waste' in sig.parameters`

- [ ] **Step 3: Extend the import in `feature.py`**

Find the existing benchmarks-models import (it imports `BenchmarkOutcome`, `BenchmarkRecord`, `BenchmarkScope`, `QualityScore`, `SpeedBag` from `..benchmarks.models`) and add `WasteBag` to it, keeping alphabetical order:

```python
    from ..benchmarks.models import (BenchmarkOutcome, BenchmarkRecord,
                                     BenchmarkScope, QualityScore, SpeedBag,
                                     WasteBag)
```

- [ ] **Step 4: Add the parameter to `_stage_record`**

At `feature.py:379`, add `waste` to the signature after `attempt`:

```python
                      task_id: str | None = None,
                      attempt: int | None = None,
                      waste: "WasteBag | None" = None,
                      error: str | None = None) -> BenchmarkRecord:
```

and pass it through in the `BenchmarkRecord(...)` construction, on the line after `speed=SpeedBag(...)`:

```python
            waste=waste,
```

- [ ] **Step 5: Pass the digest at the `stage="code"` call site**

At `feature.py:1035`, the `stage="code"` record. Add one line after `cost_usd=run.cost_usd,`:

```python
            await self._record(cfg, self._stage_record(
                cfg, stage="code", role=task.role,
                started=_attempt_started, ended=workflow.now(),
                quality_score=(1.0 if task_passed else 0.0),
                judge="contract",
                outcome=(BenchmarkOutcome.PASS if task_passed
                         else BenchmarkOutcome.FAIL),
                model=role_cfg.model,
                harness=role_cfg.harness,
                cost_usd=run.cost_usd,
                waste=WasteBag.from_digest(run.session_digest),
                fix_attempts=attempt - 1,
                task_id=task.id, attempt=attempt - 1))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_waste_population_wiring.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run the workflow purity and full fast suites**

Run: `pytest tests/test_factory_purity.py tests/test_pending_wiring.py -v && pytest`
Expected: PASS. `test_factory_purity.py` guards that workflow code performs no I/O — `WasteBag.from_digest` is a pure in-memory projection, so it must stay green.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_waste_population_wiring.py
git commit -m "feat(benchmarks): record harness waste on coding-task attempts

One call site: the stage='code' record, where the HarnessRunResult with
its SessionDigest is already in scope. Proposer stages keep waste=None
because they have no transcript by construction.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Persist `RunSummary` as data

**Files:**
- Modify: `src/sdlc/observability/activities.py:24-32`
- Test: `tests/test_export_activity.py`

**Interfaces:**
- Produces: `runs/<run_id>/summary.json` containing `RunSummary.model_dump_json(indent=2)`. Consumed by `evidence.py` (Task 4) and `sc_rollup.py` (Task 7).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_activity.py`:

```python
@pytest.mark.asyncio
async def test_export_writes_summary_json_as_data(tmp_path, monkeypatch):
    """report.html is lossy; the SC rollup needs RunSummary as data."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    summary = RunSummary(run_id="run-abc", mode="greenfield",
                         outcome="deployed:http://pr/1",
                         terminal_stage="deploy",
                         started_at=T0, ended_at=T0, duration_s=0.0)
    await export_run_artifacts(
        RunExportInput(run_id="run-abc", summary=summary, trace=[
            RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)]))
    p = tmp_path / "run-abc" / "summary.json"
    assert p.exists()
    again = RunSummary.model_validate_json(p.read_text(encoding="utf-8"))
    assert again.run_id == "run-abc"
    assert again.outcome == "deployed:http://pr/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_activity.py::test_export_writes_summary_json_as_data -v`
Expected: FAIL — `assert False` on `p.exists()`

- [ ] **Step 3: Write the file**

In `src/sdlc/observability/activities.py`, after the `report.html` write (line 30-31):

```python
    # summary.json is RunSummary as DATA. report.html above is a lossy
    # human view of the same object; the SC rollup needs the structure.
    (run_dir / "summary.json").write_text(
        inp.summary.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_export_activity.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/activities.py tests/test_export_activity.py
git commit -m "feat(observability): persist RunSummary as summary.json

report.html is a lossy human view; the cross-run SC rollup needs the
structured object. One extra write in the existing export activity.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Phase 2 — The reader and the fast command

### Task 4: `evidence.py` — one reader for both stores

**Files:**
- Create: `src/sdlc/benchmarks/evidence.py`
- Test: `tests/test_benchmark_evidence.py`

**Interfaces:**
- Consumes: `_read_all`, `scan_case_records` from `sdlc.benchmarks.report`; `_root` from `sdlc.benchmarks.recorder`; `RunSummary` from `sdlc.models`
- Produces:
  - `Evidence(records: list[BenchmarkRecord], summaries: list[RunSummary], selector: str, notes: list[str])`
  - `export_root(root: str | None = None) -> Path`
  - `load_run_summaries(root: str | None = None) -> tuple[list[RunSummary], list[str]]` — returns summaries and degradation notes
  - `load_evidence(*, bench=None, case=None, all_=False, root=None, export_root_=None) -> Evidence`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_evidence.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.evidence'`

- [ ] **Step 3: Write `src/sdlc/benchmarks/evidence.py`**

```python
"""One reader for every evidence store the scorer needs.

Two stores, joined here and nowhere else:
  - runs/benchmarks/<bench_run_id>/*.jsonl   BenchmarkRecords
  - runs/<run_id>/summary.json               RunSummary (E-32 retro export)

The artifact store (harness transcripts) is deliberately NOT read: OQ-B7
leaves the transcript TTL open, so any aggregation joining against it goes
blind once retention prunes. The bounded WasteBag rides on the record
instead.

`sdlc benchmark score` must run with no worker, no server and no client
connection. `report.py` imports `from temporalio import activity` for
finalize_benchmark_report, so it is imported LAZILY below rather than at
module scope.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from ..models import RunSummary
from .models import BenchmarkRecord

DEFAULT_EXPORT_ROOT = "./runs"


class Evidence(BaseModel):
    """Everything a score run reads, plus the notes explaining what was
    missing. `notes` is rendered into report.md so a degraded score is
    visibly degraded rather than quietly partial."""
    records: list[BenchmarkRecord] = Field(default_factory=list)
    summaries: list[RunSummary] = Field(default_factory=list)
    selector: str = "_all"
    notes: list[str] = Field(default_factory=list)


def export_root(root: str | None = None) -> Path:
    """Where the retro stage writes runs/<run_id>/. Mirrors
    observability/activities.py's SDLC_EXPORT_ROOT resolution."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get("SDLC_EXPORT_ROOT", DEFAULT_EXPORT_ROOT))


def load_run_summaries(root: str | None = None
                       ) -> tuple[list[RunSummary], list[str]]:
    """Every runs/*/summary.json under the export root, plus notes for the
    ones that could not be read. A malformed export degrades that one run,
    never the rollup."""
    base = export_root(root)
    notes: list[str] = []
    if not base.is_dir():
        return [], [f"export root {base} does not exist; no SC rates computed"]
    out: list[RunSummary] = []
    for p in sorted(base.glob("*/summary.json")):
        try:
            out.append(RunSummary.model_validate_json(
                p.read_text(encoding="utf-8")))
        except Exception as e:                              # noqa: BLE001
            notes.append(f"unreadable summary {p.parent.name}: {e}")
    if not out and not notes:
        notes.append(f"no summary.json under {base}; no SC rates computed")
    return out, notes


def load_evidence(*, bench: str | None = None, case: str | None = None,
                  all_: bool = False, root: str | None = None,
                  export_root_: str | None = None) -> Evidence:
    """Load records for exactly one selector, plus every run summary.

    Selectors are mutually exclusive so a score directory always has one
    unambiguous provenance.
    """
    from .report import _read_all, scan_case_records

    chosen = [x for x in (bench, case, True if all_ else None)
              if x is not None]
    if len(chosen) != 1:
        raise ValueError(
            "exactly one of bench=, case=, all_= must be given")

    notes: list[str] = []
    if bench is not None:
        records = _read_all(bench, root)
        selector = bench
    elif case is not None:
        records = scan_case_records(case, root)
        selector = f"_case/{case}"
    else:
        records = _read_all_benches(root)
        selector = "_all"

    if not records:
        notes.append(f"no benchmark records for selector {selector}")

    summaries, s_notes = load_run_summaries(export_root_)
    return Evidence(records=records, summaries=summaries, selector=selector,
                    notes=notes + s_notes)


def _read_all_benches(root: str | None) -> list[BenchmarkRecord]:
    """Every record under every bench_run_id directory."""
    from .recorder import _root
    from .report import _read_all

    base = Path(root if root is not None else _root())
    if not base.is_dir():
        return []
    out: list[BenchmarkRecord] = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        out.extend(_read_all(d.name, root))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_evidence.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/evidence.py tests/test_benchmark_evidence.py
git commit -m "feat(benchmarks): one reader for records and run summaries

Selector-scoped loads with degradation notes carried alongside the data,
so a partial score is visibly partial. No temporalio import -- scoring
must run with no worker and no server.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `score.py` + the `sdlc benchmark score` command

**Files:**
- Create: `src/sdlc/benchmarks/score.py`
- Modify: `src/sdlc/benchmarks/cli.py:13-14` (lazy import), add `dispatch_score`, remove `dispatch_report`/`dispatch_history`
- Modify: `src/sdlc/cli.py:129-130` (parsers), `:191-208` (dispatch)
- Modify: `tests/test_e36_imports.py`
- Test: `tests/test_benchmark_score.py`

**Interfaces:**
- Consumes: `Evidence`, `load_evidence` (Task 4); `aggregate`, `render_markdown`, `resolve_language_map`, `write_heatmap` from `report.py`; `build_task_matrix`/`render_task_matrix_*`, `build_error_matrix`/`render_error_matrix_*`, `load_task_suite`
- Produces:
  - `parse_weights(s: str) -> CompositeWeights`
  - `load_config_weights(path: Path | None = None) -> CompositeWeights`
  - `default_out_dir(selector: str, root: str | None = None) -> Path`
  - `write_score(ev: Evidence, out_dir: Path, weights: CompositeWeights) -> list[Path]`
  - `dispatch_score(*, bench, case, all_, out, weights, root=None) -> str` in `cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_score.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from sdlc.benchmarks.evidence import Evidence
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CompositeWeights,
    CostBag, QualityScore, SpeedBag, WasteBag)
from sdlc.benchmarks.score import (
    default_out_dir, load_config_weights, parse_weights, write_score)
from sdlc.models import HarnessKind

T = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


def _rec(case="c1", task=None, scope=BenchmarkScope.STAGE, stage="code",
         usd=1.0, waste=None):
    return BenchmarkRecord(
        run_id="r1", bench_run_id="b1", case_id=case, scope=scope,
        stage=stage, task_id=task, role="dev",
        harness=HarnessKind.OPENCODE, model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=2.0, started_at=T,
                       ended_at=T + timedelta(seconds=2)),
        outcome=BenchmarkOutcome.PASS, waste=waste)


def test_parse_weights_accepts_three_floats():
    w = parse_weights("0.5,0.3,0.2")
    assert (w.quality, w.cost, w.speed) == (0.5, 0.3, 0.2)


def test_parse_weights_rejects_wrong_arity():
    with pytest.raises(ValueError, match="quality,cost,speed"):
        parse_weights("0.5,0.5")


def test_parse_weights_need_not_sum_to_one():
    """scoring.py renormalises over available axes, so 3,1,1 is legal."""
    w = parse_weights("3,1,1")
    assert w.quality == 3.0


def test_load_config_weights_reads_benchmarks_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("weights:\n  quality: 0.7\n  cost: 0.2\n  speed: 0.1\n",
                 encoding="utf-8")
    w = load_config_weights(p)
    assert w.quality == 0.7 and w.speed == 0.1


def test_load_config_weights_defaults_when_absent(tmp_path):
    w = load_config_weights(tmp_path / "missing.yaml")
    assert w == CompositeWeights()


def test_default_out_dir_is_derived_from_selector(tmp_path):
    assert default_out_dir("b1", root=str(tmp_path)).name == "score"
    assert default_out_dir("b1", root=str(tmp_path)).parent.name == "b1"
    assert "c1" in str(default_out_dir("_case/c1", root=str(tmp_path)))


def test_write_score_emits_report_and_heatmap(tmp_path):
    ev = Evidence(records=[_rec()], selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    names = {p.name for p in written}
    assert {"report.md", "heatmap.html", "heatmap.json"} <= names
    assert (tmp_path / "report.md").read_text(encoding="utf-8")


def test_missing_tasks_yaml_skips_matrices_and_notes_it(tmp_path, monkeypatch):
    """cat-cafe-monitoring has no tasks.yaml; today dispatch_history RAISES.
    Under score it must degrade."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "no-cases"))
    ev = Evidence(records=[_rec(task="t01",
                                scope=BenchmarkScope.ORACLE_TASK,
                                stage="oracle")],
                  selector="_case/c1")
    written = write_score(ev, tmp_path, CompositeWeights())
    assert "task-matrix.html" not in {p.name for p in written}
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "tasks.yaml" in md


def test_empty_evidence_writes_a_report_and_does_not_raise(tmp_path):
    ev = Evidence(records=[], selector="_all",
                  notes=["no benchmark records for selector _all"])
    written = write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "no benchmark records" in md
    assert any(p.name == "report.md" for p in written)


def test_notes_are_rendered_into_the_report(tmp_path):
    ev = Evidence(records=[_rec()], selector="b1",
                  notes=["export root /x does not exist; no SC rates computed"])
    write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "no SC rates computed" in md


def test_report_markdown_is_ascii_only(tmp_path):
    """report.py:70-74 -- a Windows cp1252 console mangles non-ASCII."""
    ev = Evidence(records=[_rec()], selector="b1", notes=["a note"])
    write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    md.encode("ascii")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.score'`

- [ ] **Step 3: Write `src/sdlc/benchmarks/score.py`**

```python
"""The one writer. Turns an Evidence bundle into a score directory.

Every grid module stays pure (build_* + render_*); this module owns the
filesystem. Missing inputs degrade with a note in report.md and exit 0 --
a gap in the corpus is not a crash.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .evidence import Evidence
from .models import CompositeWeights

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"


def parse_weights(s: str) -> CompositeWeights:
    """'0.6,0.2,0.2' -> CompositeWeights. Need not sum to 1: scoring.py
    renormalises over whichever axes have data in each group."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"--weights takes three floats as quality,cost,speed; got {s!r}")
    try:
        q, c, sp = (float(p) for p in parts)
    except ValueError as e:
        raise ValueError(
            f"--weights takes three floats as quality,cost,speed; got {s!r}"
        ) from e
    return CompositeWeights(quality=q, cost=c, speed=sp)


def load_config_weights(path: Path | None = None) -> CompositeWeights:
    """benchmarks/config.yaml has declared `weights:` since E-27 and nothing
    has ever read them. This is where they start mattering."""
    p = path if path is not None else _BENCH_CONFIG
    if not Path(p).is_file():
        return CompositeWeights()
    try:
        data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
    except Exception:                                        # noqa: BLE001
        return CompositeWeights()
    w = data.get("weights") or {}
    return CompositeWeights(
        quality=float(w.get("quality", 0.6)),
        cost=float(w.get("cost", 0.2)),
        speed=float(w.get("speed", 0.2)))


def default_out_dir(selector: str, root: str | None = None) -> Path:
    from .recorder import _root
    base = Path(root if root is not None else _root())
    return base / selector / "score"


def write_score(ev: Evidence, out_dir: Path,
                weights: CompositeWeights) -> list[Path]:
    """Write every grid the evidence supports. Returns the paths written."""
    from .calibration import load_calibration_reports, render_calibration_html
    from .report import (aggregate, render_markdown, resolve_language_map,
                         write_heatmap)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    notes = list(ev.notes)

    calibration = load_calibration_reports()
    summaries = aggregate("", weights, _records=ev.records)

    lang = resolve_language_map(sorted({r.case_id for r in ev.records}))
    html_p, json_p = write_heatmap(ev.records, out_dir, lang,
                                   render_calibration_html(calibration))
    written += [html_p, json_p]

    written += _write_case_matrices(ev, out_dir, notes)

    md = render_markdown(summaries, calibration=calibration)
    md += _render_notes(notes)
    report_p = out_dir / "report.md"
    report_p.write_text(md, encoding="utf-8")
    written.append(report_p)
    return written


def _render_notes(notes: list[str]) -> str:
    """ASCII only (report.py:70-74)."""
    if not notes:
        return ""
    lines = ["", "## Notes", ""]
    lines += [f"- {n}" for n in notes]
    return "\n".join(lines) + "\n"


def _write_case_matrices(ev: Evidence, out_dir: Path,
                         notes: list[str]) -> list[Path]:
    """Per-case task and error matrices. A case with no tasks.yaml is
    skipped with a note -- today dispatch_history raises here (cli.py:92),
    and only todo-api-greenfield has the file."""
    from .error_matrix import (build_error_matrix, render_error_matrix_html,
                               render_error_matrix_json)
    from .task_matrix import (build_task_matrix, render_task_matrix_html,
                              render_task_matrix_json)
    from .tasks import load_task_suite

    written: list[Path] = []
    cases = sorted({r.case_id for r in ev.records})
    for case_id in cases:
        try:
            suite = load_task_suite(case_id)
        except Exception as e:                               # noqa: BLE001
            notes.append(f"case {case_id}: malformed tasks.yaml, task and "
                         f"error matrices skipped ({e})")
            continue
        if suite is None:
            notes.append(f"case {case_id}: no tasks.yaml, task and error "
                         f"matrices skipped")
            continue
        d = out_dir if len(cases) == 1 else out_dir / case_id
        d.mkdir(parents=True, exist_ok=True)
        tm = build_task_matrix(case_id, ev.records, suite)
        em = build_error_matrix(case_id, ev.records, suite)
        for name, text in (
            ("task-matrix.html", render_task_matrix_html(tm)),
            ("task-matrix.json", render_task_matrix_json(tm)),
            ("error-matrix.html", render_error_matrix_html(em)),
            ("error-matrix.json", render_error_matrix_json(em)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)
    return written
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_score.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Make the Temporal import lazy and add `dispatch_score`**

In `src/sdlc/benchmarks/cli.py`, delete the module-level lines 13-14:

```python
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
```

and move them inside `_run_matrix`, as its first two statements:

```python
async def _run_matrix(case_path: str, gate_policy: str | None = None) -> str:
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    spec = load_case_spec(case_path)
```

Replace `dispatch_report` and `dispatch_history` with one handler:

```python
def dispatch_score(*, bench: str | None = None, case: str | None = None,
                   all_: bool = False, out: str | None = None,
                   weights: str | None = None,
                   root: str | None = None) -> str:
    """Read every evidence store for one selector and write the full score
    directory. Seconds, no Temporal client, no worker."""
    from .evidence import load_evidence
    from .score import (default_out_dir, load_config_weights, parse_weights,
                        write_score)

    ev = load_evidence(bench=bench, case=case, all_=all_, root=root)
    w = parse_weights(weights) if weights else load_config_weights()
    out_dir = Path(out) if out else default_out_dir(ev.selector, root)
    written = write_score(ev, out_dir, w)
    return "\n".join(str(p) for p in written)
```

- [ ] **Step 6: Rewire the CLI parsers and dispatch**

In `src/sdlc/cli.py`, replace lines 129-130:

```python
    bs = bsub.add_parser("score")
    bsg = bs.add_mutually_exclusive_group(required=True)
    bsg.add_argument("--bench", help="one bench_run_id")
    bsg.add_argument("--case", help="every bench run for one case")
    bsg.add_argument("--all", action="store_true", dest="all_",
                     help="every bench run for every case")
    bs.add_argument("--out", default=None,
                    help="output dir (default: <root>/<selector>/score)")
    bs.add_argument("--weights", default=None, metavar="Q,C,S",
                    help="composite weights as quality,cost,speed; "
                         "defaults to benchmarks/config.yaml")
```

and replace the `report`/`history` branches at lines 191-208 with:

```python
    if args.cmd == "benchmark":
        if args.bench_cmd == "score":
            from .benchmarks.cli import dispatch_score
            print(dispatch_score(bench=args.bench, case=args.case,
                                 all_=args.all_, out=args.out,
                                 weights=args.weights))
            return
        if args.bench_cmd == "run":
            from .benchmarks.cli import _run_matrix
            print(await _run_matrix(args.case, args.gate_policy))
            return
        if args.bench_cmd == "drift":
            print("drift requires a live Temporal client; see ARCHITECTURE.md section 8.")
            return
```

Note the `from .benchmarks.cli import dispatch_report` at line 192 is deleted with the block — that unconditional import is what made every benchmark subcommand pay for `temporalio.client`.

- [ ] **Step 7: Extend the import-purity guard**

Replace the body of `tests/test_e36_imports.py`:

```python
def test_benchmark_and_calibration_modules_import():
    import sdlc.benchmarks.heatmap          # noqa: F401
    import sdlc.benchmarks.calibration      # noqa: F401
    from sdlc.benchmarks.report import (    # noqa: F401
        finalize_benchmark_report, write_heatmap, resolve_language_map)
    from sdlc.benchmarks.cli import dispatch_calibrate  # noqa: F401


def test_scoring_path_modules_import():
    import sdlc.benchmarks.evidence         # noqa: F401
    import sdlc.benchmarks.score            # noqa: F401
    from sdlc.benchmarks.cli import dispatch_score      # noqa: F401


def test_benchmark_cli_has_no_module_level_temporal_client():
    """`sdlc benchmark score` must run with no worker and no server, so the
    Temporal client import belongs inside _run_matrix, not at module scope."""
    import pathlib
    src = pathlib.Path("src/sdlc/benchmarks/cli.py").read_text(encoding="utf-8")
    head = src.split("def _run_matrix")[0]
    assert "from temporalio.client import Client" not in head
```

- [ ] **Step 8: Run the full fast suite**

Run: `pytest`
Expected: PASS. `tests/test_benchmark_cli.py` and `tests/test_cli_local_only.py` reference the removed handlers — update any assertion naming `dispatch_report` or `dispatch_history` to `dispatch_score`, and any `bench_cmd == "report"` / `"history"` expectation to `"score"`. Keep `_needs_temporal_client` returning `False` for `args.cmd == "benchmark"` (`cli.py:52`); that stays correct.

- [ ] **Step 9: Verify the command by hand**

Run: `python -m sdlc.cli benchmark score --all`
Expected: prints one path per written file, exits 0. On a machine with no `runs/benchmarks/` it still exits 0 and the report says `no benchmark records for selector _all`.

- [ ] **Step 10: Commit**

```bash
git add src/sdlc/benchmarks/score.py src/sdlc/benchmarks/cli.py src/sdlc/cli.py \
        tests/test_benchmark_score.py tests/test_e36_imports.py \
        tests/test_benchmark_cli.py tests/test_cli_local_only.py
git commit -m "feat(benchmarks): one fast score command replacing report/history

score reads every evidence store for one selector and writes the full
grid set in seconds. The Temporal client import moves into _run_matrix so
scoring needs no worker; a case with no tasks.yaml now degrades with a
note instead of raising (cli.py:92). --weights finally reads the
config.yaml block that has been dead since E-27.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Phase 3 — The two new grids

### Task 6: `waste_matrix.py` — task x arm tool-call behaviour

**Files:**
- Create: `src/sdlc/benchmarks/waste_matrix.py`
- Modify: `src/sdlc/benchmarks/score.py` (wire it into `write_score`)
- Test: `tests/test_benchmark_waste_matrix.py`

**Interfaces:**
- Consumes: `BenchmarkRecord.waste` (Task 1); `TaskSuite` from `sdlc.benchmarks.tasks` (optional)
- Produces:
  - `WASTE_METRICS: list[str]` — the six gridded metrics
  - `WasteCell(task_id, arm_key, metric, value, n_runs)`
  - `WasteMatrix(case_id, metrics, task_ids, arms, cells, max_by_metric)`
  - `build_waste_matrix(case_id: str, records: list[BenchmarkRecord], suite: TaskSuite | None = None) -> WasteMatrix`
  - `render_waste_matrix_html(wm) -> str`, `render_waste_matrix_json(wm) -> str`

**Aggregation rule:** sum a metric across attempts within one `(bench_run_id, run_id)` — total thrash on a task is the meaningful quantity — then mean over runs, matching `error_matrix.py:56`.

**Row rule:** `task_id` observed on records carrying a non-`None` `waste`, ordered by `suite` when given, alphabetically otherwise. No `tasks.yaml` dependency.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_waste_matrix.py`:

```python
from datetime import datetime, timedelta, timezone

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag,
    WasteBag)
from sdlc.benchmarks.tasks import TaskSpec, TaskSuite
from sdlc.benchmarks.waste_matrix import (
    WASTE_METRICS, build_waste_matrix, render_waste_matrix_html,
    render_waste_matrix_json)
from sdlc.models import HarnessKind

T = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


def _rec(*, task, bench="b1", run="r1", model="m",
         harness=HarnessKind.OPENCODE, waste=None, stage="code"):
    return BenchmarkRecord(
        run_id=run, bench_run_id=bench, case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT, stage=stage, task_id=task,
        role="dev", harness=harness, model=model,
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T,
                       ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS, waste=waste)


def _cell(wm, task, arm, metric):
    return next(c for c in wm.cells if c.task_id == task
                and c.arm_key == arm and c.metric == metric)


def test_six_metrics_are_gridded():
    """Volume metrics (file_reads, files_written, model_turns) and the
    boolean `compacted` ride on the record but are not waste grids."""
    assert WASTE_METRICS == ["tool_calls", "file_rereads", "rewrite_churn",
                             "failed_commands", "denials", "escalations"]


def test_attempts_sum_within_a_run():
    """Total thrash on a task is the meaningful quantity, not the
    per-attempt average."""
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=10)),
            _rec(task="t01", waste=WasteBag(tool_calls=15))]
    wm = build_waste_matrix("c1", recs)
    assert _cell(wm, "t01", "opencode#m", "tool_calls").value == 25.0


def test_runs_are_averaged():
    recs = [_rec(task="t01", bench="b1", waste=WasteBag(tool_calls=10)),
            _rec(task="t01", bench="b2", waste=WasteBag(tool_calls=20))]
    wm = build_waste_matrix("c1", recs)
    c = _cell(wm, "t01", "opencode#m", "tool_calls")
    assert c.value == 15.0 and c.n_runs == 2


def test_arms_separate_by_harness_and_model():
    recs = [_rec(task="t01", harness=HarnessKind.OPENCODE, model="m1",
                 waste=WasteBag(tool_calls=10)),
            _rec(task="t01", harness=HarnessKind.CLAUDE_CODE, model="m1",
                 waste=WasteBag(tool_calls=40))]
    wm = build_waste_matrix("c1", recs)
    assert wm.arms == ["claude_code#m1", "opencode#m1"]
    assert _cell(wm, "t01", "claude_code#m1", "tool_calls").value == 40.0


def test_unmeasured_records_produce_no_cell():
    """waste=None means not measured; a cell would assert zero waste."""
    recs = [_rec(task="t01", waste=None)]
    wm = build_waste_matrix("c1", recs)
    assert wm.cells == []
    assert wm.task_ids == []


def test_rows_come_from_records_without_tasks_yaml():
    """cat-cafe-monitoring has no tasks.yaml and must still get a grid."""
    recs = [_rec(task="t02", waste=WasteBag(tool_calls=1)),
            _rec(task="t01", waste=WasteBag(tool_calls=1))]
    wm = build_waste_matrix("c1", recs, suite=None)
    assert wm.task_ids == ["t01", "t02"]


def test_suite_order_wins_when_present():
    suite = TaskSuite(case_id="c1", tasks=[
        TaskSpec(id="t02", error_class="functional", oracle_tests=["a::b"]),
        TaskSpec(id="t01", error_class="security", oracle_tests=["a::c"]),
    ])
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=1)),
            _rec(task="t02", waste=WasteBag(tool_calls=1))]
    wm = build_waste_matrix("c1", recs, suite=suite)
    assert wm.task_ids == ["t02", "t01"]


def test_other_cases_are_excluded():
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=5))]
    assert build_waste_matrix("other", recs).cells == []


def test_max_by_metric_scales_each_grid_independently():
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=100, denials=2))]
    wm = build_waste_matrix("c1", recs)
    assert wm.max_by_metric["tool_calls"] == 100.0
    assert wm.max_by_metric["denials"] == 2.0


def test_html_renders_a_section_per_metric_and_blank_for_absent():
    recs = [_rec(task="t01", model="m1", waste=WasteBag(tool_calls=7)),
            _rec(task="t02", model="m2", waste=WasteBag(tool_calls=3))]
    wm = build_waste_matrix("c1", recs)
    html = render_waste_matrix_html(wm)
    assert "<!doctype html>" in html
    for m in WASTE_METRICS:
        assert m in html
    # t01 has no opencode#m2 cell -- it must be blank, never "0"
    assert 'class="empty"></td>' in html


def test_html_is_escaped():
    recs = [_rec(task="<script>", waste=WasteBag(tool_calls=1))]
    html = render_waste_matrix_html(build_waste_matrix("c1", recs))
    assert "<script>" not in html.split("<style>")[1]


def test_json_round_trips():
    import json
    recs = [_rec(task="t01", waste=WasteBag(tool_calls=7))]
    data = json.loads(render_waste_matrix_json(build_waste_matrix("c1", recs)))
    assert data["case_id"] == "c1"
    assert data["cells"][0]["metric"] in WASTE_METRICS


def test_empty_records_render_without_raising():
    wm = build_waste_matrix("c1", [])
    assert "No waste records" in render_waste_matrix_html(wm)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_waste_matrix.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.waste_matrix'`

- [ ] **Step 3: Write `src/sdlc/benchmarks/waste_matrix.py`**

```python
"""task x arm harness-waste matrix (BENCHMARK.md §4.3).

One stacked grid per waste metric: rows are tasks, columns are
harness#model arms, cell = mean-over-runs of the per-run summed metric.
Pure aggregation + rendering, no I/O -- mirrors error_matrix.py.

Rows come from task_ids observed on records that actually carry a
WasteBag, so a case with no tasks.yaml still gets a grid. A record with
waste=None contributes NOTHING: it was not measured, and a zero cell
would claim it was.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord
from .tasks import TaskSuite

# The six metrics that measure work which did not advance the goal.
# file_reads / files_written / model_turns measure VOLUME (a task that
# legitimately touches more files is not thrashing) and `compacted` is a
# boolean; all four ride on the record and land in the JSON, but none gets
# a grid.
WASTE_METRICS: list[str] = [
    "tool_calls", "file_rereads", "rewrite_churn",
    "failed_commands", "denials", "escalations",
]


class WasteCell(BaseModel):
    task_id: str
    arm_key: str
    metric: str
    value: float          # mean over runs of the per-run summed metric
    n_runs: int


class WasteMatrix(BaseModel):
    case_id: str
    metrics: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    arms: list[str] = Field(default_factory=list)
    cells: list[WasteCell] = Field(default_factory=list)
    max_by_metric: dict[str, float] = Field(default_factory=dict)


def build_waste_matrix(case_id: str, records: list[BenchmarkRecord],
                       suite: TaskSuite | None = None) -> WasteMatrix:
    recs = [r for r in records
            if r.case_id == case_id and r.task_id and r.waste is not None]
    if not recs:
        return WasteMatrix(case_id=case_id, metrics=list(WASTE_METRICS))

    # sum within a run-instance, then mean across run-instances
    per_run: dict[tuple[str, str, str, str], float] = defaultdict(float)
    runs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in recs:
        arm = f"{r.harness.value if r.harness else ''}#{r.model}"
        for metric in WASTE_METRICS:
            per_run[(r.bench_run_id, r.task_id, arm, metric)] += float(
                getattr(r.waste, metric))
        runs[(r.task_id, arm, "")].add(r.bench_run_id)

    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for (_bench, task_id, arm, metric), v in per_run.items():
        totals[(task_id, arm, metric)] += v

    cells: list[WasteCell] = []
    for (task_id, arm, metric), total in totals.items():
        n = len(runs[(task_id, arm, "")]) or 1
        cells.append(WasteCell(task_id=task_id, arm_key=arm, metric=metric,
                               value=total / n, n_runs=n))

    observed = {c.task_id for c in cells}
    if suite is not None:
        ordered = [t.id for t in suite.tasks if t.id in observed]
        task_ids = ordered + sorted(observed - set(ordered))
    else:
        task_ids = sorted(observed)

    max_by_metric = {
        m: max((c.value for c in cells if c.metric == m), default=0.0)
        for m in WASTE_METRICS}
    return WasteMatrix(
        case_id=case_id, metrics=list(WASTE_METRICS), task_ids=task_ids,
        arms=sorted({c.arm_key for c in cells}), cells=cells,
        max_by_metric=max_by_metric)


def render_waste_matrix_json(wm: WasteMatrix) -> str:
    return wm.model_dump_json(indent=2)


def _cell_color(value: float, max_value: float) -> str:
    ratio = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    g_b = round(255 - 229 * ratio)   # white (low) -> dark red (high)
    return f"rgb(255,{g_b},{g_b})"


def _grid(wm: WasteMatrix, metric: str) -> str:
    by = {(c.task_id, c.arm_key): c for c in wm.cells if c.metric == metric}
    mx = wm.max_by_metric.get(metric, 0.0)
    head = "".join(f"<th>{escape(a)}</th>" for a in wm.arms)
    rows = []
    for task_id in wm.task_ids:
        tds = [f"<th>{escape(task_id)}</th>"]
        for arm in wm.arms:
            c = by.get((task_id, arm))
            if c is None:
                # not measured on this arm -- blank, never 0
                tds.append('<td class="empty"></td>')
                continue
            tip = (f"{task_id} / {arm}: {c.value:.1f} {metric} per run "
                   f"over {c.n_runs} runs")
            tds.append(
                f'<td title="{escape(tip)}" '
                f'style="background:{_cell_color(c.value, mx)}">'
                f"{c.value:.1f}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f"<h2>{escape(metric)}</h2>"
            f"<table><tr><th>task \\ arm</th>{head}</tr>"
            + "".join(rows) + "</table>")


def render_waste_matrix_html(wm: WasteMatrix) -> str:
    if not wm.cells:
        body = "<p>No waste records. Sessions are captured only for coding "
        body += "tasks, so a case with no graded coding attempts has none.</p>"
    else:
        body = "".join(_grid(wm, m) for m in wm.metrics)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Harness waste - {escape(wm.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Harness waste - {escape(wm.case_id)}</h1>
<p>Cell = mean per run of that metric, summed across attempts within a run.
Whiter is cleaner; redder is more waste. A blank cell was never measured --
it is not a zero. Proposer stages (clarify, architect, planner, qa, reviewer,
analyst) have no harness transcript at all and never appear here.</p>
{body}
</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_waste_matrix.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Wire it into `write_score`**

In `src/sdlc/benchmarks/score.py::_write_case_matrices`, the waste matrix must be written for **every** case, including cases skipped for missing `tasks.yaml`. Restructure the loop body so the waste write happens before the suite check:

```python
def _write_case_matrices(ev: Evidence, out_dir: Path,
                         notes: list[str]) -> list[Path]:
    """Per-case grids. The waste matrix takes no tasks.yaml dependency and
    is written for every case; the task and error matrices need the suite
    and are skipped with a note when it is absent (today dispatch_history
    raises here, cli.py:92)."""
    from .error_matrix import (build_error_matrix, render_error_matrix_html,
                               render_error_matrix_json)
    from .task_matrix import (build_task_matrix, render_task_matrix_html,
                              render_task_matrix_json)
    from .tasks import load_task_suite
    from .waste_matrix import (build_waste_matrix, render_waste_matrix_html,
                               render_waste_matrix_json)

    written: list[Path] = []
    cases = sorted({r.case_id for r in ev.records})
    for case_id in cases:
        d = out_dir if len(cases) == 1 else out_dir / case_id
        d.mkdir(parents=True, exist_ok=True)

        try:
            suite = load_task_suite(case_id)
        except Exception as e:                               # noqa: BLE001
            notes.append(f"case {case_id}: malformed tasks.yaml, task and "
                         f"error matrices skipped ({e})")
            suite = None

        wm = build_waste_matrix(case_id, ev.records, suite)
        for name, text in (
            ("waste-matrix.html", render_waste_matrix_html(wm)),
            ("waste-matrix.json", render_waste_matrix_json(wm)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)
        if not wm.cells:
            notes.append(f"case {case_id}: no harness waste recorded "
                         f"(runs predating waste capture, or no coding tasks)")

        if suite is None:
            if not any(f"case {case_id}: malformed" in n for n in notes):
                notes.append(f"case {case_id}: no tasks.yaml, task and error "
                             f"matrices skipped")
            continue

        tm = build_task_matrix(case_id, ev.records, suite)
        em = build_error_matrix(case_id, ev.records, suite)
        for name, text in (
            ("task-matrix.html", render_task_matrix_html(tm)),
            ("task-matrix.json", render_task_matrix_json(tm)),
            ("error-matrix.html", render_error_matrix_html(em)),
            ("error-matrix.json", render_error_matrix_json(em)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)
    return written
```

- [ ] **Step 6: Add a score-level test for the wiring**

Append to `tests/test_benchmark_score.py`:

```python
def test_waste_matrix_written_even_without_tasks_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "no-cases"))
    ev = Evidence(records=[_rec(task="t01", waste=WasteBag(tool_calls=9))],
                  selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    assert "waste-matrix.html" in {p.name for p in written}
    assert "t01" in (tmp_path / "waste-matrix.html").read_text(encoding="utf-8")
```

- [ ] **Step 7: Run the full fast suite**

Run: `pytest`
Expected: PASS

- [ ] **Step 8: Add the import-purity guard**

In `tests/test_e36_imports.py::test_scoring_path_modules_import`, add:

```python
    import sdlc.benchmarks.waste_matrix     # noqa: F401
```

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/benchmarks/waste_matrix.py src/sdlc/benchmarks/score.py \
        tests/test_benchmark_waste_matrix.py tests/test_benchmark_score.py \
        tests/test_e36_imports.py
git commit -m "feat(benchmarks): task x arm harness-waste matrix

Six grids -- tool_calls, file_rereads, rewrite_churn, failed_commands,
denials, escalations -- summed across attempts within a run then meaned
over runs. Rows come from observed task_ids, so no tasks.yaml is needed.
An unmeasured cell renders blank; claiming zero waste for a stage with no
transcript would be a lie.

Closes E-36's deferred session-waste follow-on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `sc_rollup.py` — the four success-criteria rates

**Files:**
- Create: `src/sdlc/benchmarks/sc_rollup.py`
- Modify: `src/sdlc/benchmarks/score.py` (wire into `write_score`)
- Test: `tests/test_benchmark_sc_rollup.py`

**Interfaces:**
- Consumes: `RunSummary`, `GateOutcomeSummary`, `ClarificationOutcome` from `sdlc.models`; `BenchmarkRecord` for SC-3
- Produces:
  - `MIN_RUNS: int = 5`, `MERGE_GATE: str = "merge"`, `REACHED_PREFIXES: tuple[str, ...]`
  - `SCRate(criterion, label, rate, n, target, proxy, note)`
  - `SCRollup(rates: list[SCRate], sc4_series: list[SC4Point])`
  - `SC4Point(index: int, run_id: str, human_rate: float)`
  - `build_sc_rollup(summaries, records) -> SCRollup`
  - `render_sc_rollup_html(r) -> str`, `render_sc_rollup_json(r) -> str`, `render_sc_rollup_markdown(r) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_sc_rollup.py`:

```python
from datetime import datetime, timedelta, timezone

from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
from sdlc.benchmarks.sc_rollup import (
    MIN_RUNS, build_sc_rollup, render_sc_rollup_html,
    render_sc_rollup_json, render_sc_rollup_markdown)
from sdlc.models import (
    ClarificationOutcome, GateOutcomeSummary, HarnessKind, RunSummary)

T = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


def _summary(run_id, outcome="deployed:pr", gates=(), clars=(), offset=0):
    return RunSummary(
        run_id=run_id, mode="greenfield", outcome=outcome,
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset), duration_s=0.0,
        gates=list(gates), clarifications=list(clars))


def _gate(name, decided_by="policy", policy="soft", overrides=(), rnd=1):
    return GateOutcomeSummary(gate=name, round=rnd, policy=policy,
                              decided_by=decided_by, approved=True,
                              overrides=list(overrides))


def _clar(qid, answered_by):
    return ClarificationOutcome(question_id=qid, question="q?",
                                answered_by=answered_by)


def _code(run, task, outcome, fix, bench="b1"):
    return BenchmarkRecord(
        run_id=run, bench_run_id=bench, case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT, stage="code", task_id=task,
        attempt=fix, role="dev", harness=HarnessKind.OPENCODE, model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T,
                       ended_at=T + timedelta(seconds=1)),
        outcome=outcome, fix_attempts=fix)


def _rate(rollup, criterion):
    return next(r for r in rollup.rates if r.criterion == criterion)


def _n_summaries(n, **kw):
    return [_summary(f"run-{i}", offset=i, **kw) for i in range(n)]


# ---------------------------------------------------------------- SC-1

def test_sc1_counts_runs_that_reached_merge_unattended():
    runs = [_summary(f"run-{i}", outcome="deployed:pr", offset=i)
            for i in range(4)]
    runs.append(_summary("run-4", outcome="rejected:plan", offset=4))
    r = _rate(build_sc_rollup(runs, []), "SC-1")
    assert r.n == 5 and r.rate == 0.8


def test_sc1_rejected_at_merge_still_counts_as_reached():
    """The criterion is REACHING the merge gate, not passing it."""
    runs = _n_summaries(4) + [
        _summary("run-4", outcome="rejected:merge:advisory", offset=4)]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


def test_sc1_merged_not_deployed_counts_as_reached():
    runs = _n_summaries(4) + [
        _summary("run-4", outcome="merged-not-deployed:http://pr", offset=4)]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


def test_sc1_early_terminals_did_not_reach():
    runs = [_summary(f"run-{i}", offset=i,
                     outcome=o)
            for i, o in enumerate(["rejected:research", "rejected:architecture",
                                   "rejected:plan", "failed:dependency-cycle",
                                   "failed:quarantined-tasks"])]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 0.0


def test_sc1_human_gate_before_merge_disqualifies():
    runs = _n_summaries(4) + [_summary(
        "run-4", offset=4,
        gates=[_gate("architecture", decided_by="human"), _gate("merge")])]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 0.8


def test_sc1_human_at_the_merge_gate_itself_still_counts():
    """By then the run had already reached the gate unattended."""
    runs = _n_summaries(4) + [_summary(
        "run-4", offset=4,
        gates=[_gate("architecture"), _gate("merge", decided_by="human")])]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


# ---------------------------------------------------------------- SC-3

def _loop(run, task, final):
    """One fix loop: a failed first attempt, then a second ending `final`."""
    return [_code(run, task, BenchmarkOutcome.FAIL, 0),
            _code(run, task, final, 1)]


def test_sc3_counts_only_tasks_that_entered_a_fix_loop():
    recs = [_code("r1", "t00", BenchmarkOutcome.PASS, 0)]    # no loop
    for i in range(3):
        recs += _loop("r1", f"ok{i}", BenchmarkOutcome.PASS)
    for i in range(3):
        recs += _loop("r1", f"bad{i}", BenchmarkOutcome.FAIL)
    r = _rate(build_sc_rollup(_n_summaries(MIN_RUNS), recs), "SC-3")
    assert r.n == 6 and r.rate == 0.5


def test_sc3_floor_applies_to_loops_not_runs():
    """One floor rule for every rate, applied to that rate's own
    denominator. One loop is not a fix-loop success rate."""
    r = _rate(build_sc_rollup(_n_summaries(MIN_RUNS),
                              _loop("r1", "t01", BenchmarkOutcome.PASS)),
              "SC-3")
    assert r.n == 1 and r.rate is None


def test_sc3_final_attempt_decides():
    recs = []
    for i in range(MIN_RUNS):
        recs += [_code("r1", f"t{i}", BenchmarkOutcome.FAIL, 0),
                 _code("r1", f"t{i}", BenchmarkOutcome.FAIL, 1),
                 _code("r1", f"t{i}", BenchmarkOutcome.PASS, 2)]
    assert _rate(build_sc_rollup(_n_summaries(MIN_RUNS), recs),
                 "SC-3").rate == 1.0


# ---------------------------------------------------------------- SC-4

def test_sc4_is_the_human_answered_fraction_and_is_flagged_a_proxy():
    runs = _n_summaries(
        MIN_RUNS, clars=[_clar("q1", "human"), _clar("q2", "suggested"),
                         _clar("q3", "suggested"), _clar("q4", "suggested")])
    r = _rate(build_sc_rollup(runs, []), "SC-4")
    assert r.rate == 0.25
    assert r.proxy is True
    assert "not literal repeat detection" in r.note


def test_sc4_series_is_ordered_by_run_start():
    runs = [
        _summary("late", offset=5, clars=[_clar("q1", "suggested")]),
        _summary("early", offset=0, clars=[_clar("q1", "human")]),
    ]
    series = build_sc_rollup(runs, []).sc4_series
    assert [p.run_id for p in series] == ["early", "late"]
    assert [p.human_rate for p in series] == [1.0, 0.0]


def test_sc4_skips_runs_with_no_clarifications():
    runs = [_summary("r1", offset=0),
            _summary("r2", offset=1, clars=[_clar("q1", "human")])]
    assert [p.run_id for p in build_sc_rollup(runs, []).sc4_series] == ["r2"]


# ---------------------------------------------------------------- SC-6

def test_sc6_counts_human_decisions_on_soft_gates_only():
    """A hard gate decided by a human is not a soft-gate override; it is
    the policy working as configured."""
    soft = [_gate(f"g{i}", decided_by="human", policy="soft", rnd=i)
            for i in range(3)]
    soft += [_gate(f"g{i}", decided_by="policy", policy="soft", rnd=i)
             for i in range(3, 6)]
    hard = [_gate("deploy", decided_by="human", policy="hard")]
    runs = _n_summaries(MIN_RUNS - 1) + [
        _summary("run-x", offset=9, gates=soft + hard)]
    r = _rate(build_sc_rollup(runs, []), "SC-6")
    assert r.n == 6 and r.rate == 0.5


def test_sc6_waved_advisories_are_a_separate_number():
    gates = [_gate(f"g{i}", policy="soft", overrides=["coverage"], rnd=i)
             for i in range(3)]
    gates += [_gate(f"g{i}", policy="soft", rnd=i) for i in range(3, 6)]
    runs = _n_summaries(MIN_RUNS - 1) + [
        _summary("run-x", offset=9, gates=gates)]
    rollup = build_sc_rollup(runs, [])
    assert _rate(rollup, "SC-6-advisory").rate == 0.5
    # human decisions and waved advisories are different failures
    assert _rate(rollup, "SC-6").rate == 0.0


def test_sc6_floor_applies_to_soft_gates():
    runs = _n_summaries(MIN_RUNS - 1) + [_summary(
        "run-x", offset=9,
        gates=[_gate("architecture", decided_by="human", policy="soft")])]
    r = _rate(build_sc_rollup(runs, []), "SC-6")
    assert r.n == 1 and r.rate is None


# ------------------------------------------------------- denominator rule

def test_rate_is_na_below_the_floor():
    runs = _n_summaries(MIN_RUNS - 1)
    r = _rate(build_sc_rollup(runs, []), "SC-1")
    assert r.rate is None and r.n == MIN_RUNS - 1


def test_floor_is_five_runs():
    assert MIN_RUNS == 5


def test_no_evidence_yields_rates_with_zero_n():
    rollup = build_sc_rollup([], [])
    assert all(r.rate is None and r.n == 0 for r in rollup.rates)


# ------------------------------------------------------------- rendering

def test_markdown_shows_n_beside_every_rate_and_is_ascii():
    md = render_sc_rollup_markdown(build_sc_rollup(_n_summaries(MIN_RUNS), []))
    assert "n=" in md
    md.encode("ascii")


def test_markdown_prints_na_not_a_percentage_below_floor():
    md = render_sc_rollup_markdown(build_sc_rollup(_n_summaries(1), []))
    assert "n/a" in md
    assert "100" not in md


def test_html_and_json_render():
    import json
    rollup = build_sc_rollup(_n_summaries(MIN_RUNS), [])
    assert "<!doctype html>" in render_sc_rollup_html(rollup)
    assert json.loads(render_sc_rollup_json(rollup))["rates"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_sc_rollup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.sc_rollup'`

- [ ] **Step 3: Write `src/sdlc/benchmarks/sc_rollup.py`**

```python
"""Cross-run success-criteria rates (ROADMAP SC-1/3/4/6).

ROADMAP says of each of these: "the cross-run aggregation remains the
benchmark's job." It names the criteria but not the formulas, so the
definitions here are CHOICES, documented per rate.

Pure aggregation + rendering, no I/O -- mirrors heatmap.py.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from ..models import RunSummary
from .models import BenchmarkOutcome, BenchmarkRecord

# Below this many runs a percentage is noise dressed as a result. A single
# green run rendering "100%" WILL be quoted; n/a cannot be.
MIN_RUNS = 5

# The merge gate's registered name (workflows/feature.py:1754).
MERGE_GATE = "merge"

# Run outcomes that reached the merge gate. The criterion is REACHING it,
# not passing it, so a merge-time rejection counts (feature.py:1757, 1791,
# 1828, 1836).
REACHED_PREFIXES: tuple[str, ...] = (
    "deployed:", "merged-not-deployed:", "rejected:merge")


class SCRate(BaseModel):
    criterion: str
    label: str
    rate: float | None      # None when n < MIN_RUNS -- renders n/a
    n: int
    target: str
    proxy: bool = False
    note: str = ""


class SC4Point(BaseModel):
    index: int
    run_id: str
    human_rate: float


class SCRollup(BaseModel):
    rates: list[SCRate] = Field(default_factory=list)
    sc4_series: list[SC4Point] = Field(default_factory=list)


def _rate(n_hits: int, n: int) -> float | None:
    if n < MIN_RUNS or n == 0:
        return None
    return n_hits / n


def build_sc_rollup(summaries: list[RunSummary],
                    records: list[BenchmarkRecord]) -> SCRollup:
    ordered = sorted(summaries, key=lambda s: (s.started_at, s.run_id))
    return SCRollup(
        rates=[_sc1(ordered), _sc3(records), _sc4(ordered), *_sc6(ordered)],
        sc4_series=_sc4_series(ordered))


def _reached_merge(s: RunSummary) -> bool:
    return s.outcome.startswith(REACHED_PREFIXES)


def _unattended_to_merge(s: RunSummary) -> bool:
    """No human-decided gate BEFORE the merge gate. A human answering the
    merge gate itself does not disqualify the run -- by then it had already
    reached the gate."""
    for g in s.gates:
        if g.gate == MERGE_GATE:
            return True
        if g.decided_by == "human":
            return False
    return True


def _sc1(summaries: list[RunSummary]) -> SCRate:
    hits = sum(1 for s in summaries
               if _reached_merge(s) and _unattended_to_merge(s))
    return SCRate(
        criterion="SC-1", label="runs reaching the merge gate unattended",
        rate=_rate(hits, len(summaries)), n=len(summaries), target=">=0.80",
        note="reached = outcome in deployed/merged-not-deployed/rejected:merge; "
             "unattended = no human-decided gate before the merge gate")


def _sc3(records: list[BenchmarkRecord]) -> SCRate:
    """A fix loop existed for a (run, task) where any attempt has
    fix_attempts > 0; it succeeded if the LAST attempt passed."""
    attempts: dict[tuple[str, str], list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        if r.stage == "code" and r.task_id:
            attempts[(r.run_id, r.task_id)].append(r)

    loops = successes = 0
    for recs in attempts.values():
        recs = sorted(recs, key=lambda r: (r.attempt or 0, r.speed.started_at))
        if not any(r.fix_attempts > 0 for r in recs):
            continue
        loops += 1
        if recs[-1].outcome is BenchmarkOutcome.PASS:
            successes += 1
    # The denominator is LOOPS, not runs -- but the floor is one rule for
    # every rate: below MIN_RUNS observations, n/a rather than a percentage.
    return SCRate(
        criterion="SC-3", label="fix loops that resolved",
        rate=_rate(successes, loops), n=loops, target=">=0.70",
        note="a loop = a (run, task) with any attempt at fix_attempts>0; "
             "success = the final attempt passed; denominator is loops, "
             f"and the n/a floor of {MIN_RUNS} applies to loops")


def _sc4(summaries: list[RunSummary]) -> SCRate:
    total = sum(len(s.clarifications) for s in summaries)
    human = sum(1 for s in summaries for c in s.clarifications
                if c.answered_by == "human")
    n_runs = sum(1 for s in summaries if s.clarifications)
    return SCRate(
        criterion="SC-4", label="clarifications a human had to answer",
        rate=(human / total) if (total and n_runs >= MIN_RUNS) else None,
        n=n_runs, target="<0.10 by run 10", proxy=True,
        note="PROXY: measures questions memory could not answer, which is the "
             "intent of the criterion, but it is not literal repeat detection "
             "-- ClarificationOutcome.question_id is not established as stable "
             "across runs")


def _sc4_series(summaries: list[RunSummary]) -> list[SC4Point]:
    out: list[SC4Point] = []
    for s in summaries:
        if not s.clarifications:
            continue
        human = sum(1 for c in s.clarifications if c.answered_by == "human")
        out.append(SC4Point(index=len(out), run_id=s.run_id,
                            human_rate=human / len(s.clarifications)))
    return out


def _sc6(summaries: list[RunSummary]) -> list[SCRate]:
    soft = [g for s in summaries for g in s.gates if g.policy == "soft"]
    human = sum(1 for g in soft if g.decided_by == "human")
    waved = sum(1 for g in soft if g.overrides)
    n = len(soft)
    return [
        SCRate(criterion="SC-6", label="soft gates a human decided",
               rate=_rate(human, n), n=n, target="<0.05",
               note=f"denominator is soft gates, not runs; the n/a floor of "
                    f"{MIN_RUNS} applies to soft gates"),
        SCRate(criterion="SC-6-advisory",
               label="soft gates with waved advisory checks",
               rate=_rate(waved, n), n=n, target="<0.05",
               note="reported separately from human decisions: different "
                    "failures, and one average would hide both"),
    ]


# ------------------------------------------------------------- rendering

def render_sc_rollup_json(r: SCRollup) -> str:
    return r.model_dump_json(indent=2)


def _fmt(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.2f}"


def render_sc_rollup_markdown(r: SCRollup) -> str:
    """ASCII only (report.py:70-74)."""
    lines = ["", "## Success criteria", "",
             f"Rates below n={MIN_RUNS} render n/a rather than a percentage.",
             "",
             "| criterion | measure | rate | n | target | |",
             "|---|---|---|---|---|---|"]
    for x in r.rates:
        flag = "PROXY" if x.proxy else ""
        lines.append(f"| {x.criterion} | {x.label} | {_fmt(x.rate)} | "
                     f"n={x.n} | {x.target} | {flag} |")
    if r.sc4_series:
        lines += ["", "SC-4 series (human-answered fraction, by run order):",
                  ""]
        lines += [f"- {p.index}: {p.run_id} {p.human_rate:.2f}"
                  for p in r.sc4_series]
    lines += ["", "Definitions:", ""]
    lines += [f"- **{x.criterion}**: {x.note}" for x in r.rates if x.note]
    return "\n".join(lines) + "\n"


def render_sc_rollup_html(r: SCRollup) -> str:
    rows = "".join(
        f"<tr><th>{escape(x.criterion)}</th><td>{escape(x.label)}</td>"
        f"<td>{_fmt(x.rate)}</td><td>{x.n}</td>"
        f"<td>{escape(x.target)}</td>"
        f"<td>{'PROXY' if x.proxy else ''}</td></tr>"
        for x in r.rates)
    notes = "".join(
        f"<li><b>{escape(x.criterion)}</b>: {escape(x.note)}</li>"
        for x in r.rates if x.note)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Success criteria</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} li{{margin:.3rem 0}}
</style></head><body>
<h1>Success criteria</h1>
<p>Rates below n={MIN_RUNS} render n/a rather than a percentage: a single
run displaying 100% would be quoted as a result.</p>
<table><tr><th>criterion</th><th>measure</th><th>rate</th><th>n</th>
<th>target</th><th></th></tr>{rows}</table>
<h2>Definitions</h2><ul>{notes}</ul>
</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_sc_rollup.py -v`
Expected: PASS (every test in the file)

- [ ] **Step 5: Wire into `write_score`**

In `src/sdlc/benchmarks/score.py`, add to the imports inside `write_score`:

```python
    from .sc_rollup import (build_sc_rollup, render_sc_rollup_html,
                            render_sc_rollup_json, render_sc_rollup_markdown)
```

and, after the `_write_case_matrices` call and before the `render_markdown` call:

```python
    rollup = build_sc_rollup(ev.summaries, ev.records)
    for name, text in (("sc-rollup.html", render_sc_rollup_html(rollup)),
                       ("sc-rollup.json", render_sc_rollup_json(rollup))):
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
```

then append the rollup to the Markdown, changing the `md` assembly to:

```python
    md = render_markdown(summaries, calibration=calibration)
    md += render_sc_rollup_markdown(rollup)
    md += _render_notes(notes)
```

- [ ] **Step 6: Add a score-level wiring test**

Append to `tests/test_benchmark_score.py`:

```python
def test_sc_rollup_written_and_appended_to_report(tmp_path):
    ev = Evidence(records=[_rec()], selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    assert {"sc-rollup.html", "sc-rollup.json"} <= {p.name for p in written}
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Success criteria" in md
    assert "SC-1" in md
```

- [ ] **Step 7: Run the full fast suite and add the purity guard**

Add `import sdlc.benchmarks.sc_rollup  # noqa: F401` to
`tests/test_e36_imports.py::test_scoring_path_modules_import`.

Run: `pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/benchmarks/sc_rollup.py src/sdlc/benchmarks/score.py \
        tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py \
        tests/test_e36_imports.py
git commit -m "feat(benchmarks): cross-run SC-1/3/4/6 rollup

ROADMAP names these criteria but not their formulas; each definition is
documented on the rate it produces. SC-4 is explicitly flagged a proxy --
it measures questions memory could not answer, not literal repeats.
Rates below n=5 render n/a so a single green run cannot be quoted as 100%.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Phase 4 — The improvement cycle's memory

### Task 8: The experiment log

**Files:**
- Create: `src/sdlc/benchmarks/experiments.py`
- Create: `benchmarks/experiments/.gitkeep`
- Modify: `src/sdlc/benchmarks/cli.py` (add `dispatch_experiment_new`, `dispatch_experiment_compare`)
- Modify: `src/sdlc/cli.py` (add the `experiment` subparser and dispatch)
- Test: `tests/test_benchmark_experiments.py`

**Interfaces:**
- Consumes: `load_evidence` (Task 4); `aggregate` from `report.py`; `WASTE_METRICS` (Task 6); `CompositeWeights`
- Produces:
  - `NOISE_FLOOR: int = 3`, `EXPERIMENT_AXES: tuple[str, ...]`
  - `DeltaRow(case, stage, arm, quality, cost_usd, wall_s, composite, waste, n, note)`
  - `Experiment(id, axis, change, commit, hypothesis, baseline, candidate, verdict, notes, deltas)`
  - `compute_deltas(baseline, candidate, weights) -> list[DeltaRow]`
  - `new_experiment(*, name, axis, change, baseline, commit="", hypothesis="") -> Experiment`
  - `save_experiment(exp, path) -> Path`, `load_experiment(path) -> Experiment`
  - `render_deltas_markdown(rows) -> str`
  - `experiments_dir() -> Path`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_experiments.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from sdlc.benchmarks.evidence import Evidence
from sdlc.benchmarks.experiments import (
    NOISE_FLOOR, Experiment, compute_deltas, load_experiment,
    new_experiment, render_deltas_markdown, save_experiment)
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, CompositeWeights,
    CostBag, QualityScore, SpeedBag, WasteBag)
from sdlc.models import HarnessKind

T = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


def _rec(*, q=1.0, usd=1.0, secs=10.0, waste=None, bench="b1", run="r1"):
    return BenchmarkRecord(
        run_id=run, bench_run_id=bench, case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", task_id="t01", role="dev",
        harness=HarnessKind.OPENCODE, model="m",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=secs, started_at=T,
                       ended_at=T + timedelta(seconds=secs)),
        outcome=BenchmarkOutcome.PASS, waste=waste)


def _ev(records, selector="b1"):
    return Evidence(records=records, selector=selector)


def test_new_experiment_scaffolds_with_empty_verdict():
    """The tool computes deltas; the human writes the verdict (ADR-11)."""
    exp = new_experiment(name="planner-decompose-prompt", axis="prompt",
                         change="require inter-task contracts",
                         baseline="bench-1")
    assert exp.verdict == ""
    assert exp.baseline == "bench-1"
    assert exp.candidate == ""
    assert exp.deltas == []
    assert exp.id.endswith("planner-decompose-prompt")


def test_new_experiment_rejects_unknown_axis():
    with pytest.raises(ValueError, match="axis"):
        new_experiment(name="x", axis="vibes", change="c", baseline="b")


def test_compute_deltas_reports_quality_cost_and_wall():
    base = _ev([_rec(q=0.5, usd=1.0, secs=10.0)])
    cand = _ev([_rec(q=0.9, usd=1.5, secs=8.0)], selector="b2")
    rows = compute_deltas(base, cand, CompositeWeights())
    assert len(rows) == 1
    row = rows[0]
    assert row.quality == pytest.approx(0.4)
    assert row.cost_usd == pytest.approx(0.5)
    assert row.wall_s == pytest.approx(-2.0)


def test_compute_deltas_includes_every_waste_metric():
    base = _ev([_rec(waste=WasteBag(tool_calls=10, file_rereads=2))])
    cand = _ev([_rec(waste=WasteBag(tool_calls=48, file_rereads=6),
                     bench="b2")], selector="b2")
    row = compute_deltas(base, cand, CompositeWeights())[0]
    assert row.waste["tool_calls"] == pytest.approx(38.0)
    assert row.waste["file_rereads"] == pytest.approx(4.0)


def test_low_n_cells_are_marked_within_noise():
    base = _ev([_rec(q=0.5)])
    cand = _ev([_rec(q=0.9, bench="b2")], selector="b2")
    assert compute_deltas(base, cand, CompositeWeights())[0].note == "within-noise"


def test_sufficient_n_is_not_marked_noise():
    base = _ev([_rec(q=0.5, run=f"r{i}") for i in range(NOISE_FLOOR)])
    cand = _ev([_rec(q=0.9, run=f"r{i}", bench="b2")
                for i in range(NOISE_FLOOR)], selector="b2")
    assert compute_deltas(base, cand, CompositeWeights())[0].note == ""


def test_noise_floor_is_three():
    assert NOISE_FLOOR == 3


def test_cell_only_in_candidate_is_reported_with_none_baseline():
    base = _ev([])
    cand = _ev([_rec(q=0.9, bench="b2")], selector="b2")
    rows = compute_deltas(base, cand, CompositeWeights())
    assert len(rows) == 1 and rows[0].quality is None


def test_save_and_load_round_trip(tmp_path):
    exp = new_experiment(name="x", axis="model", change="swap dev model",
                         baseline="b1")
    exp.deltas = compute_deltas(_ev([_rec(q=0.5)]),
                                _ev([_rec(q=0.9, bench="b2")], "b2"),
                                CompositeWeights())
    p = save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    again = load_experiment(p)
    assert again.id == exp.id
    assert again.verdict == ""
    assert again.deltas[0].quality == pytest.approx(0.4)


def test_saved_yaml_carries_the_verdict_key_for_a_human_to_fill(tmp_path):
    exp = new_experiment(name="x", axis="harness", change="c", baseline="b1")
    p = save_experiment(exp, tmp_path / "x.yaml")
    text = p.read_text(encoding="utf-8")
    assert "verdict:" in text


def test_load_preserves_a_human_written_verdict(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(
        "id: 2026-08-04-x\naxis: prompt\nchange: c\nbaseline: b1\n"
        "candidate: b2\nverdict: rollback\nnotes: not worth the tokens\n",
        encoding="utf-8")
    assert load_experiment(p).verdict == "rollback"


def test_render_deltas_markdown_shows_n_and_is_ascii():
    rows = compute_deltas(_ev([_rec(q=0.5)]),
                          _ev([_rec(q=0.9, bench="b2")], "b2"),
                          CompositeWeights())
    md = render_deltas_markdown(rows)
    assert "n" in md and "within-noise" in md
    md.encode("ascii")


def test_render_deltas_markdown_handles_empty():
    assert "no overlapping cells" in render_deltas_markdown([]).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_benchmark_experiments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.experiments'`

- [ ] **Step 3: Write `src/sdlc/benchmarks/experiments.py`**

```python
"""The improvement cycle's memory: what was tried, what it did, what was
decided.

Stored in benchmarks/experiments/ and COMMITTED TO GIT -- not under runs/,
which is disposable output. The whole value is that negative results
survive; a rolled-back experiment that is not in version control gets
re-tried by whoever forgot.

The tool computes the delta. The human writes the verdict. BENCHMARK.md
§0 commits this project to the ADR-11 stance -- the instrument is fixed and
versioned, never self-modifying -- and an auto-verdict would quietly
promote it to decision-maker.

Pure: no I/O beyond explicit load/save on a caller-supplied path.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .evidence import Evidence
from .models import CompositeWeights
from .waste_matrix import WASTE_METRICS

# Below this many observations of a cell, a delta IS noise. No p-values on
# n=2 -- statistical theatre over a three-case corpus is worse than no claim.
NOISE_FLOOR = 3

EXPERIMENT_AXES: tuple[str, ...] = (
    "prompt", "model", "harness", "schema", "tool_org", "memory")

_REPO_ROOT = Path(__file__).resolve().parents[3]


class DeltaRow(BaseModel):
    """candidate minus baseline for one (case, stage, arm) cell. None where
    the cell exists on only one side."""
    case: str
    stage: str
    arm: str
    quality: float | None = None
    cost_usd: float | None = None
    wall_s: float | None = None
    composite: float | None = None
    waste: dict[str, float] = Field(default_factory=dict)
    n: int = 0
    note: str = ""          # "within-noise" when n < NOISE_FLOOR


class Experiment(BaseModel):
    id: str
    axis: str
    change: str
    commit: str = ""
    hypothesis: str = ""
    baseline: str
    candidate: str = ""
    verdict: Literal["keep", "rollback", ""] = ""
    notes: str = ""
    deltas: list[DeltaRow] = Field(default_factory=list)


def experiments_dir() -> Path:
    return Path(os.environ.get(
        "SDLC_EXPERIMENTS_ROOT", str(_REPO_ROOT / "benchmarks" / "experiments")))


def new_experiment(*, name: str, axis: str, change: str, baseline: str,
                   commit: str = "", hypothesis: str = "",
                   today: _dt.date | None = None) -> Experiment:
    if axis not in EXPERIMENT_AXES:
        raise ValueError(
            f"unknown axis {axis!r}; must be one of {list(EXPERIMENT_AXES)}")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    day = (today or _dt.date.today()).isoformat()
    return Experiment(id=f"{day}-{slug}", axis=axis, change=change,
                      commit=commit, hypothesis=hypothesis, baseline=baseline)


def _cells(ev: Evidence, weights: CompositeWeights):
    """{(case, stage, arm): (summary, n, {metric: mean waste})}"""
    from collections import defaultdict

    from .report import aggregate

    waste_sum: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {m: 0.0 for m in WASTE_METRICS})
    waste_n: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in ev.records:
        if r.waste is None:
            continue
        key = (r.case_id, r.stage,
               f"{r.harness.value if r.harness else ''}#{r.model}")
        waste_n[key] += 1
        for m in WASTE_METRICS:
            waste_sum[key][m] += float(getattr(r.waste, m))

    out = {}
    for s in aggregate("", weights, _records=ev.records):
        key = (s.case_id, s.stage,
               f"{s.harness.value if s.harness else ''}#{s.model}")
        n = waste_n.get(key, 0)
        waste = ({m: waste_sum[key][m] / n for m in WASTE_METRICS}
                 if n else {})
        out[key] = (s, n, waste)
    return out


def compute_deltas(baseline: Evidence, candidate: Evidence,
                   weights: CompositeWeights) -> list[DeltaRow]:
    """candidate minus baseline, per cell. A cell present on only one side
    is still reported, with None deltas -- an appearing or vanishing cell is
    itself a result."""
    b = _cells(baseline, weights)
    c = _cells(candidate, weights)

    rows: list[DeltaRow] = []
    for key in sorted(set(b) | set(c)):
        case, stage, arm = key
        bs, _bn, bw = b.get(key, (None, 0, {}))
        cs, cn, cw = c.get(key, (None, 0, {}))
        n = min(x.n for x in (bs, cs) if x is not None)

        def d(attr: str) -> float | None:
            if bs is None or cs is None:
                return None
            bv, cv = getattr(bs, attr), getattr(cs, attr)
            return None if bv is None or cv is None else cv - bv

        waste = {m: cw[m] - bw[m] for m in WASTE_METRICS
                 if m in bw and m in cw}
        rows.append(DeltaRow(
            case=case, stage=stage, arm=arm,
            quality=d("mean_quality"), cost_usd=d("mean_cost_usd"),
            wall_s=d("mean_wall_clock_s"), composite=d("composite"),
            waste=waste, n=n,
            note="within-noise" if n < NOISE_FLOOR else ""))
    return rows


def render_deltas_markdown(rows: list[DeltaRow]) -> str:
    """ASCII only (report.py:70-74)."""
    if not rows:
        return "No overlapping cells between baseline and candidate.\n"

    def f(x: float | None) -> str:
        return "n/a" if x is None else f"{x:+.3f}"

    lines = ["| case | stage | arm | quality | cost | wall | composite | "
             "tool_calls | n | |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r.case} | {r.stage} | {r.arm} | {f(r.quality)} | "
            f"{f(r.cost_usd)} | {f(r.wall_s)} | {f(r.composite)} | "
            f"{f(r.waste.get('tool_calls'))} | {r.n} | {r.note} |")
    return "\n".join(lines) + "\n"


def save_experiment(exp: Experiment, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = exp.model_dump()
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False),
        encoding="utf-8")
    return path


def load_experiment(path: Path) -> Experiment:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Experiment(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_benchmark_experiments.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Add the CLI handlers**

In `src/sdlc/benchmarks/cli.py`:

```python
def dispatch_experiment_new(*, name: str, axis: str, change: str,
                            baseline: str, commit: str = "",
                            hypothesis: str = "",
                            exp_dir: str | None = None) -> str:
    from .experiments import experiments_dir, new_experiment, save_experiment
    exp = new_experiment(name=name, axis=axis, change=change,
                         baseline=baseline, commit=commit,
                         hypothesis=hypothesis)
    base = Path(exp_dir) if exp_dir else experiments_dir()
    p = save_experiment(exp, base / f"{exp.id}.yaml")
    return (f"{p}\n\nRun the candidate matrix, then:\n"
            f"  sdlc benchmark experiment compare --experiment {exp.id} "
            f"--candidate <bench_id>\n"
            f"Then write `verdict: keep` or `verdict: rollback` yourself "
            f"and commit the file.")


def dispatch_experiment_compare(*, experiment: str, candidate: str,
                                exp_dir: str | None = None,
                                root: str | None = None) -> str:
    """Hard-errors on a missing bench_id. Reporting degrades; comparison
    does not -- a silent half-comparison produces a verdict on partial data."""
    from .evidence import load_evidence
    from .experiments import (compute_deltas, experiments_dir,
                              load_experiment, render_deltas_markdown,
                              save_experiment)
    from .score import load_config_weights

    base = Path(exp_dir) if exp_dir else experiments_dir()
    path = base / f"{experiment}.yaml"
    if not path.is_file():
        raise SystemExit(f"no experiment {experiment!r} at {path}")

    exp = load_experiment(path)
    baseline_ev = load_evidence(bench=exp.baseline, root=root)
    candidate_ev = load_evidence(bench=candidate, root=root)
    for label, ev in (("baseline", baseline_ev), ("candidate", candidate_ev)):
        if not ev.records:
            raise SystemExit(
                f"{label} bench {ev.selector!r} has no records; refusing to "
                f"compare against nothing")

    exp.candidate = candidate
    exp.deltas = compute_deltas(baseline_ev, candidate_ev,
                                load_config_weights())
    save_experiment(exp, path)
    return (render_deltas_markdown(exp.deltas)
            + f"\nWritten to {path}. Verdict is yours to write.\n")
```

- [ ] **Step 6: Wire the CLI parser and dispatch**

In `src/sdlc/cli.py`, after the `score` parser block:

```python
    bx = bsub.add_parser("experiment")
    bxsub = bx.add_subparsers(dest="exp_cmd", required=True)
    bxn = bxsub.add_parser("new")
    bxn.add_argument("--name", required=True)
    bxn.add_argument("--axis", required=True,
                     choices=["prompt", "model", "harness", "schema",
                              "tool_org", "memory"])
    bxn.add_argument("--change", required=True,
                     help="one line: what is under test")
    bxn.add_argument("--baseline", required=True, help="a bench_run_id")
    bxn.add_argument("--commit", default="")
    bxn.add_argument("--hypothesis", default="")
    bxc = bxsub.add_parser("compare")
    bxc.add_argument("--experiment", required=True)
    bxc.add_argument("--candidate", required=True, help="a bench_run_id")
```

and in the `benchmark` dispatch block, after the `score` branch:

```python
        if args.bench_cmd == "experiment":
            from .benchmarks.cli import (dispatch_experiment_compare,
                                         dispatch_experiment_new)
            if args.exp_cmd == "new":
                print(dispatch_experiment_new(
                    name=args.name, axis=args.axis, change=args.change,
                    baseline=args.baseline, commit=args.commit,
                    hypothesis=args.hypothesis))
            else:
                print(dispatch_experiment_compare(
                    experiment=args.experiment, candidate=args.candidate))
            return
```

- [ ] **Step 7: Create the committed log directory**

```bash
mkdir -p benchmarks/experiments
printf '' > benchmarks/experiments/.gitkeep
```

- [ ] **Step 8: Add the CLI-level tests**

Append to `tests/test_benchmark_experiments.py`:

```python
def test_compare_hard_errors_on_a_missing_experiment(tmp_path):
    from sdlc.benchmarks.cli import dispatch_experiment_compare
    with pytest.raises(SystemExit, match="no experiment"):
        dispatch_experiment_compare(experiment="nope", candidate="b2",
                                    exp_dir=str(tmp_path))


def test_compare_hard_errors_on_an_empty_bench(tmp_path):
    """Reporting degrades; comparison does not."""
    from sdlc.benchmarks.cli import dispatch_experiment_compare
    from sdlc.benchmarks.experiments import new_experiment, save_experiment
    exp = new_experiment(name="x", axis="prompt", change="c", baseline="b1")
    save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    with pytest.raises(SystemExit, match="refusing to compare"):
        dispatch_experiment_compare(
            experiment=exp.id, candidate="b2", exp_dir=str(tmp_path),
            root=str(tmp_path / "empty-records"))
```

- [ ] **Step 9: Run the full fast suite and add the purity guard**

Add `import sdlc.benchmarks.experiments  # noqa: F401` to
`tests/test_e36_imports.py::test_scoring_path_modules_import`.

Run: `pytest`
Expected: PASS

- [ ] **Step 10: Verify the commands by hand**

```bash
python -m sdlc.cli benchmark experiment new --name smoke-test --axis prompt \
    --change "verify the scaffold writes" --baseline b-does-not-exist
cat benchmarks/experiments/*-smoke-test.yaml
rm benchmarks/experiments/*-smoke-test.yaml
```

Expected: the YAML exists, contains `verdict: ''`, and the printed hint names the `compare` command.

- [ ] **Step 11: Commit**

```bash
git add src/sdlc/benchmarks/experiments.py src/sdlc/benchmarks/cli.py \
        src/sdlc/cli.py benchmarks/experiments/.gitkeep \
        tests/test_benchmark_experiments.py tests/test_e36_imports.py
git commit -m "feat(benchmarks): git-committed experiment log

Records what was tried, the per-cell delta table, and the decision -- so
negative results survive and nobody re-tries a rolled-back change. The
tool computes deltas and never writes the verdict (ADR-11: the instrument
is fixed, not self-modifying). Cells below n=3 are marked within-noise
rather than dressed up with statistics the corpus cannot support.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Documentation reconciliation

**Files:**
- Modify: `ROADMAP.md` (E-36 entry), `BENCHMARK.md` (§4.3, §4.4, §6)
- Modify: `README.md` (command surface)

- [ ] **Step 1: Update the E-36 roadmap entry**

In `ROADMAP.md`, the E-36 entry ends with *"Session-derived waste (E-38) as a heatmap input and calibration-as-CI-gate (OQ-B4) deliberately deferred."* Replace that sentence with:

```
  Session-derived waste (E-38) as a heatmap input **landed 2026-08-03** via
  `WasteBag` on `BenchmarkRecord` + `benchmarks/waste_matrix.py` (task x arm,
  six metrics); calibration-as-CI-gate (OQ-B4) still deferred. Spec
  `docs/superpowers/specs/2026-08-03-completing-the-measurement-instrument-design.md`,
  plan `docs/superpowers/plans/2026-08-03-completing-the-measurement-instrument.md`.
```

- [ ] **Step 2: Mark the SC lines measurable**

In `ROADMAP.md`, the SC-1/SC-3/SC-4/SC-6 lines each say the cross-run aggregation "remains the benchmark's job". Append to each:

```
  **Aggregation landed** (`benchmarks/sc_rollup.py`, `sdlc benchmark score`);
  the number is n/a until 5+ runs exist.
```

Leave the checkboxes unticked — the mechanism exists, the corpus does not.

- [ ] **Step 3: Update BENCHMARK.md**

In §4.3, after the session-derived-waste bullet, add:

```
  *Landed 2026-08-03:* `WasteBag` on `BenchmarkRecord` +
  `benchmarks/waste_matrix.py`. Six gridded metrics; volume metrics and
  `compacted` ride on the record without a grid. Coding tasks only --
  proposer stages have no transcript by construction.
```

In §4.4, note that the case x stage heatmap is now one of five grids written by `sdlc benchmark score`.

In §6, mark item 5 (error heatmap + calibration) complete and add the three loops table from the spec's §5.

- [ ] **Step 4: Update README.md**

Replace any `sdlc benchmark report` / `sdlc benchmark history` example with:

```bash
# score everything on disk (seconds, no Temporal needed)
sdlc benchmark score --all

# one matrix run, re-weighted
sdlc benchmark score --bench <bench_run_id> --weights 0.7,0.2,0.1

# one case across its whole history
sdlc benchmark score --case cat-cafe-monitoring
```

- [ ] **Step 5: Verify no stale command references remain**

Run: `grep -rn "benchmark report\|benchmark history" --include=*.md --include=*.py . | grep -v docs/superpowers/plans`
Expected: no hits outside this plan and the archived specs.

- [ ] **Step 6: Commit**

```bash
git add ROADMAP.md BENCHMARK.md README.md
git commit -m "docs: reconcile roadmap and benchmark design with the landed instrument

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Manual verification (not CI)

Unit tests prove the aggregation is correct given records. They cannot prove
the waste numbers describe a real harness run — that needs a live run and is
verified once, by hand:

- [ ] Run one cell: `python -m sdlc.cli benchmark run --case benchmarks/cases/cat-cafe-monitoring/case.yaml --gate-policy off`
- [ ] `python -m sdlc.cli benchmark score --case cat-cafe-monitoring`
- [ ] Open `waste-matrix.html`. Confirm: rows are the real task ids; `tool_calls` is a plausible magnitude (tens, not 0 and not millions); a task the run never attempted is **blank, not 0**.
- [ ] Cross-check one cell against the stored digest for the same task in the artifact store. They must agree exactly — the record is a copy, not a recomputation.
- [ ] Confirm `report.md` shows SC rates as `n/a` with the real `n`, not percentages.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2.1 evidence stores | Tasks 1, 3, 4 |
| §2.3 module boundaries | Tasks 4-8 + purity guards in `test_e36_imports.py` |
| §3.1 `WasteBag` | Task 1 (with the documented `None` deviation) |
| §3.2 population at `feature.py:1035` | Task 2 |
| §3.3 blank-not-zero | Task 1 (`None`), Task 6 (`td.empty` rendering + test) |
| §3.4 waste matrix, six metrics, no `tasks.yaml` dep | Task 6 |
| §4 SC-1/3/4/6 + denominator rule | Task 7. **Refinement:** the spec phrases the floor as "5 runs"; the plan applies it uniformly to each rate's own denominator — runs for SC-1, loops for SC-3, soft gates for SC-6 — because those are the units each rate is actually over. One rule, applied where it means something. |
| §5 `score` command, lazy import, degradation, `--weights` | Task 5 |
| §6 experiment log, human verdict, noise floor, no auto-rollback | Task 8 |
| §7 error handling table | Task 4 (summaries), 5 (tasks.yaml, empty), 6 (unmeasured), 7 (floor), 8 (hard error) |
| §8 testing, incl. the manual step | All tasks + the Manual Verification section |
| §9 sequencing | Phase order 1→4 |

**Type consistency:** `WasteBag.from_digest -> WasteBag | None` is used
consistently in Tasks 1, 2, 6, 8. `Evidence(records, summaries, selector,
notes)` is constructed in Task 4 and consumed unchanged in Tasks 5, 7, 8.
`WASTE_METRICS` is defined once in Task 6 and imported by Task 8.
`CompositeWeights` comes from `benchmarks.models` throughout.

**Known gap, deliberate:** `finalize_benchmark_report` (`report.py:129`) still
writes only `report.md` + heatmap at the end of a matrix run. It is left alone
— the workflow's activity stays minimal and `score` is the full view. If a
matrix run should emit the whole set inline, that is a one-line change to call
`write_score`, and it is not in this plan's scope.
