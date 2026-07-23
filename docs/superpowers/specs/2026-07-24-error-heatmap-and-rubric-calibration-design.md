# E-36 — Error heatmap + rubric-calibration tracking (design)

| | |
|---|---|
| Status | Design — approved in brainstorming 2026-07-24 |
| Roadmap item | `ROADMAP.md §9.8 E-36 (new scope)` |
| Design input | `BENCHMARK.md §2 Tier B (calibration), §3.0/§4.4 (heatmap)` |
| Anchors | FR-704 / NFR-4 (heatmap); **FR-110 (new scope, proposed here)** (calibration) |
| Depends on | E-27 (records + rubric judging), E-31 (oracle records), E-32 (FR-704 export precedent) |

---

## 1. What this delivers

E-36 is Abdullin's *prioritisation instrument* plus the *trust layer* under every
rubric number. Two independent units land together, neither touching the
deterministic gate, the workflow contract, or the on-disk record schema:

1. **Error heatmap** — a `case × stage` rework-density grid rendered as a
   self-contained `heatmap.html` + a machine-readable `heatmap.json`, aggregated
   purely from `BenchmarkRecord`s already written to
   `runs/benchmarks/<bench_run_id>/*.jsonl`. Answers the only question that
   matters between iterations: *which stage, on which class of case, is costing
   the most — so what do I fix next.* Anchors to **FR-704 / NFR-4** (existing
   scope — it renders run/benchmark history to an export).

2. **Rubric calibration** — a file-edit-then-run loop that hand-scores a sample
   of rubric fixtures, runs the cross-family judge over the same fixtures, and
   reports judge–human agreement so *a rubric score is never read without its
   trust level* (BENCHMARK.md §2 Tier B). This is genuinely **new scope**: it
   adds a measurement capability the PRD does not yet name, so §6 proposes
   **FR-110** as part of this increment.

### Design stance carried in

- **Pure core, I/O at the edge.** Both units follow the E-32 shape
  (`observability/export.py`): pure renderers/aggregators with no `temporalio`
  and no filesystem, and a single activity (heatmap) or CLI command
  (calibration) that owns the writes. This keeps the aggregation unit-testable
  outside a Temporal environment and the workflow replay-safe.
- **No new record schema.** The heatmap reads the fields `BenchmarkRecord`
  already carries (`case_id`, `stage`, `scope`, `outcome`, `fix_attempts`,
  `run_id`, `quality.judge`). Nothing in the write path changes.
- **ADR-6 / ADR-11 respected.** Calibration asserts the judge family differs
  from the fixture's author-model family per fixture (ADR-6, OQ-B2). The
  instrument itself is a fixed, reviewed artifact — it grades the system under
  test, it does not modify it (ADR-11).

---

## 2. Heatmap — data model

New pure module `src/sdlc/benchmarks/heatmap.py` (mirrors
`observability/export.py`).

### 2.1 Contracts

```python
class HeatmapCell(BaseModel):
    case: str
    stage: str
    gate_rejects: int      # outcome in {FAIL, ESCALATED, REVISED}
    fix_attempts: int      # sum of record.fix_attempts
    oracle_fails: int      # scope=ORACLE, outcome=FAIL (oracle column only)
    n_runs: int            # distinct run_id for the CASE
    density: float         # (gate_rejects + fix_attempts + oracle_fails) / max(n_runs, 1)

class Heatmap(BaseModel):
    cells: list[HeatmapCell]         # sparse: only (case, stage) pairs seen
    cases: list[str]                 # row order, sorted
    stages: list[str]                # column order, canonical (see 2.3)
    max_density: float               # colour-scale ceiling (>=0)
    language_by_case: dict[str, str] # case -> declared language ("" if none)
```

### 2.2 Density definition

For each observed `(case, stage)`:

- `gate_rejects` = count of records at that `(case, stage)` whose `outcome ∈
  {FAIL, ESCALATED, REVISED}`. `REVISED` counts as rework because a revise round
  is re-entering a stage — the "silent rework" the heatmap exists to surface.
