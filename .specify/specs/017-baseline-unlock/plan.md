# Implementation Plan: Baseline Unlock (round 017, pre-AP0)

**Branch**: orchestrator's call (spec dir `017-baseline-unlock`) | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md) | **Base**: main `e435bd10`

**Status**: GATE 2 approved (user via orchestrator, 2026-10-25): the plan
with the reviewer's fixes and amendment A-1.

**Input**: [spec.md](spec.md). GATE 1 was cleared on 2026-10-25: the spec
was approved as written and the "Calls Made in Design" list was not
contested. Scope: user stories 1 to 6, FR-001 to FR-061, SC-001 to SC-005.

**Design artifacts**:
- [research.md](research.md): decisions D-1 to D-13, each checked in the
  tree;
- [data-model.md](data-model.md): every new field, with its default;
- [contracts/records-and-wire.md](contracts/records-and-wire.md): the
  prompt, enforcement, records, verdict, research spend and replay markers;
- [quickstart.md](quickstart.md): how to validate.

All four bind the tasks the same way the spec does.

**Review**: reviewer `.workspace/tmp/reviewer-017-plan-1.md`, verdict
APPROVE WITH FIXES (3 material, 2 minor), all folded in. Every load-bearing
citation was verified in the tree, and the SDK replay question was settled
in the installed sdk-core.
- **Finding 1:** the live `run_state` roles are trace-derived. This became
  spec amendment A-1 (FR-034), listed for GATE 2.
- **Finding 2:** no `BenchmarkWorkflow` replay coverage existed, so step 0
  now records one history (D-6).
- **Finding 3:** the SC-003 recompute uses non-offline accept on throwaway
  copies and compares verdict fields only (quickstart §3).
- **Finding 4:** `_DRIFT_V2` imports temporalio lazily (D-11).
- **Finding 5:** file counts, the activity definition site and the
  `_fold_research_usage` signature were reconciled, and the judge-transient
  fixture is cited (D-12).

`S/` = `src/sdlc/`, `B/` = `src/sdlc/benchmarks/`.

## Summary

The round repairs five harness defects so the first baseline run's records
can be trusted.
- **A. Analyze.** The analyst gets the run's changed files, a static test
  inventory and per-task change counts, and can cite four validated
  evidence forms. The workflow enforces them in one pure function and hands
  the same untraced list to the merge gate (D-1).
- **B. Stage reach.** A `stage_reach` facts block is built from records the
  parent already reads. The verdict gains a "stalled" outcome, and the
  oracle names a tree that fails collection. FR-027 comes first: the 1/56
  cause is established before B's verdict and oracle parts are built.
- **C. Research spend.** Dead research attempts land in an append-only
  ledger. It is folded once into the stage spend, and research usage
  reaches the trace through `ctx.emit` (D-10) without touching the budget
  gate.
- **D. Judge readers.** Readers are verified, and only a reader that turns
  `None` into 0 is fixed.
- **E. plan_drift.** It ignores generated artifacts, behind a marker, with
  a line-neutral edit to the 998-line `code/step.py` (D-11).

Three replay markers carry every workflow-side change. No pre-017 record,
history or verdict changes.

## The six rules every task is checked against

1. **Baseline records are read-only.** Nothing under `runs/` is modified,
   moved or deleted. Step 0 writes `baseline-records.sha256` (names and
   hashes of `runs/benchmarks`), which is re-checked before the closing
   commit.
2. **Additive only.** Every new field is optional with the default in
   data-model.md. Every pre-017 record and `acceptance.yaml` loads and
   reads as before (SC-003, SC-004).
3. **Replay-safe by construction.**
   - Any change to a workflow-side command sequence sits behind its named
     marker (contract C-6).
   - `tests/replay/` histories are never re-recorded.
   - The replay gate `-m temporal` is run at step 0 and at the end.
4. **No paid run is implicit.** No code task starts a pipeline run or a
   model call. FR-027's optional R1 rerun and the US6 pre-flight each stop
   for the orchestrator's clearance.
5. **Main-branch defects go to the bug crew** (user ruling 2026-10-17). If
   FR-027 or any task finds a defect on main outside this round's items,
   the task stops and reports. It does not fix it in place.
6. **Names come from data-model.md.** A needed name that the data model
   does not define stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, Temporal Python SDK,
