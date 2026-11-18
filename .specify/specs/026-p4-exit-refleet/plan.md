# Implementation Plan: round 026, P4 exit fixes plus a smaller re-fleet

**Branch**: none (shared tree; spec dir `026-p4-exit-refleet`) | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md) | **Revision**: 2. This revision folds in the advisor consult, which landed after pass 1 went to the reviewer.

**Input**: spec.md (GATE 1 cleared 2026-11-18: Q1-A, Q2-A, Q3-A; amendments A-1 to A-8). Consults: `consults/skeptic.md` (6 findings, all adopted) and `consults/advisor.md` (D1–D7, adopted or merged; it was late, see `consults/README.md`). `S/` = `src/sdlc/`, `T/` = `tests/`.

## Shape

There are two halves in one tasks.md.

**Part A** is SDD code: test-first, reviewer gates, size L. It has five slices:

- A1, run paths and scorer accounting
- A2, SC-1 rule
- A3, per-task lint
- A4, attempt failure reasons, the triage and run 1
- A5, the `.env` rider

**Part B** is operations. It is **paid**, starts only after Part A is merged and verified **and** the $0 re-score of 025 reproduces the baseline (FR-005/050), and sits behind **GATE 2**. Part B changes no code.

**Sizing cut line, if Part A runs over L**: A1, A2, A3 and A5 stay. A4 keeps the record field, the SC-3 rows and the triage table, and defers the run-1 fix.

## Summary

1. **Run paths (A1, advisor D1).**
   - One stage-neutral resolver, `S/runs_paths.py`. Every writer and reader of the records and export roots (8 sites) calls it.
   - `SDLC_RUNS_ROOT` drives both halves, explicit variables still win, and the defaults are unchanged.
   - The scorer prints which roots it read.
   - The cell record classifies runs with no summary: `crashed`, `timed_out`, `terminated` or `summary_missing`. Every such run is an SC-1 miss.
   - The smoke is excluded.
   - A parity test and a source-guard test stop the copies from drifting again.

2. **SC-1 (A2).**
   - The headline is the PRD rule: no *unplanned* gate before merge. Unplanned means not decided by policy, and either outside the static `STAGE_GATES` or SOFT.
   - A steering guard: a planned gate decided by a non-policy decider with anything but `approve` disqualifies the run.
   - `SC-1-strict` and the Clopper-Pearson 95% interval render beside it.

3. **Per-task lint (A3).** There is **no new workflow command**.
   - `run_coding_task` applies safe autofixes to the attempt's changed `*.py` files before the checkpoint commit, excluding fenced files on repair attempts. The fix reaches the task branch, and the C2 anchor includes it.
   - `run_test_suite` runs the tests unchanged, then runs merge's own `scoped_lint` against a sibling base worktree at the task's `branch_point`. `scoped_lint` moves verbatim to `S/toolchain/lint_scope.py`.
   - Introduced findings fail the attempt and become fix-loop feedback, capped at 25 lines. NOT_COLLECTED never fails a task. Lint is kept out of the QA and review LLM prompts.
   - Merge's `lint_clean` is untouched.

4. **Failure reasons, triage and run 1 (A4).**
   - `BenchmarkRecord.failure` records the checks plus the text the dev was shown.
   - New rows `SC-3-non-lint` and `SC-3-lint`.
   - The 025 triage table, 18 rows, built from the on-disk transcripts.
   - Run 1's mode: `research_subquery_reported` adds a catch for `UnexpectedModelBehavior` (CodeMode `run_code` retries exhausted) and degrades to a gap brief with our own text.
   - The child-failure string gains its cause type.

5. **The `.env` rider (A5).** `PYTHON_DOTENV_DISABLED=1` at conftest import, `dotenv_values` for the one paid opt-in test, and a `child_env` helper at the from-scratch spawn sites.

## Technical context

**Language**: Python 3.13. **Dependencies**: none new (python-dotenv 1.2.2, ruff ≥ 0.16.5, pydantic-ai-harness 0.61.0 are already locked). **Storage**: none new; defaulted fields only. **Testing**: the fast tier, plus the replay and golden suites and `scripts/check_golden_rebaseline.py` as the replay proof.

**Ceilings**:

- `S/stages/code/step.py` is at 977 of 1000. The net edit is ≤ +10, with the helpers placed in the new `S/stages/code/attempt_failure.py`. Overflow means the record block moves to `S/stages/code/attempt_record.py` (move only).
- `S/benchmarks/sc_rollup.py` is at 418, budgeted to ≤ 470. Overflow means the renderers move to `S/benchmarks/sc_render.py` (move only).
- `scripts/check_file_size.py` runs in every task that touches either file.

## Constitution check

