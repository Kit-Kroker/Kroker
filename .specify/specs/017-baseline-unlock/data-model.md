# Data model: 017 Baseline Unlock

Every field is additive and optional. A pre-017 record, history or
`acceptance.yaml` loads with the defaults shown, and readers treat the
default as "pre-017", never as a measured value. `S/` = `src/sdlc/`, `B/` =
`src/sdlc/benchmarks/`.

## 1. Analyze slice (`S/stages/analyze/models.py`)

### 1.1 Evidence (new, in the LLM output schema)

| Field | Type | Default | Rule |
|---|---|---|---|
| `kind` | `Literal["file", "task_unchanged", "command"]` | required | |
| `ref` | `str \| None` | `None` | path for `file`, command text for `command`, None for `task_unchanged` |
| `expect` | `Literal["present", "absent"] \| None` | `None` | `file` only; None on a `file` means `present` |

### 1.2 CriterionTrace (changed)

| Field | Change |
|---|---|
| `key` | new, `str \| None = None`: the workflow-assigned key (`T01#3`) the analyst echoes |
| `evidence` | new, `list[Evidence] = []` |
| `task_id`, `criterion`, `tests` | unchanged |

### 1.3 AnalyzeOutcome (new, workflow-side, never in a model schema)

`report: AnalysisReport`, `untraced: list[str]` (labels `"task_id:
criterion"` in authoritative order, as today's `untraced_criteria`).

### 1.4 TraceInventory (new, activity result)

| Field | Type | Meaning |
|---|---|---|
| `changed_files` | `list[str]` | (a) run diff, name-only |
| `tests` | `list[str]` | (b) `path::[Class::]name` |
| `tree` | `list[str]` | (c) `git ls-files` at integration head |
| `task_changed` | `dict[str, int \| None]` | (d) per task: changed-file count; None = unknown |
| `task_files` | `dict[str, list[str]]` | (d) per task: the names (validation only) |
| `truncated` | `dict[str, bool]` | per list a/b/c/d |

### 1.5 TraceEnforcement (new, pure result)

`buckets: dict[str, int]` (`test`, `file`, `command`, `empty`), `untraced:
list[str]`, `criteria_trace: list[CriterionAudit]`, `truncated: bool`.

`CriterionAudit`: `key: str`, `bucket: Literal["test", "file", "command",
"empty"]`, `evidence: list[{kind, ref, expect, valid: bool}]`. Refs are cut
to 200 characters, and at most 300 criteria are kept.

## 2. Benchmark record (`B/models.py`)

### 2.1 BenchmarkRecord (changed)

| Field | Type | Default | Set on |
|---|---|---|---|
| `trace` | `TraceBag \| None` | `None` | analyze record (patched path) |
| `tasks_total` | `int \| None` | `None` | plan record |
| `blocking_checks` | `list[str] \| None` | `None` | merge record, all four sites |
| `stage_reach` | `StageReach \| None` | `None` | cell record and oracle record |

### 2.2 TraceBag (new)

`traced_by_test`, `traced_by_file`, `traced_by_command`, `untraced` (int;
`untraced` = command-only + empty), `criteria_trace:
list[CriterionAudit]`, `truncated: bool`.

### 2.3 StageReach (new, frozen, `extra="forbid"`)

| Field | Type | Rule |
|---|---|---|
| `last_stage` | `str \| None` | as `cell_progress` computes it today |
| `last_stage_outcome` | `Literal["pass", "fail", "other"]` | single-record stage: that record's outcome; per-task stage: pass iff every task's last record of it passed, fail if any failed, else other |
| `final_stage` | `str \| None` | `deploy` if the case enables deploy, else `merge`; None if unknown |
| `tasks_total` | `int \| None` | from the plan record; None if absent |
| `tasks_qa_passed` | `int` | tasks whose last qa record is PASS |
| `tasks_not_finished` | `int \| None` | `tasks_total − finished`; None when `tasks_total` is None |
| `merge_outcome` | `str \| None` | merge record outcome; None if no merge record |
| `merge_blocking_checks` | `list[str]` | from `blocking_checks`; [] when absent |

"Finished" means the task's last code-attempt record is PASS and its last
qa record is PASS.

### 2.4 Oracle record (changed by FR-025)

`quality.components` gains `exit_code` and `errors` (floats, the existing
dict). `quality.detail` holds `"collection/import errors: E of N"` when
`exit_code ∈ {2, 4}` or `2·errors ≥ total > 0`. The score is unchanged.

## 3. Other models

| Model | Change |
|---|---|
| `TaskResult` (`S/workflows/models.py`) | `start_ref: str \| None = None` |
| `CellProgress` (`B/cell.py`) | `stage_reach: StageReach \| None = None` |
| `OracleGrade` (`B/oracle.py`) | `exit_code: int \| None = None`, `errors: int = 0` |
| `Run` (`B/runs.py`) | `stage_reach: StageReach \| None = None` (read from the cell record) |
| `ArmEvidence` (`B/acceptance.py`) | `stall_points: list[str] = []` |
| `Reason` (`B/acceptance.py`) | `STALLED = "stalled"` |

## 4. Research dead-attempt ledger (file, not a model)

`$SDLC_RUNS_ROOT/<run_id>/research/dead-attempts.jsonl`. One JSON line per
dead attempt: `{"model": str, "input_tokens": int, "output_tokens": int,
"cache_read_tokens": int, "cache_write_tokens": int, "calls": 1}`.
Append-only. A corrupt line is skipped when read. Totals are summed per
model.

## 5. Wire names (never renamed once shipped)

`017-analyze-evidence`, `017-research-ledger`, `017-plan-drift-generated`.
Activity names: `build_trace_inventory`, `read_dead_attempt_usage`.
