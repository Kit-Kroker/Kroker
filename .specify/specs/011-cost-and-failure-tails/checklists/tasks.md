# Checklist: Tasks quality (011, US1 + US2)

Purpose: tasks-domain review of `tasks.md` against plan.md, data-model.md,
contracts/cost-and-budget.md, quickstart.md and spec.md (US1+US2, R1-R7
locked), before execution. Items are unit tests for the tasks list's
quality, answered by reading the artifacts and the code on main
`d1d87b23`. Created: 2026-10-06 (reviewer, `.workspace/tmp/
011-reviewer-tasks-1.md` brief).
Re-review 2: 2026-10-06 (`.workspace/tmp/reviewer-011-tasks-2.md` brief) —
all six findings resolved in the text (CHK002, CHK005, CHK012, CHK014
updated; the reachability FAIL is closed by the named, default-off mock
switch, verified feasible against `F/api/client.ts` and `mock/index.ts`).
Tally after re-review: 18 PASS.

## Format

- [x] CHK001 - Is every task a `- [ ] Tnnn [P?] [USn?] description` line
  with file paths, and are ids sequential T001-T018 with no gaps? —
  **PASS**: 18 tasks, ids sequential, every line carries file paths;
  story labels appear only on phase 3 ([US1], T008-T010) and phase 4
  ([US2], T011-T016) tasks; foundation, setup and close-out tasks are
  unlabelled. [Clarity, tasks.md §Phases]
- [x] CHK002 - Do the phase table's commit counts match the task counts?
  — **PASS after fix** (re-review 2): phase 2 now reads "5 or 6 (T005 and
  T006 may share one)"; 1 + 5-or-6 + 3 + 6 + 2 = 17-18 commits for 18
  tasks, exact. [Consistency, tasks.md §Phase order]

## Coverage

- [x] CHK003 - Does every in-scope requirement map to at least one task?
  — **PASS**: the coverage table lists FR-001, 001a, 001b, 002-009, 014,
  015, 015a, 016 and SC-001, 002, 003, 007; each row was re-derived from
  the task texts (e.g. FR-007's five tasks produce the validator table,
  the 422s, the exit-2s, CONSOLE-28 and START_RUN_MODAL-3). [Completeness,
  tasks.md §Requirement coverage]
- [x] CHK004 - Does every plan work-order step 0-16 map to a task? —
  **PASS**: 0→T001, 1→T011, 2→T012, 3→T013, 4→T002, 5→T003, 6→T004,
  7→T005, 8→T006, 9→T007, 10→T008, 11→T009, 12→T014, 13→T015,
  14→T010+T016 (split by story, in order), 15→T017, 16→T018. [Completeness,
  plan.md §Work order]
- [x] CHK005 - Does every contract §6 proof row and every clause
  (CONSOLE-10 amend, 24..29, START_RUN_MODAL-1 amend, -3) map to a task?
  — **PASS after fix** (re-review 2): all rows map; the FR-008 row now
  reads "CONSOLE-29 in `app.pw.ts` behind the mock switch;
  `entries.test.ts` …; `mock/index.test.ts` six items by default, seven
  with the switch", and T015/T016 build and use the switch. [Completeness,
  contracts §6]
- [x] CHK006 - Does every file in the plan's structure tree, and every
  "existing test changed on purpose" row, map to a task? — **PASS**:
  tree walked file by file (baseline.md→T001, verification.md→T018
  included); all eight changed-test rows map (RunView.tabs→T009,
  app.pw.ts:219→T010, run_state_model→T002, run_state_query→T003,
  fleet.store/AppHeader tests→T008, start_run_modal.spec→T014,
  app_header.spec→T008, fleet-snapshot.json→T005). [Completeness,
  plan.md §Project Structure / §Existing tests]
- [x] CHK007 - Is anything tasked that the plan does not hold? — **PASS**:
  T005's teaching rows, T007's seed values (budget 20, threshold 40,
  crossings 1 on `feature-graph-demo`), T013's
  `PipelineConfig(run_budget_usd=body.budget_usd or 0.0)`, T015's
  $60.00 = 20+40 sentence, T011's reject list (`None`, `[]`) all trace to
  contract §2.2/§1.1, research R-9/R-4, data-model §2.2. [Coverage,
  tasks.md vs plan set]

## Order and dependencies

- [x] CHK008 - Can each task end green on its own? — **PASS**: the one
  genuine coupling (T005 fixture regen vs T006 client tests) is handled
  in the text: T005 defers `check_ui.py` to the end of T006 and the two
  may share one commit when client tests are red between them, so no red
  commit lands; T006 gives the mock "only the minimum to compile" so
  `vue-tsc` passes before T007's behaviour. [Consistency, tasks.md T005/T006]
