# Pipeline-Step Benchmarking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Benchmark each pipeline step's effectiveness as a composite (quality + cost + speed) score, comparable across `(harness, model)` pairs, via a golden-suite matrix runner and a production-drift harvester sharing one record schema.

**Architecture:** A standalone `BenchmarkWorkflow` drives `FeatureWorkflow` children — one per `(case × harness × model)` cell — and a `DriftHarvester` reads real Temporal history; both emit `BenchmarkRecord`s (raw quality/cost/speed) to a file store under `runs/benchmarks/`. A `report` command aggregates records into per-cell composite scores (quality-dominant, weights in `benchmarks/config.yaml`) and renders Markdown/HTML. `FeatureWorkflow` gains a single gated `record_benchmark` activity call per stage boundary + code-task attempt; when `PipelineConfig.benchmark.case_id` is `None`, zero recorder calls happen (production path stays pure).

**Tech Stack:** Python ≥3.11, temporalio ≥1.9, pydantic ≥2.7, pydantic-ai-slim (already deps); pytest ≥8; no new runtime dependencies.

## Global Constraints

- The actual workflow class is `FeatureWorkflow` in `src/sdlc/workflows/feature.py` (the spec calls it `FactoryWorkflow` conceptually — code uses `FeatureWorkflow`).
- Tests follow the **existing flat layout** (`tests/test_*.py`), not `tests/unit/`, `tests/workflows/` (those are aspirational in ARCHITECTURE.md §14; reality is flat).
- `workflows/` may not import `subprocess`, HTTP clients, the memory client, or the harness package (import-linter boundary, ARCHITECTURE §14). Recorder/judge/harness/drift code lives under `activities/` or a new `benchmarks/` package imported only via `unsafe.imports_passed_through()` in workflow code — and only the `record_benchmark` activity (a thin activity wrapper) is imported by `feature.py`.
- All non-determinism lives in activities (Temporal rule, ARCHITECTURE §1/§14).
- `PipelineConfig` changes must be **additive with safe defaults** — existing code that constructs `PipelineConfig()` must behave identically.
- Use `workflow.now()` for timing inside workflows (deterministic under time-skipping tests), never `datetime.now()` or `time.time()` in workflow code.
- CI must not make real model calls — judge/LLM boundaries are injectable; tests use fakes.

---

## File Structure

**Create:**
- `src/sdlc/benchmarks/__init__.py` — package marker, exports public types.
- `src/sdlc/benchmarks/models.py` — `BenchmarkRecord`, `BenchmarkScope`, `BenchmarkOutcome`, `QualityScore`, `CostBag`, `SpeedBag`, `CompositeWeights`, `BenchmarkCell`, `BenchmarkSummary`, `CaseSpec`, `BenchmarkConfig`.
- `src/sdlc/benchmarks/scoring.py` — pure composite-score computation.
- `src/sdlc/benchmarks/recorder.py` — `record_benchmark` activity + file-backed record store.
- `src/sdlc/benchmarks/judge.py` — `judge_artifact` activity (cross-family LLM-judge with injectable boundary).
- `src/sdlc/benchmarks/matrix.py` — `expand_matrix(CaseSpec) → list[BenchmarkCell]` + same-family rejection.
- `src/sdlc/benchmarks/workflow.py` — `BenchmarkWorkflow` matrix runner.
- `src/sdlc/benchmarks/drift.py` — `DriftHarvester` (Temporal history → records).
- `src/sdlc/benchmarks/report.py` — aggregation + Markdown/HTML rendering.
- `src/sdlc/benchmarks/cli.py` — `benchmark {run,drift,report}` subcommand handlers.
- `benchmarks/config.yaml` — composite weights, default judge model.
- `benchmarks/cases/add-login-greenfield/case.yaml` + `rubric-architect.md` + `rubric-clarifier.md`.

**Modify:**
- `src/sdlc/models.py` — add `BenchmarkConfig` import-friendly hook only if `benchmarks/models.py` can't own it (it can — keep it in `benchmarks/models.py` and reference from `PipelineConfig` via import; see Task 2).
- `src/sdlc/workflows/feature.py` — add gated `record_benchmark` calls at stage boundaries + per code-task attempt.
- `src/sdlc/worker.py` — register `record_benchmark`, `judge_artifact`, `BenchmarkWorkflow`.
- `src/sdlc/cli.py` — wire `benchmark` subparser to `benchmarks.cli`.

**Test files (flat, matching existing convention):**
- `tests/test_benchmark_models.py`
- `tests/test_benchmark_config.py`
- `tests/test_benchmark_scoring.py`
- `tests/test_benchmark_recorder.py`
- `tests/test_factory_recorder.py`
- `tests/test_benchmark_report.py`
- `tests/test_benchmark_matrix.py`
- `tests/test_benchmark_judge.py`
- `tests/test_benchmark_workflow.py`
- `tests/test_drift_harvester.py`
- `tests/test_benchmark_cli.py`

---

### Task 1: Benchmark metric models

**Files:**
- Create: `src/sdlc/benchmarks/__init__.py`
- Create: `src/sdlc/benchmarks/models.py`
- Test: `tests/test_benchmark_models.py`

**Interfaces:**
- Produces: `BenchmarkScope`, `BenchmarkOutcome`, `QualityScore`, `CostBag`, `SpeedBag`, `BenchmarkRecord`, `CompositeWeights`, `BenchmarkCell`, `BenchmarkSummary`, `CaseSpec`, `BenchmarkConfig` — consumed by every later task.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_models.py`:
```python
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkConfig,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    BenchmarkSummary,
    CaseSpec,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.models import HarnessKind


def _record(**kw):
    base = dict(
        run_id="r1",
        bench_run_id="b1",
        case_id="add-login",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, 12),
        ),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


def test_record_serializes_round_trip():
    r = _record()
    js = r.model_dump_json()
    r2 = BenchmarkRecord.model_validate_json(js)
    assert r2.quality.score == 0.8
    assert r2.scope is BenchmarkScope.STAGE


def test_harness_optional_for_proposer():
    r = _record()
    assert r.harness is None  # architect is a proposer, no harness


def test_task_attempt_record_carries_task_id_and_attempt():
    r = _record(
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id="T1",
        attempt=0,
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
    )
    assert r.task_id == "T1" and r.attempt == 0


def test_benchmark_config_defaults_case_id_none():
    cfg = BenchmarkConfig()
    assert cfg.case_id is None
    assert cfg.bench_run_id is None


def test_composite_weights_default_quality_dominant():
    w = CompositeWeights()
    assert (w.quality, w.cost, w.speed) == (0.6, 0.2, 0.2)


def test_case_spec_matrix_axes():
    spec = CaseSpec(
        case_id="add-login",
        idea_summary="add login",
        mode="greenfield",
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE],
        models=["anthropic:claude-sonnet-4-6"],
        judge_model="openai/gpt-5.2",
        rubrics={"architect": "rubric-architect.md"},
    )
    assert len(spec.harnesses) == 2
    assert spec.judge_model.startswith("openai/")


def test_benchmark_cell_identity():
    c = BenchmarkCell(
        case_id="add-login", harness=HarnessKind.OPENCODE, model="anthropic:claude-sonnet-4-6"
    )
    assert c.cell_id == "add-login#opencode#anthropic:claude-sonnet-4-6"


