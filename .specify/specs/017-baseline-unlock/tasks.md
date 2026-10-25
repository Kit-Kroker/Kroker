# Tasks: Baseline Unlock (round 017, pre-AP0)

**Input**: `.specify/specs/017-baseline-unlock/`. These files bind every
task:
- spec.md: GATE 1 approved; amendment A-1 approved at GATE 2;
- plan.md: GATE 2 approved;
- research.md: D-1 to D-13;
- data-model.md;
- contracts/records-and-wire.md (C-1 to C-6);
- quickstart.md.

**Review**: reviewer `.workspace/tmp/reviewer-017-tasks-1.md`, verdict
APPROVE WITH FIXES (2 material, 1 medium, 2 minor), all folded in. Every
line reference was verified at `e435bd10`.
- **Finding 1:** T013 updates all four `_fold_research_usage` callers,
  including line 203.
- **Finding 2:** the ledger fold sits at two mutually exclusive sites, with
  tests for the refine-round and grounding-violation paths.
- **Finding 3:** T004's PIN covers `oracle_identity` for every stored case.
- **Finding 4:** T019's parallel window was narrowed.
- **Finding 5:** T002 records the graded scenario.

**Tests**: required. In every code task the failing test is written first
and seen red for the stated reason, then the code. Both land in that task's
one commit, so no commit on the branch is red. A test marked **PIN** pins
behaviour that already exists and must pass on first run. A red PIN is a
stop-guard (SG-1).

**Scope**: user stories US1 to US6, FR-001 to FR-061, SC-001 to SC-005.
The order follows plan.md "Steps" 0 to 9, not story priority. Item E (US5)
goes first because it is the smallest and proves the marker pattern. US2's
oracle and verdict tasks wait for the FR-027 finding.

`S/` = `src/sdlc/`. `B/` = `src/sdlc/benchmarks/`. Story labels:
- US1: analyze traces what the tree proves;
- US2: stage reach and the stalled verdict;
- US3: research cost records;
- US4: judge readers;
- US5: plan_drift ignores generated files;
- US6: pre-flight.

## Standing rules for every task

- **Names.** data-model.md §5 and the data-model tables are the only source
  of field names, wire names (`017-analyze-evidence`, `017-research-ledger`,
  `017-plan-drift-generated`) and activity names (`build_trace_inventory`,
  `read_dead_attempt_usage`). Copy them, never retype from memory. A needed
  name that is not there is a stop (SG-1).
- **Records are read-only** (plan rule 1). From T001 on, every line of
  `.specify/specs/017-baseline-unlock/baseline-records.sha256` must still
  match its file before every commit. `git ls-files runs/` stays empty. A
  test that writes uses `tmp_path`.
- **Additive only** (plan rule 2). Every new field has the data-model
  default. No existing field changes type, name or meaning.
- **Replay** (plan rule 3).
  - Each workflow-side command change sits behind its marker (contract
    C-6), and the marker is taken before the first new command.
  - Never re-record or edit a history under `tests/replay/histories/`. The
    only history added in this round is T002's, recorded on the
    pre-change code.
- **No run and no model call in a code task** (plan rule 4). T001 to T020
  start no pipeline run and make no model call. T003's optional R1 rerun
  and T021 each stop for the orchestrator's clearance.
- **Main-branch defects** found outside this round's items stop the task and
  are reported for the bug crew (plan rule 5). They are never fixed in
  place.
- **Run environment.**
  - Python runs in `kroker-dev` only (`docker exec kroker-dev uv run …`),
    after checking that its `/app` bind is this branch's tree (quickstart).
    Never the host venv.
  - Git runs on the host only.
  - One test run per shell call, never two chained. `addopts` already has
    `-q`, so add no extra `-q`.
