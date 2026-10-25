# Research and design decisions: 017 Baseline Unlock

Every decision below was checked in the tree at main `e435bd10`. They bind
the tasks the same way the spec does. `S/` = `src/sdlc/`, `B/` =
`src/sdlc/benchmarks/`.

## D-1. analyze.step returns the enforced untraced list (FR-002, FR-007, FR-010)

**Finding.** The untraced list is computed three times. `S/stages/analyze/step.py:151`
computes it for the record. The two orchestrators then recompute it,
`S/workflows/graph_nodes/postplan.py:93` and `S/workflows/feature.py:542`, from
`untraced_criteria(authoritative, analysis)`, and feed it to the merge gate's
advisory check (`S/stages/merge/step.py:457-461`). The new rule needs the
inventories, and only the analyze step has them. If the call sites kept
recomputing, the merge gate would keep the old rule and still block runs
that analyze now passes.

**Decision.** `analyze.step` returns a new slice model, `AnalyzeOutcome
{report: AnalysisReport, untraced: list[str]}`. Both call sites read
`outcome.untraced` and build `AnalyzeResult(report=outcome.report,
untraced=outcome.untraced, ...)`, so the graph payload shape
(`S/workflows/models.py:77-84`) is unchanged. `AnalysisReport` is the LLM
output schema, and it gains only `CriterionTrace.evidence` and `key`. No
workflow-computed field goes into the schema the model sees.

**Alternatives rejected.** (a) A workflow-filled field on `AnalysisReport`:
it would leak into the model's output schema. (b) Recomputing at the call
sites with the inventory passed out: it duplicates the rule in three
places, which is how the rule drifted in the first place.

## D-2. One replay marker for the whole analyze change (FR-010)

**Decision.** `ANALYZE_EVIDENCE_PATCH = "017-analyze-evidence"`, a wire name
that is never renamed. Inside `analyze.step`, `workflow.patched(...)`
decides the path.
- **True:** schedule the inventory activity (D-3), build the prompt with
  the inventories and keys, and enforce with `enforce_traces(...)` (D-4).
- **False:** today's prompt, no new activity, and `untraced_criteria(...)`
  exactly as now.

The marker is taken once, before the first new command. On replay of a
pre-017 history it returns False, so the command sequence and the untraced
list are identical, and so is the merge gate's flow. The FeatureWorkflow
grace rule (`S/workflows/AGENTS.md`, "Grace edits") is met because the call
site edit in `feature.py` adds no command.

## D-3. The inventory activity lives in the analyze slice (FR-004)

**Decision.** A new activity `build_trace_inventory(InventoryInput) ->
TraceInventory` goes in `S/stages/analyze/activities.py`. `ACTIVITIES`
becomes `[build_trace_inventory]`, registered through `STAGE_MODULES`
(`S/worker.py:140`).
- It uses `git` through the existing `vcs` helpers (a horizontal package,
  not a stage call) and stdlib `ast`. It never imports or runs produced
  code.
- Input: `integration_wt`, `base_sha`, and per-task `(task_id, branch,
  start_ref | None)`.
- The slice `AGENTS.md`, `analyze.md` and
  `tests/analyze/test_analyze_slice_contract.py` change in the same diff,
  per the artifact boundary rule.

**Per-task start ref (FR-004 d).** `TaskResult` has no start commit
(`S/workflows/models.py:56-68`). `TaskHost._dev_task` creates the worktree
from `from_ref` and passes `branch_point=handle.branch_point or from_ref`
to the code step (`S/workflows/task_host.py:273-292`).
- **Decision:** `TaskResult` gains an additive `start_ref: str | None =
  None`. The code step builds the `TaskResult`, and `S/stages/code/step.py`
  is at the line ceiling (D-11). So `_dev_task` stamps the field on the
  returned value: `return (await code_step(...)).model_copy(update=
  {"start_ref": handle.branch_point or from_ref})`, in
  `S/workflows/task_host.py` (300 lines). That is in-workflow state only,
  with no command change. The builder checks every other `TaskResult`
  producer (crew path, seeded work); any that does not stamp it yields
  "unknown".
