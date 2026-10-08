# Contract: benchmark records and the harness that writes them (012)

What the harness does after this round, stated so each line can be
tested. Names are in [../data-model.md](../data-model.md). `B/` =
`src/sdlc/benchmarks/`.

## 1. Case files

1.1 Every reader of case files resolves the cases directory through
`paths.cases_dir()`. With `SDLC_CASES_ROOT=/x`, the judge's rubric loader,
the report's language map, the task-suite loader, the oracle, the
DevEval import default and the verify-case default all read under `/x`.
Calibration reports are read under `/x/../calibration`.

1.2 `check_case_assets` returns, for each registered rubric or veto whose
file is absent or holds only whitespace, the text
`<kind> '<key>': <path> is missing` or `... is empty`, where kind is
`rubric` or `veto`. An absolute registered path is checked as given.

1.3 `sdlc benchmark run` on a case with a problem from 1.2 prints every
message, exits non-zero and starts no workflow.

1.4 `load_case_assets` raises `ApplicationError` with
`type="MissingCaseAsset"` and `non_retryable=True`, carrying the same
messages. The activity is attempted once. The benchmark workflow fails
before the first cell is built.

1.5 A case with empty `rubrics` and `vetoes` passes 1.2 to 1.4.

1.6 `STAGE_TO_RUBRIC["plan"] == "planner"`. `trust_for_stage("plan", ...)`
returns the planner bucket's value.

## 2. Fields on every 012 record

Applies to stage, task-attempt, oracle, oracle-task and cell records
written in a benchmark run.

2.1 `kroker_commit` is a non-empty string: a commit id or `unknown`.
Never `None`, never `""`.

2.2 `tree_dirty` is `True`, `False` or `None`. `None` only when it could
not be determined.

2.3 `arm` is the cell's arm name and `cell_id` is the cell's id. All
records of one cell carry identical values.

2.4 `model` is the model that did the work of that record. Oracle,
oracle-task and cell records carry `deterministic`.

2.5 `prompt_sha`:

| Record | Value |
|---|---|
| role in `PROMPTED_ROLES` and model not `deterministic` | 64 hex characters: sha256 of that role's `instructions.md` |
| model `deterministic` | `none:deterministic` |
| any other role | `none:no-registry-prompt` |

Identical instructions give identical values across runs. Changing one
role's instructions changes that role's value and no other.

2.6 All records of one cell are appended to one file,
`<root>/<bench_run_id>/<sanitized cell_id>.jsonl`.

2.7 Provenance resolution order: git in the Kroker source root; else
`KROKER_COMMIT` (+ `KROKER_TREE_DIRTY`); else `unknown` / `None`. It runs
once per benchmark run; every record of the run carries the same values.

2.8 Outside a benchmark run (`cfg.benchmark.case_id is None`) nothing in
this section is written and no new activity runs.

## 3. Cell status and grading

One cell record per cell that was started, written after the child ends
and after any grading.

| Case has oracle | Code finished | Oracle result | `grading` | Oracle records written |
|---|---|---|---|---|
| no | any | — | `no_oracle` | none |
| yes | no | not run | `not_graded` | none |
| yes | yes | empty diff vs base | `graded` | oracle record: score 0.0, passed 0, outcome fail, detail `empty diff vs base` |
| yes | yes | score present | `graded` | oracle record + oracle-task records as today |
| yes | yes | no score | `grading_failed` | oracle record: score `None`, outcome `not_evaluated`, `error` = the grade's detail; no oracle-task records |

3.1 Code finished = the cell's records include a stage in
`POST_CODE_STAGES`.

3.2 `last_stage` is the latest stage by `CELL_STAGE_ORDER` among the
cell's records; `None` when the cell wrote none.

3.3 `pipeline_finished` is true exactly when the child returned without
raising. `completed = pipeline_finished and code_finished`.

3.4 The cell record: scope `cell`, stage `cell`, role `cell`, quality
score `None` with judge `contract`, outcome `pass` when `completed` else
`fail`, `error` = `child_result` when not completed, speed spanning the
child's start to the end of grading.

3.5 A cell rejected before it starts (matrix or role validation) writes
no cell record, as today.

3.6 An oracle record no longer reports a language mismatch as its only
error for a cell that produced no code: such a cell has no oracle record.

3.7 Held-out breach and language mismatch on a graded cell are reported
in `error` as today.

## 4. Oracle environment