pydantic-ai at the existing analyst role only). Stdlib `ast` for the test
inventory.

**Primary Dependencies**: existing only. No change to `pyproject.toml` or
`uv.lock`.

**Storage**:
- records under `runs/benchmarks/` (unchanged layout);
- the research ledger at
  `$SDLC_RUNS_ROOT/<run_id>/research/dead-attempts.jsonl`, beside the
  existing budget counters;
- no new store.

**Testing**: all in `kroker-dev` (quickstart §1-3).
- `uv run pytest` (fast tier) and the slice suites `tests/analyze/`,
  `tests/research/`, `tests/plan/`, `tests/code/` and `tests/merge/`, plus
  the benchmark tests.
- `-m temporal tests/replay` and `-m temporal
  tests/test_benchmark_workflow_sequence.py` at step 0 and at the end.
- `ruff check`, `ruff format --check`, `mypy`.
- Host: `python scripts/check_file_size.py`, `python
  scripts/check_clauses.py`.

**Target Platform**: the Temporal worker (compose `worker` image) and the
CLI through the container.

**Performance Goals**: the inventory activity finishes in under 30 s on an
18-task tree (`git` name-only diffs plus an `ast` parse of the test files).
The analyst prompt grows by at most 150,000 characters (D-3).

**Constraints**:
- **File ceiling:** 1000 physical lines. `S/stages/code/step.py` is at 998,
  so its one edit is line-neutral (D-11). `S/stages/merge/step.py` is at 680
  and grows by about 8. Other touched files have room (step 0 records the
  counts).
- **Cross-stage calls banned.** The inventory activity uses `vcs` helpers
  (horizontal). The shared artifact-ignore list goes in `S/artifacts/`
  (horizontal), not in a stage.
- **Artifact boundary.** `analyze.md`, `merge.md`, the research and analyze
  `AGENTS.md` files, `agents/analyst/instructions.md` and `BENCHMARK.md`
  change in the same diff as the behaviour they describe.
- **Merge slice replay rule.** No marker is added to merge. Its change is
  record arguments only.

**Scale/Scope**:
- about 17 modified source files and 1 new one (`S/artifacts/generated.py`).
  `S/stages/analyze/activities.py` already exists as a stub
  (`ACTIVITIES: list[Any] = []`) and gains its first activity;
- about 6 new test files and about 8 modified;
- 4 stage documents, 1 role instruction file, `BENCHMARK.md`.
- No pipeline run in the code half. One paid pre-flight run closes the
  round.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no
constitution gate applies (016 precedent). The binding rules are the root
`AGENTS.md` and the slice `AGENTS.md` files of analyze, research, merge,
plan and code, plus `S/workflows/AGENTS.md`.

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. The analyze activity calls `vcs` (horizontal). The orchestrators still coordinate analyze → merge, and merge receives `untraced` as today, only computed in analyze (D-1). The ignore list moves to `S/artifacts/generated.py`. `qa` and `B/oracle_id.py` import a horizontal module, not each other. |
| Producer owns its artifacts | Holds. Evidence, `AnalyzeOutcome`, `TraceInventory` and `enforce_traces` are in `stages/analyze/models.py`. `StageReach` and `TraceBag` are in `B/models.py`. `TaskResult.start_ref` is in `workflows/models.py` (its producer, `_dev_task`). `core/` is untouched. |
| Behaviour and clauses change in one diff | Planned per step (see Steps): `analyze.md` with A, `merge.md` (untraced wording: "without traced evidence") with A, research `AGENTS.md` Gotchas with C, analyze `AGENTS.md` (`ACTIVITIES`) with A, `BENCHMARK.md` record section with B. `check_clauses.py` is green after each step. |
| 1000-line ceiling | `code/step.py` 998 → ≤ 998 (D-11, stop-guard SG-3). `merge/step.py` 680 → about 690. `analyze/step.py` 196 → about 260. `research/step.py` 406 → about 440. `research/stage.py` 473 → about 485. `B/acceptance.py` 221 → about 260. `B/models.py` 545 → about 600. `B/runs.py` 563 → about 575. `B/cell.py` 144 → about 200. `B/oracle.py` 395 → about 410. |
| Workflow determinism, replay safety | Three markers (contract C-6), each taken before its first new command. `ctx.emit` is pure (D-10). The parent workflow adds no command (D-6). Replay suite at step 0 and at the end. |
| FeatureWorkflow grace edits | `feature.py:542` reads `outcome.untraced`, with no command added. The analyze change is under its marker, which is the grace rule's own mechanism. |
| Merge "no `workflow.patched`" rule | Respected. Merge gets record fields only, and the untraced list arrives as an argument as before. |
| `AGENTS.md` files | Edited only where the slice's stated facts change (analyze `ACTIVITIES`, research activities and Gotchas), in the same diff. |

