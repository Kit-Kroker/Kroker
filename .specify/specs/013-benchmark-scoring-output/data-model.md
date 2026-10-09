# Data Model: Benchmark Scoring Output Rework (013)

Every name the round adds, changes or removes. A name not listed here is
not introduced without a report to the orchestrator. Decisions are in
[research.md](research.md); behaviour is in
[contracts/scoring-output.md](contracts/scoring-output.md).

`B/` = `src/sdlc/benchmarks/`. `H/` = `src/sdlc/harness/`.

## 1. `B/runs.py` (new; imports `B/models.py` and the standard library only)

### 1.1 Models (pydantic, frozen)

**`TaskOutcome`**

| Field | Type | Meaning |
|---|---|---|
| `task_id` | `str` | |
| `attempts` | `int` | code attempts recorded |
| `first_passed` | `bool` | first code attempt passed |
| `last_passed` | `bool` | last code attempt passed |

**`Run`**

| Field | Type | Meaning |
|---|---|---|
| `run_id` | `str` | the key |
| `bench_run_id` | `str` | |
| `case_id` | `str` | |
| `harness` | `str` | `harness[:lead]`, from the records or the run id |
| `arm` | `str` | research R-3 |
| `arm_recovered` | `bool` | false only when a record carried `arm` |
| `generation` | `Literal["pre012", "012"]` | |
| `commit` | `str \| None` | commit id, `unknown`, or `None` = not recorded |
| `tree_dirty` | `bool \| None` | |
| `started_at` | `datetime \| None` | earliest record start |
| `status` | `Literal["graded", "lost", "grading_failed", "no_oracle"]` | research R-2 |
| `status_derived` | `bool` | true when no cell record existed |
| `last_stage` | `str \| None` | latest by `CELL_STAGE_ORDER`, as recorded |
| `pipeline_finished` | `bool \| None` | from the cell record; `None` when derived |
| `oracle_passed`, `oracle_total` | `int \| None` | set only when `status == "graded"` |
| `discarded_oracle_records` | `int` | oracle-scope records on a lost run |
| `tasks` | `tuple[TaskOutcome, ...]` | tasks with at least one code attempt |
| `qa_is_copy` | `bool` | research R-5 |
| `tokens` | `int \| None` | input + output over the run's records; `None` when none carry any |
| `wall_clock_s` | `float \| None` | cell record's when present, else the sum over stage and attempt records |
| `records` | `tuple[BenchmarkRecord, ...]` | the run's records, cell and oracle-task records included; excluded from JSON output |

Computed properties: `partial_credit` (`passed / total` or `None`),
`all_pass`, `first_attempt` (`(k, n)`), `after_repair` (`(k, n)`).

**`Group`**

| Field | Type | Meaning |
|---|---|---|
| `case_id`, `harness`, `arm`, `generation`, `commit` | | the key |
| `runs` | `tuple[Run, ...]` | start order |
| `started`, `graded`, `lost`, `grading_failed`, `no_oracle` | `int` | sum to `started` |
| `mean`, `sd`, `lo`, `hi` | `float \| None` | partial credit over graded runs; `sd` is the sample deviation, `None` under two |
| `all_pass` | `tuple[int, int]` | |
| `low_n` | `bool` | `graded < MIN_OBSERVATIONS` |

**`Totals`**: `started`, `graded`, `lost`, `grading_failed`, `no_oracle`,
`lost_by_stage: dict[str, int]` (key `none` for no stage record),
`discarded_oracle_records`, `derived_statuses`.

**`CompositeDecision`**: `shown: bool`, `arms: int`, `reason: str`.

### 1.2 Functions and constants

| Name | Signature | Notes |
|---|---|---|
| `MIN_OBSERVATIONS` | `5` | the one under-five threshold |
| `parse_run_id` | `(run_id: str) -> tuple[str, str, str] \| None` | `(case, harness[:lead], arm)`; `None` when the shape does not match |
| `build_runs` | `(records) -> list[Run]` | drift records left out; sorted by case, arm, generation, start |
| `group_runs` | `(runs) -> list[Group]` | |
| `totals` | `(runs) -> Totals` | |
| `gate_passed` | `(stage: str, outcome: BenchmarkOutcome) -> bool \| None` | research R-9 |
| `composite_shown` | `(runs) -> dict[str, CompositeDecision]` | keyed by case |
| `attempt_sort_key` | `(r: BenchmarkRecord) -> tuple` | `(attempt or 0, started_at)`; `sc_rollup` uses it too |