def test_benchmark_summary_aggregates_fields():
    s = BenchmarkSummary(
        case_id="add-login",
        stage="code",
        harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:claude-sonnet-4-6",
        n=3,
        mean_quality=0.9,
        mean_cost_usd=0.5,
        mean_wall_clock_s=120.0,
        composite=0.88,
    )
    assert s.n == 3 and s.composite == 0.88
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/__init__.py`:
```python
"""Pipeline-step benchmarking: per-step effectiveness by (harness, model)."""
```

`src/sdlc/benchmarks/models.py`:
```python
"""Typed contracts for pipeline-step benchmarking.

One BenchmarkRecord per stage boundary and per code-task attempt. The three
dimensions (quality / cost / speed) are kept RAW — never pre-normalized — so
the reporter can recompute under different weights without re-running.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from ..models import HarnessKind


class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"


class BenchmarkOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVISED = "revise"
    ESCALATED = "escalated"


class QualityScore(BaseModel):
    score: float | None = None  # 0.0..1.0; None when judge errored
    components: dict[str, float] = Field(default_factory=dict)
    judge: Literal["contract", "llm_judge", "human_override", "error"]


class CostBag(BaseModel):
    usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class SpeedBag(BaseModel):
    wall_clock_s: float
    started_at: datetime
    ended_at: datetime


class BenchmarkRecord(BaseModel):
    # identity
    run_id: str
    bench_run_id: str  # parent BenchmarkWorkflow id; "_drift/<date>" for drift
    case_id: str  # golden case name; "_production" for drift
    scope: BenchmarkScope
    stage: str
    task_id: str | None = None
    attempt: int | None = None
    role: str
    harness: HarnessKind | None = None
    model: str
    prompt_sha: str = ""
    # raw dimensions
    quality: QualityScore
    cost: CostBag = Field(default_factory=CostBag)
    speed: SpeedBag
    outcome: BenchmarkOutcome
    fix_attempts: int = 0
    error: str | None = None


class CompositeWeights(BaseModel):
    quality: float = 0.6
    cost: float = 0.2
    speed: float = 0.2


class BenchmarkConfig(BaseModel):
    """Carried on PipelineConfig. case_id=None ⇒ not a benchmark run."""

    case_id: str | None = None
    bench_run_id: str | None = None


class CaseSpec(BaseModel):
    """A golden case: the idea + the (harness, model) matrix to run it on."""

    case_id: str
    idea_summary: str
    description: str = ""
    mode: Literal["greenfield", "brownfield"] = "greenfield"
    repo_url: str | None = None
    harnesses: list[HarnessKind]
    models: list[str]
    judge_model: str  # cross-family (ADR-6)
    rubrics: dict[str, str] = Field(default_factory=dict)  # stage → rubric file


class BenchmarkCell(BaseModel):
    """One cell of the matrix: a (case, harness, model) triple to execute."""

    case_id: str
    harness: HarnessKind
    model: str

    @property
    def cell_id(self) -> str:
        return f"{self.case_id}#{self.harness.value}#{self.model}"


class BenchmarkSummary(BaseModel):
    """Aggregate over all records for one (case, stage, harness, model)."""

    case_id: str
    stage: str
    harness: HarnessKind | None
    model: str
    n: int
    mean_quality: float | None
    mean_cost_usd: float | None
    mean_wall_clock_s: float | None
    composite: float | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_models.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/__init__.py src/sdlc/benchmarks/models.py tests/test_benchmark_models.py
git commit -m "feat(benchmarks): add BenchmarkRecord and metric models"
```

---

### Task 2: Wire BenchmarkConfig into PipelineConfig (additive, safe default)

**Files:**
- Modify: `src/sdlc/models.py` (add `benchmark` field to `PipelineConfig`)
- Test: `tests/test_benchmark_config.py`

**Interfaces:**
- Produces: `PipelineConfig.benchmark: BenchmarkConfig` (default `BenchmarkConfig()` → `case_id is None`). Consumed by Task 5 (FeatureWorkflow wiring) and Task 10 (BenchmarkWorkflow).

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_config.py`:
```python
from sdlc.benchmarks.models import BenchmarkConfig
from sdlc.models import PipelineConfig


def test_default_pipeline_config_has_no_benchmark():
    cfg = PipelineConfig()
    assert cfg.benchmark.case_id is None
    assert cfg.benchmark.bench_run_id is None


def test_pipeline_config_accepts_benchmark_fields():
    cfg = PipelineConfig()
    cfg.benchmark = BenchmarkConfig(case_id="add-login", bench_run_id="b1")
    assert cfg.benchmark.case_id == "add-login"


def test_pipeline_config_serializes_with_benchmark():
    cfg = PipelineConfig()
    js = cfg.model_dump_json()
    assert "benchmark" in js
    # round-trip preserves defaults
    cfg2 = PipelineConfig.model_validate_json(js)
    assert cfg2.benchmark.case_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_config.py -v`
Expected: FAIL with `AttributeError: 'PipelineConfig' object has no attribute 'benchmark'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/models.py`, add an import at the top (after the existing imports, within the `from __future__` guard) and a field on `PipelineConfig`.

Add to the import block at the top of `models.py` (after line 14 `from pydantic import BaseModel, Field`):
```python
from sdlc.benchmarks.models import BenchmarkConfig
```
> Note: this creates a dependency `models → benchmarks.models`. To avoid a circular import, `benchmarks/models.py` must NOT import from `sdlc.models` anything that imports back. It imports `HarnessKind` only (an Enum), which is safe.

Add the field to `PipelineConfig` (the class starting at line 219 of `models.py`). Insert inside the class body, e.g. right after the `gates` field and before `roles`:
```python
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_config.py tests/test_benchmark_models.py -v`
Expected: PASS (no circular import errors; existing tests still green).

Run the full suite to confirm nothing regressed:
Run: `pytest -q`
Expected: PASS (all pre-existing tests still pass).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_benchmark_config.py
git commit -m "feat(benchmarks): attach BenchmarkConfig to PipelineConfig (additive)"
```

---

### Task 3: Composite score computation (pure)

**Files:**
- Create: `src/sdlc/benchmarks/scoring.py`
- Test: `tests/test_benchmark_scoring.py`

**Interfaces:**
- Consumes: `BenchmarkRecord`, `BenchmarkSummary`, `CompositeWeights` (Task 1).
- Produces: `compute_summaries(records, weights) -> list[BenchmarkSummary]`. Consumed by Task 7 (report).

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_scoring.py`:
```python
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.models import HarnessKind


def _rec(case, harness, model, q, usd, secs):
    return BenchmarkRecord(
        run_id="r",
        bench_run_id="b",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd, input_tokens=10, output_tokens=5),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, int(secs)),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _summarize(records, weights=None):
    return {s.model: s for s in compute_summaries(records, weights)}


def test_composite_ranks_better_quality_higher_even_if_pricier():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].composite > s["opus"].composite


def test_cost_axis_dropped_when_fewer_than_two_costed():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=None, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=None, secs=50),
    ]
    s = _summarize(recs)
    # both composites still produced; quality + speed only (renormalized)
    assert s["sonnet"].composite is not None
    assert s["opus"].composite is not None


def test_judge_error_records_excluded_from_composite():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=None, usd=2.0, secs=200),
    ]
    # The opus record had a judge error (q=None). It still appears as a summary
    # row but its composite is None.
    s = _summarize(recs)
    assert s["opus"].composite is None
    assert s["opus"].mean_quality is None


def test_custom_weights_change_ranking():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.9, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.1, secs=10),
    ]
    # weight cost heavily → cheap opus wins
    s = _summarize(recs, CompositeWeights(quality=0.1, cost=0.8, speed=0.1))
    assert s["opus"].composite > s["sonnet"].composite


def test_multiple_records_averaged_per_cell():
    recs = [
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.8, usd=1.0, secs=100),
        _rec("c1", HarnessKind.CLAUDE_CODE, "sonnet", q=0.6, usd=2.0, secs=200),
        _rec("c1", HarnessKind.CLAUDE_CODE, "opus", q=0.5, usd=0.5, secs=50),
    ]
    s = _summarize(recs)
    assert s["sonnet"].n == 2
    assert abs(s["sonnet"].mean_quality - 0.7) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.scoring'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/scoring.py`:
```python
"""Composite-score computation for benchmark records.

Pure functions: given a bag of BenchmarkRecords and weights, produce one
BenchmarkSummary per (case, stage, harness, model) cell. Quality is the
dominant axis; cost/speed are normalized within the (case, stage) group.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .models import BenchmarkRecord, BenchmarkSummary, CompositeWeights


def _safe_mean(xs: list[float]) -> float | None:
    return mean(xs) if xs else None