- **Convergence.** A task is not done while any of these is red:
  - its named test files;
  - its slice suite (`tests/<slice>/`);
  - `uv run ruff check .` or `uv run ruff format --check .`;
  - `uv run mypy` (no new errors against T001's count);
  - `python scripts/check_file_size.py` (no file over 1000 lines; plan
    estimates in the Constitution Check);
  - `python scripts/check_clauses.py`.
- **Artifact boundary.** A task that changes a stage's behaviour edits that
  stage's `<stage>.md` clauses and, where its stated facts change, its
  `AGENTS.md`, in the same commit.
- **Commit**: one per code task. Subject and body only, with **no
  attribution trailers of any kind** (no `Co-Authored-By`, no generated-by
  lines). Use `git commit -F <msgfile>`, one path per `git add` argument, no
  heredocs, and write every file with the Write tool.
- **Reviewer gate** is per task and blocking. Task N+1 does not start until
  the reviewer has approved task N's diff.
- **Read first**: root `AGENTS.md`, plus the `AGENTS.md` of each slice the
  task edits (analyze, research, merge, plan, code; `S/workflows/AGENTS.md`
  for any host or orchestrator edit).
- **Forbidden paths**:
  - stored records under `runs/`;
  - everything under `docs/reports/`;
  - every existing file under `tests/replay/` (T002 only adds);
  - `pyproject.toml`, `uv.lock`, `docker-compose.yml`, `Dockerfile`;
  - `agents/` except `agents/analyst/instructions.md` (T010);
  - `interfaces/`;
  - every `case.yaml`, `acceptance.yaml` and `benchmarks/cases/**`;
  - earlier `.specify/specs/*`;
  - the user's untracked files in the primary checkout
    (`.claude/settings.json`, `docs/reports/Pipeline Canvas v4
    (standalone).html`, `docs/reports/Pipeline Canvas v5
    (standalone).html`).
- **Tests that must pass unedited** (existing test functions unmodified;
  added cases are allowed in the files a task names):
  - everything under `tests/replay/`;
  - `tests/test_benchmark_workflow_sequence.py`;
  - `tests/graph_workflow/test_host_attribution.py`;
  - `tests/research/test_sq_retry_policy.py`;
  - `tests/test_benchmark_stored_scores.py`;
  - `tests/test_benchmark_legacy_records.py`.
- Line numbers are as of main `e435bd10`. Find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

SG-1 to SG-6 are plan.md's, in force verbatim:
- **SG-1:** a replay test fails, a PIN is red, or a name is missing.
- **SG-2:** a stored record or `acceptance.yaml` would read differently.
- **SG-3:** `S/stages/code/step.py` would exceed 998 lines.
- **SG-4:** the records manifest changes.
- **SG-5:** FR-027 finds a harness cause.
- **SG-6:** the converged ignore list would change qa's or the oracle id's
  behaviour.

Added for tasks:
- **SG-7:** any paid run or model call without clearance.
- **SG-8:** a contradiction between plan.md, research.md or the contract
  and the tree as found. Report it with file:line before writing code.

## Phase order

| Phase | Plan step | Purpose | Story | Tasks | Commits |
|---|---|---|---|---|---|
| 1 Setup and baseline | 0 | known start, manifest, BenchmarkWorkflow history | | T001, T002 | 2 |
| 2 Finding first | 1 | why R1 scored 1/56 (FR-027) | US2 | T003 | 1 (doc only) |
| 3 plan_drift | 2 | generated files ignored, marker pattern | US5 (P3) | T004, T005 | 2 |
| 4 Analyze, pure | 3 | evidence models and enforcement | US1 (P1) | T006, T007 | 2 |
| 5 Analyze, workflow | 4 | inventory, start ref, step and call sites | US1 (P1) | T008, T009, T010 | 3 |
| 6 Research spend | 5 | ledger, wrapper, fold, emission | US3 (P2) | T011, T012, T013 | 3 |
| 7 Stage reach and verdict | 6 | producers, reach, stalled, oracle detail | US2 (P1) | T014 to T018 | 5 |
| 8 Judge readers | 7 | None never read as 0 | US4 (P2) | T019 | 1 |
| 9 Verification | 8 | whole-round checks, SC-003, SC-004 | | T020 | 1 |
| 10 Pre-flight | 9 | the paid todo-api run, closing commit | US6 (P1) | T021 | 1 |

**Dependencies:**
- Phase 1 blocks everything.
- Phase 2 (T003) blocks T017 and the shape of T015 and T016. Phases 3 to 6
  do not depend on it and may run while T003 is open.
- Phases 3, 4 and 6 are independent of each other. Phase 5 depends on phase
  4.
- Phase 7 depends on T003, and on T007 only for the shared
  `BenchmarkRecord` edits in `B/models.py`. It is sequenced after phase 5 to
  avoid conflicts in the same file.
- Phase 8 is independent after phase 1.
- Phases 9 and 10 come last.
- **The branch is merged after T020** (the orchestrator decides how), and
  T021 runs on the merged commit.

---

## Phase 1: Setup and baseline (no source edits)

- [ ] T001 Create the branch `017-baseline-unlock` from current main in the worktree the orchestrator names.
  - Confirm `kroker-dev` is bound to that tree (quickstart) and that `runs/benchmarks` is visible inside it.
  - If main has moved past `e435bd10`, run on the host `git diff --stat e435bd10 HEAD -- src/sdlc agents/analyst BENCHMARK.md tests` and report anything it prints (SG-8).
  - Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`.
  - On the host: `python scripts/check_file_size.py` and `python scripts/check_clauses.py`.
  - Write `.specify/specs/017-baseline-unlock/baseline-records.sha256`: one line per file under `runs/benchmarks`, `<sha256>  <forward-slash path relative to runs/benchmarks>`, sorted by path.
  - Write `.specify/specs/017-baseline-unlock/baseline.md` with:
    - base sha;
    - every command's result and counts, and the mypy error count;
    - line counts of every file plan.md "Source Code" marks M, with `S/stages/code/step.py` stated explicitly (expected 998);
    - verification by reading code that each D-n citation of research.md still holds (a contradiction is SG-8).
  - Commit the spec set (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md, tasks.md), `.specify/feature.json` (now pointing at 017), the `CLAUDE.md` plan pointer, baseline.md and the manifest.

- [ ] T002 Record one `BenchmarkWorkflow` replay history on the pre-change code (research D-6, plan step 0).
  - Read `tests/test_benchmark_workflow_sequence.py` and the history format and replay-test pattern under `tests/replay/` first.
  - Using the sequence test's stub-activity harness (no model call, no paid run), run one **graded** single-cell benchmark execution (the sequence test's scenario ii shape, so `summarize_cell`, `grade_oracle`, `_oracle_record` and the oracle-task records are all in the history; reviewer tasks finding 5) on a temporal test environment and export its history as JSON into `tests/replay/histories/benchmark_one_cell.json`.
  - Add `tests/replay/test_benchmark_replay.py`, which replays it with the production `BenchmarkWorkflow` class and the same `Replayer` setup as the existing replay tests. It carries `pytestmark = pytest.mark.temporal`.
  - Seen green on the base: `uv run pytest -m temporal tests/replay/test_benchmark_replay.py`.
  - This history is never re-recorded after this commit.
  - Commit (history and test only).

**Checkpoint**: baseline.md, the manifest and the BenchmarkWorkflow history exist, and no source file differs from the base.

---

## Phase 2: Finding first (FR-027, research D-13), US2

- [ ] T003 [US2] Establish why both R1 integration trees scored near zero (`bench-theatre-box-office-1792359046` glm-5.2, 1/56; `-1792347162` glm-5.3-flash). Read-only throughout: write nothing under `runs/`, change no scratch repo, start no run.
  - Order of sources:
    1. In the worker container, look for the theatre scratch repo and the two `sdlc/<child_run_id>/integration` branches (`MSYS_NO_PATHCONV=1 docker exec <worker> ls /srv/scratch-repos` and `git -C … branch -a`).
    2. If present, grade each integration head by hand with the case oracle through `B/offline_checks.py` tree mode (016 D-7) into a `tmp` directory, and capture pytest's exit code, the JUnit `errors` and `failures` counts, and the first collection or import error text.
    3. If absent, read the two children's Temporal histories (`temporal workflow show`) for the `grade_oracle` activity result.
    4. Read the stored records.
  - Write `.specify/specs/017-baseline-unlock/finding-1of56.md` with:
    - each source tried and what it held;
    - the cause, if established, with evidence;
    - whether it is (a) a model result (the produced code is broken), (b) the case or oracle, or (c) a harness defect;
    - whether FR-025's signal (exit 2 or 4, errors ≥ half of total) would have flagged it.
  - **Stop and report** in each of these cases:
    - (c) is SG-5: route to the bug crew and a spec amendment;
    - the FR-025 signal would not have flagged it: research D-8 is amended before T017;
    - no source survives: R1 rerun or pre-flight evidence, the orchestrator's call, SG-7.
  - Commit (the finding file only).

---

## Phase 3: User Story 5, plan_drift ignores generated artifacts (P3, FR-050)

**Goal**: generated paths never count as unhinted touches on new runs. Pre-017 histories compute drift exactly as before.

**Independent test**: `uv run pytest tests/plan/ tests/code/` and `uv run pytest -m temporal tests/replay`.

- [ ] T004 [P] [US5] Create `src/sdlc/artifacts/generated.py` with `GENERATED_DIRS` and `is_generated(path: str) -> bool` (research D-11).
  - Matching is on normalized forward-slash path segments: a path is generated if any segment is in `GENERATED_DIRS`, or matches `*.egg-info`, or the file ends `.pyc`.
  - The set is the union of the sets at `S/stages/qa/activities.py:582-585` and `B/oracle_id.py:8` (`IGNORED_DIRS`), plus `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `*.egg-info`.
  - Before switching either caller, write PIN tests of each caller's current behaviour on its own inputs: qa's lint-scope exclusion and the oracle id hash over a fixture tree. Then switch `qa/activities.py` and `B/oracle_id.py` to import the shared names.
  - The oracle-id PIN also asserts that `oracle_identity(<case>/oracle)` is byte-identical before and after the switch for **every** case under `benchmarks/cases/**`, read-only (reviewer tasks finding 3). `oracle_id` is a stored join key in records and `acceptance.yaml`, so a fixture-only PIN cannot see a change.
  - If a PIN would turn red under the union (SG-6), leave that caller on its own set and record that in the commit body.
  - Tests: `tests/test_artifacts_generated.py` (new: table of paths), plus the PIN cases in the existing qa and oracle-id test files.
  - Commit.

- [ ] T005 [US5] `S/stages/plan/models.py`:
  - `compute_plan_drift(task, files_touched, *, drop_generated: bool = False)` filters `files_touched` through `is_generated` when `drop_generated` is set. It applies the filter before the existing `not files_touched` check, so an all-generated touch list yields None, exactly as an empty one does today.
  - Add `PLAN_DRIFT_PATCH = "017-plan-drift-generated"` and `_DRIFT_V2() -> bool`, which imports `temporalio.workflow` **inside its body** and returns `workflow.patched(PLAN_DRIFT_PATCH)`. The module keeps no top-level temporalio import (research D-11 layering).
  - In `S/stages/code/step.py`, change line 778 (`plan_drift = compute_plan_drift(task, diff.get("files", []))`) to pass `drop_generated=_DRIFT_V2()`, and extend the existing import of `compute_plan_drift` (line 54) on the same line. The file must stay at ≤ 998 lines (SG-3). If the formatter wraps the line, stop.
  - Update `S/stages/plan/plan.md`'s plan-drift clause (or `code.md`'s, wherever plan drift is stated) for generated artifacts.
  - Tests:
    - unit tests in `tests/plan/test_plan_drift_generated.py` (new): with and without `drop_generated`, all-generated list → None, mixed list;
    - a subprocess test asserting that `import sdlc.stages.plan.models` leaves `temporalio` out of `sys.modules`;
    - a code-step test pinning that the unpatched path (patched → False) passes the unfiltered list. Mock `_DRIFT_V2` at the code-step import site.
  - Run `-m temporal tests/replay`.
  - Commit.