- Pre-017 results and any task without it yield "unknown", so
  `task_unchanged` fails closed.
- The diff is `git diff --name-only <start_ref>..<branch>`.

**Bounds (my call, reviewer-checkable).** Each of the four lists is capped
at 2,000 entries. Paths are cut to 300 characters, test names to 200. The
prompt part of (a)+(b) is capped at 150,000 characters, with a truncation
note. Even with the 60k patch, that stays far under the 1 MiB payload
guard (`S/agents/payload_guard.py`).

## D-4. Enforcement is one pure function (FR-002, FR-003, FR-005, FR-007)

**Decision.** `enforce_traces(criteria: list[KeyedCriterion], report,
inventory) -> TraceEnforcement` goes in `S/stages/analyze/models.py`. It
returns `buckets`, `untraced` (labels in authoritative order) and
`criteria_trace` (bounded). It is pure and table-testable. Precedence is
test > file (present, absent, task_unchanged) > command > empty. Failed
validation is not evidence.
- **Keys:** `"{task_id}#{n}"`, with n 1-based in plan order. Matching is by
  `key`; when the key is absent or unknown, by exact `(task_id,
  criterion)`.
- **Test-name normalization:** strip a `[...]` suffix, split on `::`. A
  full node id matches exactly. A bare name matches when exactly one
  inventory entry ends with `::name`.
- **Containment:** case-sensitive. The cited path, or its basename, is a
  substring of the criterion text.

`untraced_criteria` stays unchanged for the unpatched path.

## D-5. Analyze record fields ride the record builder (FR-007, FR-008)

**Decision.** `BenchmarkRecord` gains an optional `trace: TraceBag | None`
(scope STAGE, analyze only), holding the bucket counts and
`criteria_trace`. `stage_record` gains a matching keyword. This is
args-only, with no new command. Record payload changes are replay-safe:
Temporal does not compare activity inputs. Pre-017 records read `trace =
None`.

## D-6. Stage reach is computed in `summarize_cell` (FR-020 to FR-023)

**Decision.** `summarize_cell` (`B/cell.py:53-76`), an existing activity,
already reads every record of the cell. It returns `CellProgress` with an
added `stage_reach: StageReach | None = None`. The parent copies it onto
the cell record (`CellStatus` stays as is; `BenchmarkRecord.stage_reach`
is new) and onto the oracle record, so the score and the reach sit side by
side. No new activity is involved.
- A `CellProgress` recorded in a pre-017 history deserializes with the
  default None.
- `final_stage` comes from the case spec that the parent passes into
  `summarize_cell`. Its signature gains an optional third argument,
  `final_stage: str | None = None`. The parent passes it only under the
  existing `012-cell-record` branch.
  - Changing the arguments of an existing `execute_activity` is not a
    command-type change, so it replays. The real guarantee has three parts:
    the SDK replayer matches commands by machine, sequence and event type
    and never compares activity inputs (reviewer-verified in the installed
    `temporalio` sdk-core); a recorded `CellProgress` decodes with the
    defaulted field; and an in-flight scheduled `summarize_cell` re-executes
    its recorded two-argument input against the defaulted signature.
  - **Replay coverage (reviewer plan finding 2).** No history in
    `tests/replay/histories/` covers `BenchmarkWorkflow`, and
    `tests/test_benchmark_workflow_sequence.py` runs fresh executions, so it
    replays nothing. Step 0 therefore records one `BenchmarkWorkflow` history
    on the pre-change code: the sequence test's stub-activity harness, one
    cell, no model calls, no paid run. It goes into `tests/replay/histories/`
    with a replay test beside the existing ones, so the round's replay gate
    replays the parent under the new code. This is the only legitimate time
    to add it, before any change. The history is never re-recorded after.