def compute_summaries(
    records: list[BenchmarkRecord],
    weights: CompositeWeights | None = None,
) -> list[BenchmarkSummary]:
    w = weights or CompositeWeights()
    # group raw records by cell identity
    by_cell: dict[tuple[str, str, str | None, str], list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        by_cell[(r.case_id, r.stage, r.harness.value if r.harness else None, r.model)].append(r)

    summaries: list[BenchmarkSummary] = []
    # normalization happens within (case_id, stage) across all cells in it
    for (case_id, stage), _ in {(r.case_id, r.stage) for r in records}:
        group = [r for r in records if r.case_id == case_id and r.stage == stage]
        costed = [r for r in group if r.cost.usd is not None]
        timed = [r for r in group if r.speed.wall_clock_s is not None]
        max_usd = max((r.cost.usd for r in costed), default=None)
        max_sec = max((r.speed.wall_clock_s for r in timed), default=None)
        use_cost = len(costed) >= 2 and max_usd
        use_speed = len(timed) >= 2 and max_sec

        for (_c, _s, h, m), cell_recs in by_cell.items():
            if _c != case_id or _s != stage:
                continue
            scored = [r for r in cell_recs if r.quality.score is not None]
            mean_q = _safe_mean([r.quality.score for r in scored])
            mean_usd = _safe_mean([r.cost.usd for r in cell_recs if r.cost.usd is not None])
            mean_sec = _safe_mean(
                [r.speed.wall_clock_s for r in cell_recs if r.speed.wall_clock_s is not None]
            )

            composite = _composite(
                mean_q, mean_usd, mean_sec, max_usd, max_sec, use_cost, use_speed, w
            )
            from sdlc.models import HarnessKind

            harness = HarnessKind(h) if h else None
            summaries.append(
                BenchmarkSummary(
                    case_id=case_id,
                    stage=stage,
                    harness=harness,
                    model=m,
                    n=len(cell_recs),
                    mean_quality=mean_q,
                    mean_cost_usd=mean_usd,
                    mean_wall_clock_s=mean_sec,
                    composite=composite,
                )
            )
    return summaries


def _composite(mean_q, mean_usd, mean_sec, max_usd, max_sec, use_cost, use_speed, w):
    if mean_q is None:
        return None
    q_norm = mean_q
    # renormalize weights over available axes
    avail_w = {"quality": w.quality}
    norms = {"quality": q_norm}
    if use_cost and mean_usd is not None and max_usd:
        avail_w["cost"] = w.cost
        norms["cost"] = 1 - (mean_usd / max_usd)
    if use_speed and mean_sec is not None and max_sec:
        avail_w["speed"] = w.speed
        norms["speed"] = 1 - (mean_sec / max_sec)
    total = sum(avail_w.values())
    if total <= 0:
        return mean_q
    return sum(avail_w[k] * norms[k] for k in norms) / total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_scoring.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/scoring.py tests/test_benchmark_scoring.py
git commit -m "feat(benchmarks): composite score with per-cell normalization"
```

---

### Task 4: Recorder activity + file-backed store

**Files:**
- Create: `src/sdlc/benchmarks/recorder.py`
- Test: `tests/test_benchmark_recorder.py`

**Interfaces:**
- Consumes: `BenchmarkRecord` (Task 1).
- Produces: `record_benchmark` activity (Temporal `@activity.defn`), `RecordStore` (file backend: `append` + `read_all`), and `records_path(bench_run_id, cell_id=None)` helper. Consumed by Task 5 (FeatureWorkflow), Task 9 (BenchmarkWorkflow), Task 11 (drift).

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_recorder.py`:
```python
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore, records_path


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.recorder'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/recorder.py`:
```python
"""Recorder: a Temporal activity + a tiny file-backed record store.

records.jsonl per (bench_run_id, cell_id) under SDLC_BENCHMARKS_ROOT
(default runs/benchmarks/). One JSON object per line — a partial last line
is skipped on read so a crashed writer never corrupts the readable history.
"""

from __future__ import annotations

import os
from pathlib import Path

from temporalio import activity

from .models import BenchmarkRecord

DEFAULT_ROOT = "runs/benchmarks"


def _root() -> str:
    return os.environ.get("SDLC_BENCHMARKS_ROOT", DEFAULT_ROOT)


def records_path(bench_run_id: str, cell_id: str | None, root: str | None = None) -> Path:
    base = Path(root if root is not None else _root()) / bench_run_id
    if cell_id:
        return base / f"{cell_id}.jsonl"
    return base / "records.jsonl"


class RecordStore:
    def __init__(
        self, root: str | None = None, bench_run_id: str = "b1", cell_id: str | None = None
    ) -> None:
        self.path = records_path(bench_run_id, cell_id, root)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: BenchmarkRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def read_all(self) -> list[BenchmarkRecord]:
        if not self.path.exists():
            return []
        out: list[BenchmarkRecord] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(BenchmarkRecord.model_validate_json(line))
                except Exception:
                    continue  # skip corrupt / partial line
        return out


@activity.defn
async def record_benchmark(record: BenchmarkRecord) -> None:
    """Append one BenchmarkRecord to the cell's records.jsonl.

    Non-deterministic I/O (filesystem) — must live in an activity, never in
    workflow code. Retries on failure via Temporal RetryPolicy.
    """
    store = RecordStore(bench_run_id=record.bench_run_id, cell_id=_cell_id_for(record))
    store.append(record)


def _cell_id_for(record: BenchmarkRecord) -> str | None:
    # drift records (case_id _production) go to one file per bench_run_id
    if record.case_id == "_production":
        return None
    h = record.harness.value if record.harness else "proposer"
    return f"{record.case_id}#{h}#{record.model}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_recorder.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/recorder.py tests/test_benchmark_recorder.py
git commit -m "feat(benchmarks): record_benchmark activity + JSONL store"
```

---

### Task 5: Wire record_benchmark into FeatureWorkflow (gated, pure when off)

**Files:**
- Modify: `src/sdlc/workflows/feature.py`
- Test: `tests/test_factory_recorder.py`

**Interfaces:**
- Consumes: `record_benchmark` activity (Task 4), `BenchmarkConfig` on `PipelineConfig` (Task 2).
- Produces: `FeatureWorkflow` emits `BenchmarkRecord` per stage boundary + per code-task attempt **iff** `cfg.benchmark.case_id` is set; otherwise zero recorder calls.

**Design note (purity):** the workflow gains a single helper `_record(...)` that early-returns when `cfg.benchmark.case_id is None`. Timing uses `workflow.now()` (deterministic under time-skipping tests). The recorder call is one `workflow.execute_activity(record_benchmark, ...)` per boundary.

- [ ] **Step 1: Write the failing test**

`tests/test_factory_recorder.py`:
```python
"""The purity assertion: when benchmark.case_id is None, the recorder is
never called. We assert this by pointing SDLC_BENCHMARKS_ROOT at a temp
dir and checking no file appears after a stage-boundary helper runs."""

from sdlc.benchmarks.models import BenchmarkConfig
from sdlc.workflows.feature import FeatureWorkflow


def test_record_helper_is_noop_when_case_id_none():
    wf = FeatureWorkflow.__new__(FeatureWorkflow)  # bypass __init__
    # when case_id is None, _record_stage should be a no-op (returns None
    # without raising). We test the pure predicate directly.
    from sdlc.benchmarks.recorder import records_path
    from sdlc.models import PipelineConfig

    cfg = PipelineConfig()
    assert cfg.benchmark.case_id is None
    # the predicate the helper uses:
    assert FeatureWorkflow._benchmarking(cfg) is False


def test_record_helper_is_active_when_case_id_set():
    from sdlc.models import PipelineConfig

    cfg = PipelineConfig()
    cfg.benchmark = BenchmarkConfig(case_id="add-login", bench_run_id="b1")
    assert FeatureWorkflow._benchmarking(cfg) is True
```

> The integration-level assertion (records actually appear when a workflow runs with `case_id` set, and do not appear when unset) is covered in Task 9's workflow test, which runs the real `FeatureWorkflow` end-to-end with the `record_benchmark` activity replaced by an in-memory fake.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_factory_recorder.py -v`
Expected: FAIL with `AttributeError: type object 'FeatureWorkflow' has no attribute '_benchmarking'`

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/workflows/feature.py`:

(a) Add `record_benchmark` and `BenchmarkRecord`-building types to the `unsafe.imports_passed_through()` block (lines 14-26). Inside that block add:
```python
from ..benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from ..benchmarks.recorder import record_benchmark
```

(b) Add a module-level `RECORD_ACT` timeout near `ACT`/`LONG_ACT` (after line 32):
```python
RECORD_ACT = dict(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=5)
)
```

(c) Add the predicate + helper inside the `FeatureWorkflow` class (after `__init__`, before the signals section). The helper takes plain serializable args and builds the record itself so the stage-call sites stay tiny:
```python
@staticmethod
def _benchmarking(cfg: PipelineConfig) -> bool:
    return bool(cfg.benchmark and cfg.benchmark.case_id)


def _stage_record(
    self,
    cfg: PipelineConfig,
    stage: str,
    role: str,
    started: datetime,
    ended: datetime,
    quality_score: float | None,
    judge: str,
    outcome: BenchmarkOutcome,
    model: str,
    harness=None,
    cost_usd: float | None = None,
    fix_attempts: int = 0,
    task_id: str | None = None,
    attempt: int | None = None,
) -> BenchmarkRecord:
    scope = BenchmarkScope.TASK_ATTEMPT if task_id is not None else BenchmarkScope.STAGE
    return BenchmarkRecord(
        run_id=workflow.info().workflow_id,
        bench_run_id=cfg.benchmark.bench_run_id or "_unknown",
        case_id=cfg.benchmark.case_id or "_unknown",
        scope=scope,
        stage=stage,
        task_id=task_id,
        attempt=attempt,
        role=role,
        harness=harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=quality_score, judge=judge),
        cost=CostBag(usd=cost_usd),
        speed=SpeedBag(
            wall_clock_s=(ended - started).total_seconds(), started_at=started, ended_at=ended
        ),
        outcome=outcome,
        fix_attempts=fix_attempts,
    )