**Checkpoint**: US5 is done, and the marker pattern is proven green on replay.

---

## Phase 4: User Story 1, analyze, pure part (P1, FR-001 to FR-003, FR-005 to FR-008, FR-011)

**Goal**: one pure, table-tested enforcement function that implements contract C-2.

**Independent test**: `uv run pytest tests/analyze/test_trace_enforcement.py`.

- [ ] T006 [US1] In `S/stages/analyze/models.py`, add the data-model §1 types:
  - `Evidence`;
  - `CriterionTrace.key` and `CriterionTrace.evidence` (defaults per the data model);
  - `KeyedCriterion(key, task_id, criterion)`;
  - `criterion_keys(authoritative: list[tuple[str, str]]) -> list[KeyedCriterion]` (keys `"{task_id}#{n}"`, n 1-based within the task, in plan order);
  - `TraceInventory`, `CriterionAudit`, `TraceEnforcement`, `AnalyzeOutcome`;
  - `enforce_traces(criteria, report, inventory) -> TraceEnforcement` per research D-4 and contract C-2.

  Rules for `enforce_traces`:
  - key match first, then exact `(task_id, criterion)` text as fallback;
  - test normalization (strip `[...]`, split `::`, full node id exact, bare name only when it uniquely suffixes one entry);
  - `present` against `inventory.tree`, invalid when the path is missing and `truncated["tree"]` is set;
  - `absent` against `inventory.changed_files`, plus containment (case-sensitive substring of path or basename in the criterion text);
  - `task_unchanged` valid iff `inventory.task_changed[task_id] == 0` (None is invalid);
  - a command is never valid but is counted;
  - precedence test > file > command > empty;
  - `untraced` labels `"task_id: criterion"` in authoritative order for buckets command and empty;
  - `criteria_trace` capped at 300 criteria, refs cut to 200 characters, `truncated` set when cut.

  Leave `untraced_criteria` byte-identical (PIN: the existing `tests/analyze/test_analyst_models.py` cases pass unedited).

  Tests in `tests/analyze/test_trace_enforcement.py` (new), one table row per US1 scenario 1 to 7 plus:
  - mixed evidence;
  - failed-validation evidence falling to the next bucket;
  - key versus text fallback;
  - truncated tree;
  - unknown task count;
  - a JSON-schema check that `AnalysisReport`'s schema contains `evidence` and `key` but no workflow-computed field (research D-1).

  Commit.