- `fix_attempts` = Σ `record.fix_attempts` over records at that `(case, stage)`.
- `oracle_fails` = count of `scope=ORACLE` records for the case with
  `outcome=FAIL`. Contributes only to the synthetic `oracle` column.
- `n_runs` = number of distinct `run_id` values for the **case** (across every
  cell/repeat), so a stage's density is comparable across cases with different
  run counts.
- `density = (gate_rejects + fix_attempts + oracle_fails) / max(n_runs, 1)`.

`max_density` = max density across all cells (0 when the grid is empty), used as
the red end of the colour scale. Every raw count and `n_runs` is preserved in
`heatmap.json` and the HTML hover tooltip — the single density value only drives
colour.

### 2.3 Stage (column) order

A canonical 15-stage ordering constant, in record vocabulary, plus a trailing
synthetic `oracle` column:

```
intake, constitution, context, requirements, research, clarify, architecture,
planning, code, review, analyze, qa, quality_gate, deploy, retro, oracle
```

Only columns with at least one observed cell are rendered (the grid stays
sparse), preserving this order. A record whose `stage` is not in the canonical
list is appended after `retro` (before `oracle`) so an unrecognised stage is
visible, never dropped.

### 2.4 Language slice (BENCHMARK.md §3.0/§4.4)

`heatmap.json` carries `language_by_case`, sourced from each case's declared
`CaseSpec.language` (via a small `{case_id: language}` map passed to the
aggregator — see §3.1). The HTML renders an **"all cases"** grid plus one grid
per distinct non-empty language, so a Python-tuned pipeline quietly doing worse
on Go is visible. This is a `group-by` over the same cells — no extra data
source.

### 2.5 Functions

- `build_heatmap(records, language_by_case={}) -> Heatmap` — pure aggregation.
- `render_heatmap_json(hm) -> str` — `hm.model_dump_json(indent=2)`.
- `render_heatmap_html(hm) -> str` — pure, dependency-free, inline-CSS template
  (same discipline as `render_report_html`): a `<table>` per language group,
  cells coloured green→red by `density / max_density`, `title=` tooltip carrying
  the breakdown, all text `escape()`d. Empty grid → a "No records" page.

---

## 3. Heatmap — wiring

### 3.1 Where the language map comes from

`build_heatmap` needs `case_id → language`. The `finalize_benchmark_report`
activity does not currently know the case specs. Rather than thread specs into
the activity, the language map is derived cheaply and locally:

- The activity reads the case manifests it can find under
  `benchmarks/cases/<case_id>/` (the same dir `judge.py::_CASES_DIR` already
  resolves) for a declared `language`. (Oracle records carry only numeric
  components — `passed`/`total`/`held_out_ok`/`language_match` — not the language
  string, so the manifest is the source.) A case with no manifest or no declared
  language contributes `""` and appears only in the "all" grid.

This keeps the language map a best-effort annotation: a missing language never
breaks the heatmap, it just omits that case from per-language grids.

### 3.2 Activity extension

The existing `finalize_benchmark_report` activity (`report.py:77`) already reads
all records for the bench run and writes `report.md`. It is extended to also
write, in the same directory:

- `runs/benchmarks/<bench_run_id>/heatmap.html`
- `runs/benchmarks/<bench_run_id>/heatmap.json`

All I/O stays inside this one activity (determinism rule preserved).
`BenchmarkWorkflow` is unchanged — it already invokes the activity
(`workflow.py:151`). The activity's return value stays the `report.md` path
(back-compat); the heatmap paths are siblings.

### 3.3 CLI

`sdlc benchmark report` (in `benchmarks/cli.py`) gains the same two outputs when
run offline against an existing `bench_run_id`, so a heatmap can be regenerated
without re-running the matrix.

---

## 4. Calibration — storage & flow

New module `src/sdlc/benchmarks/calibration.py` + CLI verbs in
`benchmarks/cli.py`. Entirely offline (like `sdlc eval`); nothing runs inside a
workflow.

### 4.1 Fixture files

`benchmarks/calibration/<rubric>/fixt-*.json`, one artifact per file:

```json
{
  "artifact_json": "<the stage artifact, serialized>",
  "rubric_ref": "cat-cafe/architect",
  "rubric_text": "<rubric markdown, pinned at capture>",
  "rubric_sha": "<sha256 of rubric_text>",
  "author_model": "glm-4.6",
  "human_score": 0.8,
  "human_components": {"soundness": 0.9, "completeness": 0.7},
  "scored_by": "maksim",
  "notes": "misses the telemetry back-pressure case"
}
```

- `<rubric>` is the calibration bucket name = the rubric-map key, which is a
  **proposer role name** (`clarifier` / `architect` / `planner` / `qa` /
  `research`), matching `CaseSpec.rubrics` keys. Using the role name is what
  keeps capture unambiguous: the rubric key names both the calibration bucket
  *and* the stage artifact to harvest (`judge.py` flags that this vocabulary —
  `architect` — differs from the record `stage` field — `architecture`; the
  calibration bucket uses the rubric-key vocabulary throughout).
- `rubric_text` is **pinned into the fixture** at capture time, with its
  `rubric_sha`. A human scored *this* artifact against *this* rubric version, so
  calibration replays exactly that; a later rubric edit does not silently
  invalidate a past hand-score — it just means new fixtures should be captured.
- `human_score: null` → the fixture is unscored and skipped by `calibrate`.
- `author_model` is carried so `calibrate` can assert cross-family against the
  judge (ADR-6 / OQ-B2).

### 4.2 Commands

- **`sdlc calibrate capture --case <c> --rubric <role> [--from-run <run_id>] [--n N]`**
  Seeds fixture files under `benchmarks/calibration/<role>/` with
  `human_score: null`, harvesting the role's stage artifact + the resolved rubric
  text (via the existing `load_case_assets` path) and the author model. `--rubric`
  is the proposer role name (see §4.1), which names both the bucket and the
  artifact to harvest. Reuses E-4's history-harvesting seam (`sdlc eval capture`)
  where it already reads a run's per-role artifacts; the calibration-specific
  part is writing the fixture shape above. Human then edits files to fill
  `human_score`.

- **`sdlc calibrate <rubric> [--judge-model M] [--epsilon 0.15] [--threshold 0.75]`**
  Loads scored fixtures under `benchmarks/calibration/<rubric>/`, runs the
  existing judge (`judge.py::_judge_sync`, via the injectable `_judge_fn` so CI
  makes no model calls) over each fixture's `(artifact_json, rubric_text)`,
  **asserts `family(judge_model) != family(author_model)` per fixture and skips
  with a loud warning on violation** (never silently calibrates a same-family
  judge), computes agreement (§5), and writes
  `benchmarks/calibration/<rubric>/calibration.json` + prints a report.

The judge model defaults to the `judge_model` on the case spec(s) that own the
rubric; `--judge-model` overrides.

---

## 5. Calibration — the agreement metric

Pure `compute_agreement(pairs: list[tuple[float, float]], epsilon=0.15,
threshold=0.75) -> AgreementStats`, unit-tested, **no scipy** (Spearman
implemented in-module with average-rank tie handling):

```python
class AgreementStats(BaseModel):
    n: int
    epsilon: float
    agreement_rate: float   # fraction with |judge - human| <= epsilon
    mae: float              # mean absolute error
    spearman: float         # rank correlation (0.0 when undefined, n<2 or zero-variance)
    verdict: Literal["calibrated", "uncalibrated"]  # calibrated iff rate >= threshold
```

`calibration.json`:

```json
{
  "rubric": "architect",
  "judge_model": "gpt-5.1",
  "n_fixtures": 24,
  "epsilon": 0.15,
  "threshold": 0.75,
  "agreement_rate": 0.83,
  "mae": 0.09,
  "spearman": 0.71,
  "verdict": "calibrated",
  "computed_at": "2026-07-24T12:00:00Z"
}
```

### 5.1 Trust surfacing

The heatmap HTML and `report.md` gain a **Rubric calibration** section: a table
of `rubric → n, agreement_rate, MAE, Spearman, verdict`, read from every
`benchmarks/calibration/*/calibration.json` present. Additionally, every
rubric-derived quality score shown in `report.md` is annotated with its rubric's
`agreement_rate` (e.g. `trust 0.83`); a rubric with no `calibration.json` renders
as `uncalibrated` — so a rubric number is never displayed without its trust
level, per BENCHMARK.md §2's non-negotiable.