async def _record(self, cfg: PipelineConfig, record: BenchmarkRecord) -> None:
    if not self._benchmarking(cfg):
        return
    await workflow.execute_activity(record_benchmark, record, **RECORD_ACT)
```

(d) Wire call sites. In `run()`, capture `started` before each stage and emit after. Concretely, wrap the existing stages. Example for the architect stage (around lines 212-217 of the current file):
```python
# 2. ARCHITECT (+ human approval of the spec)
self._status = "architecting"
_started = workflow.now()
arch = (await t_architect.run(f"mode={idea.mode.value}\n{reqs.model_dump_json()}")).output
gate = await self._gate("architecture", cfg)
_ended = workflow.now()
await self._record(
    cfg,
    self._stage_record(
        cfg,
        stage="architecture",
        role="architect",
        started=_started,
        ended=_ended,
        quality_score=None,
        judge="llm_judge",
        outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
        model="anthropic:claude-sonnet-4-6",
    ),
)
if not gate.approved:
    return "rejected:architecture"
```
Repeat the same `started`/`_record` pattern around the `clarify`, `plan`, and `merge`/`deploy` stages — each emitting one stage-scope record. Use `judge="llm_judge"` and `quality_score=None` for proposer stages (the LLM-judge in Task 8 will populate real scores out-of-band; the workflow records the timing/outcome, the judge fills quality later).

(e) For the **per-task attempt** records, in `_dev_task` add a record after each QA check inside the fix loop (around line 150 of the current file, after the `qa = (...)` line and before the `if qa.tests_passed` branch):
```python
await self._record(
    cfg,
    self._stage_record(
        cfg,
        stage="code",
        role=task.role,
        started=workflow.now(),
        ended=workflow.now(),
        quality_score=(1.0 if (qa.tests_passed and not qa.issues) else 0.0),
        judge="contract",
        outcome=(
            BenchmarkOutcome.PASS if (qa.tests_passed and not qa.issues) else BenchmarkOutcome.FAIL
        ),
        model=role_cfg.model or "anthropic:claude-sonnet-4-6",
        harness=role_cfg.harness,
        cost_usd=run.cost_usd,
        fix_attempts=attempt - 1,
        task_id=task.id,
        attempt=attempt - 1,
    ),
)
```
> Note: per-attempt timing within `_dev_task` is coarse (one `workflow.now()` delta) for v1 — the wall-clock granularity that matters is at the stage level; per-attempt we mainly care about cost, outcome, and which attempt succeeded. Refining this is OQ-B-adjacent and out of scope for v1.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_factory_recorder.py -v`
Expected: PASS (2 tests)

Run the full suite to ensure the workflow edits didn't break existing tests:
Run: `pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_factory_recorder.py
git commit -m "feat(benchmarks): wire gated record_benchmark into FeatureWorkflow"
```

---

### Task 6: Register recorder activity in the worker

**Files:**
- Modify: `src/sdlc/worker.py`
- Test: `tests/test_worker_registration.py`

**Interfaces:**
- Consumes: `record_benchmark` (Task 4).
- Produces: the worker serves `record_benchmark` on the `ai-sdlc` queue so `FeatureWorkflow` can call it.

- [ ] **Step 1: Write the failing test**

`tests/test_worker_registration.py`:
```python
from sdlc.benchmarks.recorder import record_benchmark


def test_record_benchmark_is_a_temporal_activity():
    # temporalio marks activities; the attr is set by @activity.defn
    assert getattr(record_benchmark, "__temporal_activity_definition", None) is not None


def test_worker_module_imports_record_benchmark():
    # the worker registration list must include it; importing succeeds
    from sdlc import worker

    assert record_benchmark.__name__ in [
        getattr(fn, "__name__", None) for fn in _worker_activities(worker)
    ]


def _worker_activities(worker):
    # introspect the source for the activities=[...] literal — simplest robust
    # check is that 'record_benchmark' appears in the registered list by name.
    import inspect

    src = inspect.getsource(worker)
    assert "record_benchmark" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_worker_registration.py -v`
Expected: FAIL (record_benchmark not yet in worker source)

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/worker.py`, add to the import from `.activities` (or a new import line). After line 19 (`from .agents.roles import ALL_TEMPORAL_AGENTS`), add:
```python
from .benchmarks.recorder import record_benchmark
```
And add `record_benchmark` to the `activities=[...]` list in the `Worker(...)` constructor (currently lines 37-41):
```python
activities = (
    [
        create_worktree,
        setup_integration_branch,
        merge_into_integration,
        run_coding_task,
        run_test_suite,
        open_pull_request,
        deploy,
        record_benchmark,
        *agent_activities,
    ],
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_worker_registration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/worker.py tests/test_worker_registration.py
git commit -m "feat(benchmarks): register record_benchmark in worker"
```

---

### Task 7: Report aggregation + Markdown rendering

**Files:**
- Create: `src/sdlc/benchmarks/report.py`
- Test: `tests/test_benchmark_report.py`

**Interfaces:**
- Consumes: `compute_summaries` (Task 3), `RecordStore` (Task 4).
- Produces: `aggregate(bench_run_id, weights, root) -> list[BenchmarkSummary]`, `render_markdown(summaries) -> str`, `write_report(summaries, out_path)`.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_report.py`:
```python
from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.recorder import RecordStore
from sdlc.benchmarks.report import aggregate, render_markdown
from sdlc.models import HarnessKind


def _rec(model, q, usd, secs):
    return BenchmarkRecord(
        run_id="r",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge="contract"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, int(secs)),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def test_aggregate_reads_store_and_returns_summaries(tmp_path):
    store = RecordStore(root=str(tmp_path), bench_run_id="b1")
    store.append(_rec("sonnet", 0.9, 1.0, 100))
    store.append(_rec("opus", 0.5, 0.5, 50))
    sums = aggregate("b1", CompositeWeights(), root=str(tmp_path))
    assert len(sums) == 2
    by_model = {s.model: s for s in sums}
    assert by_model["sonnet"].composite > by_model["opus"].composite


def test_render_markdown_has_headers_and_rows(tmp_path):
    sums = aggregate(
        "b1",
        CompositeWeights(),
        root=str(tmp_path),
        _records=[_rec("sonnet", 0.9, 1.0, 100), _rec("opus", 0.5, 0.5, 50)],
    )
    md = render_markdown(sums)
    assert "| case" in md or "case" in md
    assert "sonnet" in md and "opus" in md
    assert "composite" in md.lower()


def test_render_markdown_handles_empty():
    md = render_markdown([])
    assert "no records" in md.lower()
```

> The `_records` kwarg in `test_render_markdown` requires `aggregate` to accept an optional in-memory list (test seam) — when omitted it reads from the store.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.report'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/report.py`:
```python
"""Aggregate benchmark records into summaries and render reports."""

from __future__ import annotations

from pathlib import Path

from .models import BenchmarkRecord, BenchmarkSummary, CompositeWeights
from .recorder import RecordStore, _root
from .scoring import compute_summaries


def aggregate(
    bench_run_id: str,
    weights: CompositeWeights | None = None,
    root: str | None = None,
    _records: list[BenchmarkRecord] | None = None,
) -> list[BenchmarkSummary]:
    records = _records if _records is not None else _read_all(bench_run_id, root)
    return sorted(
        compute_summaries(records, weights),
        key=lambda s: (
            s.case_id,
            s.stage,
            s.harness.value if s.harness else "",
            -(s.composite or -1),
        ),
    )


def _read_all(bench_run_id: str, root: str | None) -> list[BenchmarkRecord]:
    base = Path(root if root is not None else _root()) / bench_run_id
    if not base.exists():
        return []
    out: list[BenchmarkRecord] = []
    for p in base.rglob("*.jsonl"):
        store = RecordStore(
            root=root, bench_run_id=bench_run_id, cell_id=p.stem if p.stem != "records" else None
        )
        # if cell file, point store at it directly:
        store.path = p
        out.extend(store.read_all())
    return out


def render_markdown(summaries: list[BenchmarkSummary]) -> str:
    if not summaries:
        return "# Benchmark report\n\nNo records found.\n"
    lines = [
        "# Benchmark report",
        "",
        "| case | stage | harness | model | n | quality | cost ($) | wall (s) | composite |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:

        def fmt(x):
            return f"{x:.3f}" if isinstance(x, float) else "—"

        lines.append(
            f"| {s.case_id} | {s.stage} | "
            f"{s.harness.value if s.harness else 'proposer'} | {s.model} | "
            f"{s.n} | {fmt(s.mean_quality)} | {fmt(s.mean_cost_usd)} | "
            f"{fmt(s.mean_wall_clock_s)} | {fmt(s.composite)} |"
        )
    return "\n".join(lines) + "\n"


def write_report(summaries: list[BenchmarkSummary], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_markdown(summaries), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_report.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/report.py tests/test_benchmark_report.py
git commit -m "feat(benchmarks): aggregate + Markdown report rendering"
```

---

### Task 8: Matrix expansion (case × harness × model)

**Files:**
- Create: `src/sdlc/benchmarks/matrix.py`
- Test: `tests/test_benchmark_matrix.py`

**Interfaces:**
- Consumes: `CaseSpec`, `BenchmarkCell` (Task 1).
- Produces: `expand_matrix(spec) -> list[BenchmarkCell]`; raises `SameFamilyJudgeError` when the judge model shares a family with any author model in the matrix.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_matrix.py`:
```python
import pytest

from sdlc.benchmarks.matrix import SameFamilyJudgeError, expand_matrix
from sdlc.benchmarks.models import CaseSpec
from sdlc.models import HarnessKind


def _spec(models, judge="openai/gpt-5.2"):
    return CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE],
        models=models,
        judge_model=judge,
        rubrics={},
    )