- [x] CHK009 - Are the stated dependencies right? — **PASS**: T002→T003
  (fields), T002/T003→T005 (fixture mirrors model + query), T005→T006
  (the zero-with-tokens fixture row T006's mapper test reads),
  T006→T014 (`StartRunInput.budget`), T009→T016 (CONSOLE-28 reads the
  Cost tab), T011→T012/T013; `U/app.md`/`app.pw.ts` edited only by T010
  then T016. [Consistency, tasks.md §Dependencies]
- [x] CHK010 - Are the [P] marks honest (no shared files between
  parallel tasks)? — **PASS**: T004 (usage.py + its new test) shares
  nothing with T002 (models/summary) or T003 (run_host); T012 (cli.py)
  and T013 (api.py) share nothing; T015 (GateEntry, entries.test) shares
  nothing with T014 (modal five files, ui.store). [Assumption, tasks.md
  §Parallel opportunities]
- [x] CHK011 - Is T012 feasible at parser level without Temporal? —
  **PASS**: `build_parser()` is a plain importable function (cli.py:197;
  the start subparser at :205-216), so acceptance and rejection (exit 2,
  stderr naming `--budget-usd`) test without Temporal; the start branch's
  cfg block (cli.py:428-435) is small and pure, and T012 pre-authorises
  extracting it; `tests/test_cli_role_model.py` is the stated style model
  (helper-level unit tests, no main()). [Assumption, tasks.md T012]

## Specificity and guards

- [x] CHK012 - Is a budget gate entry reachable on the mock for
  T015/T016 and quickstart §2 row 9, without changing the pinned
  six-item inbox seed? — **PASS after fix** (re-review 2): the switch is
  now named and default-off in data-model §2.4 (`MockOptions.budgetGate`,
  `MOCK_BUDGET_GATE_PARAM = 'mockBudgetGate'`, the full seventh-item
  literal, the `client.ts` pass-through expression, the
  `/?mockBudgetGate=1#/inbox` URL form); T015 builds it RED-first
  (default six / switched seven), T016 opens it on its own page load,
  and quickstart §2 row 9 uses the same URL. Feasibility verified against
  the code: `createMockApi(opts)` already takes `MockOptions`
  (mock/index.ts:295-299); the build site is one line in client.ts:6;
  the search part precedes the hash and survives hash routing; default
  off leaves `mock/index.test.ts:31` and the `app.pw.ts` badge chain
  (6/5/4/5 at :286/:307/:319/:334/:372) untouched. The seventh item is
  internally coherent with T007's seeds (budget 20, crossings 1 → round
  2, threshold 40 → the $60.00 of T015's sentence), and its shape
  matches `GateItem` (types.ts:54). [Coverage, data-model §2.4, tasks.md
  T015/T016, contract §7]
- [x] CHK013 - Is each task specific enough for a context-free executor
  (names from data-model, exact test files, RED reason, commands)? —
  **PASS**: every task names its files and the RED assertions; T003's
  (a)-(e) mirror the plan's risk row; commands live in the standing
  rules and T001/T003/T018 name the temporal rows explicitly. [Clarity,
  tasks.md all tasks]
- [x] CHK014 - Do the stop-guards cover the plan's SG-1..SG-5? — **PASS
  after fix** (re-review 2): plan SG-1→tasks SG-3, SG-2→SG-5+standing
  rule, SG-3→standing rule + SG-2, SG-4→SG-6, and plan SG-5 now rides in
  T011 itself ("take research R-5's fallback … drop the `No price found
  for` cases from the test … no clearance needed (plan SG-5)"), with
  T018 recording the outcome. [Consistency, tasks.md §Stop-guards,
  T011 vs plan.md §Stop-guards]
- [x] CHK015 - Is the temporal-tier rule carried into the tasks that
  need it? — **PASS**: standing rule "Temporal-marked files" states the
  deselect trap; T001 baselines both `-m temporal` rows; T003 re-runs
  them after the riskiest change; T018 runs quickstart §1 incl. the
  `-m temporal` row; the coverage table's SC-003 row says "under
  `-m temporal`, unchanged". [Consistency, tasks.md standing rules, T001,
  T003, T018]
- [x] CHK016 - Do the forbidden paths contradict any task's needs? —
  **PASS**: T005's script and fixture, T008's app_header files, T002's
  core/models.py (the forbidden clause is the user's pending edit being
  dirty at T001, not the file), T001's spec-set commit and T017's cards
  are all outside the list; the gate files, board, fleet_row, router and
  boundaries test are untouched by any task. [Consistency, tasks.md
  §Standing rules]
- [x] CHK017 - Does T003's intended edit match the existing tests? —
  **PASS**: three tests in `tests/test_run_state_query.py` seed
  `_role_usage` without a trace (:90, :101, :112), exactly the stated
  intended edit. [Assumption, tasks.md T003]
- [x] CHK018 - Are T001's recorded-by-reading claims real? — **PASS**:
  `STAGE_ROLES` (agents/roles.py:204) and `ALL_TEMPORAL_AGENTS`
  (agents/roles.py:287) exist; `_role_rollup` sits in the module
  `run_host.py` already imports inside `imports_passed_through`
  (run_host.py:21-33); nothing truncates `_trace`; `resolved_roles(
  PipelineConfig())` runs at request time (api.py:238,254). [Assumption,
  tasks.md T001]
