# Pipeline-Step Benchmarking by Harness and Model

| | |
|---|---|
| Status | Approved (design) |
| Date | 2026-07-04 |
| Related | `ARCHITECTURE.md` (§3 DAG, §4 agent architecture, §10 trajectory harvesting), `SDLC-spec-v2.md` (§2 agent registry, §4 contracts), `PRD.md` (SC-1..6), `src/sdlc/models.py`, `src/sdlc/harness/adapters.py`, `src/sdlc/activities.py`, `src/sdlc/workflows/feature.py` |

---

## 1. Problem & goal

The factory runs a fixed 14-stage DAG where each step is executed by a
configured `(harness, model)` pair — `claude_code` vs `opencode`, and a
model per role (e.g. `anthropic:claude-sonnet-4-6`, `openai/gpt-5.2`,
`anthropic:claude-opus-4-8`). Today there is no structured way to answer
"which (harness, model) is more effective at step X?" — cost, tokens, and
exit codes are captured in `HarnessRunResult`, but they are not turned into
a comparable, per-step effectiveness measure, and there is no controlled way
to vary one variable while holding the others constant.

**Goal:** benchmark each pipeline step's effectiveness, comparable across
`(harness, model)` pairs, using a **composite score** (quality + cost +
speed) computed from both a **controlled golden suite** and **production
drift**, recorded at **stage granularity and per-task-attempt granularity**.

## 2. Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Definition of effectiveness | Composite score (quality + cost + speed) |
| Comparison method | Both: golden suite (head-to-head) + production drift |
| Step granularity | Both: 14 DAG stages + per-task code attempts (incl. fix-loop attempts) |
| Quality scoring | Code/QA via frozen `ValidationContract`; proposer stages via cross-family LLM-judge rubric |
| Storage & output | File-based (`runs/benchmarks/`) + CLI report (Markdown/HTML); DB is a later seam |
| Architecture | Approach B — standalone `BenchmarkWorkflow` driving `FactoryWorkflow` children per cell |

## 3. Metric schema — `BenchmarkRecord`

The atomic unit. Written once per stage boundary **and** once per code-task
attempt. All three dimensions are kept **raw** (never pre-normalized) so the
reporter can recompute under different weights without re-running.

```python
class BenchmarkScope(str, Enum):
    STAGE = "stage"
    TASK_ATTEMPT = "task_attempt"


class BenchmarkOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVISED = "revise"  # a gate sent the stage back (revise outcome)
    ESCALATED = "escalated"  # fix-loop / budget exhaustion → human gate


class QualityScore(BaseModel):
    score: float | None  # 0.0 .. 1.0, None when judge errored
    components: dict[str, float] = {}  # e.g. {"contract_pass": 0.9, "rubric_coverage": 0.8}
    judge: Literal["contract", "llm_judge", "human_override", "error"]


class CostBag(BaseModel):
    usd: float | None
    input_tokens: int | None
    output_tokens: int | None


class SpeedBag(BaseModel):
    wall_clock_s: float
    started_at: datetime
    ended_at: datetime


class BenchmarkRecord(BaseModel):
    # identity
    run_id: str  # the cell's FactoryWorkflow run id
    bench_run_id: str  # the parent BenchmarkWorkflow run id
    #   ("_drift" for production-drift records)
    case_id: str  # golden case name; "_production" for drift
    scope: BenchmarkScope
    stage: str  # one of the 14 stages
    task_id: str | None = None  # only when scope == TASK_ATTEMPT
    attempt: int | None = None  # fix-loop attempt index (0 = first try)
    role: str  # architect | dev | reviewer | qa | ...
    harness: HarnessKind | None = None  # null for pure proposers
    model: str  # e.g. "anthropic:claude-sonnet-4-6"
    prompt_sha: str  # role prompt version (already in memo hash)

    # dimensions (raw)
    quality: QualityScore
    cost: CostBag
    speed: SpeedBag

    outcome: BenchmarkOutcome
    fix_attempts: int = 0  # total attempts for the task (code stage)
    error: str | None = None
```

**Why raw, not baked:** different questions want different weights
(cost-tuning vs quality-ranking). Storing raw lets the reporter recompute;
storing only a baked number throws information away.

## 4. Composite score (computed at aggregation)

Computed per `(case_id, stage)` group across all `(harness, model)` cells,
**normalized within the group** so a hard case is never penalized for being
hard — only the relative spread between cells is measured.