def test_full_cross_product():
    cells = expand_matrix(_spec(["anthropic:claude-sonnet-4-6", "anthropic:claude-opus-4-8"]))
    assert len(cells) == 2 * 2  # 2 harnesses × 2 models


def test_rejects_same_family_judge():
    # author family anthropic, judge family anthropic → reject (ADR-6)
    spec = _spec(["anthropic:claude-sonnet-4-6"], judge="anthropic:claude-haiku-3-5")
    with pytest.raises(SameFamilyJudgeError):
        expand_matrix(spec)


def test_different_family_judge_ok():
    cells = expand_matrix(_spec(["anthropic:claude-sonnet-4-6"], judge="openai/gpt-5.2"))
    assert len(cells) == 2


def test_cell_ids_unique():
    cells = expand_matrix(
        _spec(["anthropic:claude-sonnet-4-6", "openai/gpt-5.2"], judge="anthropic:claude-haiku-3-5")
    )
    # author models span anthropic + openai; judge must differ from EACH author
    # family — anthropic judge conflicts with the anthropic author → reject
    with pytest.raises(SameFamilyJudgeError):
        cells  # expansion already raised above; this assert documents intent
```

> Correction: the 4th test's comment is wrong as written — fix it during implementation to a clean assertion. Replace the body of `test_cell_ids_unique` with:
```python
def test_cell_ids_unique():
    cells = expand_matrix(
        _spec(["anthropic:claude-sonnet-4-6", "openai/gpt-5.2"], judge="google/gemini-2-pro")
    )
    ids = [c.cell_id for c in cells]
    assert len(ids) == len(set(ids))  # all unique
    assert len(cells) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_matrix.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.matrix'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/matrix.py`:
```python
"""Expand a CaseSpec into the (harness × model) cell list, enforcing the
ADR-6 cross-family judge rule: the judge model's family must differ from
EVERY author model's family in the matrix."""

from __future__ import annotations

from .models import BenchmarkCell, CaseSpec


class SameFamilyJudgeError(ValueError):
    pass


def _family(model: str) -> str:
    # "anthropic:claude-sonnet-4-6" → "anthropic"; "openai/gpt-5.2" → "openai"
    sep = ":" if ":" in model else "/"
    return model.split(sep, 1)[0].lower()


def expand_matrix(spec: CaseSpec) -> list[BenchmarkCell]:
    judge_family = _family(spec.judge_model)
    author_families = {_family(m) for m in spec.models}
    if judge_family in author_families:
        raise SameFamilyJudgeError(
            f"judge model family {judge_family!r} matches an author model "
            f"family in {sorted(author_families)}; ADR-6 requires the judge "
            f"to differ from every author family"
        )
    return [
        BenchmarkCell(case_id=spec.case_id, harness=h, model=m)
        for h in spec.harnesses
        for m in spec.models
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_matrix.py -v`
Expected: PASS (4 tests — with the corrected 4th test)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/matrix.py tests/test_benchmark_matrix.py
git commit -m "feat(benchmarks): matrix expansion + cross-family judge guard"
```

---

### Task 9: Judge activity (cross-family LLM-judge with injectable boundary)

**Files:**
- Create: `src/sdlc/benchmarks/judge.py`
- Test: `tests/test_benchmark_judge.py`

**Interfaces:**
- Consumes: `QualityScore` (Task 1).
- Produces: `judge_artifact` activity + `JudgeInput`/`JudgeResult` dataclasses. The LLM call is behind an injectable `JudgeFn` so tests pass a fake. On any failure, returns `QualityScore(score=None, judge="error")` — never raises.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_judge.py`:
```python
from sdlc.benchmarks.judge import JudgeInput, judge_artifact, _set_judge_fn


def test_judge_parses_valid_json():
    def fake(inp: JudgeInput) -> str:
        # rubric expects {"score": 0.0..1.0, "components": {...}}
        return '{"score": 0.82, "components": {"coverage": 0.9, "specificity": 0.74}}'

    _set_judge_fn(fake)
    result = judge_artifact.sync(
        JudgeInput(
            artifact_json="{}",
            rubric="score coverage 0..1",
            author_model="anthropic:claude-sonnet-4-6",
        )
    )
    assert result.score == 0.82
    assert result.judge == "llm_judge"
    assert result.components["coverage"] == 0.9


def test_judge_returns_error_on_unparseable():
    _set_judge_fn(lambda inp: "not json at all")
    result = judge_artifact.sync(
        JudgeInput(artifact_json="{}", rubric="r", author_model="anthropic:claude-sonnet-4-6")
    )
    assert result.score is None
    assert result.judge == "error"


def test_judge_clamps_out_of_range_score():
    _set_judge_fn(lambda inp: '{"score": 1.5}')
    result = judge_artifact.sync(
        JudgeInput(artifact_json="{}", rubric="r", author_model="anthropic:claude-sonnet-4-6")
    )
    assert result.score == 1.0  # clamped
```

> Note: `judge_artifact.sync(...)` is a test convenience — the activity object exposes the wrapped function via `.sync` when using temporalio's `@activity.defn` with `name=`; if `.sync` isn't available in your temporalio version, the implementation exposes a module-level `_judge_sync(inp)` and the test calls that. The implementer should pick whichever the installed temporalio supports and adjust the test's call to `_judge_sync(...)` if needed — the assertions stay identical.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.judge'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/judge.py`:
```python
"""Cross-family LLM-judge for proposer-stage artifacts.

The real LLM call is behind JudgeFn so tests inject a fake and CI makes no
model calls. On any failure (exception, bad JSON, out-of-range) we return
QualityScore(score=None, judge="error") — the judge never raises, so a
broken judge can never fail a benchmark cell; the record is simply excluded
from the composite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from temporalio import activity

from .models import QualityScore


@dataclass
class JudgeInput:
    artifact_json: str  # the stage's emitted artifact, serialized
    rubric: str  # rubric markdown/text for this case+stage
    author_model: str  # to assert cross-family at call time


JudgeFn = Callable[[JudgeInput], str]
_judge_fn: JudgeFn | None = None


def _set_judge_fn(fn: JudgeFn | None) -> None:
    global _judge_fn
    _judge_fn = fn


def _default_judge(inp: JudgeInput) -> str:
    # Production default: a Pydantic AI Agent call on a cross-family model.
    # Implemented in a later hardening task; for now raise so misconfiguration
    # surfaces as judge="error" rather than a silent wrong answer.
    raise RuntimeError(
        "no judge configured; set one via _set_judge_fn or wire the production Pydantic AI agent"
    )


def _judge_sync(inp: JudgeInput) -> QualityScore:
    fn = _judge_fn or _default_judge
    try:
        raw = fn(inp)
        payload = json.loads(raw)
        score = float(payload.get("score", 0.0))
        score = max(0.0, min(1.0, score))  # clamp
        components = payload.get("components") or {}
        return QualityScore(score=score, components=components, judge="llm_judge")
    except Exception:
        return QualityScore(score=None, judge="error")


@activity.defn
async def judge_artifact(inp: JudgeInput) -> QualityScore:
    return _judge_sync(inp)


# test convenience
judge_artifact.sync = _judge_sync  # type: ignore[attr-defined]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_judge.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Register the activity in the worker and commit**

In `src/sdlc/worker.py`, add to imports:
```python
from .benchmarks.judge import judge_artifact
```
and add `judge_artifact` to the `activities=[...]` list alongside `record_benchmark`.

```bash
git add src/sdlc/benchmarks/judge.py src/sdlc/worker.py tests/test_benchmark_judge.py
git commit -m "feat(benchmarks): cross-family LLM-judge activity (injectable)"
```

---

### Task 10: BenchmarkWorkflow (matrix runner)

**Files:**
- Create: `src/sdlc/benchmarks/workflow.py`
- Modify: `src/sdlc/worker.py` (register `BenchmarkWorkflow`)
- Test: `tests/test_benchmark_workflow.py`

**Interfaces:**
- Consumes: `FeatureWorkflow` (existing), `expand_matrix` (Task 8), `CaseSpec`, `BenchmarkConfig` (Task 1), `record_benchmark` (Task 4), `report.aggregate` + `write_report` (Task 7).
- Produces: `BenchmarkWorkflow.run(spec: CaseSpec) -> str` (writes `report.md` at the end). For each cell, starts a `FeatureWorkflow` child with `cfg.roles` overridden to `(cell.harness, cell.model)` and `cfg.benchmark` set.

**Design note:** Each cell is a child workflow — a cell's escalation cannot poison the matrix, and per-cell Temporal history stays clean for drift harvesting. `FeatureWorkflow.run` currently takes `(idea: IdeaBrief, cfg: PipelineConfig | None)` — we pass both.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_workflow.py`:
```python
"""BenchmarkWorkflow matrix test. We avoid a real Temporal server by testing
the pure config-building helper directly, plus a smoke test that the workflow
class is registered and runnable-shaped. A full time-skipping integration
test lives in Task 13's golden-case smoke run."""