- [ ] T007 [P] [US1] In `B/models.py`, add `TraceBag` (data-model §2.2) and `BenchmarkRecord.trace: TraceBag | None = None`. In `B/record_builder.py`, give `stage_record` a keyword `trace: TraceBag | None = None` that is passed through.
  - PIN: every stored record under `runs/benchmarks` validates with the new model and has `trace is None`. Test in `tests/test_benchmark_record_compat.py` (new), reading through the existing record reader. It is read-only and skips when `runs/benchmarks` is absent.
  - Unit test: `stage_record(..., trace=…)` round-trips.
  - Commit.

---

## Phase 5: User Story 1, analyze, workflow part (P1, FR-004, FR-009, FR-010)

**Goal**: the analyst sees the inventories, the step enforces the new rule under its marker, and the merge gate receives the same list.

**Independent test**: `uv run pytest tests/analyze/` and `uv run pytest -m temporal tests/replay`.

- [ ] T008 [US1] `TaskResult.start_ref: str | None = None` in `S/workflows/models.py`.
  - In `S/workflows/task_host.py` `_dev_task`, return `(await code_step(...)).model_copy(update={"start_ref": handle.branch_point or from_ref})` (research D-3). Add no command.
  - Grep every other `TaskResult(` producer and every path that returns a `TaskResult` without going through `_dev_task` (crew, seeded work, failure paths). Leave them at None, and list them in the commit body.
  - Update the `S/workflows/AGENTS.md` table only if an attribute changes (none expected).
  - Tests: a task-host unit test asserting `start_ref` is set from the handle, and a PIN that a pre-017 `TaskResult` JSON (without the field) validates.
  - Run `-m temporal tests/replay`.
  - Commit.