```
For each (case_id, stage) group containing records R across cells:
  R_usd   = {r for r in R if r.cost.usd is not None}    # drop uncosted records
                                                            from the cost axis only
  q_norm  = quality.score                                  # already 0..1
  c_norm  = 1 - (usd / max(r.cost.usd for r in R_usd))     # cheaper is better;
                                                            # if |R_usd| < 2 the cost
                                                            # axis is dropped and
                                                            # weights renormalized
  s_norm  = 1 - (wall_clock_s / max(r.speed.wall_clock_s for r in R))

  composite = w_q * q_norm + w_c * c_norm + w_s * s_norm
```

When an axis cannot be computed for a group (e.g. fewer than two cells
report a cost), that axis is dropped and the remaining weights are
renormalized to sum to 1, so a composite is always produced when at least
the quality dimension is available.

**Default weights** (overridable in `benchmarks/config.yaml`, no re-run
required): `w_q = 0.6, w_c = 0.2, w_s = 0.2`. Quality dominates on purpose
— a fast, cheap, wrong answer is still wrong.

Records with `quality.score is None` (judge errored) are **excluded** from
the composite denominator; the cell is flagged "1 judge error" in the report.

### Scoring source per stage

| Stage class | `quality.judge` | Source |
|---|---|---|
| code (task_attempt) | `contract` | frozen `ValidationContract` assertions + test results |
| qa, quality_gate | `contract` | test suite + gate checks |
| clarify, architect, planner, analyst, reviewer | `llm_judge` | rubric file per case+stage; judge model from a **different family** than the author (ADR-6) |
| intake, constitution, retro | *(not scored, no record emitted)* | deterministic / no-op |

## 5. Components

```
src/sdlc/benchmarks/
  __init__.py
  models.py       # BenchmarkRecord, BenchmarkCell, BenchmarkSummary,
                  #   CompositeWeights, CaseSpec
  recorder.py     # record_benchmark activity (writes records.jsonl)
  judge.py        # judge_artifact activity (cross-family LLM-judge)
  workflow.py     # BenchmarkWorkflow (matrix runner)
  drift.py        # DriftHarvester (Temporal history → BenchmarkRecords)
  report.py       # aggregate + render Markdown/HTML
  cli.py          # wires `sdlc.cli benchmark {run,drift,report}`

benchmarks/                       # golden-case tree (versioned assets, like prompts/)
  config.yaml                     # composite weights, default judge model, default matrix
  cases/
    add-login-greenfield/
      case.yaml                   # IdeaBrief, contract refs, matrix overrides
      rubric-architect.md
      rubric-clarifier.md
      ...
```

**`PipelineConfig` extension** (additive, defaults preserve current behavior):

```python
class BenchmarkConfig(BaseModel):
    case_id: str | None = None  # None ⇒ not a benchmark run (pure path)
    bench_run_id: str | None = None


class PipelineConfig(BaseModel):
    ...
    benchmark: BenchmarkConfig = BenchmarkConfig()  # case_id=None by default
```

## 6. Wiring into `FactoryWorkflow` (purity preserved)

One new non-deterministic activity, called at each stage boundary and after
each code-task attempt. Gated by `cfg.benchmark.case_id`:

```python
# FactoryWorkflow, after each stage:
if cfg.benchmark and cfg.benchmark.case_id:
    await workflow.execute_activity(
        record_benchmark,
        BenchmarkRecord(scope="stage", stage="architecture", ...),
    )
# task loop, after each attempt:
    ... scope="task_attempt", task_id=..., attempt=n ...
```

Non-determinism stays in the activity (where it belongs). The workflow gains
one conditional + one activity call per boundary — the `workflows/` vs
`activities/` import-linter boundary is respected. The purity assertion is
codified as a test (§9): with `benchmark.case_id` unset, **zero**
`record_benchmark` activity calls occur.

## 7. Data flow — golden matrix run

```
cli: python -m sdlc.cli benchmark run --case add-login --matrix harness,model
  → BenchmarkWorkflow
       read case.yaml → expand matrix into cells
         cells = case × {claude_code, opencode} × {sonnet, opus, gpt-5.2, ...}
       for each cell (case_id, harness, model):
         reject at start if judge family == author family (ADR-6)
         start FactoryWorkflow child with
           cfg.roles[role].harness = cell.harness
           cfg.roles[role].model   = cell.model
           cfg.benchmark.case_id   = case.id
           cfg.benchmark.bench_run_id = parent.id
         child runs the real pipeline:
           - recorder emits BenchmarkRecord per stage + per attempt
               → runs/benchmarks/<bench_run_id>/<cell_id>/records.jsonl
           - proposer stages also call judge_artifact (cross-family LLM-judge)
         a cell that escalates/quarantines is recorded as outcome=escalated
         and the matrix continues (a failing cell is a data point)
       all cells done → aggregate_benchmark
         → runs/benchmarks/<bench_run_id>/report.md + report.html
```