`.specify/memory/constitution.md` is an unfilled template, so the repository seam rules were checked instead.

| Rule | Status |
|---|---|
| Cross-stage calls banned | OK. The lint scoping moves to `S/toolchain/lint_scope.py`, and merge re-exports it (the reverse import would cycle, `merge/scoping.py:19`). Run paths go to the stage-neutral `S/runs_paths.py` |
| Trust layer unchanged (FR-040) | OK. Not touched: `lint_clean`, `MERGE_REQUIRED_CHECKS`, gate semantics, `auto_decision_for`, the calibration rule and ledger, containment, ADR-6, `GraphWorkflow`. Per-task lint is feedback only, and NOT_COLLECTED never fails a task |
| Replay | No new activity, timer, signal or child. Defaulted fields only. `lint is None` means pass. The `BenchmarkWorkflow` edit changes only an activity-input string (the 021 precedent, `S/workflows/AGENTS.md:126-131`). Proof: T016 and T027 |
| code AGENTS: a checkpoint failure never raises | OK. An autofix failure is logged at WARNING and the checkpoint proceeds |
| qa AGENTS: `tests_passed` is ground truth; the qa slice imports no stage | OK. The lint field sits beside it and is excluded from the QA prompt. qa imports `toolchain`, not merge |
| Read the local AGENTS.md | `workflows`, `stages/{code,qa,merge,review,research}` before editing; named per task |
| RED before implementation | Every code task, except move-only and docs tasks |

## Surfaced for GATE 2

1. **The run-1 fix narrows a documented residual (R1).** Only `UnexpectedModelBehavior` now degrades to a gap brief. It is conditional on T021's evidence.
2. **Per-task lint can lower SC-3 and SC-1**, because lint becomes a loop trigger. Three SC-3 rows make this visible; it is not mitigated.
3. **HARD skips MergeVerdict on clean merges**, and the benchmark override replaces merge's HOLD timeout with REJECT. Both are disclosed and unchanged.
4. **The attendant duty widens.** It services gates and clarification waits, is approve-only on planned gates, runs a 30-minute watchdog and 60-second cost polling, and a `timeout` decision means infra.
5. **n=5 is the floor, not proof.** The CI prints beside SC-1.
6. **The 025 baseline is corrected** to SC-2-all n/a (4 measured), with the smoke excluded.
7. **Named behavior change (A1).** A host exporting `SDLC_RUNS_ROOT` without `SDLC_EXPORT_ROOT` now writes and reads exports under `$SDLC_RUNS_ROOT/pipeline`. Workers are unaffected, because the compose files set neither variable.
8. **One string-only edit in `BenchmarkWorkflow`** (`S/benchmarks/workflow.py:383`): the child-failure text gains its cause type.
9. **Backlog, not fixed:** the calibration ledger never sees benchmark summaries (their nested run_id escapes its one-level glob).

## Step list

- **A1 (FR-001 to FR-005).**
  - `S/runs_paths.py`, with the 8 call sites routed through it.
  - The parity and source-guard tests.
  - `load_evidence` gains `roots`, `no_summary` (cell-record classes) and `excluded_smoke`.
  - `S/benchmarks/workflow.py:383` gets the cause type.
  - Rollup and score: SC-1 n = non-smoke run_ids; no-summary runs are SC-1 misses and SC-2 not-measured; the roots line in markdown, HTML and JSON.
  - `docs/operations/fleet-runs.md`.
  - **T008: the $0 re-score of a 025 copy** is the acceptance test.
- **A2 (FR-006).** `STAGE_GATES`, `_unplanned`, `_steered`, the new `_sc1`, `_sc1_strict` and `_clopper_pearson`, rendered in all three formats.
- **A3 (FR-010 to FR-012).**
  - Move `scoped_lint` and its helpers, plus `LintFinding`/`ScopedLintReport`, to `S/toolchain/lint_scope.py` (move only, merge tests unchanged).
  - `lint_fix_cmd`.
  - Autofix in `run_coding_task`.
  - Lift `prepare_base_worktree`'s body into a destination-taking helper.
  - `QAInput` and `QAReport` lint fields; the scoped lint in `run_test_suite` after the tests.
  - `_lint_ok` and the `task_passed` conjunct; the `_fix_loop_issues` lint block.
  - Exclude lint from the QA, review and adversary prompts.
  - A parity proof against merge, then the replay proof.
  - The offline autofix read.
