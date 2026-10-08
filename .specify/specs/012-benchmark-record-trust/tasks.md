# Tasks: Benchmark Record Trustworthiness (round 012, Phase 1)

**Input**: `.specify/specs/012-benchmark-record-trust/` (spec.md, plan.md, research.md, data-model.md, contracts/records-and-harness.md, quickstart.md)

**Tests**: required (plan "Work order"; contract §8). In every task the failing test is written first and seen red for the stated reason, then the code; both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: all seven user stories, FR-001 to FR-030, SC-001 to SC-009. Phases 2 to 4 of the source report have no task here.

`B/` = `src/sdlc/benchmarks/`. `S/` = `src/sdlc/stages/`. "Contract" = `contracts/records-and-harness.md`. "Names" = `data-model.md`. "R-n" = `research.md`.

## Standing rules for every task

- **Names.** `data-model.md` is the only source of names, field names and fixed strings. Copy; do not retype from memory. A name that is needed and not there is a stop (SG-1).
- **Stored records are read-only.** Nothing under `runs/` is modified, moved or deleted. `runs/` is git-ignored (`.gitignore:5`), so git cannot show a violation; the check is the **records fingerprint**: on the host, `python -c "import hashlib,pathlib;fs=sorted(pathlib.Path('runs/benchmarks').rglob('*.jsonl'));h=hashlib.sha256();[h.update(str(f.relative_to('runs/benchmarks')).replace(chr(92),'/').encode()+hashlib.sha256(f.read_bytes()).digest()) for f in fs];print(len(fs),h.hexdigest())"`. T001 records its output; it is re-run before every commit and must print the same line (until T024, which adds one run directory). `git ls-files runs/` stays empty throughout: nothing under `runs/` is ever added, forced or not. Tests read stored records in place or copy them to `tmp_path`.
- **Non-benchmark behaviour does not change.** With `cfg.benchmark.case_id is None`, no new activity runs and every stage returns what it returned at base. The only intended differences in ordinary runs are the two trace fields of plan rule 2.
- **No reader guesses.** Absent reads as "not recorded". `None` scores and `not_evaluated` outcomes enter no count and no mean.
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv. Git on the branch's worktree: the host only. One test run per shell call, never two chained. `addopts` already has `-q`.
- **Marked tiers.** A `slow` or `temporal` test is deselected without its `-m` flag even when named. A deselect is not a pass (SG-8).
- **Convergence.** A task is not done while its named test files, `uv run ruff check .`, `uv run ruff format --check .` or `uv run mypy` (no new errors against the T001 baseline) are red, or `python scripts/check_file_size.py` reports a file over 1000 lines.
- **Commit**: one per task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`, and the nearest `AGENTS.md` of any slice you edit (`S/code/`, `S/review/`, `S/qa/`, `S/analyze/`, `S/merge/`, `src/sdlc/core/`, `src/sdlc/workflows/`).
- **Forbidden paths**: everything under `runs/` and `docs/reports/`; every file under `tests/replay/`; `src/sdlc/workflows/graph.py`, `feature.py`, `role_host.py`; `agents/`; `interfaces/`; every `AGENTS.md`; `CLAUDE.md`; `B/drift.py`; `S/qa/` source; every script except `scripts/aggregate_benchmarks.py`; `pyproject.toml` and `uv.lock`; earlier `.specify/specs/*`; the user's uncommitted and untracked files in the primary checkout.
- Line numbers are as of main `7f5191d0`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name or rule is needed that the spec set does not define, the T001 name check finds a hit, or an edit to a forbidden path appears necessary.
- **SG-2** A T001 "Verify" item fails, or T009's grep finds a reader of benchmark records the plan does not name.
- **SG-3** `S/code/step.py` would pass 997 lines, or a task needs to move code out of it.
- **SG-4** T014 finds a cause of the empty-tree result outside the oracle's environment.
- **SG-5** T019: no gate code before the orchestrator answers the diagnosis. A repair that reaches outside `S/analyze/`, `S/merge/` and `B/`, or changes non-benchmark behaviour, is a second stop.
- **SG-6** The records fingerprint differs from the T001 value (before T024), `git ls-files runs/` prints anything, or a task wants to rewrite a stored record.
- **SG-7** T024: the smoke run is not started without the orchestrator's go. One run. An abort or a missed criterion is reported with the records; a second run needs clearance.
- **SG-8** A `slow` or `temporal` test named in a gate reports "deselected"; a test marked RED passes before its code; a PIN is red.
- **SG-9** Any test under `tests/replay/`, or any existing test of non-benchmark stage behaviour, changes result against the T001 baseline for a reason other than plan rule 2's two trace fields. An existing test fails that neither this file nor plan.md "Existing tests changed on purpose" names. Do not edit a test to pass.

## Phase order

| Phase | Purpose | Story | Plan steps | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | known start, every design assumption checked | — | 0 | 1 |
| 2 Foundation | record model, old records still load | all | 2 | 1 |
| 3 Rubric scores collected | one cases location, pre-flight, plan key | US1 (P1) | 1 | 3 |
| 4 Provenance and one label, writer side | commit, prompt hash, arm, one file | US4, US5 (P2) | 3 | 3 |
| 5 Readers | no mixed aggregates, cell-aware, script | US5, R3 | 4 | 3 |
| 6 Not-graded cells | cell record, grade only finished code | US2 (P1) | 5 | 2 |
| 7 Oracle isolation | reproduction, guard, per-grade environment | US3 (P1) | 6 | 3 |
| 8 Attempt records | own time, verdict, spend | US6 (P2) | 7 | 2 |
| 9 Gates | diagnosis, causes on record, per-gate decision | US7 (P3) | 8 | 3 |
| 10 Close-out | documents, gates, smoke run | — | 9 to 11 | 3 |

Phases 4 and 5 come before the two remaining P1 stories on purpose: the cell record of phase 6 must carry the fields of phase 4 and must never reach a reader that phase 5 has not prepared. Phase 3 and phase 8 depend only on phase 2 and may be moved earlier or later by the orchestrator.

---

## Phase 1: Setup and baseline (no source edits)

- [x] T001 Create branch `012-benchmark-record-trust` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree. If main has moved past `7f5191d0`, on the host run `git diff --stat 7f5191d0 HEAD -- src/sdlc/benchmarks src/sdlc/stages/code src/sdlc/stages/review src/sdlc/stages/analyze src/sdlc/stages/merge src/sdlc/core/models.py src/sdlc/workflows/benchmark_host.py scripts/aggregate_benchmarks.py Dockerfile BENCHMARK.md` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m slow tests/test_grade_oracle.py` (record "no tests ran" if none is marked yet); `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `python scripts/check_clauses.py`; `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out <a temp file outside the repo>` and keep that output for T011. Compute the records fingerprint (standing rules) and record its output line. Do the name check of data-model §5. Then the Verify items, each by reading code or stored records, each recorded with file:line evidence:
  (a) R-4: for one stored run that stopped before code and one that reached merge, list the stage names in its record files and confirm no post-code stage (`analyze`, `merge`, `deploy`) appears in the first and one appears in the second;
  (b) R-4: read `src/sdlc/workflows/graph_nodes/postplan.py`, `src/sdlc/workflows/build.py` and `S/analyze/step.py` and state every way a run whose code stage finished can end without an analyze, merge or deploy record;
  (c) R-5: grep `src/sdlc/dashboard`, `src/sdlc/observability`, `interfaces/` for consumers of the stage-ended event's `outcome` string and state whether any maps it to a closed set;
  (d) R-7: list every `role=` value passed to `stage_record` / `_stage_record` across `src/sdlc`, and for each whether `REGISTRY[role].instructions` exists (`src/sdlc/agents/roles.py`, `src/sdlc/agents/loader.py`); this list becomes `PROMPTED_ROLES`' expected value in T006;
  (e) R-9: confirm `_now()` in `S/code/step.py` wraps `workflow.now()`, and state what the qa step returns and whether a qa record is written when the qa lens is disabled or has no agent;
  (f) R-6: read `_ensure_python_env` (`S/qa/activities.py`) and state what environment dict it returns and where the venv is created; confirm `.sdlc-venv` is ignored by the produced repos' git;
  (g) list every test that references `_CASES_DIR`, `_cases_dir` or `_CALIB_DIR`.
  Write `.specify/specs/012-benchmark-record-trust/baseline.md`: base sha, every command's result and counts, mypy error count, the replay result, name-check outcome, items (a) to (g), and line counts of `S/code/step.py`, `S/merge/step.py`, `B/workflow.py`, `B/oracle.py`, `B/models.py`, `scripts/aggregate_benchmarks.py`. Any item that contradicts research.md is SG-2: stop and report before committing anything else. Commit (spec set + baseline).

**Checkpoint**: baseline.md exists with every gate's result and items (a) to (g); no source file differs from the base.

---

## Phase 2: Foundation (blocks every story)

- [x] T002 Record model. RED first in `tests/test_benchmark_models.py`: a record built without the new fields has `kroker_commit is None`, `tree_dirty is None`, `arm is None`, `cell_id is None`, `cell is None`; `BenchmarkScope.CELL.value == "cell"`; `BenchmarkOutcome.NOT_EVALUATED.value == "not_evaluated"`; `CellStatus` is frozen and rejects an unknown field; `cell_key`, `arm_label`, `is_pre012` per Names §2.3 (cases: 012 record; pre-012 harness record; pre-012 proposer record with no harness → `proposer`; crew record with a lead; drift record `case_id="_production"` is not pre-012); `POST_CODE_STAGES == {"analyze", "merge", "deploy"}`; every stage in the T001(d) writer inventory is in `CELL_STAGE_ORDER`; `BenchmarkSummary` defaults `cell_id=None`, `arm=None`, `pre012=False`. RED in `tests/test_benchmark_config.py`: a `BenchmarkConfig` payload without the four new fields validates and they default to `None`. New file `tests/test_benchmark_legacy_records.py` (PIN, must pass before and after the model edit): every `*.jsonl` under the repository's `runs/benchmarks/` is read in place, every non-empty line validates as `BenchmarkRecord`, the total equals the count of non-empty lines, and every non-drift record satisfies `is_pre012` once that helper exists (skip the whole test with a stated reason when the directory is absent). Then edit `B/models.py` per Names §1.1 to §1.4 and §2.3, and `src/sdlc/core/models.py` `BenchmarkConfig` per Names §1.5. No writer or reader changes in this task. Commit.

**Checkpoint**: every stored record still loads; the fast tier count rises only by the new tests.

---

## Phase 3: User Story 1 — rubric scores are collected or the cell fails loudly (P1)

**Goal**: one cases location for every reader; a registered file that is missing stops the run at zero spend; the plan stage shows its trust value.

**Independent test**: with `SDLC_CASES_ROOT` pointing at a temp corpus, the rubric loader returns the rubric text; delete one registered file and both the CLI and the activity refuse, naming it.

- [x] T003 [US1] One cases location. RED first in new `tests/test_benchmark_paths.py`: `cases_dir()` returns the override when `SDLC_CASES_ROOT` is set and the checkout's `benchmarks/cases` otherwise, read at call time (set the variable after import); `calibration_dir()` is its sibling `calibration`; and, with the override pointing at a `tmp_path` corpus, each of these reads under it (contract §1.1): `load_case_assets`, `report.resolve_language_map` with no explicit directory, `tasks.load_task_suite`, the oracle's case lookup, `calibration.load_calibration_reports` with no explicit root, `cli.dispatch_verify_case` and `cli.dispatch_import_deveval` defaults. Create `B/paths.py` (Names §2.1; imports nothing from `B/`). Replace the derivations at `B/judge.py:221` (remove `_CASES_DIR`), `B/report.py:11` and `:115`, `B/oracle.py:161`, `B/tasks.py:75`, `B/calibration.py:240` (remove `_CALIB_DIR`), `B/cli.py:167`, `:173`, `:265`, `:297`. Move every test listed in T001(g) from monkeypatching a removed name to `monkeypatch.setenv("SDLC_CASES_ROOT", ...)`; change nothing else in those tests. Leave the repository-root derivations in `B/score.py:17` and `B/experiments.py:38` alone. Verify: `grep -rnE '"benchmarks" / "(cases|calibration)"' src/sdlc` returns only `B/paths.py`. Commit.
- [x] T004 [US1] A registered file that is missing or empty fails. RED first: in `tests/test_benchmark_paths.py`, `check_case_assets` cases per contract §1.2 (present; missing rubric; whitespace-only rubric; missing veto; absolute path; empty maps → `[]`; two problems → two messages in registration order); a corpus test that parses every `benchmarks/cases/*/case.yaml` in the repository and asserts `check_case_assets` returns `[]` for each; in `tests/test_benchmark_judge.py`, change the existing missing-file test from "skipped" to: `load_case_assets` raises `temporalio.exceptions.ApplicationError` with `type == "MissingCaseAsset"`, `non_retryable is True`, and the message naming the key and path, and add the empty-maps case returning `{}`; in `tests/test_benchmark_cli.py`, `_run_matrix` on a case directory with a missing registered rubric raises `SystemExit` with the messages before any Temporal client is created (assert the client constructor was not called). Then: add `check_case_assets` and `MISSING_CASE_ASSET` to `B/paths.py`; make `load_case_assets` in `B/judge.py` raise per contract §1.4 and update its docstring; in `B/cli.py` `_run_matrix`, call `check_case_assets(spec.rubrics, spec.vetoes, Path(case_path).parent)` right after `load_case_spec` and exit with the joined messages. Commit.
- [x] T005 [US1] Plan-stage rubric key and the pins. RED first in `tests/test_calibration_render.py`: `trust_for_stage("plan", reports)` returns the planner report's value (contract §1.6) and `trust_for_stage("planning", reports)` still does; every key of `STAGE_TO_RUBRIC` is in `set(CELL_STAGE_ORDER) | set(heatmap.CANONICAL_STAGES)`; for each judged stage, the rubric-map key that stage's step passes to `ctx.judge` (read them from T001's notes: `clarifier`, `architect`, `planner`, `qa`, `research`) is a key used by at least one shipped manifest's `rubrics` map, asserted against the corpus. Then add `"plan": "planner"` to `STAGE_TO_RUBRIC` in `B/calibration.py`, keeping `"planning"`. Commit.

**Checkpoint**: US1 is complete on its own. The judge can find rubric files in the worker image.

---

## Phase 4: User Stories 4 and 5, writer side — provenance and one label (P2)

**Goal**: every record a benchmark run writes carries the commit, a dirty flag, a real prompt hash, the arm and the cell id, and lands in one file per cell.

**Independent test**: build a stage record from a config that carries a commit and an arm; it has all five fields and the recorder names one file for a proposer record and a harness record of the same cell.

- [x] T006 [P] [US4] Provenance module. RED first in new `tests/test_benchmark_provenance.py`: `resolve_provenance` (call the activity function directly) returns the git head and `tree_dirty=False` in a clean temp git repository passed as the source root, `True` after an uncommitted edit; with no repository and `KROKER_COMMIT=abc` in the environment returns `abc` and `tree_dirty` from `KROKER_TREE_DIRTY` (`1`/`true` → True, `0`/`false` → False, unset → None); with neither returns `UNKNOWN_COMMIT` and `None`; never raises when git is absent from `PATH`; `prompt_sha_for(role, model)` returns 64 hex characters equal to `sha256(REGISTRY[role].instructions)` for a prompted role, `none:deterministic` when `model == "deterministic"` whatever the role, `none:no-registry-prompt` for a role without registry instructions; `PROMPTED_ROLES` equals the T001(d) list. Create `B/provenance.py` per Names §2.2 (the source root is a parameter with the checkout path as default, so the test can point it elsewhere). Add `ARG KROKER_COMMIT=unknown` and `ENV KROKER_COMMIT=${KROKER_COMMIT}` to the runtime stage of `Dockerfile` beside the other `ENV` lines. Commit.
- [x] T007 [US4] [US5] The builder writes the fields. RED first in new `tests/test_benchmark_record_builder.py`: with `cfg.benchmark` carrying `kroker_commit="abc"`, `tree_dirty=False`, `arm="a1"`, `cell_id="c#opencode#a1"`, `stage_record(...)` copies all four, sets `prompt_sha` to `prompt_sha_for(role, model)` (cases: a prompted proposer role; `model="deterministic"`; a role with no registry prompt), and leaves `model` as passed (contract §2.4); with `cfg.benchmark.kroker_commit=None` and a benchmark `case_id` set, the record's `kroker_commit` is `UNKNOWN_COMMIT`, never `None` or `""` (contract §2.1); with no benchmark case (`case_id is None`) the record is built as at base apart from `prompt_sha`, and `kroker_commit`, `tree_dirty`, `arm`, `cell_id` stay `None`. (Reading of contract §2.8: it governs what is persisted and which activities run. `stage_record` has one code path and fills `prompt_sha` on the in-memory record in every run; outside a benchmark run that record is never persisted, `B/` schedules nothing, and the stage-ended trace event does not carry the field.) In `tests/test_benchmark_workflow.py`: `_cell_config(...)` given a provenance sets `cfg.benchmark.arm == cell.arm_name`, `cell_id == cell.cell_id`, and the commit and dirty flag; called without one (existing call sites in tests) it leaves them `None`. Then edit `B/record_builder.py` (import `prompt_sha_for` and `UNKNOWN_COMMIT` inside the existing `imports_passed_through` block) and `B/workflow.py` `_cell_config` (new optional keyword `provenance`). The workflow does not call `resolve_provenance` yet; that is T013. Commit.
- [x] T008 [US5] One file per cell. RED first in `tests/test_benchmark_recorder.py`: `_cell_id_for` returns `record.cell_id` when set, for a proposer record (no harness) and a harness record alike, so both map to the same path (contract §2.6); for a record without `cell_id` it returns exactly what it returned at base (keep the existing cases as PIN); a drift record still maps to the shared file. Then edit `B/recorder.py` `_cell_id_for`. Commit.

**Checkpoint**: writer side of US4 and US5 is in place for stage and task-attempt records. Oracle and cell records get the fields in T013.

---

## Phase 5: Readers (US5 reader side; ruling R3)

**Goal**: no aggregate mixes pre-012 and 012 records; a cell record or a `not_evaluated` record changes no existing number; rows are keyed by cell.

**Independent test**: feed a reader the stored records plus one synthetic 012 cell (with a cell record and a `not_evaluated` record); every pre-012 number equals its base value.

- [x] T009 [US5] Summaries and the report. First the grep of plan step 4: search `scripts/`, `src/sdlc/eval/`, `src/sdlc/dashboard/`, `src/sdlc/observability/`, `interfaces/` for readers of `runs/benchmarks`, `records.jsonl`, `BenchmarkRecord` or `*.jsonl` under the benchmarks root; anything other than `scripts/aggregate_benchmarks.py` and the write path is SG-2. RED first in `tests/test_benchmark_scoring.py`: cell-scope records are excluded; records are grouped by `(case, stage, cell_key, is_pre012)`; a pre-012 and a 012 record of the same case and stage give two rows with `pre012` True and False; a 012 row has `cell_id` and `arm` set and `model` equal to the sorted comma-joined distinct models; a `not_evaluated` record with score `None` changes no mean; for a records list with only pre-012 records, every row's `n`, `mean_quality`, `mean_cost_usd`, `mean_wall_clock_s` and `composite` equal the base values (keep existing assertions as PIN, add `pre012 is True`). RED in `tests/test_benchmark_report.py`: contract §7.4 (section present with pre-012 rows, absent without; 012 rows first) and §7.5 (`## Cells` from cell records: started, completed, graded, not graded with the count per `last_stage`, grading failed; absent when there is no cell record). Then edit `B/scoring.py` and `B/report.py` (`aggregate`'s sort key gains `pre012` and `cell_id`; `render_markdown` gains the two sections; the row shows the arm in a `cell` column for 012 rows). Commit.
- [x] T010 [US5] Heatmap, rollup and the five matrices. RED first, one or more cases added to each of `tests/test_benchmark_heatmap.py`, `tests/test_benchmark_sc_rollup.py`, `tests/test_task_matrix.py`, `tests/test_error_matrix.py`, `tests/test_benchmark_waste_matrix.py`, `tests/test_benchmark_agreement_matrix.py`, `tests/test_benchmark_experiments.py`: adding a cell-scope record and a `not_evaluated` record to the input changes no count, density, rate or mean (contract §7.6, §7.8); a 012 record is keyed by `cell_key` and labelled by `arm_label`, a pre-012 record keeps its base key and label (§7.7); the rendered output carries `includes N pre-012 records (untrusted)` when N > 0 and not when N = 0. Then edit `B/heatmap.py`, `B/sc_rollup.py`, `B/task_matrix.py`, `B/error_matrix.py`, `B/waste_matrix.py`, `B/agreement_matrix.py`, `B/experiments.py`. Use the helpers from `B/models.py`; write no second fallback. Commit.
- [x] T011 [US5] The documentation script. RED first in new `tests/test_aggregate_benchmarks.py`, on a `tmp_path` runs directory written by the test (raw JSON lines): contract §7.9 — a cell-scope record adds nothing to a run's total wall-clock or to any count; a merge stage outcome of `not_evaluated` is neither pass nor fail and the run's overall outcome comes from the remaining stages; with no merge record, a `not_evaluated` stage outcome is left out of the all-passed test and does not fail it; a record with `arm` is labelled by it, one without by `model`; the output states `includes N pre-012 records (untrusted)` for records without `kroker_commit`. PIN: on a copy of two stored run directories, the aggregate's numbers equal those of the T001 output for the same runs. Then edit `scripts/aggregate_benchmarks.py`. On the host re-run the T001 command on `runs/benchmarks` and diff against the kept output: the only difference is the pre-012 line. Commit.