## 2. `B/models.py` (changed)

| Name | Kind | Notes |
|---|---|---|
| `TASK_LOOP_STAGES` | `frozenset[str]` | code, tool_approval, qa, review, adversary, deep_review, handoff. A test pins it as a subset of `CELL_STAGE_ORDER`. |
| `cell_progress` | `(records) -> tuple[str \| None, bool]` | the body of `summarize_cell`, moved |
| `grading_from_score` | `(has_oracle: bool, code_finished: bool, score: float \| None) -> str` | the body of `grading_status`, moved |
| `WasteBag.capture_rev` | `int \| None = None` | copied by `from_digest` |
| `waste_measured` | `(r: BenchmarkRecord) -> bool` | research R-15 |
| `RUBRIC_JUDGES` | `frozenset[str]` | `llm_judge`, `staged_rubric`; `score._SCORING_JUDGES` becomes an alias |

`BenchmarkSummary` gains, all optional with defaults:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `generation` | `str` | `""` | `pre012` or `012`; `pre012` flag stays and agrees |
| `pass_n`, `pass_d` | `int \| None` | `None` | verdict stages: passes over counted records |
| `first_attempt` | `tuple[int, int] \| None` | `None` | code row only |
| `after_repair` | `tuple[int, int] \| None` | `None` | code row only |
| `all_pass` | `tuple[int, int] \| None` | `None` | oracle row only |
| `tokens` | `int \| None` | `None` | mean tokens per run at the stage |
| `qa_is_copy` | `bool` | `False` | qa row built only from runs whose qa verdict copies code |

`composite` keeps its type; it is `None` whenever the case's decision is
"not shown". `model` stays as the sorted distinct models of the row.

No field of `BenchmarkRecord` changes. Nothing is added to stored records.

## 3. `B/heatmap.py` (rewritten below `CANONICAL_STAGES`) and `B/heatmap_render.py` (new)

`CANONICAL_STAGES` stays, byte for byte, with a comment that it is the
graph's vocabulary and no longer the heatmap's columns.

| Name | Where | Shape |
|---|---|---|
| `LAYERS` | `heatmap.py` | `("attrition", "first_attempt", "wasted_tokens", "oracle")` |
| `ORACLE_COLUMN` | `heatmap.py` | `"oracle"` |
| `LayerCell` | `heatmap.py` | `layer`, `row`, `stage`, `num: float`, `den: float`, `observations: int`, `value: float \| None`, `state: Literal["value", "low_n", "blank", "copy"]`, `not_measured: int = 0` |
| `OracleMark` | `heatmap.py` | `row`, `run_id`, `passed`, `total` |
| `HeatmapRow` | `heatmap.py` | `key`, `case_id`, `harness`, `arm`, `generation`, `language`, `started`, `lost_before_code`, `lost_tokens: int \| None`, `no_stage_recorded` |
| `LayeredHeatmap` | `heatmap.py` | `rows`, `stages`, `cells`, `oracle_marks`, `pre012_records` |
| `build_layers` | `heatmap.py` | `(runs, language_by_case=None) -> LayeredHeatmap` |
| `render_heatmap_json` | `heatmap.py` | kept name |
| `SCALES` | `heatmap_render.py` | per layer: four bounds and `higher_is_worse` |
| `step_for` | `heatmap_render.py` | `(layer: str, value: float) -> int` (0 to 4) |
| `render_heatmap_html` | `heatmap_render.py` | `(hm, calibration_html="") -> str` |