- [ ] T009 [US1] The `build_trace_inventory(InventoryInput) -> TraceInventory` activity in `S/stages/analyze/activities.py` (research D-3, contract C-1).
  - Inventory (a): `git diff --name-only <base_sha>` on the integration worktree.
  - Inventory (b): a stdlib `ast` scan of files matching `test_*.py` or `*_test.py` under the integration tree. Collect module-level `test*` functions and `test*` methods of `Test*` classes as `path::[Class::]name`. Never import or execute the files, and skip a file that fails to parse (count it in a `parse_errors` note).
  - Inventory (c): `git ls-files` at HEAD.
  - Inventory (d): for each `(task_id, branch, start_ref)`, `git diff --name-only <start_ref>..<branch>` from the repo the worktree belongs to. A None start ref, a missing branch or a failed diff gives `task_changed[task_id] = None`.
  - Bounds: 2,000 entries per list, paths cut to 300 characters, names to 200, `truncated` flags set.
  - Use the existing `vcs` git helpers. Add no new subprocess pattern.
  - Set `ACTIVITIES = [build_trace_inventory]` and export it in `S/stages/analyze/__init__.py`. Update `tests/analyze/test_analyze_slice_contract.py`, the analyze `AGENTS.md` (`ACTIVITIES` lines, "enforcement" invariant), and confirm the worker picks it up through `STAGE_MODULES` (`S/worker.py:140`).
  - Tests in `tests/analyze/test_trace_inventory.py` (new), on a `tmp_path` git repo:
    - a tree whose diff exceeds 60,000 characters still lists every test name;
    - a parametrized test and a class method;
    - a syntax-error test file is skipped;
    - per-task diffs where task 2 starts from task 1's head and inherits its files (task 2's own count excludes them);
    - an empty-diff task gives 0;
    - a missing branch gives None.
  - Commit.

- [ ] T010 [US1] Wire it under `ANALYZE_EVIDENCE_PATCH = "017-analyze-evidence"` (research D-1 and D-2).
  - In `S/stages/analyze/step.py`, take `workflow.patched(...)` once, before any new command.
  - **Patched path:**
    1. build keyed criteria;
    2. execute `build_trace_inventory`, with per-task `(task_id, branch, start_ref)` from `task_results`;
    3. build the prompt with `analyst_prompt_v2` (new in `prompts.py`, the contract C-1 section order and the 150,000-character cap on (a)+(b));
    4. run the role;
    5. `enforce_traces`;
    6. write the record with `trace=TraceBag(...)`;
    7. write the error text per contract C-2 (first three labels, "(command only)" marker).
  - **Unpatched path:** today's prompt, no new activity, and `untraced_criteria` as now.
  - Both paths return `AnalyzeOutcome(report, untraced)`.
  - Change both callers to read `outcome.untraced` and `outcome.report`, so the `AnalyzeResult` shape is unchanged: `S/workflows/graph_nodes/postplan.py:78-95` and `S/workflows/feature.py:531-542` (where `untraced = untraced_criteria(...)` is replaced). Add no command at either site (FeatureWorkflow grace rule).
  - Retained memory text stays as today, with the count taken from the outcome.
  - Update `agents/analyst/instructions.md` per contract C-1: the four evidence forms, keys, a command never satisfies, cite only listed tests and paths, never invent.
  - Update `S/stages/analyze/analyze.md` (evidence forms, inventories, inexpressible criteria stay untraced, record `trace`).
  - Update `S/stages/merge/merge.md` and the advisory check's message text at `S/stages/merge/step.py:455-464` from "without a test" to "without traced evidence". Change the text only. The check logic and its argument are unchanged.
  - Tests in `tests/analyze/test_analyze_patched.py` (new), with the stage context stubbed as the existing analyze tests do:
    - patched → inventory activity scheduled, prompt has the sections, untraced from `enforce_traces`, record has `trace`;
    - unpatched → no inventory activity, prompt byte-identical to the base, untraced identical to `untraced_criteria`.
  - Update the existing analyze wiring tests only where the return type changed, and say so in the commit body.
  - Run `-m temporal tests/replay` and `-m temporal tests/test_benchmark_workflow_sequence.py`.
  - Commit.

**Checkpoint**: US1 is done. A fresh run traces through evidence, and pre-017 histories replay unchanged.

---

## Phase 6: User Story 3, research cost records (P2, FR-030 to FR-034)

**Goal**: dead-attempt spend is counted, research spend reaches the trace, and the budget gate is unchanged.

**Independent test**: `uv run pytest tests/research/` and `uv run pytest tests/graph_workflow/test_host_attribution.py`.

- [ ] T011 [P] [US3] In `S/stages/research/budget_store.py`, add `append_dead_attempt(run_id: str, usage: RoleUsage) -> None` and `read_dead_attempts(run_id: str) -> list[RoleUsage]` (research D-9, data-model §4).
  - `append_dead_attempt` writes one JSON line through a single `os.write` on an `O_APPEND` file descriptor to `<runs_root>/<run_id>/research/dead-attempts.jsonl`. Create the parent directory, use the same runs-root resolution as the existing counters, and take no lock.
  - `read_dead_attempts` sums per model in first-seen order, skips corrupt lines, and returns [] for a missing file.
  - Tests in `tests/research/test_research_dead_attempts.py` (new, `tmp_path`, env `SDLC_RUNS_ROOT`):
    - append and read;
    - two models;
    - a corrupt line;
    - a missing file;
    - 20 concurrent appends from threads giving 20 lines.
  - Commit.