4.1 Each call of `grade_oracle` that runs tests creates a virtual
environment inside that call's temporary worktree and deletes it with the
worktree.

4.2 The test command runs with an environment that contains only the
allowlisted names plus: the virtual environment's script directory first
on `PATH`, `VIRTUAL_ENV`, `PYTHONNOUSERSITE=1`. `PYTHONPATH` and
`PYTHONHOME` are absent.

4.3 Installed into the environment, in order: the produced project's
declared dependencies (existing provisioning), then
`oracle/requirements.txt` when the case has one, else `pytest`.

4.4 Provisioning failure → no score, detail starting
`oracle environment failed:`; the cell is `grading_failed`.

4.5 Empty diff against the base branch → the zero grade of §3 and no
provisioning, no test run.

4.6 Two calls on the same branch return the same passed and total.

4.7 After a call returns, nothing it installed is importable by the next
call or by the worker.

## 5. Timings, verdicts and spend per task attempt

For one attempt with a code record C, a qa record Q and a review record R:

5.1 `C.started_at` = attempt start; `C.ended_at` = the moment before the
test run begins.

5.2 `Q.started_at` = `C.ended_at`; `Q.ended_at` = the moment the qa step
returns.

5.3 `R.started_at` = `Q.ended_at`; `R.ended_at` = the moment the review
record is written.

5.4 So `C.ended_at <= Q.started_at <= Q.ended_at <= R.started_at <=
R.ended_at`, and no two of the three share both endpoints.

5.5 `Q.outcome` is pass exactly when the tests passed and qa reported no
issues. Containment drift does not change it.

5.6 `R.outcome` is pass exactly when the reviewer approved.

5.7 `R.cost` carries the reviewer call's input and output tokens.

5.8 No qa record when the qa lens did not run; no review record when the
reviewer did not run.

5.9 The task verdict, the fix loop, the gates and the returned
`TaskResult` are unchanged.

## 6. Analyze and merge records

6.1 Every analyze record with outcome fail carries in `error` the number
of untraced criteria and up to three of them.

6.2 Every merge path that returns `rejected:merge:...` writes a merge
record first. Its `error` names the blocking checks (absolute branch) or
the rejection kind (advisory, soft verdict).

6.3 A gate or check may be written as `not_evaluated` only in benchmark
mode and only when `gate-diagnosis.md` shows it depends on something a
benchmark run cannot have. `error` then starts `not evaluated:` and gives
the reason. Checks that inspect the produced code are never written this
way.

6.4 With `cfg.benchmark.case_id is None`, analyze and merge behave and
return exactly as at base. Their tests at base pass unedited.

6.5 Which gates are repaired and which are not evaluated is fixed by
`gate-diagnosis.md` and reported to the orchestrator before coding; this
contract gains one line per gate at that point.

Per-gate decision (gate-diagnosis.md, ruled on by the orchestrator
2026-10-08 — "no code change for either gate"):

- **Merge, absolute checks (tests, lint, security): stays a rejection.**
  The diagnosis showed right-reasoned rejections of the produced code
  (introduced lint findings; failing or uncollectable produced tests);
  no benchmark-only condition. Not evaluated: never.
- **Merge, advisory path (incl. the soft-verdict route) and analyze
  traceability acting through it: stays a rejection.** Code-inspecting,
  no benchmark-only dependency found; the visibility mechanism is the
  §6.1/§6.2 error text, not a new outcome. Not evaluated: never.

## 7. Readers

7.1 Every stored record file under `runs/benchmarks/` loads with no line
skipped that loaded at base.

7.2 `is_pre012(r)` is true exactly when `r.kroker_commit is None` and
`r.case_id != "_production"`. Drift records carry no commit and are not
pre-012; they are in no "pre-012 records" count.

7.3 `compute_summaries` excludes cell and oracle-task records, groups the
rest by `(case, stage, cell_key, is_pre012)`, and sets `pre012`,
`cell_id`, `arm` on each row. No row mixes kinds.

7.4 The report lists 012 rows, then a section
`## Pre-012 records (untrusted)` with one sentence saying why, then the
pre-012 rows. With no pre-012 records the section is absent.

7.5 The report has a `## Cells` section built from cell records: cells
started, completed, graded, not graded (with the count per last stage),
grading failed. Not-graded cells contribute to no quality mean.

7.6 The heatmap, the task, error, waste and agreement matrices, the
experiments view and the success-criteria rollup ignore cell records and
print `includes N pre-012 records (untrusted)` when N > 0.