- The configured final stage is `deploy` when the case enables deploy and
  `merge` otherwise (`B/workflow.py:130`). The rule is pure and lives in
  `B/models.py` beside `cell_progress`.

**Producers.** `tasks_total` is added to the plan record. It is written by
`stage_record(..., tasks_total=len(artifact.tasks))` at
`S/stages/plan/step.py:148-163`.

`merge_blocking_checks` comes from a new `blocking_checks` field on the
merge record, filled at the four sites (`S/stages/merge/step.py:485-521,
538-556, 623-641, 643-657`) from `GateReport.blocking`.
- It is args-only. Merge's slice rule ("diff-scoped gates ... no
  `workflow.patched`") is about the gate's commands, and this change adds
  none.

## D-7. The stalled verdict (FR-024)

**Decision.** `B/runs.py`'s `Run` gains `stage_reach: StageReach | None`,
read from the cell record. `ArmEvidence.stall_points` lists the runs'
`last_stage`. `decide()` gains the stalled branch between SATURATED and
DEGENERATE, as the spec orders it. `STALL_EPSILON = 0.05` sits beside
`SEPARATION_MARGIN` (`B/acceptance.py:15`). `Reason.STALLED = "stalled"`
is added. `separation()` still computes the margin, so the record keeps
the means.

## D-8. Oracle collection-error signal (FR-025)

**Finding.** `_bounded_shell` returns the exit code, but `grade_oracle`
drops it (`B/oracle.py:327-329`). `grade_from_junit` parses passed and
total but not `errors` (`B/oracle.py:31-58`).

**Decision.**
- `OracleGrade` gains `exit_code: int | None = None` and `errors: int =
  0`. `grade_from_junit` returns the errors count.
- `_oracle_record` adds `components["exit_code"]` and
  `components["errors"]`. When `exit_code in (2, 4)` or `errors * 2 >=
  total > 0`, it sets `quality.detail = "collection/import errors: E of
  N"`.
- The score is untouched (FR-026). `OracleGrade` is an activity result,
  and the new fields default for old histories.
- It is built only after T-finding (FR-027) confirms or amends the signal.
- **Amendment (T003 finding, 2026-10-25).** The R1 1/56 was not a collection
  or import failure. On both arms pytest exited 1 with errors=0 and
  failures=55. The models broke the case's stated `POST /productions`
  contract, and one shared test helper (`make_performance`) raised before any
  assertion, so every test that uses it failed. FR-025's signal (exit 2/4,
  errors ≥ half) would not have flagged it, and is not meant to. The signal is
  kept as designed: it guards a different, real failure mode (an unimportable
  or uncollectable tree). It does not explain or detect R1's mode.
  Detecting a shared-setup failure (a high share of failures with one common
  first failing frame) is out of FR-025's scope. Adding it would change the
  FR-025 text (spec amendment, orchestrator/user call). It is not built in
  this round unless that call is made.

## D-9. Research dead-attempt ledger (FR-030 to FR-032)

**Decision.**
- `budget_store.py` gains `append_dead_attempt(run_id, usage: RoleUsage)
  -> None`. It is a synchronous `open(..., "a")` append of one JSON line to
  `$SDLC_RUNS_ROOT/<run_id>/research/dead-attempts.jsonl`, with a single
  `os.write`. It takes no async lock, so the `CancelledError` path cannot
  stall.
- It also gains `read_dead_attempts(run_id) -> list[RoleUsage]`, which sums
  per model and skips corrupt lines, the same tolerance as the record
  reader.
- An append-only line file makes concurrent sub-question appends safe
  without the lock. This is the builder's call that FR-031 allows. One
  `os.write` of a line under 4 KiB is atomic on the local filesystems the
  worker uses.
