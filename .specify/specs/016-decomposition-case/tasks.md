# Tasks: Decomposition Case (round 016, Phase 3)

**Input**: `.specify/specs/016-decomposition-case/` (spec.md with rulings R1 to R7 and amendments A1 to A8, plan.md)

**Review**: reviewer `.workspace/tmp/reviewer-016-tasks-1.md`, tasks checklist. VERDICT: approve with fixes (0 blocker, 0 major, 4 minor, 4 nits), all folded in. It confirmed every plan-review fix. Folded in here: the three test files T003 extends are now in plan.md's "changed on purpose" table; phase 10 rebinds `kroker-dev` to the detached worktree; the report script's baselines-only mode is in Names; the coverage rows for FR-016 and FR-007 are corrected; T007 is `[P]` and carries no story label; T006's test pattern is stated; the host path is `<store>` in every committed file; T018 says where the scratch repository goes. One more correction by the planner: T005 and T007 wait for T004 (shared files).

**Tests**: required. In every code task the failing test is written first and seen red for the stated reason, then the code. Both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: user stories 1 to 5, FR-001 to FR-030, SC-001 to SC-007. The skeleton is plan.md's work order: code half (steps 0 to 11), authoring half (steps 12 to 17), run half (steps 18 to 21).

`B/` = `src/sdlc/benchmarks/`. "Names" = the Names section of plan.md. "D-n" = plan.md Design decisions. "Store" = the private store. "Case" = `theatre-box-office`. Story labels: US1 offline acceptance, US2 hand-verification, US3 isolated store, US4 verdict after runs, US5 closing report.

## Standing rules for every task

- **Names.** plan.md "Names" is the only source of names, env vars, fields and fixed strings. Copy them; do not retype from memory. A needed name that is not there is a stop (SG-1).
- **Nothing private in the public repo** (plan rule 1). From T010 on, the `check-private-leak` hook runs on every commit. Never `--no-verify` (SG-4). Store content is read in place and never copied into a tracked file, a commit message or this spec directory. `verification.md` carries aggregates only.
- **Baseline records are read-only.** From T001 on, every line of `.specify/specs/016-decomposition-case/baseline-records.sha256` must still match its file before every commit. `git ls-files runs/` stays empty. Any score command carries `--out <a directory outside runs/>`. A test that writes uses `tmp_path`.
- **No run and no model call in a code task.** T001 to T013 start no pipeline run. The only model calls before the run half are T008's, capped at $1, under ruling R3 (SG-5).
- **Held-out material stays held out.** Nothing of a case's `oracle/`, `reference/`, `verification/`, `review/`, `tasks.yaml` or `acceptance.yaml`, in either root, is copied into a scratch repository, a worktree or a prompt (SG-9).
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv. Git on the branch worktree and on the store: the host only. One test run per shell call, never two chained. `addopts` already has `-q`.
- **Convergence.** A task is not done while its named test files, `uv run ruff check .`, `uv run ruff format --check .` or `uv run mypy` (no new errors against T001) are red, or `python scripts/check_file_size.py` reports a file over 1000 lines.
- **Commit**: one per code task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool. Store commits are separate, in the store's own repository, on the host.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff (for store tasks: on the store diff, read in place).
- **Read first**: root `AGENTS.md`. `B/` has none of its own.
- **Forbidden paths**: stored records under `runs/`; everything under `docs/reports/`; every file under `tests/replay/`; everything under `src/sdlc/stages/`, `src/sdlc/workflows/`, `src/sdlc/harness/`, `src/sdlc/eval/`; `B/workflow.py`, `B/acceptance.py`, `B/root_cause.py`, `B/calibration.py`, `B/oracle_id.py`, `B/importers/`; `agents/`; `interfaces/`; every `AGENTS.md`; `CLAUDE.md`; `pyproject.toml`, `uv.lock`; `docker-compose.yml`, `Dockerfile`; every in-repo `case.yaml`; `benchmarks/labels/`; earlier `.specify/specs/*`; the user's uncommitted and untracked files in the primary checkout.
- **Tests that must pass unedited** (existing test functions unmodified; added cases are allowed only where plan.md "Existing tests changed on purpose" lists the file): every existing test of `tests/test_benchmark_paths.py`, `tests/test_load_case_assets.py`, `tests/test_benchmark_stored_scores.py`, `tests/test_benchmark_legacy_records.py`, `tests/test_deveval_verify.py`, `tests/test_cat_cafe_case.py`, `tests/test_golden_case_loads.py`, `tests/test_benchmark_workflow_sequence.py`, everything under `tests/replay/`.
- Line numbers are as of main `f61261ba`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