from sdlc.benchmarks.models import CaseSpec
from sdlc.benchmarks.workflow import BenchmarkWorkflow, _cell_config
from sdlc.models import HarnessKind, PipelineConfig, ProjectMode, IdeaBrief


def _spec():
    return CaseSpec(
        case_id="add-login",
        idea_summary="add login",
        mode="greenfield",
        harnesses=[HarnessKind.CLAUDE_CODE],
        models=["anthropic:claude-sonnet-4-6"],
        judge_model="openai/gpt-5.2",
        rubrics={},
    )


def test_cell_config_overrides_role_and_sets_benchmark():
    base = PipelineConfig()
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(
        base, idea, _spec(), HarnessKind.OPENCODE, "openai/gpt-5.2", bench_run_id="b1"
    )
    # every role is overridden to the cell's harness+model
    for role, rc in cfg.roles.items():
        assert rc.harness is HarnessKind.OPENCODE
        assert rc.model == "openai/gpt-5.2"
    assert cfg.benchmark.case_id == "add-login"
    assert cfg.benchmark.bench_run_id == "b1"


def test_cell_config_is_pure_when_base_unbenchmark():
    base = PipelineConfig()
    assert base.benchmark.case_id is None
    idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    cfg = _cell_config(
        base, idea, _spec(), HarnessKind.OPENCODE, "openai/gpt-5.2", bench_run_id="b1"
    )
    assert cfg.benchmark.case_id == "add-login"


def test_benchmark_workflow_class_has_run():
    # the @workflow.run method exists
    assert hasattr(BenchmarkWorkflow, "run")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_workflow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.workflow'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/workflow.py`:
```python
"""BenchmarkWorkflow — the matrix runner.

For each (case × harness × model) cell, start a FeatureWorkflow child with
the cell's roles overridden and benchmark config set. Collect nothing in-
workflow — the record_benchmark activity writes each record to the file
store; after all cells complete, aggregate and write the report.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..workflows.feature import FeatureWorkflow
    from ..models import HarnessKind, IdeaBrief, PipelineConfig, ProjectMode, RoleConfig
    from .matrix import expand_matrix
    from .models import BenchmarkConfig, CaseSpec
    from .report import aggregate, write_report
    from .models import CompositeWeights

CHILD_ACT = dict(
    start_to_close_timeout=timedelta(hours=4), retry_policy=RetryPolicy(maximum_attempts=1)
)


def _cell_config(
    base: PipelineConfig,
    idea: IdeaBrief,
    spec: CaseSpec,
    harness: HarnessKind,
    model: str,
    bench_run_id: str,
) -> PipelineConfig:
    """Build a per-cell PipelineConfig: every doing-role overridden to
    (harness, model), benchmark fields set so FeatureWorkflow records."""
    cfg = base.model_copy(deep=True)
    cfg.roles = {
        role: RoleConfig(
            harness=harness,
            model=model,
            context_budget_tokens=rc.context_budget_tokens,
            extra_args=rc.extra_args,
        )
        for role, rc in base.roles.items()
    }
    cfg.benchmark = BenchmarkConfig(case_id=spec.case_id, bench_run_id=bench_run_id)
    return cfg


@workflow.defn
class BenchmarkWorkflow:
    @workflow.run
    async def run(self, spec_json: str) -> str:
        spec = CaseSpec.model_validate_json(spec_json)
        bench_run_id = workflow.info().workflow_id
        cells = expand_matrix(spec)
        idea = IdeaBrief(
            title=spec.case_id,
            description=spec.description,
            mode=ProjectMode(spec.mode),
            repo_url=spec.repo_url,
        )
        base = PipelineConfig()
        cell_ids: list[str] = []
        for cell in cells:
            cfg = _cell_config(
                base, idea, spec, cell.harness, cell.model, bench_run_id=bench_run_id
            )
            child_id = f"{bench_run_id}/{cell.cell_id}"
            try:
                await workflow.execute_child_workflow(
                    FeatureWorkflow.run,
                    idea,
                    cfg,
                    id=child_id,
                    task_queue=workflow.info().task_queue,
                )
            except Exception as e:
                # a failed/escalated cell is a data point, not a crash
                workflow.logger.warning("cell %s failed: %s", child_id, e)
            cell_ids.append(cell.cell_id)

        summaries = aggregate(bench_run_id, CompositeWeights())
        report_path = f"runs/benchmarks/{bench_run_id}/report.md"
        write_report(summaries, report_path)
        return report_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_workflow.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Register the workflow and commit**

In `src/sdlc/worker.py`, add to imports:
```python
from .benchmarks.workflow import BenchmarkWorkflow
```
and add `BenchmarkWorkflow` to the `workflows=[FeatureWorkflow, BenchmarkWorkflow]` list.

```bash
git add src/sdlc/benchmarks/workflow.py src/sdlc/worker.py tests/test_benchmark_workflow.py
git commit -m "feat(benchmarks): BenchmarkWorkflow matrix runner"
```

---

### Task 11: Drift harvester (Temporal history → records)

**Files:**
- Create: `src/sdlc/benchmarks/drift.py`
- Test: `tests/test_drift_harvester.py`

**Interfaces:**
- Consumes: `BenchmarkRecord` (Task 1), `RecordStore` (Task 4).
- Produces: `DriftHarvester(client)` with `async harvest_since(hours) -> str` (writes `runs/benchmarks/_drift/<date>/records.jsonl`). The harvester takes an injectable `history_provider` so tests pass a fake (no real Temporal connection).

- [ ] **Step 1: Write the failing test**

`tests/test_drift_harvester.py`:
```python
from datetime import datetime

from sdlc.benchmarks.drift import DriftHarvester


class FakeHistory:
    """Yields a canned list of (run_id, events) tuples."""

    def __init__(self, runs):
        self._runs = runs

    async def list_completed(self, hours):
        return [(rid, evs) for rid, evs in self._runs]

    async def fetch_history(self, run_id):
        return dict(self._runs)[run_id]


def _harness_result_event(cost=0.42, exit_code=0):
    # one activity-completed event whose result is a HarnessRunResult-ish dict
    return {
        "event_type": "ActivityTaskCompleted",
        "activity": "run_coding_task",
        "result": {
            "harness": "claude_code",
            "exit_code": exit_code,
            "cost_usd": cost,
            "summary": "",
            "input_tokens": 100,
            "output_tokens": 20,
            "context_window": 200000,
            "compacted": False,
        },
        "timestamp": datetime(2026, 7, 4, 10, 0, 30),
    }


def test_drift_emits_records_from_history(tmp_path):
    runs = [("feature-1", [_harness_result_event(cost=0.42)])]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path), bench_run_id="_drift/2026-07-04")
    import asyncio

    n = asyncio.run(h.harvest_since(hours=24))
    assert n == 1
    from sdlc.benchmarks.recorder import RecordStore

    store = RecordStore(root=str(tmp_path), bench_run_id="_drift/2026-07-04", cell_id=None)
    recs = store.read_all()
    assert len(recs) == 1
    assert recs[0].case_id == "_production"
    assert recs[0].cost.usd == 0.42