**Checkpoint**: readers are ready for cell records and the new outcome. The records fingerprint equals the T001 value.

---

## Phase 6: User Story 2 — an aborted cell is recorded as not graded (P1)

**Goal**: one cell record per cell; the oracle runs only when the code stage finished.

**Independent test**: with a records file holding only research and clarify records, the cell reads `not_graded`, `last_stage="clarify"`, and no oracle record is written.

- [x] T012 [US2] Cell status, pure parts. RED first in new `tests/test_benchmark_cell.py`: `summarize_cell` (activity function called directly, records root via `SDLC_BENCHMARKS_ROOT`) returns `last_stage` by `CELL_STAGE_ORDER` and `code_finished` per contract §3.1 and §3.2 for: no file; research and clarify only; through code with task attempts but no post-code record; through analyze; through merge; `grading_status` for every row of the contract §3 table; `cell_record` per contract §3.4 (scope, stage, role, score `None`, judge `contract`, outcome pass only when completed, `error` = `child_result` when not completed, provenance, `arm`, `cell_id`, `model="deterministic"`, `prompt_sha="none:deterministic"`, graph attribution when a sha is given); `child_result` truncated to 500 characters. Create `B/cell.py` per Names §2.4. Commit.
- [x] T013 [US2] The benchmark parent's sequence. RED first in `tests/test_benchmark_workflow.py`: `_oracle_record` and `_oracle_task_records` carry `arm`, `cell_id`, `kroker_commit`, `tree_dirty`, `model="deterministic"`, `prompt_sha="none:deterministic"` (update `test_oracle_record_shape` and the graph-attribution tests for `model`); a grade with score `None` gives outcome `NOT_EVALUATED` with `error` = the grade's detail (replace `test_oracle_record_none_score_is_fail`); a grade with score 0.0 gives outcome FAIL (the `changed_files` field and the empty-diff detail arrive in T015). Sequence test: `temporal`-marked tests in a new file `tests/test_benchmark_workflow_sequence.py`, using `temporalio.testing.WorkflowEnvironment` the way `tests/test_budget_gate.py` and `tests/replay/harness.py` do, with stub activities registered under the real activity names and a stub child registered as `@workflow.defn(name="GraphWorkflow")` (the parent starts the child by class reference at `src/sdlc/workflows/pipeline_child.py:48` and Temporal dispatches by name): (i) child raises, `summarize_cell` returns `code_finished=False` → `grade_oracle` is not called, no oracle record, one cell record with `grading="not_graded"`; (ii) child returns, `code_finished=True`, grade has a score → oracle records then a cell record `graded`; (iii) grade has no score → one oracle record `not_evaluated`, no oracle-task records, cell record `grading_failed`; (iv) case without a language → cell record `no_oracle`; (v) `resolve_provenance` is called once for two cells. Run them with `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` and confirm a non-zero passed count (SG-8). Only if the environment cannot run the parent at all (state the error): extract the per-cell decision into a pure helper in `B/cell.py`, test (i) to (iv) there, and report to the orchestrator that (v) has no test before committing; do not drop it silently. Then edit `B/workflow.py`: inside `if workflow.patched("012-cell-record"):` call `resolve_provenance` once before the cell loop and pass it to `_cell_config`; after the child, record whether it raised and its result or failure text; call `summarize_cell`; grade only when the case has a language and code finished; write oracle records per the contract §3 table; write the cell record last. The un-patched branch keeps the base sequence unchanged. Import `B/cell.py` and `B/provenance.py` inside the existing `imports_passed_through` block. Register `resolve_provenance` and `summarize_cell` where `record_benchmark` and `grade_oracle` are registered (find the list by grepping for `grade_oracle`). Run `uv run pytest -m temporal tests/replay` and compare with the T001 baseline (SG-9). Commit.