SG-1 to SG-11 are plan.md's, verbatim in force. In short: SG-1 names, forbidden paths and unedited tests; SG-2 verify items; SG-3 line ceilings (`B/cli.py` 800, others 900); SG-4 leak or manifest; SG-5 any paid call or run without clearance, T008 over $1, a second lost run of one arm; SG-6 the judge proof fails at 16000; SG-7 no test, reference or variant before GATE 2; SG-8 no run before the review record; SG-9 held-out material where an agent can read it; SG-10 an `oracle/` change after R1 scores; SG-11 R1 on a worker with raw stream capture active.

## Phase order

| Phase | Plan step | Purpose | Story | Tasks | Commits |
|---|---|---|---|---|---|
| 1 Setup + baseline | 0 | known start, manifest, verify items | | T001 | 1 |
| 2 Storage (foundational) | 1, 2, 3 | second cases root; exposure; refusal text | US3 (P1) | T002, T003, T004 | 3 |
| 3 Authoring tools | 4, 5 | mapping tier and feature; tree grading | US2 (P1) | T005, T006 | 2 |
| 4 Planner judge | 6 | output budget; offline proof | (R3) | T007, T008 | 1 (+ plan value) |
| 5 Raw stream capture | 7 | R4 | | T009 | 1 |
| 6 Leak guard | 8 | hook, script, tests | US3 (P1) | T010 | 1 |
| 7 Decomposition report | 9 | plan shape, per-tier credit | US5 | T011 | 1 |
| 8 Close-out of the code half | 10, 11 | documents, gates, **merge** | | T012, T013 | 2 |
| 9 Authoring (store only) | 12 to 17 | store, list (GATE 2), case, reference, oracle, checks, review record | US1, US2, US3 | T014 to T019 | store commits only |
| 10 Runs | 18 to 21 | R0, R1, verdict, closing commit | US4, US5 | T020 to T023 | 2 |

Phases 3 to 7 depend only on phase 2 (all of it, through T004) and may be reordered by the orchestrator, except that T010 must land before T014 (the guard exists before any private content is on the machine). **The branch is merged after T013. Phase 9 moves no repo commit; phase 10 runs on the merged commit.**

---

## Phase 1: Setup and baseline (no source edits)

- [ ] T001 Create the branch `016-decomposition-case` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree and `runs/benchmarks` is visible inside it. If main has moved past `f61261ba`, on the host run `git diff --stat f61261ba HEAD -- src/sdlc/benchmarks src/sdlc/artifacts scripts .pre-commit-config.yaml BENCHMARK.md tests/conftest.py` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `python scripts/check_clauses.py`. Write `.specify/specs/016-decomposition-case/baseline-records.sha256`: one line per file under `runs/benchmarks`, `<sha256>  <forward-slash path relative to runs/benchmarks>`, sorted by path. Verify items V1 to V5 of plan.md, each by reading code, files or the venv, each recorded with file:line evidence: (V1) where pydantic-ai prints "(provider default)" and that it means `max_tokens` is None; (V2) re-run the case-reader grep (`cases_dir()`, `_default_cases_dir()`, `benchmarks/cases`, `SDLC_CASES_ROOT`) over `src/` and confirm the D-3 list is still complete; (V3) `docker-compose.override.yml` is git-ignored and compose merges its worker `volumes` and `environment` (run `docker compose config` on the host and read the worker service); (V4) whether Logfire on this machine is configured to a cloud project and whether spans carry prompt text; (V5) what `memory_retains: 0` in the 015 R2 strong-arm cell `summary.json` means (no retain attempted, or retains failed), by reading the retain path. Write `.specify/specs/016-decomposition-case/baseline.md`: base sha, every command's result and counts, the mypy error count, the replay result, V1 to V5, and line counts of `B/paths.py`, `B/cli.py`, `B/corpus.py`, `B/offline_checks.py`, `B/judge.py`, `B/tasks.py`, `src/sdlc/artifacts/capture.py`, `tests/conftest.py`, `BENCHMARK.md`. Any item that contradicts plan.md is SG-2: stop and report before committing anything else. Commit (spec set, baseline, manifest).