- [ ] T012 [US3] In `S/stages/research/stage.py`, wrap the body of `_research_subquestion_impl` after `run_usage = RunUsage()` (line 270) in one outer `try/except BaseException`.
  - If `run_usage` has input or output tokens, call `append_dead_attempt(deps.run_id, _role_usage(run_usage, inp.model, calls=1))` inside its own `try/except Exception` that logs at WARNING. Then a bare `raise`.
  - The degrade handlers (lines 307-342) keep returning and so never reach the wrapper.
  - Define the activity `read_dead_attempt_usage(run_id: str) -> list[RoleUsage]` in `stage.py`, beside the other definitions, and add it to `ACTIVITIES` in `S/stages/research/activities.py`.
  - Update `tests/research/test_research_slice_contract.py` and the research `AGENTS.md`:
    - the activities list;
    - the Gotchas line "an attempt that raises still loses its spend", rewritten to describe the ledger and its known limits (SIGKILL, hard timeout, the gate-REJECT path).
  - Tests, added to `tests/research/test_research_dead_attempts.py`:
    - an agent stub that spends then raises `ModelHTTPError` → one line and the same exception re-raised;
    - raise with zero usage → no line;
    - ledger write raising `TimeoutError` → the original exception still re-raised;
    - `CancelledError` → a line written and `CancelledError` re-raised;
    - the `BudgetExceeded` degrade path → no line (PIN: existing cap tests unedited).
  - `tests/research/test_sq_retry_policy.py` passes unedited.
  - Commit.

- [ ] T013 [US3] In `S/stages/research/step.py`:
  - change the signature to `_fold_research_usage(ctx, cfg, usage, into, *, calls: int = 1)` and update **all four** callers: line 203 (the `plan_research` fold), 225 (findings), 280 (first synthesis) and 345 (refine synthesis). `ctx` is required, never defaulted. `_fan_out_research` gains the `ctx` it passes through;
  - after pricing, emit `ctx.emit(RunEventKind.MODEL_USAGE, stage="research", role="research", model=…, calls=str(n), input_tokens=…, output_tokens=…, cache_read_tokens=…, cache_write_tokens=…, cost_usd=…)`, with the field set of `report_host.py:90-100` and `cost_usd` only when priced (research D-10);
  - fold the ledger through one local helper, `_fold_dead_attempts(ctx, cfg, run_id, research_spend)`. Under `RESEARCH_LEDGER_PATCH = "017-research-ledger"` it executes `read_dead_attempt_usage(run_id)` and folds each model total once with `calls=usage.calls`; unpatched, it does nothing. It is called at exactly **two** sites, and every execution passes exactly one of them (reviewer tasks finding 2):
    1. immediately before the grounding-violation record at line 294, on the path that returns at line 310 before any refine fan-out, so it sees the round-1 dead attempts, which are the only ones that path has;
    2. once after the refine `while` loop ends (after line 359, before `if brief_digest_val:` at line 361), covering both records at 372 and 389 after every refine fan-out.

    The gate-REJECT return at line 319 folds nothing (a Known Limit). `workflow.patched` with the same id is taken inside the helper, and taking it at either site is idempotent.

  No `_role_usage` write and no `_track_usage` call on this path. Update the research `AGENTS.md` "Fail-and-continue" lines on spend.

  Check the Cost tab's "counted toward budget" notice text (011 FR-009; find it in the dashboard or interfaces source). Report whether it matches the FR-034 split as amended (A-1). Do not edit `interfaces/`. A mismatch is reported in the commit body for a follow-up.

  Tests, added to `tests/research/test_research_dead_attempts.py` plus a stage-level test with a stub context:
  - the fold adds ledger totals once with the right `calls`;
  - a refine round with a dead attempt → its tokens reach the line 372 record;
  - the grounding-violation path → the line 294 record carries the round-1 ledger totals;
  - the `plan_research` fold emits a `MODEL_USAGE` event;
  - one `MODEL_USAGE` event per fold, with role `research`;
  - `_role_rollup` over the emitted trace includes research;
  - the unpatched path schedules no `read_dead_attempt_usage`;
  - a `RoleHost` fixture run (SC-005) whose `_check_budget` sum equals the pre-change sum with research spend present;
  - `tests/graph_workflow/test_host_attribution.py` passes unedited.

  Run `-m temporal tests/replay`. Commit.

**Checkpoint**: US3 is done.

---

## Phase 7: User Story 2, stage reach and the stalled verdict (P1, FR-020 to FR-026)

**Goal**: every new graded run carries `stage_reach` beside its unchanged score, and stalled arms resolve to `not_assessed`.

**Independent test**: the benchmark tests named below, and `uv run pytest -m temporal tests/replay/test_benchmark_replay.py`.

**Prerequisite**: T003 is closed with no open SG-5.