**Checkpoint**: US2 is complete. An aborted cell can no longer receive a score.

---

## Phase 7: User Story 3 — each grade runs in its own clean environment (P1)

**Goal**: nothing from one grade can influence another; an empty change scores zero.

**Independent test**: grade a passing branch, then an empty branch of the same repository, in one process: the second has 0 passed.

- [x] T014 [US3] Reproduce the empty-tree result (no source edits). From stored material only, no pipeline run: (i) in the scratch repository of the audited run `bench-cat-cafe-monitoring-1791216395` (the case's `repo_url` is `/srv/scratch-repos/<case>` in the container; `docker-compose.override.yml` binds that to `D:/own/sdlc-scratch-repos` on the host — verify, and ask the orchestrator if it is not there), show the commits on that run's integration branch, the content of its base branch at that time (`git show <base>:app.py` and the file list), and the integration branch of the run that finished just before it; (ii) in the worker image or container, list `site-packages` entries matching `__editable__*`, `*.pth`, `app*` and anything pointing at a worktree path; (iii) if both come back clean, try the direct reproduction in the container: grade a passing temp repository and then an empty one with the base `grade_oracle`, in one process. Write `.specify/specs/012-benchmark-record-trust/f3-reproduction.md`: what was checked, the evidence, and one of "reproduced, cause: …" or "not reproduced, tried: …". A cause outside the oracle's environment (wrong branch graded, run-id collision, a polluted base branch) is SG-4: stop and report before T015. Commit.
- [x] T015 [US3] The empty-diff guard. RED first in `tests/test_grade_oracle.py`: a branch with no change against the base returns score 0.0, passed 0, `changed_files == 0`, detail `empty diff vs base`, and the test command is never run (assert through a stub of `_bounded_shell`); a branch with changes reports `changed_files` equal to the number of changed files; two grades in one process, a passing branch then an empty branch of the same repository, give a positive passed count then 0 (SC-005, fast). Then edit `B/oracle.py`: `OracleGrade.changed_files` (Names §1.6), set it from the existing `git diff --name-only`, and return the zero grade before copying the oracle in. Commit.
- [x] T016 [US3] The per-grade environment. RED first in `tests/test_grade_oracle.py`: every existing test installs a stub for `_provision_oracle_env` returning the current process environment (an autouse fixture in that file); new fast tests: the environment passed to the test command contains only the allowlisted names plus the venv entries of contract §4.2, with `PYTHONPATH` and `PYTHONHOME` absent even when set in the worker's environment, and `PYTHONNOUSERSITE == "1"`; a provisioning failure returns score `None` with detail starting `oracle environment failed:` (contract §4.4); `oracle/requirements.txt` is installed when present and `pytest` alone otherwise (assert on the commands the stubbed shell received). New `slow`-marked tests with the real provisioner: a produced project that imports a small pure-Python package it declares, graded twice back to back, returns the same counts (§4.6); after the call the venv directory no longer exists and the package is not importable in the worker process (§4.7); a passing branch then an empty branch gives a positive count then 0. Then edit `B/oracle.py`: `_provision_oracle_env` (calls `_ensure_python_env` imported from `S/qa/activities.py` as `S/merge/activities.py` does, removes a pre-existing `.sdlc-venv` in the fresh worktree first, then installs the oracle requirements with the venv's interpreter), `_ORACLE_ENV_ALLOW`, and the filtered environment passed to `_bounded_shell`; append `; oracle env: isolated` to the grade detail. Create `benchmarks/cases/cat-cafe-monitoring/oracle/requirements.txt` and `benchmarks/cases/todo-api-greenfield/oracle/requirements.txt` from the imports of each `oracle/` directory; read each `deveval-*/oracle/` and add a file only where it imports something beyond `pytest` and the produced project (state the outcome per case in the commit body). In the container, time one real provision for each of the two oracle cases against a small local project and record the numbers in the commit body; if provision plus the suite's 600 s limit can exceed 15 minutes, raise the oracle activity's `start_to_close_timeout` in `B/workflow.py` in this task and say so. Run `uv run pytest -m slow tests/test_grade_oracle.py` and confirm a non-zero passed count (SG-8). Commit.