- `stage.py`: the body of `_research_subquestion_impl` is wrapped once.

  ```text
  try: <existing body>
  except BaseException:
      if run_usage has tokens: try append_dead_attempt(...) except Exception: log
      raise
  ```

  The degrade handlers return, so the wrapper never sees them.
  `run_usage` must be bound before the `try`. The builder moves its
  construction above the wrapper if it is not already.
- `step.py`: under `RESEARCH_LEDGER_PATCH = "017-research-ledger"`, one
  activity `read_dead_attempt_usage(run_id)` runs after the last fan-out
  and synthesis and before the first record site. The activity is
  **defined** in `S/stages/research/stage.py`, beside the slice's other
  activity definitions, and **assembled** into `ACTIVITIES` in
  `S/stages/research/activities.py`. That is the slice's existing pattern.
  The slice `AGENTS.md` updates in the same diff. For each model total,
  `_fold_research_usage(ctx, cfg, usage, research_spend, calls=usage.calls)`
  adds it once.
  - The one signature is `_fold_research_usage(ctx, cfg, usage, into, *,
    calls: int = 1)`: `ctx` is added first for D-10's emission, and `calls`
    is keyword-only with default 1. Every existing caller is updated
    (`research/step.py:203, 225, 280, 345`).
  - **Fold placement (reviewer tasks finding 2).** No single site precedes
    all three records: the grounding-violation record (`step.py:294`)
    returns at `:310`, before any refine fan-out at `:325`. So
    `_fold_dead_attempts` is called at two mutually exclusive sites:
    immediately before `:294`, and once after the refine loop, before
    `:361`. Every execution passes exactly one of them.
  - The gate-REJECT return (`step.py:318-319`) happens before the fold, as
    the spec states (Known Limits).
- The research `AGENTS.md` Gotchas line "an attempt that raises still loses
  its spend" is rewritten to describe the ledger.

## D-10. Emit-only research usage uses `ctx.emit` (FR-033, FR-034)

**Finding.** `StageContext.emit` (`S/core/context.py:29`) is
`ReportHost._emit` (`S/workflows/report_host.py:38-44`), a pure trace
append that schedules no command and touches neither `_role_usage` nor
attribution.

**Decision.**
- `_fold_research_usage` (signature in D-9) gains the `ctx` it needs and, after pricing, calls
  `ctx.emit(RunEventKind.MODEL_USAGE, stage="research", role="research",
  model=..., calls=str(n), input_tokens=..., output_tokens=...,
  cache_read_tokens=..., cache_write_tokens=..., cost_usd=...)`, with the
  same field names `_track_usage` emits (`report_host.py:90-100`), so
  `_role_rollup` (`S/observability/summary.py:54-73`) needs no change.
- No new host method. No marker for the emission itself: it is not a
  command. The workflows `AGENTS.md` precedent is a harvest that "schedules
  nothing extra" and needs no `workflow.patched`.
- The ledger fold's emission rides D-9's marker, because the fold does.
- The architect's research tool path (`S/workflows/role_host.py:258-267`)
  is untouched. It already emits through `_track_usage`, so nothing is
  counted twice.
- One check for the builder: `_role_rollup` merges per role. A run with an
  architect research tool and a research stage then shows one `research`
  role that sums both. That is intended (both are research spend), and the
  Cost tab notice says so (FR-034).
- **The surface split (FR-034 as amended A-1).** Trace-derived, and so
  gaining research spend: the run summary, the live `run_state` roles and
  `cost_usd_total` (already `_role_rollup(self._trace)`,
  `S/workflows/run_host.py:147-151,174`), the Cost tab total, and benchmark
  cost records. Bag-derived, and unchanged: `_check_budget` and the
  `budget_counted_usd` figures (`run_host.py:117,185`), plus per-activation
  `graph_view` spend (`S/workflows/graph.py:115`). The Cost tab's existing
  "counted toward budget" notice (011 FR-009) describes exactly this split.
  Its text is checked, and updated only if it claims otherwise.
