# Tasks: Corpus Acceptance (round 015, Phase 3)

**Input**: `.specify/specs/015-corpus-acceptance/` (spec.md, plan.md, cat-cafe-requirements.md)

**Tests**: required. In every code task the failing test is written first and seen red for the stated reason, then the code; both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: user stories 1 to 7, FR-001 to FR-040, SC-001 to SC-012. The skeleton is the spec's DAG, nodes A to I and run batches R0 to R3.

`B/` = `src/sdlc/benchmarks/`. "Cases" = `benchmarks/cases/`. "Names" = the Names section of plan.md. "D-n" = plan.md Design decisions. "Stored test" = `tests/test_benchmark_stored_scores.py`.

## Standing rules for every task

- **Names.** plan.md "Names" is the only source of names, field names and fixed strings. Copy; do not retype from memory. A name that is needed and not there is a stop (SG-1).
- **Baseline records are read-only.** The **records fingerprint**, on the host: `python -c "import hashlib,pathlib;fs=sorted(pathlib.Path('runs/benchmarks').rglob('*.jsonl'));h=hashlib.sha256();[h.update(str(f.relative_to('runs/benchmarks')).replace(chr(92),'/').encode()+hashlib.sha256(f.read_bytes()).digest()) for f in fs];print(len(fs),h.hexdigest())"`. Until T019 it must print `111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831` before every commit. From T019 on, the check is the **manifest**: every line of `.specify/specs/015-corpus-acceptance/baseline-records.sha256` still matches its file. `git ls-files runs/` stays empty. Any score command run during the round carries `--out <a directory outside runs/>`. A test that writes uses `tmp_path`.
- **No run in a code task.** T001 to T018 start no pipeline run and call no model. Tests that would need one use records built in memory.
- **Held-out material stays held out.** Nothing of a case's `reference/`, `oracle/`, `tasks.yaml` or `acceptance.yaml` is copied into a scratch repository, a worktree or a prompt (SG-9).
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv. Git on the branch's worktree: the host only. One test run per shell call, never two chained. `addopts` already has `-q`.
- **Convergence.** A task is not done while its named test files, `uv run ruff check .`, `uv run ruff format --check .` or `uv run mypy` (no new errors against the T001 baseline) are red, or `python scripts/check_file_size.py` reports a file over 1000 lines.
- **Commit**: one per task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`. `B/` has none of its own.
- **Forbidden paths**: the 111 baseline record files; everything under `docs/reports/`; every file under `tests/replay/`; everything under `src/sdlc/stages/`, `src/sdlc/workflows/`, `src/sdlc/harness/`; `B/oracle.py`, `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/tasks.py`, `B/error_matrix.py`, `B/task_matrix.py`, `B/importers/`; `agents/`; `interfaces/`; every `AGENTS.md`; `CLAUDE.md`; `pyproject.toml` and `uv.lock`; the `description` and `idea_summary` of every `case.yaml`; the files of a DevEval case other than `case.yaml` and `acceptance.yaml`; earlier `.specify/specs/*`; the user's uncommitted and untracked files in the primary checkout.
- **Tests that must pass unedited** (existing test functions unmodified; the one sanctioned addition is T010's new function in the Stored test): `tests/test_benchmark_stored_scores.py`; `tests/test_benchmark_legacy_records.py`; `tests/test_deveval_verify.py`; `tests/test_deveval_importer.py`; the tests of `B/error_matrix.py` and `B/task_matrix.py` that T001 lists; existing cases in `tests/test_benchmark_matrix.py` and `tests/test_benchmark_arms.py`.
- Line numbers are as of main `c3f6319c`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name or rule is needed that the spec set does not define; an edit to a forbidden path or to a "must pass unedited" test appears necessary; any test under `tests/replay/` changes result against the T001 baseline. Do not edit a test to pass.
- **SG-2** A T001 verify item fails.
- **SG-3** `src/sdlc/cli.py` would pass 900 lines, or any other file 800.
- **SG-4** Before T019 the fingerprint differs from the base value; at any time a manifest line does not match, `git ls-files runs/` prints anything, or a score was written under `runs/`.
- **SG-5** T019 to T022: no run, probe or model call before the orchestrator's clearance for that batch. A second lost run of one case: stop.
- **SG-6** T012: nothing of the cat-cafe mapping, tests or reference is written before the orchestrator confirms the requirement list was approved at GATE 2.
- **SG-7** The cat-cafe reference fails one of the 12 existing tests and the cause is the test.
- **SG-8** A `temporal` test named in a gate reports "deselected"; a test marked RED passes before its code; a PIN is red.
- **SG-9** Held-out material is found where an agent can read it.
- **SG-10** The offline acceptance half is red for a DevEval case. Report it as a finding; do not edit the case's files.

## Phase order

| Phase | DAG node | Purpose | Story | Tasks | Commits |
|---|---|---|---|---|---|
| 1 Setup + baseline | | known start, the manifest, design assumptions checked | | T001 | 1 |
| 2 Case metadata | A | role, visibility, arms | US1, US2 | T002 | 1 |
| 3 Oracle identity | B | written on new records; never mixed | US4 | T003, T004 | 2 |
| 4 Acceptance, offline | C | record, reference, floor, the command | US1 (P1) | T005, T006 | 2 |
| 5 Smoke | D | conditions, stamp, run gate | US2 (P1) | T007, T008 | 2 |
| 6 Root cause | F | rule, labels, view | US3 | T009, T010 | 2 |
| 7 Licence note | G | the finding | US7 | T011 | 1 |
| 8 cat-cafe | E | mapping, reference, 36 tests | US4 | T012, T013 | 2 |
| 9 Acceptance, separation | H | strong against weak; full verdict | US1, US6 | T014 | 1 |
| 10 Corpus status | I | the tally | US6 | T015, T016 | 2 |
| 11 Close-out of the code half | | documents, gates | | T017, T018 | 2 |
| 12 Runs | R0 to R3, I | smoke, screen, two arms, final records | US5, US6 | T019 to T023 | 5 |

Phases 5, 6 and 7 depend only on phase 2 and may be reordered by the orchestrator. Phase 8 needs phases 3 and 4. **The branch is merged after T018; phase 12 runs on that commit.**

---

## Phase 1: Setup and baseline (no source edits)

- [ ] T001 Create branch `015-corpus-acceptance` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree and that `runs/benchmarks` is visible inside it. If main has moved past `c3f6319c`, on the host run `git diff --stat c3f6319c HEAD -- src/sdlc/benchmarks src/sdlc/cli.py benchmarks BENCHMARK.md` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `python scripts/check_clauses.py`; the records fingerprint (must print the base value). Write the manifest `.specify/specs/015-corpus-acceptance/baseline-records.sha256`: one line per `*.jsonl` under `runs/benchmarks`, `<sha256 of the file>  <forward-slash path relative to runs/benchmarks>`, sorted by path; 111 lines. Then the verify items, each by reading code or files, each recorded with file:line evidence:
  (a) D-1: `CellProgress` is a frozen dataclass returned by the `summarize_cell` activity, and a payload without a new defaulted field still decodes (read how the data converter decodes dataclasses; name the test that will prove it in T003);
  (b) D-1: a cell id starts with its case id followed by `#`, for every cell `expand_matrix` builds, including a crew cell;
  (c) Names: for each of the seven corpus cases, the arm name `expand_matrix` produces today from `models:` equals `zai-coding-plan-glm-5.2`; and `extra_args_by_model` is looked up by model id, so an explicit arm with the same model keeps `--variant max`;
  (d) D-3: `_ensure_python_env` installs from a root `requirements.txt` when the tree has no packaging metadata; say what it does on an empty tree;
  (e) D-3: each DevEval case's `reference/` has no `requirements.txt`, and which cases have `reference_env/requirements.txt`;
  (f) D-4: what `grade_from_junit` returns for a suite whose modules fail to import (run `pytest` by hand on one oracle against an empty directory, outside the repo, in the container);
  (g) D-8: how `resolve_provenance` resolves the commit and the dirty flag, and that the same calls work from a detached worktree;
  (h) D-9: on the three stored 012 todo-api runs, which of the four smoke conditions each would pass (rubric scores on clarify and architecture, a commit on every record, one record file per cell, oracle all-pass);
  (i) rule 4: how a scratch repository and a run's worktree are seeded, and that nothing under Cases is copied into either except `oracle/` at grade time;
  (j) list the test files that assert on `B/error_matrix.py`, `B/task_matrix.py`, the group key of `group_runs`, the row keys of `compute_summaries`, the heatmap row key and the gate-oracle row key, and the file list `write_score` returns;
  (k) `src/sdlc/cli.py`: where the benchmark subparsers are registered and dispatched, and its line count;
  (l) whether `CaseSpec` rejects unknown keys (it must not: old workflow inputs lack the new fields, and new inputs must load in an old worker only if the user says so; report the finding).
  Write `.specify/specs/015-corpus-acceptance/baseline.md`: base sha, every command's result and counts, mypy error count, the replay result, the fingerprint line, items (a) to (l), and line counts of `src/sdlc/cli.py`, `B/cli.py`, `B/models.py`, `B/runs.py`, `B/score.py`, `B/report.py`. Any item that contradicts plan.md is SG-2: stop and report before committing anything else. Commit (spec set, baseline, manifest).

**Checkpoint**: baseline.md and the manifest exist; no source file differs from the base.

---

## Phase 2: Case metadata (DAG A; blocks everything)

**Goal**: a case states its role, its visibility and its two arms.

**Independent test**: every manifest under Cases loads and states a role and a visibility.

- [ ] T002 [US1] [US2] Role, visibility, arms. RED first in `tests/test_benchmark_models.py`: `CaseSpec` without the new keys loads with `role == corpus`, `visibility is None`, `strong_arm is None`, `weak_arm is None`; each of the four roles and two visibilities loads; an unknown role fails; `strong_arm` naming no arm in `arms` fails; `strong_arm == weak_arm` fails; one of the two set alone is allowed. RED in new `tests/test_benchmark_corpus.py`: `load_corpus(cases root)` returns ten specs; todo-api is `smoke`; cat-cafe is `corpus`, `private`; the six DevEval cases are `corpus`, `public`; add-login and crew-probe are `probe`, `private`; `smoke_case` returns todo-api and raises a clear error when zero or two cases are `smoke` (on a `tmp_path` corpus); for each of the seven corpus cases `strong_arm == "zai-coding-plan-glm-5.2"`, `weak_arm == "zai-coding-plan-glm-5.3-flash"`, both arms set exactly `dev`, `test`, `devops`, and `expand_matrix` gives two cells whose strong cell id equals the cell id the base manifest gave (PIN the base id as a literal in the test, from T001(c)). In `tests/test_deveval_corpus.py` add: every imported case states role and visibility. Add the two enums and four fields to `B/models.py` with the validator; create `B/corpus.py` with `load_corpus` and `smoke_case` only. Edit the ten `case.yaml` files: add `role` and `visibility`; on the seven corpus cases add `arms`, `strong_arm`, `weak_arm` and keep `models:` as it is; touch no `description`. Changed on purpose: `tests/test_golden_case_loads.py::test_cat_cafe_case_loads_as_one_cell` asserts one cell and cat-cafe now has two; rewrite it to assert two cells and that the strong cell id equals the base id; every other test of that file is a PIN. PIN: `tests/test_todo_api_case_loads.py`, `tests/test_benchmark_matrix.py`, `tests/test_benchmark_arms.py`, `tests/test_cell_config.py` pass unedited. Commit.

**Checkpoint**: FR-001 and FR-002 hold. A run of a corpus case would now start two cells; nothing is run.

---

## Phase 3: Oracle identity (DAG B)

**Goal**: new records carry the identity of the oracle they were graded by; runs of two identities are never mixed.

**Independent test**: two runs of one case and arm with different identities form two groups.

- [ ] T003 [US4] The identity and where it is written. RED first in new `tests/test_benchmark_oracle_id.py`: `oracle_identity` returns `sha256:` and 64 hex characters; the same tree gives the same value; a changed byte, an added file and a renamed file each change it; a `__pycache__` directory, a `.pytest_cache` directory and a `.pyc` file do not; a tree written with `\r\n` and the same tree with `\n` give the same value; a missing directory raises. RED in `tests/test_benchmark_cell.py`: `summarize_cell` for a cell whose case has an `oracle/` returns that identity, and `None` for a case without one or an unknown case (cases root at `tmp_path` through `SDLC_CASES_ROOT`); `CellProgress(last_stage=..., code_finished=...)` still constructs (PIN); `cell_record` writes `oracle_id`. RED in `tests/test_benchmark_workflow.py`: `_oracle_record` and `_oracle_task_records` write the identity they are given and `None` by default. RED in `tests/test_benchmark_models.py`: a stored-shape record without `oracle_id` loads with `None`. Create `B/oracle_id.py`; add the field to `BenchmarkRecord` and `CellProgress`; fill it in `summarize_cell` (case id = the cell id up to its first `#`; identity never raises: any error gives `None`); add an `oracle_id` keyword to `cell_record`, `_oracle_record`, `_oracle_task_records`; in `B/workflow.py` pass `progress.oracle_id` to the calls of those three functions inside the `012-cell-record` branch; the calls in the pre-012 branch are not edited. Then `uv run pytest -m temporal tests/replay` and `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`: same result as T001 (SG-1 otherwise). Commit.
- [ ] T004 [US4] The identity splits groups and rows. RED first, each on records built in memory: in `tests/test_benchmark_runs.py`, `Run.oracle_id` is taken from the cell record, else the oracle record, else `None`; two graded runs of one case, harness, arm, generation and commit with different identities form two groups; a lost run with the same identity as a graded run shares its group; in `tests/test_benchmark_grid.py`, the group header prints `oracle <8 hex>` when the identity is set and nothing when it is not; in `tests/test_benchmark_scoring.py`, `tests/test_benchmark_heatmap.py` and `tests/test_benchmark_gate_oracle.py`, two identities give two rows and no count is shared. Edit `B/runs.py` (field, group key), `B/grid.py` (header), `B/scoring.py`, `B/heatmap.py`, `B/gate_oracle.py` (row keys). PIN: the Stored test and every existing case of the five test files pass unedited (every baseline run has no identity). Commit.

**Checkpoint**: FR-014 and FR-015 hold on fixtures; every pinned figure of round 013 is unchanged.

---

## Phase 4: User Story 1 — acceptance, the offline half (P1, DAG C)

**Goal**: one command runs a case's reference and an empty tree against its oracle and writes the acceptance record.

**Independent test**: `sdlc benchmark accept --case deveval-readtime --offline` with no worker running writes a record whose reference check passed and whose floor passed fewer tests.

- [ ] T005 [US1] The record and the verdict over the offline checks. RED first in new `tests/test_benchmark_acceptance.py`: the constants of Names; `decide` with a failed reference → `rejected` / `reference`; reference passed and floor not below it → `rejected` / `floor`; both passed and no separation data → `not_assessed`; a reference check of `None` (no `reference/`) → `rejected` / `reference` with the detail text; `save_acceptance` then `load_acceptance` round-trips every field; the file is YAML, ASCII, keys in a fixed order; `load_acceptance` on a missing file returns `None`. Create `B/acceptance.py` with the models, `decide` (the separation branches return `not_assessed` until T014), `load_acceptance`, `save_acceptance`. Commit.
- [ ] T006 [US1] The offline checks and the command. RED first in new `tests/test_benchmark_offline_checks.py`, fast tier, with the environment function replaced by a stub that returns the current interpreter's environment: on a `tmp_path` case built from `tests/fixtures/mini_calc` by the importer, `run_reference_check` returns `passed`, with tests passed equal to tests total; with the reference broken it returns not passed and the detail names the failing test; with no `reference/` it returns `passed is None`; `run_floor_check` returns fewer tests passed than the reference; when the case has `reference_env/requirements.txt` and the reference has no `requirements.txt`, the file is present at the root of the checked tree (D-3) and absent from the floor tree; neither check leaves a file under the case directory; neither check is given the worker's environment variables beyond the allowlist of `B/oracle.py`. One test marked `slow` runs both checks for real on the mini_calc case. RED in `tests/test_benchmark_cli.py`: `dispatch_accept(case=..., offline=True, cases_root=tmp_path)` writes `acceptance.yaml` with verdict `not_assessed`, the identity, the test count, role, visibility, exposure `repo_public`, the commit and the date, and prints the verdict line; a case with no `language` gives `not_assessed` with the note `no oracle`; a `smoke` case with an oracle and no `reference/` (the shape of todo-api) gives `rejected` / `reference` (SC-002); the parser accepts `benchmark accept --case X --offline`. RED in `tests/test_benchmark_corpus.py` (FR-031): for every case with a `reference/`, no path under `reference/` is named in `case.yaml`; and the function that seeds a run (found in T001(i)) is given no path under Cases. Create `B/offline_checks.py` (D-3, D-4); add `dispatch_accept` to `B/cli.py` and a function there that registers the new benchmark subparsers and dispatches them; call it from `src/sdlc/cli.py` at the two places T001(k) names. Commit.

**Checkpoint**: the offline half works on a fixture. No real case has a record yet (T016).

---

## Phase 5: User Story 2 — the smoke test before any corpus run (P1, DAG D)

**Goal**: a stamp says the smoke case passed on a commit; a corpus run without one is refused.

**Independent test**: with an empty ops root, `benchmark run` on a corpus case exits non-zero with the refusal text and opens no connection.

- [ ] T007 [US2] Conditions and stamp. RED first in new `tests/test_benchmark_smoke.py`, on records built in memory: `check_smoke` returns no failure for a run with rubric-scored clarify and architecture records, a commit on every record, one record file per cell and an all-pass oracle record; each of the four conditions fails alone and is named by its constant; a commit of `unknown` or `None` on any record fails `commit_on_records`; a clarify record whose judge is not a rubric judge fails `rubric_scores`; `write_stamp` writes `<ops root>/smoke/<commit>.json` under `SDLC_OPS_ROOT`; `passing_stamp(commit)` returns the stamp when it passed, `None` when it failed, when the file is missing or unreadable, and for another commit; a later stamp for the same commit replaces the earlier. Create `B/smoke.py`. Commit.
- [ ] T008 [US2] The run gate, one arm, and the smoke command. RED first in `tests/test_benchmark_cli.py`, with the Temporal client replaced by a stub that fails the test if it is constructed: a corpus case with no stamp → `SystemExit` whose text names `sdlc benchmark smoke` and the commit; with a passing stamp for the current commit → the client is reached; with `--skip-smoke` → reached, and `smoke check skipped` is printed; a dirty tree → refused even with a stamp, and the text says the tree is dirty; a `smoke` or `probe` case → no stamp needed; a `parked` case → refused, and `--allow-parked` lets it through; `--arm zai-coding-plan-glm-5.3-flash` reduces the matrix to that arm's cells, and an unknown arm name fails before the client with the list of arm names; a `corpus` case whose matrix has more than one cell is refused without `--arm`, the text listing the arm names, and `--all-arms` lets it through; a `probe` case with two cells needs neither flag; the refusal path returns in under five seconds (SC-004). RED: `dispatch_smoke` with the run function stubbed to return a bench run id whose records are in `tmp_path` writes a passing stamp and prints `smoke: PASS <commit>`; with a failing condition it writes a failing stamp, prints each failed condition and exits non-zero. Edit `B/cli.py` (`_run_matrix` gate per D-8, the four flags, `dispatch_smoke` per D-9). The commit and the dirty flag are resolved by a small function in `B/smoke.py` that makes the same two git calls as `B/provenance.py`; `B/provenance.py` is not edited. Commit.

**Checkpoint**: FR-016 to FR-019 hold on stubs. Nothing has been run.

---

## Phase 6: User Story 3 — the failure view names the stage (P2, DAG F)

**Goal**: lost runs and failed requirements counted under planning, execution, verification or unattributed.

**Independent test**: the stored cat-cafe records give 8 lost runs under planning.

- [ ] T009 [US3] The rule and the labels. RED first in new `tests/test_benchmark_root_cause.py`, on runs and records built in memory: a lost run with last stage `research`, `clarify`, `architecture` or `plan` counts once under `planning`; a lost run with last stage `code` or any task-loop stage counts once under `execution`; a lost run with no stage recorded counts under `planning` and is noted; a graded run's oracle-task record with score below 1 and no label counts under `unattributed`; with a label it counts under the label's cause and `labelled` rises by one; a requirement with score 1 counts nowhere; a graded run with no oracle-task record adds one to `no_requirement_results`; rows are per case, harness, arm, generation and identity; every cell carries numerator and denominator (lost runs over runs started; failed requirements over requirements graded); a cell under `MIN_OBSERVATIONS` is flagged low-n; `load_labels` reads `<labels root>/<case>/<bench_run_id>.yaml`, returns nothing when the directory is absent, and raises naming the entry for an unknown cause, a `task_id` not in the case's mapping, a `run_id` not among the bench run's records, and a `run_id` of another case. Create `B/root_cause.py` without renderers. Commit.
- [ ] T010 [US3] The view in a score. RED first in `tests/test_benchmark_root_cause.py`: the HTML prints the four columns in the order of `ROOT_CAUSES`, value and denominator in every cell, the line `N failed requirements labelled by a person, M not labelled`, and the line `K graded runs have no requirement results` when K > 0; the markdown is ASCII; the JSON carries the same figures. RED in `tests/test_benchmark_score.py`: `write_score` for a one-case selection also returns `root-cause.html` and `root-cause.json`, for a case with a mapping and for a case without one (D-11). RED in `tests/test_benchmark_report.py`: `report.md` has a `## Root cause` section once, after `## Gate versus oracle`. Add a new function to the Stored test (the existing ones are not edited): cat-cafe shows 8 lost runs under planning, 0 under execution, and 10 graded runs with no requirement results. Add the renderers; wire them into `B/score.py` and `B/report.py`, imported inside the functions. Create `benchmarks/labels/README.md` (the file format, one example, the validation rules). Commit.

**Checkpoint**: US3 is complete on the stored records. SC-005 holds.

---

## Phase 7: User Story 7 — the licence note (P3, DAG G)

- [ ] T011 [P] [US7] Write `.specify/specs/015-corpus-acceptance/licence-nl2repo.md`: the date; what was checked (the repository root listing of `multimodal-art-projection/NL2RepoBench`, the licence field the GitHub API returns for it, the README, the paper page arXiv 2512.12730 for a dataset licence statement); the result of each; the conclusion (no grant to copy the requirement documents; each upstream project keeps its own licence; this repository is public); the decision (ruling R2: nothing imported). Re-check each source on the day of writing with `gh api repos/multimodal-art-projection/NL2RepoBench --jq .license` and a read of the root listing; if a licence has appeared, stop and report instead of writing the note (SG-2). Confirm with `git status` and `git diff --stat <base>..HEAD -- benchmarks` that the branch adds no file of that provenance. Commit.

---

## Phase 8: User Story 4 — cat-cafe grows (P2, DAG E)

**Goal**: 36 tests, a mapping, a reference that passes all of them.

**Independent test**: `sdlc benchmark accept --case cat-cafe-monitoring --offline` gives a passed reference check with 36 of 36 and a floor of 0.

- [ ] T012 [US4] The mapping of the 12 existing tests, and the reference. **Stop first (SG-6)**: confirm with the orchestrator that `cat-cafe-requirements.md` was approved at GATE 2, and take any change to it from the orchestrator in writing. RED first in new `tests/test_cat_cafe_case.py`: `load_task_suite("cat-cafe-monitoring")` returns the 9 requirement ids of the approved list that have a test today, with their error classes; every test function in the case's `oracle/` is in exactly one requirement and every mapped node id exists (parse with `ast`, as `tests/test_deveval_corpus.py` does); the 6 requirements whose present count is 0 are not yet in the file (they arrive in T013, since a requirement must name a test); the case's `description` equals a literal copied from the base manifest (PIN, FR-028); `reference/app.py` exists and no file under `reference/` imports from `oracle`. Write `benchmarks/cases/cat-cafe-monitoring/tasks.yaml` for the 12 tests. Write `reference/`: `app.py` exposing `app`, its `requirements.txt`, and nothing else the contract does not need; the generator starts only under `python app.py`. One test marked `slow`: `run_reference_check` on the real case passes 12 of 12 and `run_floor_check` passes 0. Run it. A reference that cannot pass an existing test because the test is wrong is SG-7. Commit.
- [ ] T013 [US4] The oracle grown to 36. For each row of the approved list, add tests up to its target, in the existing three files or new files beside them, using only the helpers of the case's `conftest.py` (add helpers there if needed; do not change an existing helper's behaviour). Every new test carries a one-line docstring citing its requirement id and the sentence of the case text it rests on, and obeys the five rules of `cat-cafe-requirements.md`. Extend `tasks.yaml` to all 15 requirements. Extend `tests/test_cat_cafe_case.py`: the oracle has between 30 and 40 tests and the count per requirement is at least the present count of the approved list; no test file contains `sleep`, `random`, `datetime.now` or `time.time`; no numeric literal is passed as a zone coordinate (the tests take coordinates from the helpers). The `slow` test now expects every test passed for the reference and 0 for the floor. Then two checks by hand, recorded in the commit body: the reference with its risk rule disabled fails only `risk_flag` tests; the reference with its 24-hour window widened fails only `mon_history_window` tests. If the reference needs a change to pass a new test, the change is made in the reference, and the reviewer checks that the test rests on the case text and not on the reference. Commit.

**Checkpoint**: FR-026 to FR-030 hold. The reviewer gate for T013 reads every new test against rule 3 of the requirement list.

---

## Phase 9: User Stories 1 and 6 — separation and the full verdict (DAG H)

**Goal**: the strong arm against the weak arm on recorded runs; every verdict and reason of the spec.

**Independent test**: one graded run per arm, 0.75 and 0.50, gives `provisional`.

- [ ] T014 [US1] [US6] Separation. RED first in `tests/test_benchmark_acceptance.py`, on runs built in memory (US1 scenarios 5 to 9, FR-007 to FR-009): strong-arm runs only, not all 1.0 → `not_assessed`; one graded run per arm with a margin of 0.15 or more → `provisional`; three per arm with the margin on the means → `accepted`; three on one arm and two on the other → `provisional`; a margin of 0.1499 → `rejected` / `no_separation`; the weak arm above the strong → `rejected` / `no_separation` with both means recorded; the strong arm at 1.0 on every graded run → `rejected` / `saturated`, with and without weak runs; the strong arm at 0.0 on every graded run → `rejected` / `degenerate`; the order of reasons when two apply (a failed reference beats saturated); runs of another identity are left out and counted in `not_comparable`; lost runs and grading failures enter nothing; a case with no `strong_arm` → `not_assessed` with a note; for a `smoke`, `probe` or `parked` case the separation check is not run and reads not assessed, while a failed reference or floor still gives `rejected`; a case parked by the screen keeps the `saturated` or `degenerate` record written before its role changed (the order in T020). Fill the separation branches of `decide`; add `separation()` (D-6); `dispatch_accept` without `--offline` loads the case's evidence with `load_evidence(case=...)`, builds runs, and runs all three checks. `SEPARATION_MARGIN` is compared with a tolerance of 1e-9 so that 0.75 minus 0.60 counts as 0.15. Commit.

---

## Phase 10: The tally (DAG I, code part)

- [ ] T015 [US6] Corpus status. RED first in `tests/test_benchmark_corpus.py`, on a `tmp_path` corpus: `corpus_status` gives one row per case with role, visibility, exposure, verdict, reason and `stale` (true when the record's identity differs from the case's present identity; false when equal; `not assessed` when there is no record); the rendered text ends with `N of 8 accepted or provisional, M of 2 private`, counting only `corpus` cases whose record is not stale; a parked case is listed with its reason and counted in neither figure; the text is ASCII. RED in `tests/test_benchmark_cli.py`: `benchmark corpus` prints it. Add `CorpusRow`, `corpus_status`, `render_corpus_status` to `B/corpus.py`; `dispatch_corpus` to `B/cli.py`. Commit.
- [ ] T016 [US1] Offline records for the seven corpus cases. In the container, one call per case, run `sdlc benchmark accept --case <id> --offline` for cat-cafe-monitoring and the six DevEval cases. Expected: reference passed with every test, floor fewer, verdict `not_assessed`. A red reference or floor on a DevEval case is SG-10: stop and report; the record is committed as it came out only after the orchestrator rules. Run `sdlc benchmark corpus` and paste its output into the commit body. Add `tests/test_benchmark_corpus.py::test_committed_records_match_their_cases`: every corpus case has an `acceptance.yaml` whose identity equals `oracle_identity` of its `oracle/` (SC-007). Commit the seven `acceptance.yaml` files and the test.

**Checkpoint**: SC-001 and SC-007 hold. The tally reads `0 of 8 accepted or provisional, 0 of 2 private`, which is the honest state before any run.

---

## Phase 11: Close-out of the code half

- [ ] T017 Documents. Edit by finding each passage by its text (plan "Document changes"): `BENCHMARK.md` section 5 (the acceptance rule; roles, visibility, exposure; the corpus table; parked cases; rounds 016 and 017), section 4.4 (the root-cause view, its rule, its limits, the labels file), and the passage on how to run a benchmark (the smoke command, the run gate, `--arm`); `README.md` (the new subcommands); `ROADMAP.md` (Phase 3 in progress, with the tally and what the runs will add). On the host: `python scripts/check_clauses.py` and read it; `python scripts/check_file_size.py`. Commit.
- [ ] T018 Full gates of the code half. One command per call, in the container: `uv run pytest`; `uv run pytest -m slow tests/test_benchmark_offline_checks.py tests/test_cat_cafe_case.py tests/test_deveval_verify.py`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: file size, clauses, the records fingerprint (the base value), `git ls-files runs/` (empty). Score cat-cafe with `--out` outside `runs/` and read the root-cause files. Write `.specify/specs/015-corpus-acceptance/verification.md`: each command and its result against the T001 baseline; SC-001 to SC-010 with evidence, SC-008 with the tally as it stands; SC-011 and SC-012 marked "awaits runs". Commit. **Report to the orchestrator: the code half is ready to merge. The run phase starts only after the merge and on the merged commit.**

---

## Phase 12: Runs (each task stops for clearance first, SG-5)

Rules for T019 to T022: every command of this phase (run, smoke, score, accept, corpus) runs with `SDLC_BENCHMARKS_ROOT` and `SDLC_OPS_ROOT` exported as absolute paths to `runs/benchmarks` and `runs/ops` of the primary checkout, in the CLI's shell and in the worker's, so that records written from the detached worktree land beside the stored ones; the commit under test is the merged commit, in a clean detached worktree; a dedicated Temporal on port 7234; no pipeline run executing (`temporal workflow list` on the live stack shows none running); one run at a time; gate policy off; every run's console output is kept under `runs/ops/`. After each batch, check the manifest. Results are committed on a follow-up branch from the merged commit; that branch does not change the worktree under test.

- [ ] T019 [US2] R0, the smoke run. Ask for clearance with the estimate (1 run, about 1.6 h, about $1.6). First verify the roots: from the detached worktree, `sdlc benchmark score --case cat-cafe-monitoring --out <outside runs/>` shows the 18 stored runs; if it shows none, the roots are wrong, stop. Run `sdlc benchmark smoke`. On PASS record the stamp's commit and the bench run id. On FAIL report the failed conditions and stop; a fix is a code change, which moves the commit and repeats R0 (plan D-12). No commit unless a note is needed in `verification.md`.
- [ ] T020 [US5] R1, the DevEval screen. Ask for clearance with the estimate (6 runs, up to 12 with retries; 6 to 12 h; under $6), restated after the first run from its measured time. For each of the six cases, in name order: `sdlc benchmark run --case <path> --arm zai-coding-plan-glm-5.2 --gate-policy off`. A lost run is repeated once; a second lost run gives the case `no result`. After each case: `sdlc benchmark score --case <id> --out <outside runs/>`, then `sdlc benchmark accept --case <id>`. Then, per US5: a result strictly between 0 and 1 keeps `role: corpus`; 0.0 or 1.0, or `no result`, sets `role: parked` in the manifest after the acceptance record is written (its verdict is `rejected` / `degenerate` or `saturated`, or `not_assessed` with the note `no result`). Commit the six acceptance records and the role changes on the follow-up branch, one commit, with a table of case, bench run id, tests passed over total and role in the body.
- [ ] T021 [US6] R2, cat-cafe on the grown oracle. Ask for clearance with the estimate (1 probe call; 2 runs, 7 to 9 h, about $4). First the probe of FR-034: one `opencode run` call on `zai-coding-plan/glm-5.3-flash`, in a throwaway directory outside the repository, with a one-line prompt; a refusal or an unknown-model error stops the task and goes to the orchestrator. Then `sdlc benchmark run --case benchmarks/cases/cat-cafe-monitoring/case.yaml --arm zai-coding-plan-glm-5.2 --gate-policy off`, and after it the same with `--arm zai-coding-plan-glm-5.3-flash`. A lost run is repeated once. Score, then `sdlc benchmark accept --case cat-cafe-monitoring`. Confirm in the score that the new runs form their own group, apart from the ten stored 12-test runs. Commit the acceptance record.
- [ ] T022 [US6] R3, the weak arm on the cases that screened in. Ask for clearance with the estimate restated from R1's measured times and the number of cases that kept `role: corpus`. For each, in name order: `sdlc benchmark run --case <path> --arm zai-coding-plan-glm-5.3-flash --gate-policy off`; a lost run is repeated once; score; `sdlc benchmark accept --case <id>`. Commit the acceptance records.
- [ ] T023 [US6] Final records and tally. Run `sdlc benchmark corpus`; update `BENCHMARK.md` section 5's corpus table and `ROADMAP.md` with the verdict of every case and the line `N of 8 accepted or provisional, M of 2 private`; list each parked case with its reason; update `verification.md` (SC-008, SC-010 to SC-012; the manifest check; every bench run id with its cost and wall-clock from the score; runs that were lost and why). File the plan's follow-ups under `.workspace/tasks/` if the orchestrator asks. Commit. The round ends here whichever batches ran: a batch the user did not clear is reported as not run, and the tally says what it would have needed.

---

## Dependencies

```text
T001 → T002 → T003 → T004
T002 → T005 → T006 → T014 → T015 → T016 → T017 → T018 → (merge) → T019 → T020 → T022 → T023
T002 → T007 → T008 ──────────────────────────────────────────────────┘ (T019 needs T008)
T002 → T009 → T010 (needs T004 for the row key)
T001 → T011
T003, T006 → T012 → T013 → T016
T018 → T019 → T021 (needs T013, T014) → T023
```

- T016 needs T013 (cat-cafe's record is taken on the grown oracle) and T006.
- T014 needs T004 (runs carry the identity) and T005.
- T021 may run before or after T020; the spec's order is R1 then R2. T022 needs T020.
- With one executor the order is the numeric order.

## Parallel opportunities

One executor seat implements, so parallelism is the orchestrator's choice. Where two executors exist: after T002, the smoke pair (T007, T008), the root-cause pair (T009, T010, after T004) and the acceptance pair (T005, T006) touch disjoint source files; `B/cli.py` and `tests/test_benchmark_cli.py` are shared by T006, T008 and T015, so those three are serial. T011 is marked [P]: it touches no source. Runs are never parallel.

## Implementation strategy

- **MVP**: T001 to T006 and T016 for the DevEval cases: the acceptance command exists and six cases have an offline record.
- **Then**: smoke and the run gate (T007, T008); the root-cause view (T009, T010); cat-cafe (T012, T013); separation and the tally (T014, T015).
- **Merge point**: T018. Everything before it is useful with no run.
- **Run tail**: T019 to T023, each batch on its own clearance. Stopping after any of them leaves committed records and an honest tally.

## Requirement coverage

| Task | Requirements |
|---|---|
| T001 | FR-038 (manifest), FR-039 |
| T002 | FR-001, FR-002, FR-011 |
| T003 | FR-014 |
| T004 | FR-015 |
| T005 | FR-008 (offline part), FR-010 |
| T006 | FR-004, FR-005, FR-006, FR-012, FR-031 |
| T007 | FR-016, FR-017 |
| T008 | FR-018, FR-019; SC-004 |
| T009 | FR-020 to FR-023, FR-025 |
| T010 | FR-020, FR-024; SC-005 |
| T011 | FR-037; SC-009 |
| T012 | FR-027, FR-028, FR-030 |
| T013 | FR-026, FR-027, FR-029, FR-030; SC-003 |
| T014 | FR-003, FR-007, FR-008, FR-009; SC-002, SC-010 |
| T015 | FR-003, FR-013 |
| T016 | SC-001, SC-007 |
| T017 | FR-040 |
| T018 | FR-038, FR-039; SC-001 to SC-010 |
| T019 | FR-016, FR-036 |
| T020 | FR-032, FR-035, FR-036; SC-011 |
| T021 | FR-033, FR-034, FR-035, FR-036; SC-012 |
| T022 | FR-033, FR-035, FR-036 |
| T023 | FR-013; SC-006, SC-008 |