- [ ] T014 [US2] Producers (research D-6).
  - `BenchmarkRecord.tasks_total` and `BenchmarkRecord.blocking_checks` (data-model §2.1).
  - `stage_record(..., tasks_total=None, blocking_checks=None)`.
  - `S/stages/plan/step.py:148-163` passes `tasks_total=len(<plan>.tasks)` on the plan record.
  - `S/stages/merge/step.py` passes `blocking_checks=[c.name for c in report.blocking]` (use the attribute `GateReport` actually exposes, `S/workflows/gate.py:56,155-167`) at all four record sites (485-521, 538-556, 623-641, 643-657), `[]` on the pass.
  - These are record arguments only, so no marker (merge slice rule). Update `merge.md` and `plan.md` (the stage contracts) for the new record fields.
  - Tests: the plan record carries the count; each merge path's record carries its blocking names (extend the existing merge record tests).
  - PIN: T007's compat test still passes.
  - Commit.

- [ ] T015 [US2] `StageReach` in `B/models.py` (data-model §2.3), plus pure `final_stage_for(spec) -> str | None` and `stage_reach_from(records, final_stage) -> StageReach`, beside `cell_progress`.
  - "Finished" and `last_stage_outcome` follow data-model §2.3 exactly.
  - Add `BenchmarkRecord.stage_reach`.
  - `B/cell.py`: `summarize_cell(bench_run_id, cell_id, final_stage: str | None = None)` returns `CellProgress(..., stage_reach=stage_reach_from(records, final_stage))`, with the new dataclass field defaulted to None.
  - `B/workflow.py`, inside the existing `012-cell-record` branch (line 363 onward): pass `final_stage_for(spec)` as the third `summarize_cell` argument, then set `stage_reach=progress.stage_reach` on the oracle record (`_oracle_record` gains the keyword) and on the cell record (`cell_record` gains the keyword). Add no other command (research D-6).
  - Shape per T003's finding: if T003 amended anything, apply its amendment first.
  - Tests in `tests/test_benchmark_stage_reach.py` (new):
    - the pure function over fixture records for the R1 shape (merge FAIL, deploy off), a mid-loop code stall, a finished run, a run with no plan record (`tasks_total` None);
    - `summarize_cell` on a `tmp_path` record store.
  - Run `-m temporal tests/test_benchmark_workflow_sequence.py` (unedited, must pass) and `-m temporal tests/replay/test_benchmark_replay.py` (T002's history must replay).
  - Commit.

- [ ] T016 [US2] The stalled verdict (research D-7, contract C-4).
  - `B/runs.py`: `Run.stage_reach` is read from the cell record, None when absent.
  - `B/acceptance.py`: add `STALL_EPSILON = 0.05`, `Reason.STALLED`, `ArmEvidence.stall_points` (filled in `separation()`), and the stalled branch in `decide()` between SATURATED and DEGENERATE, with the four preconditions exactly as C-4 states them and the note `"not separable: stalled at <stage>"`.
  - Tests in `tests/test_benchmark_acceptance_stalled.py` (new):
    - two stalled arms (R1 shape) → NOT_ASSESSED stalled;
    - two arms finished at `final_stage` with PASS and ≤ ε → today's verdict;
    - one run without `stage_reach` → today's verdict;
    - stalled at different stages → today's verdict;
    - all-zero strong arm that stalled → stalled, not degenerate;
    - an SC-003 recompute: for every stored `acceptance.yaml` under `benchmarks/cases/`, recompute through the non-offline accept path on a `tmp_path` copy (quickstart §3), comparing `verdict`, `reason`, `note` and `separation` only. Skip when the stored records are absent.
  - Commit.

- [ ] T017 [US2] Oracle collection-error signal (research D-8, FR-025), as T003 confirmed or amended it.
  - `B/oracle.py`: keep `_bounded_shell`'s exit code at line 327, add `OracleGrade.exit_code` and `OracleGrade.errors` (defaults per data-model §3), and have `grade_from_junit` return the JUnit `errors` count. Update its callers in the same file; the signature change is internal to `B/oracle.py` plus its tests.
  - `B/workflow.py` `_oracle_record`: `components["exit_code"]` and `components["errors"]`, and `quality.detail` = `"collection/import errors: E of N"` under the rule. The score is unchanged (FR-026).
  - Tests: the JUnit fixtures for errors; exit 2; exit 4 (score None path unchanged); the errors-ratio threshold; and a PIN that a normal grade's score and outcome are byte-identical.
  - Commit.

- [ ] T018 [US2] `BENCHMARK.md`: document the new record fields (`trace`, `tasks_total`, `blocking_checks`, `stage_reach`, oracle `exit_code` and `errors`), the stalled verdict and the FR-034 spend split (A-1). Also document that inexpressible analyze criteria are a plan-authoring result. Keep the file under 1000 lines. Run `python scripts/check_clauses.py`. Commit.

**Checkpoint**: US2 is done.

---

## Phase 8: User Story 4, judge readers never read None as 0 (P2, FR-040)

**Independent test**: `uv run pytest tests/test_benchmark_judge_none_readers.py`, plus the existing judge retry tests.

- [ ] T019 [P] [US4] Verify first (research D-12).
  - Feed a record with `quality.score=None, judge="error"`, and an oracle-task grade with `score=None`, through every reader: `B/runs.py` (`build_runs`, `partial_credit`), `B/report.py`, `B/acceptance.py` (`separation()` lines 103-108), the grid and the rubric rollups. Grep `B/` for `.score` and `partial_credit` reads.
  - Establish when `TaskGrade.score` is None (`B/tasks.py:153,159`). If it can be None for a grading failure rather than a real 0, change `B/workflow.py:249` so that such a record is `NOT_EVALUATED`, not `FAIL`. Otherwise leave it and record why in the commit body.
  - Fix only a reader that counts None as 0.
  - The FR-060 judge-transient fixture is the existing S-batch retry tests for `B/judge.py`. Re-run them unedited and cite them in the commit body.
  - Tests in `tests/test_benchmark_judge_none_readers.py` (new).
  - Commit.

---

## Phase 9: Verification

- [ ] T020 Run quickstart §3 in full, one command per call:
  - `-m "slow or temporal"`, ruff, format, mypy (no new errors against T001), `check_file_size.py`, `check_clauses.py`;
  - SC-003 (T016's recompute over every stored `acceptance.yaml`: equal);
  - SC-004 (T007's compat test over every stored record: zero validation errors);
  - SC-005 (T013's budget-sum test);
  - the manifest check (every line of `baseline-records.sha256` matches).

  Write `.specify/specs/017-baseline-unlock/verification.md`:
  - each command's result;
  - each FR mapped to its test;
  - every SC with its evidence;
  - the final line counts (`S/stages/code/step.py` ≤ 998);
  - the list of replay markers taken.

  Commit. **Stop**: the orchestrator decides the merge. Memory says ff-merge main and push; that is an outward-facing action needing confirmation.

---

## Phase 10: User Story 6, pre-flight (P1, paid, SC-001, SC-002)

- [ ] T021 [US6] **Stop for clearance before any step** (SG-7). Then, on the merged main, follow quickstart §4:
  1. Rebuild the worker image with `--build-arg KROKER_COMMIT=$(git rev-parse --short HEAD)` and recreate it.
  2. Launch one todo-api-greenfield benchmark run against the live temporal (7233), with its per-case scratch repo and `--gate-policy off`, never in parallel with a live pipeline run.
  3. Grep the report: a lost run exits rc=0.
  4. Read the records.

  Check SC-001 item by item:
  - analyze PASS, or each untraced criterion classified by hand from `trace.criteria_trace` as expressible (a distortion, so the round failed) or inexpressible (reported);
  - `stage_reach` on the cell and oracle records;
  - research spend in the run summary's `research` role and in the stage record;
  - no judge 0 from a transient;
  - no `plan_drift` firing on generated paths.

  Append the outcome to `verification.md`, with SC-001 and SC-002 marked met or failed. Name any harness cause plainly. Do not re-run silently.

  Closing commit (`verification.md`, plus the `ROADMAP.md` line for the round if the orchestrator asks for it).

---

## Coverage

| Requirement | Tasks |
|---|---|
| FR-001 to FR-003, FR-005 to FR-008, FR-011 | T006, T007, T010 |
| FR-004 | T008, T009 |
| FR-009, FR-010 | T010 |
| FR-020 to FR-023 | T014, T015 |
| FR-024 | T016 |
| FR-025, FR-026 | T017 (after T003) |
| FR-027 | T003 |
| FR-030 to FR-032 | T011, T012, T013 |
| FR-033, FR-034 | T013, T018 |
| FR-040 | T019 |
| FR-050 | T004, T005 |
| FR-060 | the new test files of T004 to T019; the judge transient through the existing retry tests (T019) |
| FR-061 | T002, and the replay runs in T005, T008, T010, T013, T015, T020 |
| SC-001, SC-002 | T021 |
| SC-003 | T016, T020 |
| SC-004 | T007, T020 |
| SC-005 | T013, T020 |

## Parallel opportunities

- T004 runs beside T006 and T007, and T011 beside both (different files, all independent after T001 and T002).
- T007 and T006 can run in parallel (`B/models.py` and `record_builder.py` against `S/stages/analyze/models.py`).
- T019 can run after T002 and before phase 7, or after T018. It may edit `B/workflow.py:249`, which T015 and T017 also edit.
- T003 is investigation only and can run while phases 3 to 6 proceed.
- Everything else is sequential: T008 → T009 → T010, T011 → T012 → T013, and T014 → T015 → T016 → T017 → T018.
- Under the per-task reviewer gate, the orchestrator decides how much parallelism to use.

## Implementation strategy

**MVP** = phases 1 to 5 (US1): analyze stops auto-rejecting, which is the visible F8 failure and SC-001 item 1. Then:
- US3 (cost records);
- US2 (reach and verdict, gated on T003);
- US4 (verify);
- verification;
- the paid pre-flight that closes the round.

Each phase ends green and committed, so the round can stop after any checkpoint with the main branch consistent.