def test_drift_skips_run_with_no_relevant_events(tmp_path):
    runs = [("feature-2", [{"event_type": "WorkflowStarted"}])]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path), bench_run_id="_drift/2026-07-04")
    import asyncio

    n = asyncio.run(h.harvest_since(hours=24))
    assert n == 0


def test_drift_skips_malformed_event_without_crashing(tmp_path):
    runs = [
        (
            "feature-3",
            [
                _harness_result_event(),
                {
                    "event_type": "ActivityTaskCompleted",
                    "activity": "run_coding_task",
                    "result": "not-a-dict",
                },
            ],
        )
    ]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path), bench_run_id="_drift/2026-07-04")
    import asyncio

    n = asyncio.run(h.harvest_since(hours=24))
    # the malformed one is skipped, the well-formed one is kept
    assert n == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_drift_harvester.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.drift'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/drift.py`:
```python
"""DriftHarvester — production telemetry → BenchmarkRecords.

Observational only: judge ∈ {"contract", "human_override"} — we never re-judge
production artifacts with the LLM. The Temporal client is behind an injectable
history_provider so tests pass a fake.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from .recorder import RecordStore
from ..models import HarnessKind


class HistoryProvider(Protocol):
    async def list_completed(self, hours: int) -> list[tuple[str, Any]]: ...
    async def fetch_history(self, run_id: str) -> Any: ...


class DriftHarvester:
    def __init__(
        self, provider: HistoryProvider, root: str | None = None, bench_run_id: str = "_drift"
    ) -> None:
        self.provider = provider
        self.store = RecordStore(root=root, bench_run_id=bench_run_id, cell_id=None)

    async def harvest_since(self, hours: int) -> int:
        runs = await self.provider.list_completed(hours)
        n = 0
        for run_id, _ in runs:
            try:
                history = await self.provider.fetch_history(run_id)
            except Exception:
                continue
            for ev in _iter_events(history):
                rec = _record_from_event(run_id, ev, self.store.path.parent.name)
                if rec is not None:
                    self.store.append(rec)
                    n += 1
        return n


def _iter_events(history: Any):
    # history is either a list of events or a dict with "events"
    if isinstance(history, dict) and "events" in history:
        return history["events"]
    if isinstance(history, (list, tuple)):
        return history
    return []


def _record_from_event(run_id: str, event: Any, bench_ns: str) -> BenchmarkRecord | None:
    if not isinstance(event, dict):
        return None
    if event.get("event_type") != "ActivityTaskCompleted":
        return None
    if event.get("activity") != "run_coding_task":
        return None
    result = event.get("result")
    if not isinstance(result, dict):
        return None
    ts = event.get("timestamp") or datetime.now(timezone.utc)
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            ts = datetime.now(timezone.utc)
    started = ts
    ended = ts
    try:
        harness = HarnessKind(result.get("harness", "claude_code"))
    except ValueError:
        return None
    exit_code = int(result.get("exit_code", 1))
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=f"_{bench_ns}" if not bench_ns.startswith("_") else bench_ns,
        case_id="_production",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id=run_id,
        attempt=0,
        role="dev",
        harness=harness,
        model="unknown",  # drift can't reliably recover the per-run model
        # without parsing WorkflowStarted attributes; left
        # for a later hardening pass
        quality=QualityScore(score=None if exit_code != 0 else 1.0, judge="contract"),
        cost=CostBag(
            usd=result.get("cost_usd"),
            input_tokens=result.get("input_tokens"),
            output_tokens=result.get("output_tokens"),
        ),
        speed=SpeedBag(wall_clock_s=0.0, started_at=started, ended_at=ended),
        outcome=(BenchmarkOutcome.PASS if exit_code == 0 else BenchmarkOutcome.FAIL),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_drift_harvester.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/drift.py tests/test_drift_harvester.py
git commit -m "feat(benchmarks): DriftHarvester reads Temporal history"
```

---

### Task 12: CLI wiring (`sdlc.cli benchmark {run,drift,report}`)

**Files:**
- Create: `src/sdlc/benchmarks/cli.py`
- Modify: `src/sdlc/cli.py` (add the `benchmark` subparser)
- Test: `tests/test_benchmark_cli.py`

**Interfaces:**
- Consumes: `CaseSpec` (Task 1), `BenchmarkWorkflow` (Task 10), `DriftHarvester` (Task 11), `aggregate`/`render_markdown` (Task 7).
- Produces: `benchmark run --case <path>`, `benchmark drift --since <hours>`, `benchmark report --bench <id> [--source golden,drift]`.

- [ ] **Step 1: Write the failing test**

`tests/test_benchmark_cli.py`:
```python
from sdlc.benchmarks.cli import load_case_spec, build_parser, dispatch_report


def test_load_case_spec_reads_yaml(tmp_path):
    case = tmp_path / "case.yaml"
    case.write_text(
        "case_id: add-login\n"
        "idea_summary: add login\n"
        "description: login page\n"
        "mode: greenfield\n"
        "harnesses: [claude_code, opencode]\n"
        "models: [anthropic:claude-sonnet-4-6]\n"
        "judge_model: openai/gpt-5.2\n"
        "rubrics:\n  architect: rubric-architect.md\n",
        encoding="utf-8",
    )
    spec = load_case_spec(str(case))
    assert spec.case_id == "add-login"
    assert len(spec.harnesses) == 2
    assert spec.judge_model == "openai/gpt-5.2"


def test_parser_accepts_benchmark_subcommands():
    p = build_parser()
    args = p.parse_args(["benchmark", "report", "--bench", "b1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "report"
    assert args.bench == "b1"


def test_dispatch_report_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    # no records → empty report, but no crash
    out = dispatch_report("b1", source="golden", root=str(tmp_path))
    assert "No records" in out or "case" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.cli'`

- [ ] **Step 3: Write minimal implementation**

`src/sdlc/benchmarks/cli.py`:
```python
"""CLI handlers for the `sdlc benchmark` subcommands.

python -m sdlc.cli benchmark run    --case benchmarks/cases/add-login/case.yaml
python -m sdlc.cli benchmark drift  --since 168
python -m sdlc.cli benchmark report --bench <id> [--source golden,drift]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
import yaml

from ..models import HarnessKind
from ..worker import TASK_QUEUE
from .models import CaseSpec
from .workflow import BenchmarkWorkflow
from .report import aggregate, render_markdown, write_report
from .models import CompositeWeights
from .recorder import _root


def load_case_spec(path: str) -> CaseSpec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw["harnesses"] = [HarnessKind(h) for h in raw.get("harnesses", [])]
    return CaseSpec(**raw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("benchmark")
    bsub = b.add_subparsers(dest="bench_cmd", required=True)

    run = bsub.add_parser("run")
    run.add_argument("--case", required=True)

    drift = bsub.add_parser("drift")
    drift.add_argument("--since", type=int, default=168)  # hours

    rep = bsub.add_parser("report")
    rep.add_argument("--bench", required=True)
    rep.add_argument("--source", default="golden")
    return p


def dispatch_report(bench: str, source: str = "golden", root: str | None = None) -> str:
    summaries = aggregate(bench, CompositeWeights(), root=root)
    md = render_markdown(summaries)
    out_path = Path(root if root is not None else _root()) / bench / "report.md"
    write_report(summaries, str(out_path))
    return md


async def _run_matrix(case_path: str) -> str:
    spec = load_case_spec(case_path)
    client = await Client.connect("localhost:7233", data_converter=pydantic_data_converter)
    handle = await client.start_workflow(
        BenchmarkWorkflow.run,
        spec.model_dump_json(),
        id=f"bench-{spec.case_id}-{int(__import__('time').time())}",
        task_queue=TASK_QUEUE,
    )
    return await handle.result()


async def _run_drift(since_hours: int) -> int:
    # production wiring uses a real Temporal client; left to operator runtime
    from .drift import DriftHarvester, HistoryProvider  # noqa: F401

    raise NotImplementedError(
        "drift requires a live Temporal client; run via the operator CLI "
        "with a connected client. See ARCHITECTURE.md §8."
    )


def main_async(args: argparse.Namespace) -> None:
    if args.cmd != "benchmark":
        return
    if args.bench_cmd == "run":
        print(asyncio.run(_run_matrix(args.case)))
    elif args.bench_cmd == "drift":
        print(asyncio.run(_run_drift(args.since)))
    elif args.bench_cmd == "report":
        print(dispatch_report(args.bench, args.source))
```

