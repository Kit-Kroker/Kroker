# Tasks: Cost Visibility and Run Budget (011, US1 + US2)

**Input**: `.specify/specs/011-cost-and-failure-tails/` (spec.md, plan.md, research.md, data-model.md, contracts/cost-and-budget.md, quickstart.md)

**Tests**: required (spec FR-005; plan "Work order"; contract §6). In every task the failing test is written first and seen red for the stated reason, then the code; both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: US1 and US2 only (ruling R1). US3, US4, US5, FR-010 to FR-013 and SC-004 to SC-006 belong to a follow-up S-batch run and have no task here.

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. "Contract" = `contracts/cost-and-budget.md`. "Names" = `data-model.md`. "R-n" = `research.md`.

## Standing rules for every task

- **Names.** `data-model.md` is the only source of names, fixed strings and test ids. Copy; do not retype from memory. If a name you need is not there, stop (SG-1). Read its §3 traps table before every task.
- **One price rule.** Dollars are printed only through `F/shared/cost.ts` (`rowPrice`, `totalPrice`, `priceLabel`). No `money(` on a value that can be null or zero-with-tokens; no `?? 0` on a cost. The reviewer checks this on every client diff.
- **The gate is not touched.** No edit in `src/sdlc/workflows/role_host.py`, `graph.py`, `feature.py`, `src/sdlc/stages/code/step.py`, any file under `tests/replay/`, or `tests/test_budget_gate.py`. Nothing writes harness usage into `_role_usage`.
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv. Client: `python scripts/check_ui.py` from the repository root on the host; do not call `npm`, `npx`, `vitest` or `playwright` directly for a gate. One test run per shell call, never two chained. `addopts` already has `-q`. Benchmark agents are live on this machine: run one suite at a time.
- **Temporal-marked files.** `tests/test_budget_gate.py` and `tests/test_model_usage_capture.py` carry `pytestmark = pytest.mark.temporal`. Without `-m temporal` they are deselected even when named. A deselect is not a pass.
- **Convergence.** A Python task is not done while its named test files, `ruff check`, `ruff format --check` or `mypy` (no new errors against the T001 baseline) are red. A client task is not done while `check_ui.py` is red or reports a skipped step.
- **Commit**: one per task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`, and the nearest `AGENTS.md` to any Python package you edit (`src/sdlc/workflows/`, `src/sdlc/stages/code/`, `src/sdlc/dashboard/` where present).
- **Forbidden paths**: those under "The gate is not touched", plus `src/sdlc/operator/`, `src/sdlc/stages/research/`, `.github/`, `F/app/boundaries.test.ts`, `F/app/router.ts`, `F/features/board/`, `F/features/graphs/`, `U/src/components/fleet_row/`, every `AGENTS.md`, `CLAUDE.md`, `package.json` and lock files, earlier `.specify/specs/*`, and the user's uncommitted and untracked files in the primary checkout (`agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `docs/reports/*`, the pending edit in `src/sdlc/core/models.py`: if that file is dirty in your tree at T001, stop and ask). `F/api/__fixtures__/fleet-snapshot.json` is changed only by running `python scripts/dump_dashboard_fixtures.py`.
- **Styles**: tokens only (`var(--*)`, pass-three names); no bare hex in a component. Playwright assertions carry no hex and no pixel values. Clause ids use underscores; the `// clause: X-N` marker sits on the same line as its test.
- Line numbers are as of main `d1d87b23`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name, test id or rule is needed that the spec set does not define, or the T001 name check differs from data-model §1.
- **SG-2** An edit to a forbidden path appears necessary.
- **SG-3** Any test under `tests/replay/` or `tests/test_budget_gate.py` changes result against the T001 baseline, other than the known flake `budget_arch_reject-sandboxed`. Do not edit a test to pass.
- **SG-4** An existing test fails after a change and neither this file nor plan.md "Existing tests changed on purpose" names it as an intended edit.
- **SG-5** `_role_rollup` cannot be called from `run_host.py` without a sandbox error or an import outside the existing passed-through block (plan SG-2).
- **SG-6** `check_ui.py` reports a skipped step, or a test in a file this run does not touch times out or fails (known load flake card). Report; do not fix.
- **SG-7** Any file would exceed 1000 lines, a new `@kroker/ui` component appears necessary, or `tests/test_fleet_fixture_fresh.py` or `tests/test_graph_fixtures_fresh.py` needs an edit.
- **SG-8** A test this file marks RED passes before its code, or a PIN is red.

## Phase order

| Phase | Purpose | Story | Plan steps | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | known start, name check | — | 0 | 1 |
| 2 Foundation | honest wire, price rule, client model | US1, US2 | 4 to 9 | 5 or 6 (T005 and T006 may share one) |
| 3 Cost visibility | header and Cost tab | US1 | 10, 11, 14 | 3 |
| 4 Budget at start | validator, CLI, API, form, inbox note | US2 | 1 to 3, 12, 13, 14 | 6 |
| 5 Close-out | documents, card, gates | — | 15, 16 | 2 |

Phase 4's T011 to T013 depend on nothing in phases 2 and 3 and may be done first if the orchestrator wants the server half of US2 early; the order below is the default.

---

## Phase 1: Setup and baseline (no source edits)

- [X] T001 Create branch `011-cost-and-failure-tails` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree (`docker exec kroker-dev git -C /app rev-parse HEAD` equals the branch head). If main has moved past `d1d87b23`, run `git diff --stat d1d87b23 HEAD -- src/sdlc/workflows src/sdlc/dashboard src/sdlc/core/models.py src/sdlc/cli.py src/sdlc/stages/code/usage.py src/sdlc/observability src/sdlc/agents scripts/dump_dashboard_fixtures.py interfaces README.md ROADMAP.md` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py`; `uv run pytest -m temporal tests/replay`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_ui.py`; `python scripts/check_clauses.py`; `python scripts/check_file_size.py`. Do the name check of data-model §4. Confirm by reading and record: `_role_rollup` is in the module `run_host.py` already imports `build_run_summary` from inside `imports_passed_through` (R-1); nothing truncates `_trace`; the proposer role list for R-5 (from `src/sdlc/agents/roles.py`, `ALL_TEMPORAL_AGENTS` / `STAGE_ROLES`); `dashboard/api.py` already calls `resolved_roles(PipelineConfig())` at request time. Write `.specify/specs/011-cost-and-failure-tails/baseline.md`: base sha, every command's result and counts, the exact state of `budget_arch_reject-sandboxed`, mypy error count, Vitest and Playwright counts, `check_clauses.py` summary, name-check outcome, and line counts of `src/sdlc/cli.py`, `src/sdlc/core/models.py`, `src/sdlc/workflows/run_host.py`, `F/api/http.ts`, `F/api/mock/index.ts`, `U/app.md`, `U/app.pw.ts`. Commit (spec set + baseline).

**Checkpoint**: baseline.md exists with every gate's result; no source file differs from the base.

---

## Phase 2: Foundation (blocks both stories)

- [X] T002 Additive wire fields. RED in `tests/test_run_state_model.py` (shared-field list gains the new names; a `RunState` built without them has None for both) and `tests/test_run_summary_model.py` (a summary JSON without `budget_counted_usd` loads with None), and in `tests/test_run_summary_build.py` (`build_run_summary(..., budget_counted_usd=1.5)` sets it; omitted → None). Then add to `src/sdlc/core/models.py`: `RunState.budget_threshold_usd`, `RunState.budget_counted_usd`, `RunSummary.budget_counted_usd` exactly as data-model §2.1; and to `src/sdlc/observability/summary.py` the `build_run_summary` keyword `budget_counted_usd: float | None = None`. Nothing else in either file changes.

- [X] T003 Live run state from the trace. RED in `tests/test_run_state_query.py`: (a) a host with a `MODEL_USAGE` trace event for role `dev` and no `_role_usage` entry for it lists `dev` in `roles`; (b) `cost_usd_total` equals the sum of the rows whose `cost_usd` is not None, and is None when none is priced; (c) for a seeded run every role in `_role_usage` appears in `roles` with equal tokens and dollars (PIN-style equality, plan risk row 1); (d) with a budget of 40: `budget_threshold_usd == 40.0`, `budget_counted_usd` equals the priced sum of `_role_usage`; after `_budget_threshold` is raised to 80 the state reports 80; (e) with no budget both are None. Existing tests in this file that seed `_role_usage` without the trace are updated to seed the trace too (intended edit). Then edit only `_snapshot_run_state` and `_retro` in `src/sdlc/workflows/run_host.py`: `roles = _role_rollup(self._trace)`; total from those rows; the two budget fields; `_retro` passes `budget_counted_usd` to `build_run_summary` (None without a budget). Import `_role_rollup` on the existing import line inside the passed-through block (SG-5 otherwise). After green, run `uv run pytest -m temporal tests/replay` and `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py` once each and compare with baseline (SG-3).

- [X] T004 [P] Missing price stays missing (FR-015a). RED in new fast-tier `tests/test_code_attempt_usage.py`: `_record_attempt_usage` with a fake context capturing `emit` and a `HarnessRunResult` whose `cost_usd` is None emits an event with no `cost_usd` key; with `cost_usd=0.0` and with `0.25` the key is present with that value; `_role_rollup` over the no-key event leaves role `dev` with `cost_usd is None` and its tokens intact. Then change only the `ctx.emit(...)` call in `src/sdlc/stages/code/usage.py` so `cost_usd` is passed only when `run.cost_usd is not None`. Update the function's docstring sentence about `cost_usd` to match. Do not touch `stages/code/step.py`.

- [X] T005 Fixture. In `scripts/dump_dashboard_fixtures.py` teach, on existing rows where possible: one open row with a budget, `budget_threshold_usd`, `budget_counted_usd`, one crossing, and three roles of which one has tokens and `cost_usd=0.0` and one has `cost_usd=None`; one closed row with `budget_counted_usd`; keep at least one closed row with `roles=[]` and a positive total (N9). Any new row carries an explicit `project_key` and is not added to the pinned sets in `tests/test_fleet_fixture_fresh.py` (SG-7 if that file needs an edit). Run the script to regenerate `F/api/__fixtures__/fleet-snapshot.json`; never hand-edit it. `uv run pytest tests/test_fleet_fixture_fresh.py` green. Client tests that read the fixture are fixed in T006, so run `check_ui.py` only at the end of T006; T005 and T006 are reviewed as two diffs and may share one commit if `check_ui.py` is red between them (say so in the commit body).

- [X] T006 Client model and the price rule. RED first: new `F/shared/cost.test.ts` covering every rule of data-model §2.4 (`tokensOf`; `rowPrice` four cases incl. cost 0 with tokens → `not-priced`, cost null no tokens → `no-usage`; `totalPrice` priced / partial / not-priced / no-usage / no-roles-with-wire-total / no-roles-zero-total; `priceLabel` four labels; no rule returns dollars a row did not carry); `F/shared/format.test.ts` gains `tokens(12340) === '12,340'` and the renamed `budgetPct(counted, threshold)` cases; `F/api/http.test.ts` gains: `mapRun` and `mapClosed` fill `roles` (camelCase), `budgetThreshold` (closed → null), `budgetCounted`, `budgetCrossings` (missing → 0), `budgetNotice: null`, and `cost` is null for the fixture row whose only priced-looking value is a zero with tokens. Then: `F/api/types.ts` additions exactly as data-model §2.4 (existing names and signatures unchanged); new `F/shared/cost.ts`; `F/shared/format.ts` (`tokens`, `budgetPct` parameter rename); `F/api/http.ts` mappers and the optimistic row (`budget` from the input, `roles: []`, `budgetNotice` from the response; send `budget_usd` only when `input.budget` is not null). Add the new required `Run` fields to every `Run` literal the type checker reports: known `F/features/run/RunView.tabs.test.ts`, `RunView.test.ts`, `F/features/fleet/*.test.ts`, `F/shared/fleet.store.test.ts`, `F/shared/stageStrip.adapter.test.ts`, `F/shared/stageState.test.ts`, `F/app/RunPage.test.ts`, `F/app/shell.stores.test.ts`, `F/app/App.test.ts`; `StartRunInput` literals gain `budget: null` (`F/app/shell/StartRunModal.vue` passes `budget: null` for now). No assertion in those files changes. `F/api/mock/index.ts` gets only the minimum to compile (new fields on seeds, `roles: []`), its behaviour is T007.

- [X] T007 Mock parity. RED in `F/api/mock/index.test.ts`: seeds include the four cases of contract §2.2; after `tickCosts` every run with roles has `cost` equal to `totalPrice(roles, …).usd`; `startRun({ …, budget: 5 })` returns a row with `budget === 5` and a non-null `budgetNotice` containing `BUDGET_SCOPE_NOTE`, and with `budget: null` a null notice. Then implement in `F/api/mock/index.ts` (R-7): seed roles on existing runs (keep `feature-graph-demo` as the budget run: budget 20, three roles, one not priced, `budgetThreshold` 40, `budgetCounted`, `budgetCrossings` 1, status unchanged), add the no-roles closed case and the all-not-priced case on existing seeded runs where possible, `tickCosts` per R-7, `startRun` budget. The inbox seed, `removeItem` and the six-item count do not change. `check_ui.py` fully green: the existing app-tier tests must still pass with the new seeds (SG-4 otherwise).

**Checkpoint**: Python fast tier and the two temporal rows match baseline plus the new tests; `check_ui.py` green; nothing on screen has changed yet except fleet rows that showed `$0.00` for an unpriced run now show `—`.

---

## Phase 3: User Story 1 - See what a run costs (P1)

**Goal**: the Cost tab is live for open and closed runs; no figure reads `$0.00` for a missing price; the header total is honest.

**Independent test**: on the mock, open `feature-graph-demo?tab=cost`: one row per role, one "not priced" with tokens, total marked partial, budget block with counted, percent, crossings and the scope sentence.

- [X] T008 [US1] Header total (R-8, CONSOLE-27). RED: `F/shared/fleet.store.test.ts` (`totalCost` is `{ usd, excluded }`: sum over non-null `cost`; `usd` null when none; `excluded` counts runs whose total is `not-priced` or `partial`); `F/app/shell/AppHeader.test.ts` (the four strings of contract §4: `$12.40`, `$12.40 · 3 not priced`, `not priced`, `—`); `U/src/components/app_header/app_header.spec.ts` (label reads `spend`; with no `totalCost` prop the placeholder is `—`). Then `F/shared/fleet.store.ts`, `F/app/shell/AppHeader.vue`, `U/src/components/app_header/AppHeader.vue` (label, default), `app_header.md` (failure-modes sentence per contract §5.3), and `app_header.profiles.ts` only if a profile pins the old default. These three existing tests change on purpose (plan table).

- [X] T009 [US1] Cost tab (R-6, contract §3). RED: new `F/features/cost/CostTab.test.ts`, one test per row of the two tables in contract §3 (loading; no usage; no breakdown; rows with tokens and price labels; not-priced row prints `not priced` and never `$0.00`; totals; research note present in every state; budget block for no budget / open with budget incl. percent = counted over threshold / closed with budget and no percent), using the test ids of data-model §2.6; `F/features/run/RunView.tabs.test.ts`: the existing "Gates and Cost are disabled…" test becomes "Gates is disabled; Cost is disabled without a `#cost` slot" and a new test "with a `#cost` slot, `?tab=cost` shows the slot content, selecting Cost sets `?tab=cost`, selecting Graph clears it" (intended edit); `F/app/RunPage.test.ts` gains "fills the cost slot". Then: `F/features/run/RunView.vue` (typed `cost` slot, the same mechanism as `#board` but with its own shape `{ runId: string }`, `hasCostSlot`, tab enabled only with the slot, `active` gains the cost branch, panel renders the slot; Gates unchanged; update the header comment); new `F/features/cost/CostTab.vue` (imports only `shared/fleet.store`, `shared/cost`, `shared/format`, `api/types`, `@kroker/ui`); `F/app/RunPage.vue` fills `#cost`. `RunView` must not import `features/cost/`.

- [X] T010 [US1] Console clauses for US1. In `U/app.md`: amend CONSOLE-10 (`?tab=cost` → `?tab=gates`, nothing else), add CONSOLE-24, CONSOLE-25, CONSOLE-26, CONSOLE-27 with the wording of contract §5.1, and the failure-modes sentence. In `U/app.pw.ts`: the CONSOLE-10 test navigates to `?tab=gates` (intended edit); add one or more tests per new clause on the mock, each citing its clause on the test's line: CONSOLE-24 (rows, total, `?tab=cost` opens and survives reload), CONSOLE-25 (a `cost-row-price` reads `not priced`; the total reads partial; no `cost-row-price` or `cost-total-price` text equals `$0.00`), CONSOLE-26 (budget, counted, percent, crossings and note visible on the budget run; the no-budget sentence on a run without one), CONSOLE-27 (header spend contains `not priced`). Use non-running seeded runs or assertions that do not depend on the ticker. `python scripts/check_clauses.py`: no uncovered CONSOLE-24..27, no dangling citation.

**Checkpoint**: US1 is complete and demonstrable on the mock; quickstart §2 rows 1 to 6 pass.

---

## Phase 4: User Story 2 - Set a budget when starting a run (P1)

**Goal**: a budget can be given from the CLI and the dashboard; 0 and non-numbers are rejected before anything starts; the person is told what the budget counts.

**Independent test**: `POST /runs` with `budget_usd: 5` reaches the starter with `run_budget_usd == 5.0` and returns the notice; with `0` it answers 422 naming `budget_usd`; the CLI rejects `--budget-usd 0` with exit 2.

- [X] T011 [US2] The validator and the notice (R-4, R-5). RED in new `tests/test_run_budget.py`: the table of contract §1.1 against `parse_run_budget` (accepts `5`, `5.5`, `"5"`, `" 5 "`; rejects `0`, `"0"`, `0.0` with a message equal to `BUDGET_ZERO_HINT`; rejects `-1`, `"abc"`, `True`, `"nan"`, `"inf"`, `None`, `[]` with `ValueError`); `budget_notice(PipelineConfig())` is None; with `run_budget_usd=5` it starts `Budget $5.00 ` and contains `BUDGET_SCOPE_NOTE`; with a planning role overridden to a model `compute_price` does not know it ends with `No price found for: <role>.`; with all known it has no such sentence; a role that is not a planning role is never listed. Then new `src/sdlc/run_budget.py` exactly as data-model §2.2. The planning-role set is the one recorded in baseline.md by T001. Not imported by any workflow module. If the probe needs registry loading the test environment does not do, or raises, take research R-5's fallback (the fixed sentence only, drop the `No price found for` cases from the test), record it in the commit body and in verification.md, and continue: no clearance needed (plan SG-5).

- [X] T012 [P] [US2] CLI flag. RED in new `tests/test_cli_budget.py` (parser level, in the style of `tests/test_cli_role_model.py`): `start --title t --budget-usd 5` parses to `5.0`; absent → None; `0`, `-1`, `abc` exit with code 2 and stderr names `--budget-usd` (and for `0` contains `omit it`); the config the start branch builds carries `run_budget_usd == 5.0` when given and `0.0` when absent (extract the few lines that build `cfg` into a small function in `cli.py` if that is the only way to test it without Temporal; keep `cli.py` under 1000 lines). Then `src/sdlc/cli.py`: the argument per data-model §2.3, `cfg.run_budget_usd`, and printing `budget_notice(cfg)` on its own line after the run id when not None.

- [X] T013 [P] [US2] API. RED in `tests/test_dashboard_api.py` (new cases only): `POST /runs` without `budget_usd` calls the starter with `run_budget_usd == 0.0` and returns `budget_notice` null (PIN for today's behaviour plus the new key); with `5` and with `"5"` the starter gets `5.0` and the response carries the notice; with `0`, `-1`, `"abc"`, `true` the answer is 422, `detail[0].loc` ends with `budget_usd`, the starter was not called, and for `0` the message contains `omit it`. Then `src/sdlc/dashboard/api.py`: `StartBody.budget_usd` with a `mode="before"` validator calling `parse_run_budget` (None passes through), `StartedRun.budget_notice`, and `PipelineConfig(run_budget_usd=body.budget_usd or 0.0)` passed to `start_run`; the fleet-capacity path is unchanged.

- [X] T014 [US2] Start form (R-10). RED: `U/src/components/start_run_modal/start_run_modal.spec.ts` (START_RUN_MODAL-1 payload gains `budget`, `''` when empty: intended edit; START_RUN_MODAL-3: `0`, `-1`, `abc` show `start-budget-error` with the matching message and block submit; `5` submits with `budget: '5'`; empty submits); `start_run_modal.pw.ts` one test citing START_RUN_MODAL-3; `F/app/shell/StartRunModal.test.ts` (exists; new cases, and its existing `startRun` call expectation gains `budget: null`): a payload with `budget: '5'` calls `fleet.startRun` with `budget: 5`, `''` with `budget: null`; when the returned run has a `budgetNotice` a toast shows it. Then: the library modal's five files (`StartRunModal.vue` input `start-budget-input`, `initialBudget` prop, inline error, payload; `start_run_modal.md` per contract §5.2; profiles gain one with a budget error if the showcase needs it), `F/app/ui.store.ts` (`startBudget`, reset), `F/app/shell/StartRunModal.vue` (pass and convert; toast). Tokens only in the new styles.

- [X] T015 [P] [US2] Budget gate note in the inbox (R-9, FR-008). RED in `F/features/inbox/entries.test.ts`: a `GateItem` with `gate: 'budget'` whose run row has `budget 20`, `budgetThreshold 40` renders `gate-budget-note` with `Approve raises the limit to $60.00 and the run continues. Any other decision ends the run.`; with no run row the amount is omitted; a gate that is not `budget` renders no note. Then `F/features/inbox/GateEntry.vue` reads the run through `shared/fleet.store` (`getOrLoad(item.runId)`), amount through `money`. The decide event and `GateDecision` usage do not change. Also in this task, the mock switch of data-model §2.4: RED in `F/api/mock/index.test.ts` (default: six inbox items, none with `gate: 'budget'`; `createMockApi({ budgetGate: true })`: seven, the seventh exactly as data-model gives it); then `MockOptions.budgetGate`, `MOCK_BUDGET_GATE_PARAM` and the conditional seventh item in `F/api/mock/index.ts`, and the one-line pass-through in `F/api/client.ts`. The default seed and the six-item count do not change.

- [X] T016 [US2] Console clauses for US2. `U/app.md`: CONSOLE-28 and CONSOLE-29 with the wording of contract §5.1. `U/app.pw.ts`: CONSOLE-28 (open the start form, budget `0` shows the error and no run is added; budget `5` starts a run whose Cost tab shows the budget); CONSOLE-29 (open `/?mockBudgetGate=1#/inbox`; the budget entry shows `gate-budget-note` with the text of contract §4; this test uses its own page load so the badge-count chain of the other inbox tests is untouched). The clause is cited from `app.pw.ts`, because `check_clauses.py` reads only `*.spec.ts` and `*.pw.ts`. `check_clauses.py`: no uncovered CONSOLE-24..29 or START_RUN_MODAL-3.

**Checkpoint**: US2 is complete from both entry points; quickstart §2 rows 7 to 9 and §3 pass.

---

## Phase 5: Close-out

- [X] T017 Documents and the card. Apply the "Document changes" table of plan.md to `README.md`, `interfaces/dashboard/frontend/README.md` and `ROADMAP.md` (FR-601, FR-701 with the E-19 meaning, SC-10, Last verified); touch `PRD.md` only if its FR-701 text states what the gate counts, and say so in the commit body either way. Do not edit any `AGENTS.md`; list the two orchestrator-owned updates (plan GATE 2 item 7) in the final report. Write `.workspace/tasks/2026-10-06-budget-gate-counts-all-recorded-spend.md` (size M, queued behind the golden-trace flake fix; cite spec N5, N6 and ruling R6), and two more cards: research-stage spend is in neither the trace nor the role list (N5), and a role priced on some calls only is not marked (N8). `python scripts/check_file_size.py` green.

- [X] T018 Full gates and the record. Run every row of quickstart §1, one per call, and compare with baseline.md; walk quickstart §2 on the mock and §3 in the container. Confirm with `git diff --stat <base>..HEAD` that no forbidden path changed. Write `.specify/specs/011-cost-and-failure-tails/verification.md`: each command, its result and counts against baseline; the state of `budget_arch_reject-sandboxed`; the manual-walk table with what was seen; any stop-guard that fired and its clearance; the R-5 probe outcome (kept or fallback); deviations, including the no-trailer commit rule. Mark tasks done in this file. Commit.

---

## Dependencies

- T001 → everything.
- T002 → T003, T005. T003 → T005. T004 is independent of T002/T003. T005 → T006 → T007.
- US1: T006, T007 → T008, T009 → T010.
- US2: T011 → T012, T013. T006, T007 → T014, T015 (T015 also edits `F/api/mock/index.ts` and its test, after T007). T013, T014, T015, T009 → T016 (CONSOLE-28 reads the Cost tab).
- T010, T016 → T017 → T018.

`U/app.md` and `U/app.pw.ts` are edited by T010 and T016 only, in that order.

## Parallel opportunities

One executor seat and a blocking reviewer gate per task make the run sequential in practice. Where the orchestrator splits work: T004 beside T002/T003; T012 and T013 beside each other after T011; T015 beside T014. T011 to T013 touch no client file and can run while phase 3 is under review.

## Requirement coverage

| Requirement | Tasks |
|---|---|
| FR-001, FR-002 | T009, T010 |
| FR-001a | T003, T009 |
| FR-001b | T002, T003, T009, T010 |
| FR-003, FR-004 | T006, T007, T008, T009, T010 |
| FR-005 | T010, T016 |
| FR-006 | T012, T013, T014 |
| FR-007 | T011, T012, T013, T014, T016 |
| FR-008 | T015, T016 |
| FR-009 | T011, T012, T013, T014 |
| FR-014, SC-007 | T017 |
| FR-015 | T003 (replay and gate rows unchanged), T018 |
| FR-015a | T004 |
| FR-016 | T002, T005, T018 |
| SC-001 | T009, T010 |
| SC-002 | T012, T013, T014, T016 |
| SC-003 | T003, T018 (`tests/test_budget_gate.py` under `-m temporal`, unchanged) |

## Implementation strategy

MVP is phases 1 to 3: the Cost tab and an honest header, which need no budget. Phase 4 adds the entry points. If the run must stop early, stopping after T010 leaves main coherent (Cost visible, budget still unsettable, documents not yet updated: do T017's FR-601 and README rows before integrating). Stopping between T011 and T016 is also coherent provided T017 describes only what landed.