**Checkpoint**: US3 is complete. The oracle no longer uses the worker's environment.

---

## Phase 8: User Story 6 — qa and review report their own time, verdict and spend (P2)

**Goal**: the three attempt records partition the attempt's time; each carries its own role's verdict; review carries its tokens.

**Independent test**: one attempt where qa passes and the reviewer rejects yields a qa record with pass, a review record with fail, and ordered, distinct time spans.

- [x] T017 [US6] Code and qa records. RED first in `tests/code/` (the file that already drives the code step with a fake context; add a new file `tests/code/test_attempt_records.py` if none fits): for one attempt driven with a controllable clock, the code, qa and review records satisfy contract §5.1 to §5.4; with tests passing, no qa issues and the reviewer rejecting, the qa record's outcome is pass while the task does not pass (§5.5); with containment drift found and qa clean, the qa record's outcome is pass and the task verdict is unchanged from base (§5.5, §5.9); when the qa lens did not run per T001(e), no qa record is written (§5.8); the returned `TaskResult` equals the base result for each case (§5.9). Then edit `S/code/step.py`: `_code_ended = _now()` immediately before the `run_test_suite` activity; `_qa_ended = _now()` immediately after `qa_step` returns; the code record's `ended=_code_ended`; the qa record's `started=_code_ended`, `ended=_qa_ended`, outcome from tests-passed and no qa issues; `review_step(..., started=_qa_ended)`. Do not move anything out of the file. Check the line count: over 997 is SG-3. Update the benchmark-record clause in `S/code/code.md` (the sentence at line 19) to say what each of the three records spans and whose verdict it carries. Run `uv run pytest tests/code tests/qa` and `uv run pytest -m temporal tests/replay`; a failing test that asserts `duration_s` of a code, qa or review stage-ended event is updated with the reason stated in the commit body (plan rule 2); any other change is SG-9. Commit.
- [x] T018 [US6] Review spend. RED first in `tests/review/`: the review record's `cost.input_tokens` and `cost.output_tokens` equal the usage the fake role run reported (contract §5.7); the record's `started_at` is the `started` argument and `ended_at` is taken at the write (§5.3); no record when the reviewer is disabled or absent (PIN, §5.8). Then edit `S/review/step.py`: create `RoleUsage(role="reviewer", model=model)`, pass `into=` to `ctx.run_role` and `spend=` to the record builder, following `run_adversary` in the same file. Add one sentence to `S/review/review.md` on the review record's span and tokens. Run `uv run pytest tests/review tests/code`; a test asserting the review stage-ended event has no `cost_usd` is updated with the reason stated (plan rule 2). Commit.