- `merge_usage` has no `calls` parameter, so the event's `calls` field is
  informational, as it is on `_track_usage`'s events today.

## D-11. plan_drift filter, line-neutral in `code/step.py` (FR-050)

**Finding.** `S/stages/code/step.py` is 998 lines, against the
1000-physical-line ceiling (root `AGENTS.md`).

**Decision.**
- `compute_plan_drift(task, files_touched, *, drop_generated: bool =
  False)` goes in `S/stages/plan/models.py`, filtering with `is_generated(path)`.
- The single call site `S/stages/code/step.py:778` becomes:

  ```text
  plan_drift = compute_plan_drift(task, diff.get("files", []), drop_generated=_DRIFT_V2())
  ```

  `_DRIFT_V2` is imported from `plan/models.py` as a zero-argument
  callable wrapping `workflow.patched(PLAN_DRIFT_PATCH)`. That keeps it at
  one line under the 100-character limit. The edit to the existing import
  line (`S/stages/code/step.py:54`) keeps the file line-neutral.
- **Layering (reviewer plan finding 4).** `plan/models.py` is a pure-models
  module imported widely (`B/models.py:23`, `B/record_builder.py:13`,
  `S/calibration/labels.py:15`, board, demo, tidyup), and
  `S/calibration/AGENTS.md` states "labels.py ... pure. No temporalio". So
  `_DRIFT_V2` imports `temporalio.workflow` **lazily inside its body**, and
  the module keeps no top-level temporalio import. A test asserts that
  importing `sdlc.stages.plan.models` does not import `temporalio`, for
  example a `sys.modules` check in a subprocess.
- If the import makes the file exceed 1000 lines, the builder first moves
  an existing helper out of `code/step.py` in a separate commit (stop-guard
  SG-3). It never grows the baseline.
- **The shared ignore list:** `S/artifacts/generated.py` (horizontal) with
  `GENERATED_DIRS` and `is_generated()`. `qa/activities.py:582-585` and
  `B/oracle_id.py:8` import it, unchanged in content, converged as a union.
  The builder checks that the union does not change either existing
  caller's behaviour; if it would, the callers keep their own sets and only
  the drift filter uses the union.
- `PLAN_DRIFT_PATCH = "017-plan-drift-generated"`.

## D-12. Judge readers (FR-040), verify-first

Already safe: `B/workflow.py:181-193` writes NOT_EVALUATED for a scoreless
grade, and `B/judge.py:294-298` returns `score=None`.

Candidate to check: `B/workflow.py:249`, `(t.score or 0.0) >= 1.0` on
oracle-task grades. That is not a judge, but it counts None as FAIL. The
builder establishes when `TaskGrade.score` can be None. If it can for a
grading failure (not a real 0), it records NOT_EVALUATED instead.

FR-060's "judge transient" fixture is the existing S-batch retry tests for
`B/judge.py` (the 429/5xx/timeout loop), cited in tasks.md and re-run, not
duplicated. The new D-12 fixture is a `score=None` / `judge="error"` record
through every reader.

The builder also checks the grid, report, acceptance and rubric readers
(`B/runs.py`, `B/report.py`, `B/acceptance.py:103-108` reads
`partial_credit if not None else 0.0` for graded runs only).

## D-13. Finding first (FR-027)

Order: (1) look for the theatre scratch repo inside the worker container
(`docker exec ... ls /srv/scratch-repos`); (2) the Temporal history of the
two R1 children (`bench-theatre-box-office-1792359046/...`), activity
results of `grade_oracle`; (3) records. If the integration branch
survives, grade it by hand with the oracle in the per-grade environment
(`B/offline_checks.py` tree mode, from 016). Read-only throughout: no
records are written and nothing under `runs/` changes. Output: the
`finding-1of56.md` file in this directory. A harness cause goes to the bug
crew (memory: main bugs via bug crew) and into SC-001 by amendment.