**Why a child workflow per cell:** each cell is an independent factory run
with its own gates, fix loops, and history. Child isolation means one cell's
escalation cannot poison the matrix, and per-cell Temporal history stays
clean — which is exactly what the drift harvester reads later.

## 8. Data flow — production drift

```
cli: python -m sdlc.cli benchmark drift --since 7d
  → DriftHarvester scans Temporal visibility for completed FactoryWorkflow runs
       for each run: replay history → emit BenchmarkRecords
         judge ∈ {"contract", "human_override"}   # never re-judge production
                                                    # artifacts with the LLM;
                                                    # drift is observational
         case_id = "_production"
         bench_run_id = "_drift/<date>"
       → runs/benchmarks/_drift/<date>/records.jsonl

cli: python -m sdlc.cli benchmark report --source golden,drift --group-by stage,harness
  → report.py aggregates both sources uniformly, renders comparison tables
```

The schema is identical for both sources, so `report.py` treats them
uniformly — drift records just carry `case_id = "_production"`.

## 9. Error handling (benchmark-specific)

| Failure | Behavior |
|---|---|
| A cell's factory run escalates / quarantines a task | Record `outcome=escalated`/`failed`; **continue the matrix**. A failing cell is a data point, not a crash. |
| LLM-judge API fails or returns unparseable JSON | `quality.judge="error"`, `quality.score=None`; record still written; aggregation excludes it from the composite denominator; cell is not failed. |
| Judge model same family as author (config bug) | Rejected at `benchmark run` startup — mirrors the existing reviewer cross-family validator (ADR-6). |
| Cell times out / worker crash mid-run | Child workflow retries from last completed state (Temporal); records already flushed to `records.jsonl` persist (one JSON object per line; partial last line is skipped on read). |
| Drift harvester hits a run with missing artifacts / pruned history | Skip that run with a logged warning; never crash the harvest. |
| `record_benchmark` write fails (disk full, permissions) | Activity retries per Temporal `RetryPolicy`; on exhaustion the cell continues but is flagged `recording_failed` so the report can say "1 cell missing data". |

## 10. Testing strategy

Maps onto the existing layout under `tests/`:

- `tests/unit/test_benchmark_models.py` — serialization; `CompositeWeights`
  math (known raw dims → expected score; within-cell normalization; weight
  override from config; exclusion of `score=None`).
- `tests/unit/test_matrix.py` — `case × (harness, model)` expansion produces
  the expected cell set; rejects same-family author/judge at expansion time.
- `tests/unit/test_judge_prompt.py` — `judge_artifact` assembles the rubric +
  artifact correctly; parses a canned LLM response into a `QualityScore`.
- `tests/workflows/test_benchmark_workflow.py` — time-skipping Temporal test:
  matrix of 3 cells, one escalates → the other two complete and a report is
  produced; all cells' records land in the right files.
- `tests/workflows/test_factory_recorder.py` — `FactoryWorkflow` with
  `benchmark.case_id` set emits records at each stage boundary; with it unset,
  **zero** `record_benchmark` activity calls (the purity assertion that
  protects the production path).
- `tests/integration/test_drift_harvester.py` — feed a synthetic Temporal
  history fixture → assert emitted `BenchmarkRecord`s match (stage boundaries,
  outcomes, costs).
- CI uses `tests/fakes/fake_harness.py` (already in the repo layout,
  ARCHITECTURE §14) — no real model calls, fully deterministic.

## 11. Explicit non-goals (YAGNI for v1)

- No dashboard integration — file-based + CLI (per storage decision).
- No Postgres / Hindsight backend — `BenchmarkRecord` store is a seam (file
  backend now; DB-swappable interface, drop-in later).
- No automatic model selection / auto-tiering — the system reports, humans
  decide.
- No re-judging production artifacts with the LLM-judge; drift uses only
  contracts and recorded gate outcomes.
- No new task queues — benchmark runs on the existing `ai-sdlc` /
  `ai-sdlc-harness` queues.
- No mutation of production prompts, validators, or gates by the benchmark
  (NG4 still holds).

## 12. Open questions (deferred)

- **OQ-B1:** Golden-case authoring workflow — hand-authored only at first, or
  seed from a successful production run (anonymized) via a `benchmark seed`
  command? Defer until v1 ships and the value of more cases is clear.
- **OQ-B2:** Statistical confidence at small N — with 1 run per cell, a single
  outlier dominates. Minimum N per cell (default 3) and whether to surface
  variance in the report. Decide at report-implementation time.
- **OQ-B3:** Judge-cost budget — the cross-family LLM-judge is itself a model
  call per proposer stage per cell; cap per bench run, with a fallback to
  `judge=human_override` on exhaustion.