**Checkpoint**: US6 is complete.

---

## Phase 9: User Story 7 — analyze and merge gates (P3)

**Goal**: every rejection says why; no rejection is caused by a condition only a benchmark run has; nothing is switched off without evidence.

**Independent test**: a merge that is rejected at the human gate in benchmark mode leaves a merge record naming the rejection.

- [x] T019 [US7] Diagnose (no source edits, no pipeline run), then stop. Subjects: each stored todo-api run that scored 6 of 6, and two cat-cafe runs that reached merge. Establish which merge check blocked and why, and which criteria analyze reported untraced and whether a test for each exists in the produced tree. The stored records do not say (merge and analyze rows carry quality 0.0 and no error text), and at base there is no pipeline export for benchmark children (`runs/pipeline/` holds only `bf-e2e-*` runs) and gate feedback goes to an external memory service. So use these evidence sources, in this order, and state in the document which were used for each finding: (1) check again for an export under `runs/pipeline/bench-*` and for the console and stderr logs under `runs/ops/bench-*`; read what exists; (2) **re-run the deterministic checks on the stored result**: on the host or in the container, make a detached temporary worktree of the run's `sdlc/<run_id>/integration` branch from the scratch repository (as in T014; remove the worktree afterwards; never commit to or modify a branch of the scratch repository), and call the check activities the merge step itself calls, directly against it, from a short throwaway script kept outside the repository. Take the list from the `_exec_activity(...)` calls in `S/merge/step.py:340-485` (at base: `run_integration_checks` and `measure_coverage` in `S/merge/activities.py`, plus `run_lint`, `scoped_security_scan` and `evaluate_gate`; locate each module by grep, and read the step for the inputs each takes and for which checks are absolute). Record each check's pass or fail and its detail text; (3) for analyze, read `untraced_criteria` (`S/analyze/models.py:36`) and the analyst prompt, and compare how criteria are matched (exact `(task_id, criterion)` text) with what the stored plan and the produced tests contain; the analyst's own report is not stored, so say plainly what can and cannot be established without it; (4) if (1) to (3) leave a cause unestablished, say so and ask the orchestrator whether traces exist elsewhere. Do not guess a cause. For each cause decide which of the three it is (research R-10): (1) depends on something a benchmark run cannot have; (2) a defect in the gate or in how benchmark mode configures it; (3) a correct rejection of the produced code. Write `.specify/specs/012-benchmark-record-trust/gate-diagnosis.md`: evidence per run, cause per gate and check, the class of each cause, and the proposed treatment per gate (not evaluated with its reason; repair, naming files; or stays a rejection). Commit the document, send the orchestrator its path, and **wait for the answer (SG-5)**. Do not start T021 before it.
- [x] T020 [US7] Every rejection is on the record (independent of the diagnosis answer; may run while waiting). RED first in `tests/merge/`: the absolute-failure record's `error` names the blocking checks (contract §6.2); the advisory rejection and the soft-verdict rejection each write one merge record before returning, with quality 0.0, outcome fail and `error` naming the kind; the returned strings are unchanged; with no benchmark case no activity is added (assert the recorder's activity is not scheduled; the stage-ended event is emitted as for any record). RED in `tests/analyze/`: a failing analyze record's `error` gives the count of untraced criteria and the first three (§6.1); a passing one has `error is None`. Then edit `S/merge/step.py` (`error=` on the absolute record; a record before the returns at `:526` and `:591`) and `S/analyze/step.py` (`error=`). Update `S/merge/merge.md` and `S/analyze/analyze.md`: every rejection is recorded with its cause. Run `uv run pytest tests/merge tests/analyze` and `uv run pytest -m temporal tests/replay` (SG-9). Commit.
- [x] T021 [US7] Apply the per-gate decision, exactly as the orchestrator answered T019. For each gate treated as not evaluated: RED first in that slice's tests — in benchmark mode the record has score `None`, outcome `NOT_EVALUATED`, `error` starting `not evaluated:` with the reason, and the stage's return value is what the answer specifies; outside benchmark mode the base tests pass unedited (contract §6.3, §6.4). For each repair: RED first on the defect, then the fix, inside `S/analyze/`, `S/merge/` and `B/` only. For a gate that stays a rejection: no code; one test pinning that it still rejects. Add one line per gate to contract §6.5 and to the stage's `.md`. If the answer is "no code change for either gate", this task is the contract and `.md` lines only. Run the two slices' tests and the replay suite. Commit.