No violation, so Complexity Tracking is empty. The only near-violation is
the line ceiling on `code/step.py`, handled by D-11 and SG-3.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/017-baseline-unlock/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/records-and-wire.md
├── tasks.md                     (next: /speckit-tasks)
└── written during execution: baseline.md, baseline-records.sha256,
    finding-1of56.md (FR-027), verification.md
```

### Source Code (after the feature)

```text
src/sdlc/
├── stages/analyze/
│   ├── models.py        M  Evidence, CriterionTrace.key/.evidence, AnalyzeOutcome,
│   │                       TraceInventory, KeyedCriterion, TraceEnforcement,
│   │                       CriterionAudit, enforce_traces, criterion_keys
│   ├── activities.py    M  build_trace_inventory (first activity); ACTIVITIES
│   ├── prompts.py       M  analyst_prompt_v2 (contract C-1)
│   ├── step.py          M  marker 017-analyze-evidence; returns AnalyzeOutcome; trace on record
│   ├── analyze.md       M  clauses for evidence forms, inventories, inexpressible criteria
│   └── AGENTS.md        M  ACTIVITIES, enforcement line
├── stages/merge/step.py M  blocking_checks at the four record sites
├── stages/merge/merge.md M untraced check wording
├── stages/plan/
│   ├── models.py        M  compute_plan_drift(drop_generated=), PLAN_DRIFT_PATCH,
│   │                       _DRIFT_V2 (temporalio imported lazily inside it; D-11)
│   └── step.py          M  tasks_total on the plan record
├── stages/code/step.py  M  one line at :778 (line-neutral)
├── stages/qa/activities.py  M  import the shared ignore list (582-585)
├── stages/research/
│   ├── budget_store.py  M  append_dead_attempt, read_dead_attempts
│   ├── stage.py         M  BaseException wrapper; read_dead_attempt_usage activity (defined here)
│   ├── step.py          M  marker 017-research-ledger; ledger fold; ctx.emit MODEL_USAGE;
│   │                       _fold_research_usage(ctx, cfg, usage, into, *, calls=1)
│   ├── activities.py    M  ACTIVITIES += read_dead_attempt_usage (assembled here)
│   └── AGENTS.md        M  activities list, Gotchas (raising attempts now ledgered)
├── artifacts/generated.py   N  GENERATED_DIRS, is_generated
├── workflows/
│   ├── models.py        M  TaskResult.start_ref
│   ├── task_host.py     M  stamp start_ref on the returned TaskResult
│   ├── feature.py       M  :531-542 read outcome.untraced
│   └── graph_nodes/postplan.py  M  :78-95 read outcome.untraced
└── benchmarks/
    ├── models.py        M  TraceBag, StageReach, BenchmarkRecord.trace/.tasks_total/
    │                       .blocking_checks/.stage_reach, final_stage_for, stage_reach_from
    ├── record_builder.py M stage_record(trace=, tasks_total=, blocking_checks=)
    ├── cell.py          M  summarize_cell(final_stage=) -> CellProgress.stage_reach
    ├── workflow.py      M  pass final_stage; stage_reach onto cell and oracle records;
    │                       FR-025 components/detail; D-12 fix only if confirmed
    ├── oracle.py        M  OracleGrade.exit_code/.errors; keep _bounded_shell's code
    ├── oracle_id.py     M  import the shared ignore list
    ├── runs.py          M  Run.stage_reach
    └── acceptance.py    M  STALL_EPSILON, Reason.STALLED, ArmEvidence.stall_points, stalled branch