7.7 Those matrices label a column with `arm_label` and key a cell with
`cell_key`.

7.8 A `not_evaluated` record is counted by no reader as a pass, a fail, a
reject or a rework. "Reader" means every module of the benchmark package
and `scripts/aggregate_benchmarks.py`.

7.9 `scripts/aggregate_benchmarks.py`, which reads the record files as
raw JSON for the documentation build:

- skips records whose scope is `cell` in every sum and count (a run's
  total wall-clock is the sum over stage, task-attempt, oracle and
  oracle-task records, as at base);
- counts an outcome of `not_evaluated` as neither pass nor fail: a run
  whose merge outcome is `not_evaluated` takes its overall outcome from
  the remaining stage outcomes, and the stage outcome matrix gets no
  pass or fail increment from it. The same holds on the path with no
  merge record: a `not_evaluated` stage outcome is left out of the
  "all stages passed" test, it does not fail it. The test covers both
  paths;
- labels a record with `arm` when the record has one, else `model`;
- prints `includes N pre-012 records (untrusted)` when N > 0, by the
  rule of §7.2 applied to the raw fields.

On the stored (all pre-012) records its output differs from base only by
that one line.

## 8. Requirement to proof

"Smoke" = the single todo-api validation run (quickstart §3). Everything
else is a deterministic test. A requirement proved only by tests is never
claimed from the smoke run.

| Requirement | Proof |
|---|---|
| FR-001 | `tests/test_benchmark_paths.py`: each reader under an override (§1.1) |
| FR-002, SC-008 | `test_benchmark_paths.py` (§1.2); `test_benchmark_cli.py` (§1.3); `test_benchmark_judge.py` (§1.4, §1.5); corpus test: every shipped manifest passes |
| FR-003, SC-001 | smoke; `test_benchmark_judge.py` loader under the override |
| FR-004 | `test_calibration_render.py` (§1.6) |
| FR-005 | `test_benchmark_paths.py` or `test_calibration_render.py`: key-set pins (research R-3) |
| FR-006, FR-007, SC-004 | `tests/test_benchmark_cell.py`: status table (§3); `tests/test_benchmark_workflow_sequence.py` (`temporal` tier): an aborted cell yields a cell record and no oracle record |
| FR-008 | `test_benchmark_scoring.py`, `test_benchmark_report.py` (§7.3, §7.5) |
| FR-009 | `test_benchmark_cell.py`, `test_benchmark_workflow.py`, `test_benchmark_workflow_sequence.py` (§3 last row) |
| FR-010 | `f3-reproduction.md` exists and states an outcome |
| FR-011, FR-012 | `test_grade_oracle.py`: environment allowlist (§4.2) fast; real venv `slow` (§4.1, §4.7) |
| FR-013, SC-005 | `test_grade_oracle.py`: passing branch then empty branch in one process, fast (§4.5) and `slow` (§4.6) |
| FR-014, FR-016, SC-002 | `tests/test_benchmark_provenance.py` (§2.1, §2.2, §2.7); `test_benchmark_record_builder.py`; smoke |
| FR-015 | `test_benchmark_provenance.py` (§2.5) |
| FR-017, SC-003 | `test_benchmark_recorder.py` (§2.6); smoke |
| FR-018 | `test_benchmark_record_builder.py` (§2.4) |
| FR-019, SC-006 | `tests/code/` attempt-timing test (§5.1 to §5.4); smoke |
| FR-020 | `tests/code/`: qa passes and reviewer rejects (§5.5, §5.6) |
| FR-021 | `tests/review/` (§5.7) |
| FR-022 | `tests/code/`, `tests/review/` (§5.8) |
| FR-023 | `gate-diagnosis.md` exists and states a cause per gate |
| FR-024, FR-025, SC-007 | `tests/analyze/`, `tests/merge/` (§6.1 to §6.3); reader tests and `tests/test_aggregate_benchmarks.py` (§7.8, §7.9); smoke for the positive half |
| FR-026 | `tests/analyze/`, `tests/merge/` at base pass unedited (§6.4) |
| FR-027, SC-009 | `tests/test_benchmark_legacy_records.py` (§7.1, §7.2); `test_benchmark_report.py` (§7.4); readers (§7.6); `tests/test_aggregate_benchmarks.py` (§7.9) |
| FR-028, FR-029 | quickstart §3 and `verification.md` |
| FR-030 | document table in the plan; `scripts/check_clauses.py` read |