**Checkpoint**: US7 is complete. Every story is implemented.

---

## Phase 10: Close-out

- [x] T022 Documents, per plan.md "Document changes": `BENCHMARK.md` (§1 record fields, cell record, one file per cell, pre-012 records; Tier A grading states, per-grade environment, `oracle/requirements.txt`, empty-diff rule, and that oracle scores from 012 on are not comparable with earlier ones; Tier B a registered file must exist and `SDLC_CASES_ROOT`; §4.1 and §4.2 the two sentences of research R-13; §5 `oracle/requirements.txt`), `README.md` (benchmark section: `KROKER_COMMIT` for a worker that cannot read git, and the pre-flight failure), `ROADMAP.md` (one entry: Phase 1 of the benchmark improvement plan landed, Phases 2 to 4 open; the "Last verified" line). File the follow-up cards of plan.md "Follow-ups to file" as one `.md` each under `.workspace/tasks/`. Run `python scripts/check_file_size.py` and read `python scripts/check_clauses.py`. Commit.
- [x] T023 Full gates. Run quickstart §1 row by row, one command per call, and §2 (stored-data checks, including the records fingerprint equal to the T001 value, `git ls-files runs/` empty, and the cat-cafe score showing only a pre-012 section). Start `.specify/specs/012-benchmark-record-trust/verification.md` with each row's command and result against the T001 baseline. Any red row is fixed in the task that owns it, with the reviewer gate, not here. Commit.
- [x] T024 The validation smoke run (SG-7: only on the orchestrator's go, in the environment the orchestrator names, per the benchmark launch runbook; nothing else running on the machine). One `sdlc benchmark run` of `benchmarks/cases/todo-api-greenfield/case.yaml`, with `KROKER_COMMIT` set to the branch head if the worker cannot read git. Check every row of quickstart §3 on the new run directory and append the run id, the commit and each row's result to `verification.md`. The new run directory under `runs/benchmarks/` is the one permitted addition there: the records fingerprint changes by exactly that directory's files (record the new line). It is not added to git (`runs/` is ignored and `git ls-files runs/` stays empty). Report the result; do not start a second run. Commit `verification.md`.

**Checkpoint**: quickstart §1 and §2 green, §3 recorded.

---

## Dependencies

```text
T001 → T002 → T003 → T004 → T005                      (US1)
        T002 → T006 ─┐
        T002 → T007 ─┼→ T008                           (US4, US5 writers; T007 needs T006)
        T002 → T009 → T010 → T011                      (readers)
        T007, T008, T011 → T012 → T013                 (US2)
        T013 → T014 → T015 → T016                      (US3)
        T002 → T017 → T018                             (US6)
        T002 → T019 ⇢ (orchestrator) ⇢ T021 ;  T002 → T020 → T021   (US7)
        all → T022 → T023 ⇢ (orchestrator) ⇢ T024
```

- T006 is the only task marked [P]: it creates a new module and edits `Dockerfile`, and can be done alongside T003 to T005 by a second executor. Everything else is sequential under the per-task reviewer gate.
- T017, T018 and T020 depend only on T002 and can be reordered by the orchestrator; T020 fits the wait after T019.
- Two points wait on the orchestrator: after T019 (SG-5) and before T024 (SG-7).

## Requirement coverage

| Story | Tasks | Requirements |
|---|---|---|
| US1 | T003, T004, T005 | FR-001 to FR-005; SC-001 (with T024), SC-008 |
| US2 | T012, T013, T009 | FR-006 to FR-009; SC-004 |
| US3 | T014, T015, T016 | FR-010 to FR-013; SC-005 |
| US4 | T006, T007, T013 | FR-014 to FR-016; SC-002 (with T024) |
| US5 | T007, T008, T009, T010, T011 | FR-017, FR-018; SC-003 (with T024) |
| US6 | T017, T018 | FR-019 to FR-022; SC-006 (with T024) |
| US7 | T019, T020, T021 | FR-023 to FR-026; SC-007 (with T024) |
| all | T002, T009 to T011, T022 to T024 | FR-027 to FR-030; SC-009 |

## Implementation strategy

- **Smallest useful increment**: T001 to T005. After it the judge can find rubrics and a broken manifest cannot start a run. It can be integrated on its own.
- **Then** the record model's writers and readers (T006 to T011), which change no behaviour a run can observe except the file a record lands in.
- **Then** the three changes that alter what a run records: cell status (T012, T013), the oracle environment (T014 to T016), attempt records (T017, T018).
- **Then** the gates, which wait on a decision.
- **Last** the one run that spends tokens.

## Phase 2: Convergence

<!-- Numbered T026, not M+1=T025: the T025 id is taken by the
orchestrator-authorized amendment (judge async/sync fix, commit
7c1f05fa), which this task also records. -->

- [x] T026 Mark T001 to T024 complete in this file (all executed, committed and reviewer-approved; evidence: git log 69c97447..78204deb and verification.md §1–§3c), and append one completed entry recording the authorized amendment T025 (judge runs the sync scoring off the event loop; RED-first, reviewer-approved, commit 7c1f05fa) so the task list matches what shipped (tasks.md bookkeeping; partial).
- [x] T025 (amendment, added outside the original list by the orchestrator's ruling after the T024 smoke runs; recorded here by T026) Fix the judge async/sync seam: `judge_artifact` runs the sync `_judge_sync` via `asyncio.to_thread`. RED-first (`test_judge_artifact_runs_the_sync_judge_off_the_event_loop`, real async path, no `_judge_fn` patch), consequential amendment to the T002 PIN (two-sided pre-012/012 invariant after the authorized smoke runs added 012 records to the stored tree), full quickstart §1 gates. Commit 7c1f05fa; proven live on the third smoke run (clarify `staged_rubric` score 1.0).