The calibration table is read-only annotation: it never changes a composite
score or gates anything. A low agreement rate is a signal to fix the *rubric*,
surfaced loudly, not an automatic score adjustment.

---

## 6. PRD amendment — FR-110 (new scope)

Add to `PRD.md §6` under Governance & ops / observability (beside FR-704):

> **FR-110 (new scope) — Rubric-judge calibration.** Before a rubric's LLM-judge
> score is trusted in a phase-exit decision, the factory SHALL support
> calibrating that rubric against a sample of human-scored fixtures and SHALL
> report judge–human agreement (a within-ε agreement rate, mean absolute error,
> and rank correlation) per rubric. A rubric's calibration verdict and agreement
> rate SHALL be surfaced alongside every score derived from it, so a rubric score
> is never read without its trust level. Calibration is an offline measurement
> tool; it SHALL NOT modify scores or gate outcomes automatically — low agreement
> is a rubric defect to be fixed, not an automatic adjustment.

The heatmap needs no new FR: it is an observability export under FR-704
("render run history to `events.jsonl` + `report.html`"), extended with a
benchmark-scoped `heatmap.{html,json}` rendering of the same history.

---

## 7. Testing

Following TDD; unit tests, no live model calls.

**Heatmap (`build_heatmap`):**
- synthetic records → expected per-cell densities, including the
  `gate_rejects + fix_attempts + oracle_fails` composition;
- `n_runs` de-dups distinct `run_id` per case (two records same run → n_runs=1);
- `scope=ORACLE` failures land only in the `oracle` column;
- unrecognised stage is appended, not dropped;
- language slice groups cases correctly; a case with `""` language appears only
  in the "all" grid;
- empty records → empty `Heatmap`, `max_density=0`, "No records" HTML.
- `render_heatmap_html` is well-formed and escapes case/stage text.

**Calibration:**
- `compute_agreement`: within-ε boundary (exactly ε counts as agree), MAE,
  Spearman on perfect / anti-correlated / tied / n<2 inputs; verdict threshold;
- fixture loader skips `human_score: null` and malformed files (like
  `RecordStore.read_all`'s corrupt-line skip);
- the cross-family assertion fires and skips a same-family fixture with a
  warning;
- end-to-end `calibrate` over injected-judge fixtures writes a
  `calibration.json` with the expected stats.

---

## 8. Files

| File | Change |
|---|---|
| `src/sdlc/benchmarks/heatmap.py` | **new** — `HeatmapCell`/`Heatmap`, `build_heatmap`, `render_heatmap_html`, `render_heatmap_json` |
| `src/sdlc/benchmarks/report.py` | extend `finalize_benchmark_report` activity to also write `heatmap.{html,json}`; add language-map resolution helper |
| `src/sdlc/benchmarks/calibration.py` | **new** — fixture model + load/store, `compute_agreement`, `AgreementStats`, `run_calibration` |
| `src/sdlc/benchmarks/cli.py` | add `calibrate` + `calibrate capture` verbs; extend `benchmark report` to emit heatmap |
| `benchmarks/calibration/` | **new** dir (fixture files, git-tracked) |
| `PRD.md` | add FR-110 |
| `ROADMAP.md` | mark E-36 landed |
| `tests/` | heatmap + calibration unit tests |

---

## 9. Out of scope (explicit)

- **Session-derived waste** (E-38's `HarnessSession` tool-call/backtrack
  aggregates, BENCHMARK.md §4.3) as a heatmap input — the heatmap is designed to
  accept it later (density is already a sum of rework signals), but this
  increment aggregates only the three record-derived signals. Folding session
  waste in is a follow-on once §4.3 aggregates are on records.
- **Calibration as a CI gate** (OQ-B4 / OQ-E2) — calibration is on-demand and
  advisory here; a committed-baseline CI check is a separate increment.
- **Interactive / spreadsheet calibration entry** — file-edit only.
- Any change to the composite score, the deterministic gate, or record schema.
