# Implementation Plan: Benchmark Record Trustworthiness (round 012, Phase 1)

**Branch**: orchestrator's call (spec dir `012-benchmark-record-trust`) | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md) | **Base**: main `7f5191d0`

**Input**: [spec.md](spec.md), GATE 1 cleared 2026-10-06 with rulings R1 (cell label = arm name), R2 (analyze/merge decided per gate after diagnosis), R3 (existing records untouched, marked pre-012). Scope: all seven user stories; FR-001 to FR-030; SC-001 to SC-009. Source of the findings: `docs/reports/2026-10-06-benchmark-improvement-plan.md` §1 and §4 Phase 1 (read-only; never edited, staged or committed).

**Consults**: advisor `.workspace/tmp/012-advisor-answer.md`, skeptic `.workspace/tmp/012-skeptic-answer.md`. Folded into [research.md](research.md) (consult log at its end).

**Review**: reviewer `.workspace/tmp/reviewer-012-plan-1.md` — VERDICT: fixes-needed, 1 blocking, 8 non-blocking. All folded in: `scripts/aggregate_benchmarks.py` is a reader of the record files outside the benchmark package and joins the reader work with its own contract section and test (blocking 1); the path verify is scoped to case locations; intake and retro leave the stage lists (they write no record); two, not three, merge returns lack a record; the non-retryable mechanism is named; the replay row says what is true; drift records are not pre-012; one growth figure for `code/step.py`; rule 2 names the trace fields that change in ordinary runs. Re-review `.workspace/tmp/reviewer-012-plan-2.md` — VERDICT: approve; all nine resolved; three new nits fixed (quickstart names the new script test; one `check_case_assets` signature; the script's "neither" rule pinned on both of its outcome paths). Tasks review `.workspace/tmp/reviewer-012-tasks-1.md` — VERDICT: fixes-needed, 1 blocking, 4 non-blocking; all folded in: the gate diagnosis names evidence that exists (re-running the merge checks on the stored integration branches; no pipeline export exists for benchmark children) (blocking 1); the read-only rule for `runs/` uses a fingerprint, since `runs/` is git-ignored; T007 states how contract §2.8 reads; the parent's sequence test names its harness and cannot drop the provenance case silently; the quickstart's run command takes the case file path. Re-review `.workspace/tmp/reviewer-012-tasks-2.md` — VERDICT: approve, nothing open.

`B/` = `src/sdlc/benchmarks/`. `S/` = `src/sdlc/stages/`.

## Summary

The benchmark harness writes records that cannot be trusted. This round makes each field of a record mean what it says, and nothing else.

- **Case files**: one function decides where cases live; a registered rubric or veto that is missing stops the run before it costs anything; the plan stage shows its trust value.
- **Cell status**: a new per-cell record says whether the cell completed, how far it got, and whether it was graded. A cell whose code stage did not finish is not graded. The oracle no longer runs for it.
- **Oracle**: each grade builds and destroys its own environment; an empty change scores zero without running a test.
- **Provenance**: every record carries the Kroker commit, a dirty flag and a real prompt hash.
- **Label**: every record of a cell carries the arm name and the cell id, and lands in one file.
- **Attempt records**: code, qa and review each report their own time and verdict; review reports its tokens.
- **Gates**: the reason analyze and merge reject every benchmark run is diagnosed from stored evidence, then each gate is repaired or recorded as not evaluated under a stated rule.
- **Old records**: untouched, still loadable, never averaged together with new ones.

Decisions R-1 to R-13 are in [research.md](research.md). Every name is in [data-model.md](data-model.md). Behaviour and the requirement-to-proof table are in [contracts/records-and-harness.md](contracts/records-and-harness.md). Validation is in [quickstart.md](quickstart.md).

## The four rules every task is checked against

1. **Stored records are read-only.** Nothing under `runs/` is modified, moved or deleted. `runs/` is git-ignored, so the check is a fingerprint of the stored record files taken at the baseline and compared before every commit (tasks.md standing rules); `git ls-files runs/` stays empty. Tests that need old records read them in place or copy them to a temp directory.
2. **Non-benchmark behaviour does not change.** With `cfg.benchmark.case_id is None`, no new activity runs and every stage returns what it returned at base. Proof: the stage test suites and `-m temporal tests/replay` match the baseline. Two trace fields do change in ordinary runs, on purpose (research R-9): the stage-ended event of code, qa and review carries the corrected `duration_s`, and the review event gains `cost_usd` when the reviewer's spend is priced. A test that asserts those fields is updated with that reason stated; it is not an SG-1 stop.
3. **No reader guesses.** A field that is absent reads as "not recorded", never as zero, pass or fail. `None` and `not_evaluated` are counted by no aggregate.
4. **Names come from data-model.md.** Its §5 check is in the first task. A name not in it stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, Temporal Python SDK, argparse).