**Checkpoint**: baseline.md and the manifest exist; no source file differs from the base.

---

## Phase 2: User Story 3 — the private store is read alongside the in-repo cases (P1, foundational)

**Goal**: every reader of case files finds a case in either root. Nothing changes when no store is configured.

**Independent test**: with `SDLC_PRIVATE_CASES_ROOT` pointing at a `tmp_path` root holding one synthetic case, `sdlc benchmark corpus` lists it with exposure `isolated`. With the variable unset, the fast tier gives the T001 result.

- [ ] T002 [US3] The resolver (the orchestrator caveat's own task). RED first, in `tests/test_benchmark_paths.py` (added cases only): `private_cases_dir()` is None when the env var is unset or empty, and the path otherwise, read at call time; `case_roots()` is `[cases_dir()]` with no private root and adds it when configured, even if absent; `case_dir(id)` returns the primary dir, the private dir, `cases_dir()/id` when in neither (lenient), and raises `DuplicateCase` naming both paths when in both; `require_case_dir(id)` raises `CaseNotFound` naming every root, adding `private store configured at <p> but not readable` when the root is configured and not a directory; `iter_case_dirs()` returns `(root, dir)` pairs sorted by id over `*/case.yaml` in both roots and raises `DuplicateCase`; `root_exposure` gives `isolated` under the private root and `repo_public` otherwise. PIN: every existing test of the file, unedited. In `tests/conftest.py` add the autouse fixture of D-12 (`monkeypatch.delenv("SDLC_PRIVATE_CASES_ROOT", raising=False)`). Implement in `B/paths.py` per Names: still a leaf, importing nothing from the benchmark package; `cases_dir()` and `calibration_dir()` unchanged. Test command: `uv run pytest tests/test_benchmark_paths.py`, then the fast tier `uv run pytest` (same result as T001). Commit.
- [ ] T003 [US3] Call sites, exposure, corpus note, clean CLI errors. RED first: in `tests/test_benchmark_corpus.py`, a synthetic case in a `tmp_path` private root is listed by `corpus_status()` with exposure `isolated`, beside the in-repo cases; `render_corpus_status(rows)` with no `store_note` is byte-identical to today (PIN the existing render test); with each of the three notes the note line is printed; the tally counts the private case by visibility. In `tests/test_benchmark_cli.py`, `dispatch_accept` and `dispatch_verify_case` resolve a case id found only in the private root; `dispatch_accept` writes `exposure: isolated` for it and `repo_public` for an in-repo case; a duplicate id exits with `SystemExit` whose message names both paths and with no traceback; `dispatch_corpus` prints the store note. In `tests/test_benchmark_cell.py`, `tests/test_grade_oracle.py`, `tests/test_tasks_suite.py` and `tests/test_benchmark_report.py`, one added case each: the reader finds the oracle, mapping or language of a case that exists only in the private root; with no private root, the existing cases are unchanged (PIN). Change `tests/test_benchmark_corpus.py::test_reference_isolation_fr031` and `::test_committed_records_match_their_cases` to iterate `iter_case_dirs()` under the real env (`REAL_PRIVATE_ROOT` per D-12), and add `verification/` and `review/` to the isolation assertion. Implement the swaps of D-3 exactly: `B/oracle.py:280`, `B/cell.py:70`, `B/judge.py:307,311`, `B/tasks.py:83` and `B/report.py:298` (default branches only), and in `B/cli.py` accept, verify-case and corpus when `--cases-root` is absent. Replace the `exposure="repo_public"` literals at `B/cli.py:483,535` with `root_exposure(case_dir)`. Make `B/corpus.py` `corpus_status` and `render_corpus_status` follow Names. Do not swap the D-3 non-goals (smoke, DevEval import destination, eval, calibration, labels). Test commands: `uv run pytest tests/test_benchmark_corpus.py tests/test_benchmark_cli.py`, then, in a separate call, `uv run pytest tests/test_benchmark_cell.py tests/test_grade_oracle.py tests/test_tasks_suite.py tests/test_benchmark_report.py`, then the fast tier. Commit.
- [ ] T004 [US3] The refusal text of A5 (D-6). RED first, in `tests/test_benchmark_judge.py` (added cases): `load_case_assets` for a case id that is in no root and registers a rubric raises the non-retryable `MissingCaseAsset` error, and its message ends with `case <id> is in no cases root (<roots>); private root configured: no`, or `yes` when the env var is set; for a case dir that exists with one missing registered file, the message is exactly today's (PIN, no added line). PIN: `tests/test_load_case_assets.py` and every existing case of `tests/test_benchmark_judge.py`, unedited. Implement in `B/judge.py` `load_case_assets` only. Then `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` (same as T001). Test command: `uv run pytest tests/test_benchmark_judge.py tests/test_load_case_assets.py`. Commit.

**Checkpoint**: FR-017, FR-018, FR-019 (A5), FR-022 hold on synthetic stores; the fast tier equals T001 with no store.

---

## Phase 3: User Story 2 — authoring tools (P1)

**Goal**: a mapping can state tier and feature; any tree can be graded against a case's oracle in the per-grade environment, per test.

**Independent test**: `run_tree_check` on a mini case gives per-test results for an empty, a partial and a full tree.

- [ ] T005 [P] [US2] `tier` and `feature` on the mapping (A3). RED first, in `tests/test_tasks_suite.py`: a mapping without the keys loads as today (PIN); `tier` accepts `basic`, `rule`, `cross` and rejects other values; `feature` is a free string; a suite where some tasks set `tier` and others do not fails `_tier_all_or_none` and names the tasks without it. PIN: the error matrix, task matrix and root-cause tests pass unedited (they read only `id` and `error_class`). Implement in `B/tasks.py` per Names. Test command: `uv run pytest tests/test_tasks_suite.py`, then the fast tier. Commit.
- [ ] T006 [P] [US2] `run_tree_check` (D-7). RED first, in `tests/test_benchmark_offline_checks.py`, on the mini-case pattern the file already uses: a tree that passes all tests gives `passed` true and every `per_test` value true; a tree that fails one test gives that test false and the count; an empty tree gives the floor figures; `tree_dir` missing gives `passed` None with a detail. These per-test assertions follow the file's stub pattern, so they are fast. Add one real-environment test of the tree mode beside the existing `slow` one (`tests/test_benchmark_offline_checks.py` near line 164), marked `slow`. PIN: the existing reference and floor tests, unedited. Implement the third mode and `TreeCheck` in `B/offline_checks.py` per Names, reusing the reference path's environment calls unchanged. Test command: `uv run pytest -m slow tests/test_benchmark_offline_checks.py`. Commit.

**Checkpoint**: the ablation and free-choice checks of FR-011 to FR-013 have their grading primitive.

---

## Phase 4: The planner judge gets an output budget (ruling R3; the spec's "Judge output limit" edge case)

- [ ] T007 [P] The setting (D-8). RED first, in `tests/test_benchmark_judge.py`: with `_run_judge_agent`'s model replaced by a `FunctionModel` that records `info.model_settings`, both staged calls (`generate_steps` and the scoring call) receive `max_tokens == 16000` by default and the env value when `SDLC_JUDGE_MAX_TOKENS` is set (read at call time). No network. Implement `JUDGE_MAX_TOKENS_ENV`, `DEFAULT_JUDGE_MAX_TOKENS`, `judge_max_tokens()` and the `model_settings` argument in `B/judge.py` per Names. Test command: `uv run pytest tests/test_benchmark_judge.py`. Commit.
- [ ] T008 The offline proof on stored plans (R3; paid, at most $1; SG-5, SG-6). Ask the orchestrator for clearance first, stating the calls and the cap. In the container, with the host `.env` keys, write a throwaway script under `.workspace/tmp/` (never committed). It loads `runs/pipeline/bench-cat-cafe-monitoring-1792148180/.../artifacts/plan-v25.json` and `runs/pipeline/bench-cat-cafe-monitoring-1792137753/.../artifacts/plan-v24.json` with `benchmarks/cases/cat-cafe-monitoring/rubric-planner.md`. It calls `generate_steps`, then the scoring call, through the T007 code, and logs per call: usage, finish reason, wall clock. Success: on both artifacts `judge == "staged_rubric"` with a non-null score. On failure at 16000: stop (SG-6) and report the usage and finish reason. Record the result in `verification.md` part 1 (aggregates and the two scores; cat-cafe is in-repo and public). If the working value differs from 16000, change `DEFAULT_JUDGE_MAX_TOKENS` and plan.md Names in one commit with the T007 test updated to the new default; else no commit.

---

## Phase 5: Raw stream capture (R4)

- [ ] T009 [P] Opt-in raw stream (D-9). RED first, in `tests/test_session_capture.py`: with `SDLC_RAW_STREAM_DIR` unset, `capture_session` writes exactly what it writes today (PIN); with it set to a `tmp_path`, it also writes the unmodified raw stdout to `<dir>/<safe run_id>/<safe task_id>-a<attempt>.jsonl` and logs `raw stream captured: <path>`; when that write fails (unwritable dir), the normal capture still happens and returns the same values. Implement in `src/sdlc/artifacts/capture.py` per Names, inside its own try/except, before normalising. No other file. Test command: `uv run pytest tests/test_session_capture.py`, then `uv run pytest -m temporal tests/replay` (same as T001). Commit.

---

## Phase 6: User Story 3 — the leak guard (P1, rule 1)

- [ ] T010 [US3] Script, hook, tests (D-10). RED first, in new `tests/test_private_leak.py`: on a synthetic store under `tmp_path` (a fake case with an oracle test, a mapping, a reference module, a description and a rubric, all invented strings), `collect_tokens` returns the test node id, the test function name, the requirement id, the feature, the reference module and function names and 8-word shingles of the description and rubric; it excludes the six error-class names, tokens under 8 characters without `_`, and the domain words of spec R5; `scan` finds a staged line that contains a token and a line that contains an 8-word run of the description; it finds nothing in clean text; the CLI exits 0 with `private store absent; skipped` when the env var is unset; `--staged` scans only added lines of the index (in a `tmp_path` git repo); `--tracked` scans `git ls-files` content. One more test, skipped unless `REAL_PRIVATE_ROOT` is set: `--tracked` over this repository finds nothing. Create `scripts/check_private_leak.py` per Names. Add the hook `check-private-leak` to `.pre-commit-config.yaml` per Names. On the host run `pre-commit run check-private-leak --all-files` (expect the skip note) and `pre-commit run --all-files`. Test command: `uv run pytest tests/test_private_leak.py`. Commit.

**Checkpoint**: from here on, every commit is scanned. No store content exists yet.

---

## Phase 7: User Story 5 — the decomposition report

- [ ] T011 [P] [US5] `scripts/decomposition_report.py` (D-11). RED first, in new `tests/test_decomposition_report.py`, on synthetic inputs: `plan_shape` on a 4-task plan with a known diamond gives tasks 4, edges 4, longest chain 3, dangling 0; a dependency on an unknown id counts as dangling and is excluded from the chain; `latest_plan` picks `plan-v10.json` over `plan-v9.json` and reports the count; `tier_credit` over in-memory oracle-task records and a synthetic mapping with tiers gives per (arm, tier) the mean, the requirement count and the test count, uses only runs of the given oracle identity, and puts runs of another identity nowhere; the CLI output contains no task id, test name or requirement id of the synthetic case. Implement per Names. Then V6 on the stored runs, in the baselines-only mode of Names (`uv run python scripts/decomposition_report.py --baseline-plan <strong plan-v25.json> --baseline-plan <weak plan-v24.json>`; a test also covers that mode and the rule that `--case` and `--bench-run` go together): strong 10 tasks, 18 edges, chain 7; weak 10, 16, 6. A mismatch is SG-2. Test command: `uv run pytest tests/test_decomposition_report.py`. Commit.

---

## Phase 8: Close-out of the code half

- [ ] T012 Documents. Find passages by their text. `BENCHMARK.md` section 5 and 5.1: the private store (what lives there, exposure `isolated`, the tally counts private by visibility); how to run a private case (store layout, the override mount and env, `<store>` placeholder only, the host `.env` line, accept writing into the store, labels unsupported for private cases this round); research off for the private case and why; the leak hook; the new env vars `SDLC_PRIVATE_CASES_ROOT`, `SDLC_RAW_STREAM_DIR`, `SDLC_JUDGE_MAX_TOKENS`; round 016 in progress. `docker-compose.override.example.yml`: a commented block for both services, with `<store>`. No corpus row and no tally change yet (T023). Run on the host `python scripts/check_clauses.py` and read it; `python scripts/check_file_size.py`. Commit.
- [ ] T013 Full gates. One per call, in the container: `uv run pytest`; `uv run pytest -m slow tests/test_benchmark_offline_checks.py`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `pre-commit run --all-files`; the manifest check. Every result must equal T001's except added tests. Write `.specify/specs/016-decomposition-case/verification.md` part 1 (results, T008 proof, line counts). Commit. **The orchestrator merges here (fast-forward main), and that commit is the commit under test for phase 10.**

**Checkpoint**: the code half is on main. Nothing has been run.

---

## Phase 9: Authoring (private store only; no repo commit)

Every file of this phase lives in the store and is committed in the store's own repository on the host. The leak hook runs on any repo commit made meanwhile. None is expected.

- [ ] T014 [US3] Store bootstrap (run-infrastructure change; the orchestrator confirms with the user first). On the host: create `<store>` (a directory outside the repository; the orchestrator gives the path, and it is written only into the git-ignored override and `.env`) with `cases\`, `git init` it, and add a `README.md` that says what it is (no case content). Add the store mounts and env of plan Runbook to the git-ignored `docker-compose.override.yml` (worker `:ro`, kroker-dev read-write) and `SDLC_PRIVATE_CASES_ROOT=<store>\cases` to the host `.env`. Recreate `kroker-dev` and the worker. Check: in the container `uv run sdlc benchmark corpus` prints `private store: 0 case(s) at /srv/private-cases`, and `uv run pytest` equals T013 (the autouse fixture hides the store). Store commit.
- [ ] T015 [US2] Requirement list (GATE 2; SG-7). Write `<store>/cases/theatre-box-office/review/requirements.md`: a draft of the case's features (at least four, one component each, internal seams left free, ruling R5's domain), then 15 to 25 requirements. Each has an id, a feature, a tier, an error class, the sentence of the draft case text it traces to, and the tests it will get, in words (no test code). Then the list of what the case text leaves free and that no test may assert. Check the tier spread of FR-007 on the planned test counts. Reword anything that repeats an 8-word run of the spec (D-10). Store commit. Report to the orchestrator only the path and the counts (requirements, planned tests, per tier). **Stop until the orchestrator confirms the user approved the list at GATE 2.**
- [ ] T016 [US2] Case text, manifest, mapping, rubrics. Write `<store>/cases/theatre-box-office/case.yaml`: `case_id`, `idea_summary`, `description` (the case text: features, every rule the oracle asserts with its values, the frozen interface contract in the cat-cafe form, a sentence that internal structure is the implementer's choice), `mode: greenfield`, `language: python`, `repo_url: /srv/scratch-repos/theatre-box-office`, `role: corpus`, `visibility: private`, `strong_arm: zai-coding-plan-glm-5.3-flash`, `weak_arm: zai-coding-plan-glm-5.2`, the two arms exactly as cat-cafe's, `research_enabled: false`, `harnesses: [opencode]`, `models` and `extra_args_by_model` as cat-cafe's, `judge_model: anthropic:claude-sonnet-5`, `rubrics` for clarifier, architect, planner and qa (no research). Write the four rubric files, with the planner rubric scoring the plan against the case's seams (cat-cafe's planner rubric as the model). Write `tasks.yaml` from the approved list, with `tier` and `feature` on every requirement. Write `verification/check_shape.py`: it asserts FR-005 (reference 500 to 1,500 non-blank lines over at least four modules; it runs once the reference exists), FR-006 (40 to 60 tests, 15 to 25 requirements, each test in exactly one requirement) and FR-007 (at least 25% of tests `basic`, at least 20% of requirements `cross`, every feature has a `rule` requirement). In the container: `uv run sdlc benchmark corpus` lists the case `not_assessed`, exposure `isolated`; `load_task_suite("theatre-box-office")` loads. Store commit.
- [ ] T017 [US1] Reference, then oracle. Write `reference/` (FR-004: importing starts nothing; time only from caller timestamps; no network, no randomness in graded paths) and its dependency list. Then `oracle/` (`conftest.py`, the tests, `requirements.txt` only if needed), test by test against the approved list. Every test goes through the interface contract only and asserts nothing the case text leaves free (FR-003). Run `uv run sdlc benchmark accept --case theatre-box-office --offline` until the reference passes every test and the floor passes fewer. Run `verification/check_shape.py`: all bounds pass. A test that cannot be written without asserting a free choice goes back to the list (SG-7: report, do not improvise). Store commit.
- [ ] T018 [US2] Mechanical checks and the scratch repository. Write `verification/ablate-<requirement id>.patch`, one per requirement, each removing only that requirement's behaviour from `reference/`. Write `verification/variant-free/`: a full second implementation that changes every free choice listed in `review/requirements.md` (module layout, internal names and seams, unfixed parameters). Write `verification/run_checks.py`: for each patch, apply it to a temp copy of `reference/`, call `run_tree_check`, and assert that at least one of that requirement's mapped tests fails. Assert that `variant-free/` passes every test. Grade the reference three times and assert the three `per_test` maps are identical. Run it in the container: all pass (FR-010 to FR-013). Run `uv run sdlc benchmark accept --case theatre-box-office --offline` once more and keep the record it writes into the store. Create the scratch repository `/srv/scratch-repos/theatre-box-office`: on the host, under the directory the override binds at `/srv/scratch-repos`, `git init` and one empty initial commit, as the 015 cases' were. Then the first full fast tier with the store bound under the real env: `uv run pytest` (the iterate-all tests now see the case and its record). On the host, `python scripts/check_private_leak.py --tracked` finds nothing. Store commit.
- [ ] T019 [US2] The review record (review gate; SG-8). The orchestrator asks the user to read the case text, `review/requirements.md` and every test in place. Write `review/record.md` from the user's answer: reviewer, date, the oracle identity reviewed (`oracle_identity` of `oracle/`), the outcomes of FR-010 to FR-013 from T018, every finding and how it was resolved, and the human hours spent on authoring and review. Any change to `oracle/` repeats T017 and T018 for the new identity before the record is written. Store commit. **No run of the case before this record exists for the identity to be run.**

**Checkpoint**: SC-001, SC-002, SC-003 hold in the store; SC-004 holds in the repo.

---

## Phase 10: Runs (gated; on the merged commit; from a clean detached worktree with absolute roots, A8)

Rules for T020 to T023: plan.md Runbook "Checkout and roots" and "Container working tree" in full. Create the clean detached worktree of the merged commit on the host and rebind `kroker-dev` to it, as T001 binds the branch worktree; the worker is untouched by the rebind. Every command runs from that worktree, with `SDLC_BENCHMARKS_ROOT` and `SDLC_OPS_ROOT` exported as absolute paths into the primary checkout. Verify the roots first by scoring cat-cafe with `--out <outside runs/>` and seeing the stored runs. Compose worker on the live Temporal; one run at a time; nothing else running; gate policy off for smoke. A lost run exits 0: read the report. After each batch, check the manifest.

- [ ] T020 R0, the smoke run with stream capture (SG-5). Ask for clearance with the estimate (1 run, about 1.6 h, about $1.6) and the infrastructure changes (worker image rebuilt with `--build-arg KROKER_COMMIT=<merged commit>`, worker recreated with `SDLC_RAW_STREAM_DIR=/app/runs/ops/raw-stream`). Run `sdlc benchmark smoke`. On PASS record the stamp's commit and bench run id, and list the files under `runs/ops/raw-stream/`. On FAIL report the failed conditions and stop. A fix is a code change, which moves the commit and repeats R0. Then recreate the worker **without** `SDLC_RAW_STREAM_DIR` and check its log has no `raw stream captured` line after the recreate (SG-11). No commit.
- [ ] T021 [US4] R1, two arms (SG-5, SG-8, SG-11). Ask for clearance with the estimate (2 runs, about 6 to 9 h, $2 to $4), the V4 and V5 findings, and the review record's oracle identity, which must equal `oracle_identity` of the store's `oracle/` now. Run `sdlc benchmark run --case /srv/private-cases/theatre-box-office/case.yaml --arm zai-coding-plan-glm-5.3-flash` (the container path of the store mount). When it ends, read the report: graded, lost, or grading failed. Then the same with `--arm zai-coding-plan-glm-5.2`. A lost arm: report and ask for a separate clearance for one repeat (FR-024). A second loss of that arm: stop. No commit.
- [ ] T022 [US4] [US5] Verdict and evidence. Run `sdlc benchmark accept --case theatre-box-office` (writes into the store); `sdlc benchmark corpus` (expect `2 of 8 accepted or provisional, 2 of 2 private` if the verdict is `provisional`). Run `scripts/decomposition_report.py` for both R1 runs, with the two stored cat-cafe plans as baselines, output to `.workspace/tmp/`. Read `PlanDrift` per task from the R1 records. Write `verification.md` part 2, aggregates only: verdict and reason, both means, margin, run counts, plan shape per run beside cat-cafe's, partial credit per tier per arm with denominators, the number of tasks with touched-unhinted files, the manifest check. Do not edit `oracle/` (SG-10). Store commit (the record). On the host, `python scripts/check_private_leak.py --tracked` and the hook on the staged `verification.md`. Repo commit (`verification.md` only).
- [ ] T023 Closing commit. Scrub one stream from `runs/ops/raw-stream/` (todo-api only) per plan Runbook "Fixture scrub". Then grep it for the host user name and `D:\`, read it once, and save it as `tests/fixtures/opencode/<bench run id>-<task>-a<n>.jsonl`. In `BENCHMARK.md` 5.1: the case's corpus row (id, `corpus`, `private`, `isolated`, verdict, means, margin, n per arm) and the tally line. In `ROADMAP.md`: the Phase 3 status with the honest tally. File the follow-ups of plan.md into `.workspace/tasks/`, one `.md` each. Host checks: `python scripts/check_clauses.py`, `python scripts/check_file_size.py`, `pre-commit run --all-files`, the manifest. Commit. **SC-005 to SC-007 are closed by this commit's figures.**

---

## Dependencies

```text
T001 → T002 → T003 → T004
T004 → T005, T006, T007, T009, T010        (independent of each other; T005 shares B/tasks.py with T003 and T007 shares B/judge.py with T004, so none starts before T004)
T007 → T008                                 (plus a clearance)
T003 + T005 → T011
T004 … T011 → T012 → T013 → merge
merge → T014 → T015 → GATE 2 → T016 → T017 → T018 → T019 → T020 → T021 → T022 → T023
T010 → T014                                 (guard before any private content)
```

- T008 needs T007 and a clearance; it may run any time before T013.
- T011 needs T003 (`load_task_suite` across roots) and T005 (tier).
- T018 needs T006 (`run_tree_check`).
- T020 needs T019 only for ordering discipline (R0 does not touch the case), and T013's merge for the commit.

## Parallel opportunities

- After T004: T005, T006, T007, T009 (all `[P]`) touch different files from each other and may run in parallel seats, each with its own reviewer gate. They wait for T004 because T005 edits `B/tasks.py` (also edited by T003) and T007 edits `B/judge.py` (also edited by T004).
- T010 and T011 are independent of each other.
- Nothing in phases 9 and 10 is parallel: one store, one machine, one run at a time.

## Implementation strategy

- **MVP**: T001 to T004 and T010. The private store exists as a capability, with the leak guard. This alone discharges the 015 condition ("private storage is built in round 016").
- **Second increment**: T005 to T013 merged. Every tool the authoring half needs is on main.
- **Third increment**: T014 to T019. An offline-green, hand-verified private case (SC-001 to SC-003).
- **Last**: T020 to T023, the paid runs and the verdict. Stopping before them leaves a complete, unrun case.

## Coverage

| Task | Requirements |
|---|---|
| T002, T003 | FR-017, FR-018, FR-022, US3-1/2/3, SC-004 |
| T004 | FR-019 (A5), US3-6 |
| T005 | FR-006, FR-007 (A3) |
| T006 | FR-011, FR-012, FR-013 |
| T007, T008 | R3 |
| T009, T020, T023 | R4 |
| T010 | FR-021, US3-5, SC-004 |
| T011, T022 | FR-028, US5, SC-006 |
| T012 | FR-029 |
| T013 | gates; A6 |
| T014 | FR-016, FR-019 (store visible), FR-020 |
| T015 | FR-007 (planned spread), FR-009, GATE 2 |
| T016 | FR-001, FR-002, FR-003, FR-004, FR-007 (`check_shape.py`), FR-008, FR-016, A2 |
| T017 | FR-003, FR-004, FR-005, FR-006, FR-007 (bounds run), FR-010, US1, SC-001 |
| T018 | FR-010, FR-011, FR-012, FR-013, SC-001, SC-002, SC-003 |
| T019 | FR-014, FR-015, US2, SC-002 |
| T020, T021 | FR-023, FR-024, FR-025 (A8), US4 |
| T022 | FR-026, FR-027, US4, SC-005, SC-007 |
| T023 | FR-027, FR-029, FR-030, SC-005 |
| rules, every task | FR-030 (manifest), FR-021 (hook), SC-007 (no oracle edits after scores) |