agents/analyst/instructions.md   M  evidence forms, keys, command never satisfies
BENCHMARK.md                     M  record fields (trace, stage_reach, blocking_checks), stalled verdict
tests/
├── analyze/test_trace_enforcement.py         N  pure table over C-2
├── analyze/test_trace_inventory.py           N  activity on a tmp git repo (incl. >60k, inherited)
├── analyze/test_analyze_patched.py           N  patched vs unpatched step paths
├── research/test_research_dead_attempts.py   N  ledger, wrapper, fold, emission, budget sum
├── test_benchmark_stage_reach.py             N  stage_reach_from + summarize_cell
├── test_benchmark_acceptance_stalled.py      N  stalled branch + SC-003 recompute
└── modified: analyze slice contract, merge record tests, plan record tests,
    plan_drift tests, oracle tests, research slice contract, cell tests
```

**Structure Decision**: a single project. Every change sits in the slice
or horizontal package that owns it (Constitution Check).

## Steps (the order tasks.md will follow)

Each step ends green on its slice suite plus the fast tier, with its
documents in the same diff.

0. **Baseline.** Run quickstart §1 and record it in `baseline.md`: fast-tier
   counts, the replay suite, the sequence test, the file sizes of every
   touched file, and the records manifest. Also record the
   `BenchmarkWorkflow` replay history on the pre-change code, with its
   replay test (research D-6). It must replay green before step 1.
1. **FR-027, finding first** (D-13). This is read-only investigation, and it
   writes `finding-1of56.md`.
   - **Stop:** if the cause is a harness defect, report it to the
     orchestrator for the bug crew and a spec amendment. If it amends the
     FR-025 signal, update research D-8 before step 6.
   - An R1 rerun needs clearance (rule 4).
2. **Item E** (smallest; proves the marker pattern). `S/artifacts/generated.py`,
   `compute_plan_drift(drop_generated=)`, the line-neutral `code/step.py`
   edit, the qa and oracle_id imports, and tests with the patched and
   unpatched paths pinned.
3. **Item A, pure part.** The evidence models, keys, `enforce_traces` and its
   table test (contract C-2). No workflow change yet.
4. **Item A, workflow part.** `build_trace_inventory`, `TaskResult.start_ref`
   stamping, prompt v2, the marker in `analyze.step`, `AnalyzeOutcome` at both
   call sites, `trace` on the record, `merge.md` wording, `analyze.md`, the
   analyze `AGENTS.md`, the analyst instructions, and replay plus
   sequence tests.
5. **Item C.** The ledger in `budget_store`, the wrapper in `stage.py`, the
   `read_dead_attempt_usage` activity, the marker and fold in `step.py`,
   `ctx.emit` emission, the `_fold_research_usage(calls=)` signature, the
   research `AGENTS.md`, and a test asserting the `_check_budget` sum and the
   attribution invariant are unchanged (SC-005).
6. **Item B** (after step 1). `tasks_total` on the plan record,
   `blocking_checks` on merge records, `StageReach` and `stage_reach_from`,
   `summarize_cell(final_stage=)`, records, `Run.stage_reach`, the stalled
   verdict, FR-025, the `BENCHMARK.md` section, and the SC-003 recompute
   test.
7. **Item D.** Reader verification (D-12), plus a fix only where a reader
   counts None as 0.
8. **Verification.** Quickstart §3: the whole-round checks, SC-003, SC-004
   and the records manifest. Written to `verification.md`.
9. **Pre-flight** (paid). **Stop for clearance.** Quickstart §4. The closing
   commit records the outcome against SC-001.

## Stop-guards

- **SG-1:** a replay test fails → stop. Never re-record a history.
- **SG-2:** any stored record or `acceptance.yaml` would read differently →
  stop (rule 2).
- **SG-3:** `code/step.py` would exceed 998 lines → stop. Move an existing
  helper out in its own commit first, with the orchestrator's agreement.
- **SG-4:** the records manifest changes → stop.
- **SG-5:** FR-027 finds a harness cause → stop and route to the bug crew
  (rule 5).
- **SG-6:** the converged ignore list would change qa's or the oracle id's
  behaviour → keep their own sets (D-11 fallback) and note it.

## Runbook (pre-flight only)

Follow memory "benchmark launch runbook" and "benchmark runs use compose
worker on 7233":
1. Rebuild the worker image on the merged main with `--build-arg
   KROKER_COMMIT`.
2. Run against the live temporal, using a per-case scratch repo
   (todo-api-greenfield at `D:\srv\scratch-repos`) and `--gate-policy off`.
3. Never run it in parallel with a live pipeline run.
4. A lost run exits rc=0, so grep the report.

## Complexity Tracking

No violation.