**Primary Dependencies**: existing only. No new dependency in `pyproject.toml`. Two case directories gain an `oracle/requirements.txt` (test dependencies of the held-out suite, installed into the per-grade environment).

**Storage**: JSON-lines record files under `runs/benchmarks/<bench_run_id>/`. Additive optional fields; one file per cell for new runs; old files untouched.

**Testing**: in the `kroker-dev` container: `uv run pytest` (fast tier), named files per task, `-m slow tests/test_grade_oracle.py` for the real per-grade environment, `-m temporal tests/replay` once at baseline and once at the end. `ruff check .`, `ruff format --check .`, `mypy`. Host: `python scripts/check_file_size.py`, `python scripts/check_clauses.py` (always exits 0; read it).

**Target Platform**: Temporal worker in a Linux container; CLI. Developer host is Windows.

**Project Type**: single Python project; benchmark package plus five stage slices.

**Performance Goals**: none. A grade gains one environment build (tens of seconds to a few minutes). The oracle activity has a 20-minute single attempt today; the first oracle task measures the build on the two oracle cases and, if the build plus the suite can pass 15 minutes, raises the activity timeout in the same task.

**Constraints**: stored records read-only (R3); no benchmark run except the one validation smoke run; 1000-line ceiling with `S/code/step.py` at 991 (budget: at most 997, research R-9); cross-stage call ban; producer owns its artifacts; behaviour and its clauses change in the same diff; workflow code stays deterministic (new I/O only in activities; the benchmark parent's new activity calls sit behind `workflow.patched`); `core/` envelopes keep pydantic's default `extra`; no file under `tests/replay/` is edited.

**Scale/Scope**: 3 new source modules, about 17 modified source files and one script, 7 new test files, about 14 modified test files, 2 or more new corpus files, 8 documents, 3 files written into the spec directory during execution. No new file is expected to pass 250 lines.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md` and the nearest `AGENTS.md` of each slice edited (`S/code/`, `S/review/`, `S/qa/`, `S/analyze/`, `S/merge/`, `src/sdlc/core/`, `src/sdlc/workflows/`; the benchmark package has none). The executor reads each before editing that slice. Checked after design:

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. No stage calls another stage. `B/oracle.py` imports `_ensure_python_env` from the qa slice's activities, as the merge slice already does; `B/` is a horizontal package, not a stage. |
| Producer owns its artifacts; `core/` holds configuration and envelopes only | Holds. Record models stay in `B/models.py`. `core/models.py` gains four optional fields on `BenchmarkConfig`, which it already owns. |
| Whoever changes behaviour updates its clauses in the same diff | Planned per task: `code.md`, `review.md`, `merge.md`, `analyze.md`, `BENCHMARK.md` (document table below). |
| 1000-line ceiling | Holds. `S/code/step.py` 991 → at most 997; stop-guard SG-3 at 1000. `scripts/aggregate_benchmarks.py` 625 (+ about 25). `S/merge/step.py` 630, `B/workflow.py` 334 (+ about 60), `B/oracle.py` 279 (+ about 60), `B/models.py` 282 (+ about 70). |
| Workflow determinism / sandbox marking | New modules imported by workflow code (`B/cell.py`, `B/provenance.py`, `B/paths.py`) are imported inside the existing `imports_passed_through` blocks of `B/workflow.py` and `workflows/benchmark_host.py`. No file or git access in workflow code. |
| Replay safety | Outside a benchmark run no command sequence changes: the recorder schedules its activity only in benchmark mode. Inside a benchmark run two things add commands: `BenchmarkWorkflow` gains activity calls behind `workflow.patched("012-cell-record")`, and step 8 adds a `record_benchmark` activity before two merge rejections (and possibly more per `gate-diagnosis.md`). Those stage-step additions are not patch-guarded, so a benchmark child in flight across the deploy of this change would not replay. None is in flight (the report forbids runs until this round lands) and no replay history includes a benchmark run (verified: `tests/replay/` has none). The replay suite is run after steps 5, 7 and 8 all the same. |
| `AGENTS.md` files | Not edited by the executor. Two lines are listed for the orchestrator under "Items for GATE 2". |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/012-benchmark-record-trust/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   records-and-harness.md
├── checklists/  requirements.md (+ plan.md, tasks.md from the reviewer)
├── tasks.md     (/speckit-tasks)
└── written during execution:
    baseline.md, f3-reproduction.md, gate-diagnosis.md, verification.md
```

### Source Code (after the feature)

```text
src/sdlc/
├── benchmarks/
│   ├── paths.py                N  cases_dir, calibration_dir, check_case_assets, MISSING_CASE_ASSET
│   ├── provenance.py           N  resolve_provenance (activity), prompt_sha_for, PROMPTED_ROLES
│   ├── cell.py                 N  summarize_cell (activity), cell_record, grading_status
│   ├── models.py               M  record fields, CellStatus, CELL scope, NOT_EVALUATED, summary fields, cell_key/arm_label/is_pre012, stage order
│   ├── record_builder.py       M  prompt_sha, kroker_commit, tree_dirty, arm, cell_id from cfg
│   ├── recorder.py             M  _cell_id_for prefers record.cell_id
│   ├── judge.py                M  load_case_assets raises; _CASES_DIR removed
│   ├── oracle.py               M  per-grade environment, empty-diff guard, changed_files; uses paths
│   ├── tasks.py                M  uses paths
│   ├── calibration.py          M  STAGE_TO_RUBRIC + plan; uses paths
│   ├── cli.py                  M  pre-flight before start; uses paths (three sites)
│   ├── workflow.py             M  provenance once; cfg carries arm/cell/provenance; summarize → grade or not → cell record
│   ├── scoring.py              M  exclude cell records; group by cell_key and pre012
│   ├── report.py               M  uses paths; Cells section; pre-012 section
│   ├── heatmap.py, sc_rollup.py                          M  ignore cell records; pre-012 line
│   └── task_matrix.py, error_matrix.py, waste_matrix.py,
│       agreement_matrix.py, experiments.py               M  cell_key / arm_label; pre-012 line
├── core/models.py              M  BenchmarkConfig + arm, cell_id, kroker_commit, tree_dirty
├── worker.py (or wherever activities are registered)     M  register resolve_provenance, summarize_cell
└── stages/
    ├── code/step.py            M  _code_ended, _qa_ended; qa outcome; record endpoints
    ├── code/code.md            M  clause on the three attempt records
    ├── review/step.py          M  reviewer spend into the record
    ├── review/review.md        M  clause: review record time and tokens
    ├── analyze/step.py, analyze.md   M  error text on a failing record; per gate-diagnosis.md
    └── merge/step.py, merge.md       M  record before every rejected return, error text; per gate-diagnosis.md

Dockerfile                      M  ARG/ENV KROKER_COMMIT
scripts/aggregate_benchmarks.py M  raw-JSON reader for the docs build: skip cell records, not_evaluated is neither, arm label, pre-012 line
benchmarks/cases/
├── cat-cafe-monitoring/oracle/requirements.txt   N
└── todo-api-greenfield/oracle/requirements.txt   N   (deveval-*: only if their oracle needs more than pytest)

tests/
├── test_benchmark_paths.py            N
├── test_benchmark_provenance.py       N
├── test_benchmark_cell.py             N
├── test_benchmark_record_builder.py   N
├── test_benchmark_legacy_records.py   N  loads every stored record file in place, read-only
├── test_aggregate_benchmarks.py       N  the script on a temp runs directory
├── test_benchmark_workflow_sequence.py N  temporal tier: the parent's per-cell sequence with stub activities and a stub child
├── test_benchmark_judge.py, test_benchmark_cli.py, test_benchmark_recorder.py,
│   test_benchmark_models.py, test_benchmark_scoring.py, test_benchmark_report.py,
│   test_benchmark_workflow.py, test_grade_oracle.py, test_calibration_render.py   M
├── test_benchmark_heatmap.py, test_task_matrix.py, test_error_matrix.py,
│   test_benchmark_waste_matrix.py, test_benchmark_agreement_matrix.py,
│   test_benchmark_experiments.py, test_benchmark_sc_rollup.py                     M  gain cases
└── code/, review/, analyze/, merge/                                               M  gain cases

BENCHMARK.md, README.md, ROADMAP.md   M
```

**Not touched**: anything under `runs/`; `docs/reports/`; `tests/replay/` (histories, golden traces, fixtures); `workflows/graph.py`, `workflows/feature.py`, `workflows/role_host.py`; `agents/`; `interfaces/`; every `AGENTS.md`; `S/qa/` source (its activities are imported, not changed); `B/drift.py`; the repository-root derivations in `B/score.py` and `B/experiments.py`; every script except `scripts/aggregate_benchmarks.py`.

## Design in brief

1. **Paths** (R-1, R-2, R-3; contract §1). `paths.py` first, because the judge, the report, the oracle and the CLI all move onto it.
2. **Record fields and helpers** (R-7, R-8; contract §2). Models, then the builder, then the recorder's file key. Provenance and labels ride `BenchmarkConfig`.
3. **Readers** (R-11; contract §7). Summaries partition by kind and cell; matrices use the helpers; the report gains two sections.
4. **Cell status** (R-4, R-5; contract §3). `summarize_cell`, the status table, the workflow sequence: child → summarize → grade only if code finished → cell record.
5. **Oracle environment** (R-6; contract §4). Reproduction note first, then the guard, then the environment behind a seam.
6. **Attempt records** (R-9; contract §5). Two timestamps in the code step; spend in the review step.
7. **Gates** (R-10; contract §6). Diagnosis from stored traces, a report to the orchestrator, then the repair.
8. **Documents**, then the smoke run.

## Work order

Tasks come from `/speckit-tasks`; this is the order and why. Each test lands with the code that satisfies it, test written first, no red commits. Each step ends with its named checks green.

| Step | What | Why here |
|---|---|---|
| 0 | Baseline in the container (fast tier counts, `-m temporal tests/replay` result, ruff, mypy count) and on the host (file size, clauses). Container binding check. Data-model §5 name check. Research "Verify" items for R-4 (stage sets on stored runs; analyze after a quarantined task), R-5 (consumers of the stage-ended outcome string), R-7 (roles record writers pass; which have registry prompts), R-9 (`_now`, qa record when the lens is off). Record all of it in `baseline.md`. | A known start, and every assumption the design rests on is checked before code depends on it. |
| 1 | `B/paths.py` + `test_benchmark_paths.py`; move every derivation onto it; `load_case_assets` raises; CLI pre-flight; `STAGE_TO_RUBRIC` + key-set pins; corpus test. | US1. Smallest change that makes rubric scores possible; nothing else depends on later steps. |
| 2 | Models: record fields, `CellStatus`, the two enum values, summary fields, helpers, stage order. `BenchmarkConfig` fields. `test_benchmark_models.py`, `test_benchmark_legacy_records.py`. | Everything after this needs the names. The legacy-load test proves R3 from the first commit that changes the model. |
| 3 | `B/provenance.py` + tests; `record_builder` fills the new fields + `test_benchmark_record_builder.py`; `recorder._cell_id_for` + test; `Dockerfile` argument. | US4 and US5 writer side. |
| 4 | First a grep for any reader of `runs/benchmarks` or of record JSON outside `B/` (`scripts/`, `src/sdlc/eval/`, `src/sdlc/dashboard/`, `src/sdlc/observability/`, `interfaces/`); a hit this plan does not name is reported before the step continues. Then readers: `scoring`, `report`, heatmap, rollup, five matrices + their tests; `scripts/aggregate_benchmarks.py` + `test_aggregate_benchmarks.py`. | US5 reader side and R3. Done before the workflow starts writing cell records, so a cell record never reaches an unprepared reader. |
| 5 | `B/cell.py` + `test_benchmark_cell.py`; `B/workflow.py` sequence behind the patch id; provenance and labels onto the cell config; oracle and oracle-task records carry the new fields; activity registration; `test_benchmark_workflow.py`. | US2. The riskiest change to workflow code, isolated in one step with the replay check right after it. |
| 6 | `f3-reproduction.md`. Then `B/oracle.py`: empty-diff guard, `changed_files`, environment seam, allowlist, oracle requirements files; `test_grade_oracle.py` fast and `slow`. | US3. The reproduction comes first so that, if it finds a cause outside the environment, the step is re-planned before code is written. |
| 7 | `S/code/step.py` timestamps and qa outcome; `S/review/step.py` spend; clause edits; tests in `tests/code/`, `tests/review/`. | US6. Independent of steps 1 to 6 apart from the models. |
| 8 | `gate-diagnosis.md`. No pipeline export exists for benchmark children and the stored merge and analyze records carry no cause, so the evidence is the stored integration branches in the scratch repository, against which the merge slice's deterministic checks are re-run, plus whatever logs exist (research R-10). **Report to the orchestrator and wait.** Then the error text on rejecting records, the record before each rejected return, and the per-gate repair or not-evaluated path; clause edits; tests. | US7. The diagnosis decides the code; the wait is ruling R2. |
| 9 | Documents (table below). | Describe what is on the branch. |
| 10 | Full gates (quickstart §1), stored-data checks (§2). | Everything green before tokens are spent. |
| 11 | The validation smoke run (quickstart §3); `verification.md`. | The exit criterion. Needs the orchestrator's go: it is a live run on a shared machine. |

US1 is deliverable after step 1. US4 and US5 after steps 2 to 4. US2 after step 5. US3, US6 and US7 are each one step.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `tests/test_benchmark_workflow.py` `test_oracle_record_none_score_is_fail`, `test_oracle_task_records_none_score_is_fail` | a missing case-level score now gives outcome `not_evaluated`; the oracle-task test is unchanged unless contract §3 removes its case | R-4, R-5 |
| `tests/test_benchmark_workflow.py` `test_oracle_record_shape` and the graph-attribution tests | `model` is `deterministic`; `arm` carries the arm name | R-8 |
| `tests/test_benchmark_recorder.py` cell-file tests | a record with `cell_id` goes to that file; records without it keep the old path | R-8 |
| `tests/test_benchmark_judge.py` missing-rubric test | "skipped" becomes "raises" | R-2 |
| `tests/test_grade_oracle.py` | every test installs the environment seam stub; the missing-branch test is unchanged | R-6 |
| `tests/test_benchmark_scoring.py`, `test_benchmark_report.py` | assertions on row keys gain the cell and kind; pre-existing expectations on pre-012-shaped fixtures move under the pre-012 section | R-11 |
| any test that monkeypatches `_CASES_DIR`, `_cases_dir` or `_CALIB_DIR` | sets `SDLC_CASES_ROOT` instead | R-1 |
| `tests/code/` tests asserting the qa record's outcome equals the task verdict, or equal start times | assert contract §5 | R-9 |

Files marked M in the structure tree but not listed here only gain cases. If any file under `tests/replay/`, or any stage test for non-benchmark behaviour, needs an edit to pass, that is a stop-guard (SG-1), not a fix.

## Document changes

| File | Now | Change to |
|---|---|---|
| `BENCHMARK.md` §1 (what exists) | describes records without provenance or cell status | the record's new fields; the cell record; one file per cell; pre-012 records and how reports show them |
| `BENCHMARK.md` Tier A (held-out tests) | oracle runs after the child | when a cell is graded, not graded, grading failed; the per-grade environment; `oracle/requirements.txt`; the empty-diff rule |
| `BENCHMARK.md` Tier B (rubrics) | rubric files per case | a registered file must exist; `SDLC_CASES_ROOT` |
| `BENCHMARK.md` §4.1, §4.2 | quality and cost metrics | two sentences (research R-13): code-stage quality is the share of attempts that passed; dollars on harness records are not measured, tokens are |
| `BENCHMARK.md` §5 (authoring cases) | case layout | `oracle/requirements.txt` |
| `S/code/code.md` line 19 clause | code and qa records per attempt | what each of the three attempt records spans and whose verdict it carries |
| `S/review/review.md` | review record | its time span and tokens |
| `S/merge/merge.md`, `S/analyze/analyze.md` | rejection paths | every rejection is recorded with its cause; benchmark-mode treatment per `gate-diagnosis.md` |
| `README.md` benchmark section | how to run and score | `KROKER_COMMIT` for a worker that cannot read git; the pre-flight failure |
| `ROADMAP.md` | benchmark epics | one entry: Phase 1 of the benchmark improvement plan landed; Phases 2 to 4 open; "Last verified" line |

Find each passage by its text; line numbers are from the base. Documents describe main, so these ride the branch.

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: any test under `tests/replay/`, or any stage test of non-benchmark behaviour, changes result against the step-0 baseline. Stop, diagnose, report.
- **SG-2**: a step-0 "Verify" item fails, or step 4's grep finds a reader of benchmark records this plan does not name (for example: a finished code stage can end with no post-code record; a dashboard consumer maps the outcome string to a closed set). Stop and report; the design decision it guards is re-opened, not patched around.
- **SG-3**: `S/code/step.py` would pass 1000 lines, or a task needs to move code out of it. Stop.
- **SG-4**: the F3 reproduction finds a cause outside the oracle's environment (wrong branch graded, run-id collision, base branch polluted). Stop before step 6's code and report; the fix may belong elsewhere.
- **SG-5**: step 8. No gate code is written before the orchestrator has answered the diagnosis report. A repair that reaches outside `S/analyze/`, `S/merge/` and `B/`, or changes non-benchmark behaviour, is a second stop.
- **SG-6**: the stored-records fingerprint changes, anything under `runs/` is added to git, or a task wants to rewrite a stored record. Stop.
- **SG-7**: the smoke run. Not started without the orchestrator's go. One run. If it aborts or misses a criterion, report with the records; a second run needs clearance.
- **SG-8**: a `slow` or `temporal` test named in a gate reports "deselected". A deselect is not a pass. Stop.

## Risks

| Risk | Mitigation |
|---|---|
| The "code finished" rule misreads a pipeline shape (a finished code stage with no post-code record) | Step-0 verify item on stored runs and on the quarantine path; SG-2. |
| Per-grade environments make grades slow or flaky on package downloads | Measured in step 6; provisioning failure is `grading_failed`, never a zero. Timeout raised only with the measurement in hand. |
| Oracle scores drop because produced projects relied on the worker's packages | Expected and correct. Stated in `BENCHMARK.md`; pre-012 and 012 rows are never averaged together. |
| A new outcome value breaks a consumer outside the benchmark package | Step-0 grep of the dashboard backend and client; SG-2. |
| The gate repair turns out large | Diagnosis is reported before any repair; ruling R2 allows "stays a rejection, cause recorded" as an outcome, and SC-007 only excludes benchmark-only causes. |
| The worker cannot see the commit and the smoke run records `unknown` | Quickstart §3 sets `KROKER_COMMIT`; the smoke check requires a real id. |
| Old tests leaned on `(score or 0.0)` turning a missing score into FAIL | Listed in "tests changed on purpose"; the new value is asserted explicitly. |
| The smoke run aborts for reasons unrelated to this round (the audit's unexplained early stops) | The cell must then read `not_graded` (itself a check of US2); SG-7 governs a retry. |

## Follow-ups to file (`.workspace/tasks/`)

- Prompt hash does not cover the prompt builders in `stages/*/prompts.py` (skeptic L6). Size S to M.
- `_ensure_python_env` is imported across slices by merge and now by the benchmark package; lift it to a neutral module. Size S.
- Three vocabularies for one stage (record stage, manifest rubric key, calibration bucket). Size M, with Phase 2.
- Scratch repositories keep every run's integration branch forever. Size S.
- Whatever `gate-diagnosis.md` finds that is real but outside this round.

## Items for GATE 2

1. **The graded line changed after GATE 1.** The spec said "the code stage produced an integration result the oracle can check out". The integration branch exists before any code task runs, so that wording grades an empty aborted run. It now reads "the code stage finished", detected by a post-code stage record. Spec FR-007, US2 scenario 1, two edge cases and one assumption were amended.
2. **A new outcome value `not_evaluated`** and a new record scope `cell`. Two readers of the record files exist: the benchmark package, and `scripts/aggregate_benchmarks.py` for the documentation build. Both are updated in step 4, which starts with a grep for any third.
3. **Six additive record fields** (`kroker_commit`, `tree_dirty`, `arm`, `cell_id`, `cell`, and `changed_files` on the grade) and four on `BenchmarkConfig`.
4. **`model` on oracle records changes from the arm name to `deterministic`.** The arm moves to `arm`.
5. **Oracle scores from 012 on are not comparable with earlier ones**: the environment is isolated, and aborted cells no longer count as zero.
6. **The prompt hash covers `instructions.md` only.** A prompt-builder change shows as a new commit or a dirty tree. Follow-up filed.
7. **Analyze and merge**: the decision per gate is made at step 8 on the diagnosis, by the orchestrator. The plan fixes the rule, not the outcome.
8. **A registered rubric must exist even for a stage the run skips** (skeptic's narrower rule not taken).
9. **Two `AGENTS.md` lines are the orchestrator's**: `src/sdlc/workflows/AGENTS.md` if it lists the benchmark parent's activities; a note in root `AGENTS.md` only if the orchestrator wants `KROKER_COMMIT` mentioned under build.
10. **The smoke run needs a go** and the benchmark environment of the launch runbook.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind (no `Co-Authored-By:`, no `Claude-Session:`), even where a template prints one.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only. Git on a worktree runs on the host.
- Never chain two test runs in one shell call. `addopts` already carries `-q`.
- The reviewer gate is per task and blocking: no task N+1 commit before the reviewer has answered on task N's diff.
- The benchmark improvement plan under `docs/reports/` and the other untracked or modified files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