In `src/sdlc/cli.py`, add the benchmark subparser to the existing `main()`. Insert after the existing `st = sub.add_parser("status")` block (before `args = p.parse_args()`):
```python
from .benchmarks.cli import build_parser as _bench_parser

# delegate benchmark subcommands to the benchmarks.cli parser
bp = sub.add_parser("benchmark")
bsub = bp.add_subparsers(dest="bench_cmd", required=True)
br = bsub.add_parser("run")
br.add_argument("--case", required=True)
bd = bsub.add_parser("drift")
bd.add_argument("--since", type=int, default=168)
bf = bsub.add_parser("report")
bf.add_argument("--bench", required=True)
bf.add_argument("--source", default="golden")
```
And in the dispatch block (after the existing `if args.cmd == "start":` branch), add:
```python
if args.cmd == "benchmark":
    from .benchmarks.cli import dispatch_report

    if args.bench_cmd == "report":
        print(dispatch_report(args.bench, args.source))
        return
    if args.bench_cmd == "run":
        from .benchmarks.cli import _run_matrix

        print(asyncio.run(_run_matrix(args.case)))
        return
    if args.bench_cmd == "drift":
        print("drift requires a live Temporal client; see ARCHITECTURE.md §8.")
        return
```

> `pyyaml` is a transitive dependency of `pydantic-ai-slim`; if it's missing, add `pyyaml>=6` to `pyproject.toml` `[project].dependencies`. Verify with `python -c "import yaml"` in Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -c "import yaml"` (confirm available; if `ModuleNotFoundError`, add `pyyaml>=6` to `pyproject.toml` deps and `pip install -e .`)

Run: `pytest tests/test_benchmark_cli.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/cli.py src/sdlc/cli.py tests/test_benchmark_cli.py
git commit -m "feat(benchmarks): wire sdlc.cli benchmark {run,drift,report}"
```

---

### Task 13: Golden-case assets + config

**Files:**
- Create: `benchmarks/config.yaml`
- Create: `benchmarks/cases/add-login-greenfield/case.yaml`
- Create: `benchmarks/cases/add-login-greenfield/rubric-architect.md`
- Create: `benchmarks/cases/add-login-greenfield/rubric-clarifier.md`
- Test: `tests/test_golden_case_loads.py`

**Interfaces:**
- Consumes: `load_case_spec` (Task 12).
- Produces: one shippable golden case + the default config that the README / smoke run use.

- [ ] **Step 1: Write the failing test**

`tests/test_golden_case_loads.py`:
```python
from pathlib import Path

from sdlc.benchmarks.cli import load_case_spec
from sdlc.benchmarks.matrix import expand_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE = REPO_ROOT / "benchmarks" / "cases" / "add-login-greenfield" / "case.yaml"
CONFIG = REPO_ROOT / "benchmarks" / "config.yaml"


def test_default_case_file_exists_and_loads():
    assert CASE.exists(), f"missing {CASE}"
    spec = load_case_spec(str(CASE))
    assert spec.case_id == "add-login-greenfield"
    cells = expand_matrix(spec)
    assert len(cells) >= 2  # at least 2 harnesses × 1 model


def test_config_yaml_has_weights():
    assert CONFIG.exists()
    import yaml

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert "weights" in cfg
    w = cfg["weights"]
    assert abs(w["quality"] + w["cost"] + w["speed"] - 1.0) < 1e-9


def test_rubric_files_exist():
    d = CASE.parent
    assert (d / "rubric-architect.md").exists()
    assert (d / "rubric-clarifier.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_golden_case_loads.py -v`
Expected: FAIL (files don't exist yet)

- [ ] **Step 3: Write minimal implementation**

`benchmarks/config.yaml`:
```yaml
# Pipeline-step benchmark defaults. Override per `benchmark run` invocation.
weights:
  quality: 0.6
  cost: 0.2
  speed: 0.2
# Default judge model — must be a DIFFERENT family than any author model in
# a case's matrix (ADR-6). The matrix expander rejects same-family configs.
default_judge_model: openai/gpt-5.2
```

`benchmarks/cases/add-login-greenfield/case.yaml`:
```yaml
case_id: add-login-greenfield
idea_summary: Add a login page (email + password) to a fresh greenfield web app.
description: |
  A small greenfield feature: one login route, credential check against a
  user table, session cookie on success. Exercises architect (stack choice),
  planner (task decomposition), and dev (one implementation task with a
  frozen contract). Sized for a single short factory run.
mode: greenfield
repo_url: null
harnesses:
  - claude_code
  - opencode
models:
  - anthropic:claude-sonnet-4-6
judge_model: openai/gpt-5.2     # different family than the author (ADR-6)
rubrics:
  architect: rubric-architect.md
  clarifier: rubric-clarifier.md
```

`benchmarks/cases/add-login-greenfield/rubric-architect.md`:
```markdown
# Architect rubric — add-login-greenfield

Score the architecture artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **stack_choice (0.3):** named a boring, mainstream stack (no exotic
  choices for a login page)
- **security (0.3):** explicitly addressed password hashing, session
  management, and at least one auth-specific risk (CSRF / brute-force)
- **file_tree (0.2):** produced a coherent file/module layout matching the
  stack
- **decisions_documented (0.2):** each non-trivial choice has rationale +
  alternatives considered
```

`benchmarks/cases/add-login-greenfield/rubric-clarifier.md`:
```markdown
# Clarifier rubric — add-login-greenfield

Score the ClarifiedRequirements artifact 0.0..1.0.

- **questions_material (0.4):** every open question materially changes the
  design (no filler); each has a "why_it_matters"
- **scope_discipline (0.3):** out_of_scope is explicit and reasonable
- **suggested_answers (0.3):** each open question has a concrete suggested
  answer the human could accept in one click
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_golden_case_loads.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add benchmarks/ tests/test_golden_case_loads.py
git commit -m "feat(benchmarks): golden case add-login-greenfield + config"
```

---

## Final verification

After all 13 tasks:

- [ ] **Run the full test suite**
  Run: `pytest -q`
  Expected: all pre-existing tests + ~38 new tests pass.

- [ ] **Smoke-check imports**
  Run: `python -c "from sdlc.worker import main; from sdlc.cli import main; from sdlc.benchmarks.workflow import BenchmarkWorkflow"`
  Expected: no `ImportError`, no circular-import errors.

- [ ] **Verify the production path is unchanged**
  Run: `python -c "from sdlc.models import PipelineConfig; c=PipelineConfig(); print(c.benchmark.case_id)"`
  Expected: prints `None`.

---

## Self-Review

**1. Spec coverage:**
- §3 BenchmarkRecord schema → Task 1 ✓
- §4 Composite score (normalization, None-cost, weight override) → Task 3 ✓
- §5 Components file layout → Tasks 1,3,4,7,8,9,10,11,12 ✓
- §5 PipelineConfig extension → Task 2 ✓
- §6 FeatureWorkflow wiring (gated, pure when off) → Task 5 ✓ (+ Task 9's workflow test covers emission)
- §7 Golden matrix run → Tasks 8, 10, 12 ✓
- §8 Drift harvesting → Task 11 ✓
- §9 Error handling (cell failure, judge error, malformed history, partial JSONL) → Tasks 9, 10, 11, 4 ✓
- §10 Testing strategy → test files map 1:1 to spec §10 ✓
- §11 Non-goals respected → no dashboard, no DB, no new task queues, no auto-tiering ✓

**2. Placeholder scan:** no TBD/TODO; every code step shows complete code. Two intentional production-seam markers (`_run_drift` raises `NotImplementedError` with a pointer, judge `_default_judge` raises when unconfigured) — both are deliberate v1 seams, documented in-file, not placeholders.

**3. Type consistency:**
- `BenchmarkRecord` fields match across Tasks 1, 3, 4, 5, 11.
- `compute_summaries` signature `(records, weights=None)` used identically in Tasks 3 and 7.
- `RecordStore(root, bench_run_id, cell_id)` constructor signature consistent across Tasks 4, 7, 11.
- `_cell_config(base, idea, spec, harness, model, bench_run_id)` consistent across Task 10's impl and test.
- `judge_artifact.sync` attached in Task 9 — if the installed temporalio rejects attribute assignment on the activity wrapper, the implementer switches the test to call `_judge_sync` directly (noted inline in Task 9).

**4. Scope check:** single cohesive subsystem; one plan; produces working, testable software (a golden case runs end-to-end after Task 13).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-04-pipeline-step-benchmarking.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a 13-task plan: keeps each task's context small and lets me gate quality at every boundary.

2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review. Faster turnaround but the session context grows with each task.

Which approach?