- **A4 (FR-020 to FR-023).**
  - `AttemptFailure` and `BenchmarkRecord.failure`, from the pure builder.
  - Wire it into the code, QA and review records.
  - The SC-3 rows.
  - The run-1 fix (conditional on T021's evidence).
  - `triage.md`.
- **A5 (FR-030).** The conftest flag, `dotenv_values` in the paid opt-in test, `child_env` at the CLI-spawning from-scratch sites, and the fast tier with `.env` present.
- **A6 (close-out).** The battery with `.env` present, replay, golden rebaseline check, file sizes, docs, an FR-040 diff guard, `verification.md` §026-A, and the fleet commit candidate.
- **B (FR-050 to FR-054).**
  - Pre-flight: the 025 host fixes, containment off, adversary off, attendant scope, cost polling, dedicated checkout, fresh scratch seeding.
  - Freeze.
  - Smoke `--gate-policy hard`.
  - Ceiling re-announce.
  - Runs 1 to 5: cat-cafe, readtime, then geotext and lice overlapping, then cat-cafe repeat.
  - Run-6 decision.
  - Score and fleet report with deltas, the CI and three SC-3 rows.
  - The P4 read.
  - Card closes, including the calibration-glob backlog card.

## Dispositions

| Finding | Disposition |
|---|---|
| Skeptic 1: baseline counted the smoke | **Adopted** (A-1). The planner had found this independently |
| Skeptic 2: carve-out gameable | **Adopted**: allowlist, SOFT-human means unplanned, steering guard, strict companion (A-2) |
| Skeptic 3: HARD skips MergeVerdict; HOLD overwritten; clarify waits | **Adopted** as disclosure plus attendant protocol (A-3) |
| Skeptic 4: lint trades SC-3/SC-1; autofix versus freeze | **Adopted**: three SC-3 rows; autofix before the checkpoint, fence-excluded (A-4) |
| Skeptic 5: n=5 power; cost polling | **Adopted**: CI; 60-second polling; run-6 headroom of at least $1.73 (A-5) |
| Skeptic 6: transcripts on disk | **Adopted** (A-6) |
| Advisor D1: one resolver for all sites, parity and source guards | **Adopted** over the planner's scorer-only resolver. The named behavior change is GATE 2 item 7 |
| Advisor D1 side finding: ledger blind to benchmark summaries | **Adopted as a backlog card** (T052); FR-040 forbids the fix |
| Advisor D2: cell record authority, `summary_missing`, cause type | **Adopted.** The cause-type edit is GATE 2 item 8 |
| Advisor D3: static planned set, `!= policy`, unknown means unplanned | **Merged** with skeptic 2: the advisor's predicate plus the planner and skeptic's SOFT clause and steering guard |
| Advisor D4: autofix inside `run_test_suite` with a workflow-side anchor advance | **Placement not adopted.** Autofix before the checkpoint inside `run_coding_task` puts the fix in the commit and the anchor with no workflow logic. **Adopted from D4:** the merge type `ScopedLintReport` on `QAReport`, the sibling base worktree, `--force-exclude` and `*.py`-only files, renames, NOT_COLLECTED never fails, fenced findings report-only, a 25-line cap, lint kept out of the LLM prompts, `scripts/check_golden_rebaseline.py` |
| Advisor D5: the failure field and where it is computed | **Adopted** (checks order, summary equals the dev's feedback, never `error`) |
| Advisor D6: catch `UnexpectedModelBehavior` only | **Adopted** over the planner's bare-`Exception` draft |
| Advisor D7: flag at import, `dotenv_values`, `child_env` | **Adopted** |

## Traceability

| Requirement | Step / tasks | Validation |
|---|---|---|
| FR-001 run paths | A1 / T001–T002 | `T/test_runs_paths.py` (parity plus source guard) |
| FR-002/003/004 no-summary, denominator, smoke | A1 / T003–T006 | `T/test_benchmark_evidence_roots.py`, `T/test_benchmark_sc_rollup.py` |
| FR-005 $0 re-score | A1 / T008 | quickstart re-score, in verification.md |
| FR-006 SC-1 | A2 / T009–T010 | `T/test_benchmark_sc_rollup.py -k sc1` |
| FR-010/011/012 per-task lint | A3 / T011–T018 | `T/test_lint_scope.py`, `T/code/test_autofix_checkpoint.py`, `T/qa/test_task_lint.py`, `T/code/test_task_lint_loop.py`, `T/merge/` unchanged, replay |
| FR-020/021/022/023 | A4 / T019–T024 | `T/test_attempt_failure.py`, `T/test_architect_research_degrade.py`, `triage.md` |
| FR-030 | A5 / T025–T026 | `T/test_dotenv_isolation.py`; fast tier with `.env` present |
| FR-040 | all / T016, T027 | replay, golden check, the T027 diff guard |
| FR-050 to FR-054 | B / T040–T052 | preflight.md, announcements, fleet report |
| SC-A1 to SC-A4 | T008, T027 | verification.md §026-A |
| SC-B1 to SC-B4 | T050–T051 | fleet report, verification.md §026-B |
