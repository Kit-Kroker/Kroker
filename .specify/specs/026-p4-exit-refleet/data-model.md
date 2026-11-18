# Data model: round 026

Every addition is defaulted and additive. Pre-026 JSON, records and workflow payloads load unchanged.

## Stored or wire fields

| Model (file) | Field | Type / default | Meaning |
|---|---|---|---|
| `QAInput` (`S/stages/qa/activities.py`) | `lint_base` | `str \| None = None` | The task's `branch_point`. None means no per-task lint (legacy, qa fallback and crew paths) |
| `QAInput` | `lint_key` | `str = ""` | Base-worktree key `<run>/base-<task_id>`, a sibling of the task worktree |
| `QAInput` | `lint_report_only` | `list[str] = []` | Fenced globs on repair attempts: findings there are reported but not failing |
| `QAReport` (`S/stages/qa/models.py`) | `lint` | `ScopedLintReport \| None = None` | Merge's own report type, scoped to the task. None means not run |
| `CodingTaskResult` (`run_coding_task` result) | `lint_autofix` | `LintAutofix \| None = None` | Safe fixes applied before the checkpoint |
| `LintAutofix` (new, `S/toolchain/lint_scope.py`) | `files`, `rules` | `list[str]`, `dict[str, int]` | Which files were touched and the fix count per rule |
| `ScopedLintReport`, `LintFinding` | (moved) | unchanged | They move from `S/stages/merge/models.py` to `S/toolchain/lint_scope.py`, and merge re-exports them. The JSON wire format is unchanged |
| `BenchmarkRecord` (`S/benchmarks/models.py`) | `failure` | `AttemptFailure \| None = None` | Set on the code, QA and review records of a failed task attempt. Never written to `error` |
| `AttemptFailure` (new, same file) | `checks` | `list[str]` | An ordered subset of `tests, qa, drift, review, lint, no_feedback` |
| `AttemptFailure` | `summary` | `str` (≤ 500 chars) | The `_fix_loop_issues` text plus the drift note: what the dev was told |
| Cell record `child_result` string (`S/benchmarks/workflow.py:383`) | (content only) | `ChildWorkflowError(cause=<Type>): …` | Lets the scorer tell `timed_out` apart from `crashed`. No schema change |

## Derived (not stored)

- **`S/runs_paths.py`:** `benchmarks_root()`, `export_root()`, `explicit_export_root()` (the explicit `SDLC_EXPORT_ROOT` or None, for `graph/store.py`'s sibling rule) and `roots_report() -> RootsReport(records, export, records_how, export_how)`, where each `how` is `explicit`, `runs_root` or `default`.
- **`NoSummaryRun(run_id, case_id, terminal_class)`**, with `terminal_class` one of:
  - `crashed`: a cell record with `pipeline_finished=False`;
  - `timed_out`: the same, with a `cause=TimeoutError` marker;
  - `terminated`: no cell record;
  - `summary_missing`: a cell record with `pipeline_finished=True` but no summary.

  `Evidence` gains `no_summary`, `excluded_smoke` and `roots`.
- **`STAGE_GATES`** (`S/benchmarks/sc_rollup.py`): `{research, clarify, architecture, plan, merge, deploy}`.
- **`unplanned(g)`**: `g.decided_by != "policy"` and (`g.gate not in STAGE_GATES` or `g.policy == "soft"`).
- **`steered(g)`**: `g.gate in STAGE_GATES`, `g.decided_by != "policy"`, and the outcome is not `approve`.
- **SC-1** (headline): hits are runs that reached merge with no unplanned or steered gate before the first `merge` entry. n is the non-smoke run_ids (summaries plus no-summary runs). It renders with the Clopper-Pearson 95% interval.
- **SC-1-strict**: the existing `_unattended_to_merge`, over the same n.
- **SC-3-non-lint and SC-3-lint**: they partition SC-3's loops. A lint-only loop has every failed code attempt with `failure.checks == ["lint"]`. Legacy (`failure is None`) loops count as non-lint.
- **`_lint_ok(qa_raw)`** (`S/stages/code/attempt_failure.py`): `lint is None or lint.state is not MEASURED or not failing_introduced(lint, report_only)`.

## Unchanged by contract

`lint_clean`, `MERGE_REQUIRED_CHECKS`, gate-policy semantics, `auto_decision_for`, the calibration rule and ledger, containment, ADR-6, `GraphWorkflow`, `RunSummary`, the worker's default export location, and the merge path's lint behavior.