**Removed**: `HeatmapCell`, `Heatmap`, `build_heatmap`, `ORACLE_STAGE`,
`REWORK_OUTCOMES`, `_cell_color`, `_grid` (heatmap's).

## 4. `B/gate_oracle.py` (new)

| Name | Shape |
|---|---|
| `GATE_STAGES` | `("qa", "review", "adversary", "deep_review", "handoff", "analyze", "merge")` |
| `GateRow` | `row` (heatmap row key), `gate`, `pass_pass`, `pass_fail`, `reject_pass`, `reject_fail`, `n`, `agree_rate`, `escape_rate`, `false_reject_rate` (each `float \| None`), `mean_credit_passed`, `mean_credit_rejected`, `low_n: dict[str, bool]`, `is_copy: bool` |
| `GateOracle` | `rows`, `pre012_records` |
| `build_gate_oracle` | `(runs) -> GateOracle` |
| `render_gate_oracle_json`, `render_gate_oracle_html`, `render_gate_oracle_markdown` | |

Output files: `gate-oracle.html`, `gate-oracle.json`.

## 5. `B/grid.py` (new)

| Name | Shape |
|---|---|
| `StageMark` | `Literal["first", "repaired", "failed", "not_reached", "not_evaluated", "copy"]` |
| `GridCell` | `stage`, `mark: StageMark`, `tasks: tuple[int, int] \| None` (passed first time, total) |
| `GridRow` | `run: Run` fields needed for display, `cells: tuple[GridCell, ...]` |
| `Grid` | `groups` (each: `Group` figures + rows), `stages`, `totals: Totals` |
| `build_grid` | `(runs) -> Grid` |
| `render_grid_json`, `render_grid_html`, `render_grid_markdown` | markdown is ASCII |

Output files: `grid.html`, `grid.json`. The markdown is the first section
of `report.md`.

## 6. Other changed names

| Name | Where | Change |
|---|---|---|
| `summarize_cell`, `grading_status` | `B/cell.py` | bodies call §2's functions; signatures unchanged |
| `compute_summaries` | `B/scoring.py` | builds runs; rows keyed per research R-11; composite per R-10 |
| `_composite` | `B/scoring.py` | normalises against arm means |
| `render_markdown` | `B/report.py` | new signature `(summaries, calibration=None, records=None, *, grid=None, gate_oracle=None, decisions=None, sc_rollup=None, notes=None)`; it emits every section of contract §8 itself, each heading once; `write_score` passes the rollup and the notes in and appends nothing after it |
| `_TABLE_HEADER` | `B/report.py` | replaced by `_table_header(show_composite: bool)` |
| `write_heatmap` | `B/report.py` | takes runs |
| `finalize_benchmark_report` | `B/report.py` | calls `score.write_score`; name, argument and return unchanged |
| `write_score` | `B/score.py` | writes grid and gate-oracle; returns paths; adds the weights note |
| `Evidence.summary_runs`, `Evidence.selection_runs` | `B/evidence.py` | `int`, default 0 |
| `load_evidence` | `B/evidence.py` | summaries by run id (research R-12) |
| `MIN_RUNS` | `B/sc_rollup.py` | alias of `runs.MIN_OBSERVATIONS` |
| `SCRollup.summary_runs`, `SCRollup.selection_runs` | `B/sc_rollup.py` | `int`, default 0; rendered as "N of M runs left a summary" |
| `build_sc_rollup` | `B/sc_rollup.py` | gains keyword `selection_runs: int = 0` |
| `WasteMatrix.not_measured` | `B/waste_matrix.py` | `int`, default 0; runs counted by `run_id` |
| `render_deltas_markdown` | `B/experiments.py` | gains `show_composite: bool = False`; `_cells` skips unmeasured waste |
| page title and heading | `B/agreement_matrix.py` | "Reviewer vs adversary split"; names and files unchanged |
| `SessionDigest.capture_rev` | `H/models.py` | `int \| None = None` |
| `CAPTURE_REV` | `H/session.py` | `1`; `digest_of` writes it |
| `OpenCodeHarness.normalise_session`, `_TOOL_MAP` | `H/opencode.py` | research R-15 |
| `parse_report` | `scripts/aggregate_benchmarks.py` | first table whose header has a cell exactly `case` and a cell exactly `stage` |

## 7. Files added outside source

| File | What |
|---|---|
| `tests/fixtures/opencode/session_tools.jsonl` | a real captured opencode stream (research R-15) |

## 8. Name check (first task)

Before any edit, confirm none of these exists with another meaning:
`rg -n "build_runs|group_runs|parse_run_id|cell_progress|grading_from_score|TASK_LOOP_STAGES|waste_measured|capture_rev|CAPTURE_REV|RUBRIC_JUDGES|MIN_OBSERVATIONS|LayeredHeatmap|LayerCell|build_layers|step_for|gate_oracle|GateOracle|build_grid|composite_shown|CompositeDecision|attempt_sort_key" src tests interfaces scripts`.
Expected: no hits outside this spec directory. A hit is reported before
work continues.
