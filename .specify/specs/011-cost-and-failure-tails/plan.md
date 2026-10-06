# Implementation Plan: Cost Visibility and Run Budget (audit item 6, US1 + US2)

**Branch**: orchestrator's call (spec dir `011-cost-and-failure-tails`) | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md) | **Base**: main `d1d87b23`

**Input**: [spec.md](spec.md), GATE 1 cleared 2026-10-06 with rulings R1 to R5, escalation 1 ruled R6 (P1: honest display, gate unchanged) and R7 (budget 0 rejected). Scope: US1, US2; FR-001, FR-001a, FR-001b, FR-002 to FR-009, FR-014, FR-015, FR-015a, FR-016; SC-001, SC-002, SC-003, SC-007. **Not planned** (R1, follow-up S-batch run): US3, US4, US5; FR-010 to FR-013; SC-004 to SC-006.

**Consults**: advisor `.workspace/tmp/advisor-011-1.md`, skeptic `.workspace/tmp/skeptic-011-1.md`, escalation `.workspace/tmp/011-escalation-1.md`. Folded into [research.md](research.md).

**Review**: reviewer `.workspace/tmp/reviewer-011-plan-1.md` — VERDICT: fixes-needed, 1 blocking, 5 non-blocking, 4 nits. All folded in: the two temporal-marked proof files get their own `-m temporal` row and FR-015a gets a fast-tier unit test (blocking 1); three more `Run`-literal test files named; the changed-tests table says which M files only gain cases; `src/sdlc/workflows/AGENTS.md` readers column routed to the orchestrator; fixture teaching rows and the freshness test's pinned sets; R-5 probe recorded as confirmed; line cites corrected; `budgetPct` parameters renamed. Re-review `.workspace/tmp/reviewer-011-plan-2.md` — VERDICT: approve; all ten resolved; one new nit (stale new-file count) fixed. Tasks review `.workspace/tmp/reviewer-011-tasks-1.md` — VERDICT: fixes-needed, 1 blocking, 2 non-blocking, 3 nits; all folded in: the budget gate entry is reachable on the mock through a named, default-off switch (data-model §2.4, contract §7), so CONSOLE-29 is proved at the app tier; T011 carries the R-5 fallback; T015/T016 reworded. Re-review `.workspace/tmp/reviewer-011-tasks-2.md` — VERDICT: approve, nothing open.

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`.

## Summary

Two things a person cannot do today: see what a run spent, and give a run a budget. The data and the gate exist; the entry points and the screen do not.

- **Server (small)**: a budget validator shared by the CLI flag and the dashboard start request; a notice that says what the budget counts; the live run state lists every role the run recorded (built from the trace, query-side) and carries the current threshold and the dollars counted toward the budget; the code stage stops writing a missing price as 0.0.
- **Client**: one pure module that decides "priced / partial / not priced / no usage" for every dollar figure; a Cost tab composed into the run page through a slot; the header total; a budget field in the start form; one sentence on the budget inbox item.
- **Contract**: CONSOLE-10 amended, CONSOLE-24 to 29 added, START_RUN_MODAL-3 added, with tests.
- **Documents**: README, frontend README, ROADMAP (FR-601, FR-701, E-19, SC-10).

The budget gate's behaviour is not changed (FR-015, R6). Decisions R-1 to R-11 are in [research.md](research.md); every name is in [data-model.md](data-model.md); behaviour, clause wording and the requirement-to-proof table are in [contracts/cost-and-budget.md](contracts/cost-and-budget.md); validation is in [quickstart.md](quickstart.md).

## The three rules every task is checked against

1. **One price rule.** No component, adapter or store prints dollars except through `F/shared/cost.ts` (`rowPrice`, `totalPrice`, `priceLabel`). Review check on every client diff: no `money(` call on a value that can be null or zero-with-tokens, and no `?? 0` on a cost. Proof: `cost.test.ts`, CONSOLE-25.
2. **The gate is not touched.** `git diff` for the run shows no change in `src/sdlc/workflows/role_host.py`, `graph.py`, `feature.py`, no golden or history file, and nothing writes harness usage into `_role_usage`. Proof: `tests/test_budget_gate.py` unchanged and green.
3. **Names come from data-model.md.** Its §4 check is the first task. A name not in it stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, FastAPI, Temporal Python SDK, argparse); TypeScript 5 / Vue 3.4 single-file components.

**Primary Dependencies**: existing only. `genai_prices` through `sdlc.pricing.compute_price`; `@kroker/ui`; Pinia; vue-router. No new dependency.

**Storage**: N/A. Additive fields on the live run-state query result and on the run summary.

**Testing**: Python in the `kroker-dev` container: `uv run pytest` (fast tier), named files per task, `-m temporal tests/replay` once at baseline and once at the end. `tests/test_budget_gate.py` and `tests/test_model_usage_capture.py` are temporal-marked: `addopts` deselects them even when named by path, so they are always run with `-m temporal` and a run that reports them deselected proves nothing. Client: `python scripts/check_ui.py` from the repository root on the host (install, typecheck ×2, builds, vitest-dashboard, ds-bundle, vitest-ui, playwright). `python scripts/check_clauses.py` (always exits 0; read it). `python scripts/check_file_size.py`.

**Target Platform**: Temporal worker and FastAPI dashboard backend (Linux container); browser SPA. Developer host is Windows.

**Project Type**: web application plus CLI; backend, design-system package and dashboard package are all touched.

**Performance Goals**: none new. The trace rollup in the state query is linear in the run's trace length per poll; a run's trace is in the hundreds of events.

**Constraints**: budget gate semantics frozen (FR-015); no workflow command change; wire fields additive with defaults (FR-016); 1000-line ceiling (`stages/code/step.py` is at 991 and is not edited); cross-stage call ban; screens never import another screen; `ui/` never imports `dashboard/`; tokens only, no hex or pixels in Playwright assertions; clause ids with underscores, same-line citations; both client providers implement every change; heavy suites staggered (benchmark agents live).

**Scale/Scope**: 8 new source and test files, about 30 modified, 4 documents. No new file is expected to pass 250 lines.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`, and the nearest `AGENTS.md` of any package edited (the executor reads `src/sdlc/stages/code/AGENTS.md` and `src/sdlc/workflows/AGENTS.md` if present before T-code edits). Checked after design:

| Rule | Status |
|---|---|
| Cross-stage calls banned; producer owns its artifacts | Holds. `run_budget.py` is top-level like `pricing.py`; `core/` gains only fields on envelopes it already owns. |
| Screens import only `app/*.store.ts`, `shared/`, `api/`, `@kroker/ui` | Holds. `features/cost/` imports `shared/fleet.store`, `shared/cost`, `shared/format`, `api/types`, `@kroker/ui`. `RunView` gets the tab through a slot. |
| `shared/` never imports `app/` or `features/` | Holds. `cost.ts` imports `api/types` and `format`. |
| `ui/` never imports `dashboard/` | Holds. The modal's payload is a literal shape. |
| New library component ⇒ five files + registry | Not triggered. `StartRunModal` and `AppHeader` are edited through their existing five files. |
| New shipped surface ⇒ `CONSOLE-N` clauses + `app.pw.ts` | Planned: CONSOLE-24 to 29, CONSOLE-10 amended. |
| Whoever changes behaviour updates its clauses in the same diff | Planned per task. |
| 1000-line ceiling | Holds. Largest touched: `cli.py` 801 (+ about 15), `core/models.py` 545, `mock/index.ts` 464 (+ about 60), `app.pw.ts` 446 (+ about 90). |
| Sandbox module marking | `run_host.py` imports `_role_rollup` inside its existing `imports_passed_through` block, beside `build_run_summary`. `run_budget.py` is not imported by workflow code. |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/011-cost-and-failure-tails/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   cost-and-budget.md
├── checklists/  requirements.md (+ plan.md, tasks.md from the reviewer)
└── tasks.md     (/speckit-tasks)
```

### Source Code (after the feature)

```text
src/sdlc/
├── run_budget.py                 N  parse_run_budget, budget_notice, constants
├── cli.py                        M  start --budget-usd; print notice
├── core/models.py                M  + RunState.budget_threshold_usd, budget_counted_usd; RunSummary.budget_counted_usd
├── dashboard/api.py              M  StartBody.budget_usd + validator; StartedRun.budget_notice; cfg carries budget
├── observability/summary.py      M  build_run_summary(budget_counted_usd=)
├── stages/code/usage.py          M  omit cost_usd when the harness reported none
└── workflows/run_host.py         M  roles/total from trace rollup; threshold; counted (state and summary)

scripts/dump_dashboard_fixtures.py   M  teach rows: threshold/counted, a not-priced role, a no-roles closed row
tests/
├── test_run_budget.py            N
├── test_cli_budget.py            N
├── test_dashboard_api.py         M  start with/without budget; 422 cases; notice
├── test_run_state_query.py       M  dev in roles; total = priced sum; threshold; counted
├── test_run_state_model.py       M  shared-field list
├── test_run_summary_build.py     M  counted
├── test_run_summary_model.py     M  old summary loads
├── test_code_attempt_usage.py    N  fast tier: missing price stays missing (FR-015a)
└── test_budget_gate.py, test_model_usage_capture.py   not edited; run under -m temporal

interfaces/dashboard/frontend/src/
├── api/
│   ├── types.ts                  M  RoleCost; Run + roles, budgetThreshold, budgetCounted, budgetCrossings, budgetNotice; StartRunInput.budget
│   ├── http.ts, http.test.ts     M  mappers, startRun body and notice, optimistic row
│   ├── __fixtures__/fleet-snapshot.json  M  regenerated, never hand-edited
│   ├── client.ts                 M  passes the budget-gate switch to the mock (data-model §2.4)
│   └── mock/index.ts, index.test.ts      M  seeds, startRun budget, tickCosts keeps cost = priced sum, budgetGate option
├── shared/
│   ├── cost.ts, cost.test.ts     N
│   ├── format.ts, format.test.ts M  + tokens()
│   └── fleet.store.ts, fleet.store.test.ts  M  totalCost → { usd, excluded }
├── app/
│   ├── RunPage.vue               M  fills #cost
│   ├── ui.store.ts               M  startBudget
│   ├── shell/AppHeader.vue (+ test)      M  formats the spend string
│   └── shell/StartRunModal.vue (+ test)  M  passes budget; toast with notice
└── features/
    ├── cost/CostTab.vue, CostTab.test.ts N
    ├── run/RunView.vue, RunView.tabs.test.ts  M  #cost slot; Cost enabled with slot; Gates still disabled
    └── inbox/GateEntry.vue, entries.test.ts   M  budget note

interfaces/ui/
├── app.md, app.pw.ts             M  CONSOLE-10 amended; CONSOLE-24..29
└── src/components/
    ├── start_run_modal/  (vue, md, spec.ts, pw.ts, profiles.ts)  M  budget field; START_RUN_MODAL-3
    └── app_header/       (vue, md, spec.ts, profiles.ts as needed)  M  label "spend", placeholder "—"

README.md, interfaces/dashboard/frontend/README.md, ROADMAP.md, PRD.md(FR-701 note only if it states the gate scope)  M
.workspace/tasks/2026-10-06-budget-gate-counts-all-recorded-spend.md   N  the R6 card
```

Every test file that builds a `Run` literal or fakes `totalCost` gains the new fields; the type checker lists them. Known from reading: `F/features/run/RunView.tabs.test.ts`, `RunView.test.ts`, `F/features/fleet/*.test.ts`, `F/shared/fleet.store.test.ts`, `F/shared/stageStrip.adapter.test.ts`, `F/shared/stageState.test.ts`, `F/app/RunPage.test.ts`, `F/app/shell.stores.test.ts`, `F/app/App.test.ts`, `F/features/board/*` only if they build a `Run`. To keep that mechanical, T-types adds a test helper only if one already exists; otherwise each literal gains the four fields.

**Not touched** (research R-11): `workflows/role_host.py`, `graph.py`, `feature.py`, `stages/code/step.py`, research stage, `operator/tools.py`, golden traces, replay histories, `.github/workflows/`, `F/app/boundaries.test.ts`, `F/app/router.ts` (the `tab` query already reaches `RunPage`), `fleet_row/`, every `AGENTS.md`.

## Design in brief

1. **Validation** (R-4, contract §1). `parse_run_budget` is the one rule. argparse and the `StartBody` validator both call it. 0 is rejected with the R7 hint.
2. **Notice** (R-5). `budget_notice(cfg)` returns the fixed scope sentence, plus unpriced planning roles when the probe finds any. API returns it; CLI prints it; the dashboard toasts it.
3. **Live state** (R-1, R-3). `_snapshot_run_state` returns `roles = _role_rollup(self._trace)`, total = sum of priced rows, `budget_threshold_usd = self._budget_threshold`, `budget_counted_usd` = priced sum of `_role_usage`; the last two None without a budget. `_retro` passes the counted sum to `build_run_summary`.
4. **Missing stays missing** (R-2). `_record_attempt_usage` builds its event data and adds `cost_usd` only when `run.cost_usd is not None`.
5. **Client model** (R-7). Mappers fill `roles` and the budget fields; `Run.cost` goes through `totalPrice`.
6. **Price rule** (R-2). `cost.ts`, pure, exhaustively unit-tested before anything renders.
7. **Cost tab** (R-6, contract §3). `RunView` slot, `RunPage` composition, `CostTab` states.
8. **Header** (R-8), **start form** (R-10), **inbox note** (R-9).
9. **Contract and documents**.

## Work order

Tasks come from `/speckit-tasks`; this is the order and why. Tests land with the code that satisfies them, test written first (no red commits). Each step ends with its named checks green.

| Step | What | Why here |
|---|---|---|
| 0 | Baseline in the container (fast tier counts, `-m temporal tests/replay` result incl. the known flake, ruff, mypy count) and on the host (`check_ui.py`, clauses, file size). Data-model §4 name check. T-verify items of research R-1 and R-5 (sandbox import, trace not truncated, proposer role list). Record in `baseline.md`. | Known start; the flake's state is recorded before anything changes. |
| 1 | `run_budget.py` + `test_run_budget.py`. | No dependencies; steps 2 and 3 import it. |
| 2 | CLI flag + `test_cli_budget.py`. | US2, first entry point. |
| 3 | API: `StartBody`, `StartedRun`, cfg + tests. | US2, second entry point. Server half of US2 is complete here. |
| 4 | Models: three additive fields; `build_run_summary` keyword; model tests. | Step 5 needs them. |
| 5 | `run_host.py`: rollup roles, total, threshold, counted; `_retro` passes counted; `test_run_state_query.py`, `test_run_summary_build.py`. | The riskiest Python change; isolated in one task with the temporal replay check right after it. |
| 6 | `stages/code/usage.py` + new fast-tier `tests/test_code_attempt_usage.py`. | Independent; small. |
| 7 | Fixture generator teaching rows; regenerate `fleet-snapshot.json`; freshness test. `tests/test_fleet_fixture_fresh.py:36-38` pins row sets by run id (`OMITTED`, `KROKER_ROWS`, `GRAPH_ROWS`): teach the new cases on **existing** rows where possible; any new row carries an explicit `project_key` and is not added to those sets, so the test file needs no edit. If it does need one, that is a planned-edit stop: report first. | Client mappers are tested against the fixture. |
| 8 | Client types, `cost.ts` + test, `format.tokens`, mappers + `http.test.ts`, existing `Run` literals. | Everything on screen needs it. `vue-tsc` proves both providers. |
| 9 | Mock seeds, `startRun` budget, `tickCosts`; mock tests. | App-tier tests need the seeds. |
| 10 | `fleet.store.totalCost`, shell header, library header label and placeholder + contract and spec. | Smallest visible win; CONSOLE-27. |
| 11 | `RunView` slot + tabs test; `CostTab` + test; `RunPage`. | US1 complete here. |
| 12 | Library modal budget field (five files), shell modal, `ui.store`, toast. | US2 complete on the dashboard. |
| 13 | Inbox budget note + test. | FR-008. |
| 14 | `app.md` CONSOLE-10 amend, CONSOLE-24..29; `app.pw.ts`. | Needs the built screens. |
| 15 | Documents; the R6 inbox card. | Describe what is on the branch. |
| 16 | Full gates; quickstart walk; `verification.md`. | Done = quickstart §1 green, §2 walked. |

US2 is deliverable after steps 1 to 3 (CLI and API) without any client work; US1 after 4 to 11.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `F/features/run/RunView.tabs.test.ts:170` "Gates and Cost are disabled…" | becomes "Gates is disabled; Cost is disabled without a slot and selectable with one" | Cost is now live through the slot (R-6) |
| `U/app.pw.ts:219` | `?tab=cost` → `?tab=gates` in the CONSOLE-10 test | the amended clause |
| `tests/test_run_state_model.py` shared-field list | new fields added | additive wire |
| `tests/test_run_state_query.py` | assertions on `roles`/total move to trace-derived values where a test seeded `_role_usage` only | R-1 changes the source; a test that seeds the bag without the trace must seed the trace too |
| `F/shared/fleet.store.test.ts`, `F/app/shell/AppHeader.test.ts` | `totalCost` shape and the formatted string | R-8 |
| `U/.../start_run_modal.spec.ts` START_RUN_MODAL-1 | payload gains `budget` | R-10 |
| `U/.../app_header.spec.ts` | label and placeholder | R-8 |
| `fleet-snapshot.json` | regenerated | new fields and teaching rows |

Files marked M in the structure tree but not listed above (`tests/test_dashboard_api.py`, `tests/test_run_summary_build.py`, `tests/test_run_summary_model.py`, `F/api/http.test.ts`, `F/api/mock/index.test.ts`, `F/shared/format.test.ts`, `F/features/inbox/entries.test.ts`, the `Run`-literal files) only **gain** cases or fields; no existing assertion in them changes. No other existing test is edited. If `tests/test_budget_gate.py` or any replay test needs an edit to pass, that is a stop-guard (rule 2), not a fix.

## Document changes

| File | Now | Change to |
|---|---|---|
| `README.md` ~42, ~123 (start examples) | no budget | add `--budget-usd` to one example with one sentence: what it does, that 0 is rejected, and what the budget counts today |
| `README.md` ~181 | "…Cost not built yet" | Cost is built; Gates is not |
| `interfaces/dashboard/frontend/README.md` ~41 | "Not built: the run page's Gates and Cost tabs" | Not built: Gates |
| `interfaces/AGENTS.md` screen table | no Cost row | **not edited by the executor** (`AGENTS.md` files are the orchestrator's); listed for the scribe/orchestrator as a one-row addition: Cost, tab of `/runs/:id` (`?tab=cost`), `src/features/cost/`, `CostTab.vue` |
| `ROADMAP.md` FR-601 (~314) | "Gates and Cost tabs are not" | Cost tab built (011); Gates not. Stays `[ ]` ⚠️ |
| `ROADMAP.md` FR-701 (~323) | E-33 text | append: the budget is settable at start (CLI `--budget-usd`, dashboard start form); the gate counts priced planning-agent spend only, coding-harness, crew and research-stage spend is not counted (card filed); "E-19 remains the general version" gains its meaning: per-phase budgets (FR-922/E-55) and a pre-run estimate, neither built |
| `ROADMAP.md` SC-10 (~461) | "needs E-55 budgets + runs" | append: unchanged by 011; still waits on E-55 per-phase budgets and measured runs per repo-size band |
| `ROADMAP.md` line 6 | Last verified | prepend the date and what was re-checked |

Line numbers are from the base; find each passage by its text. Documents describe main, so these ride the branch.

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: any test under `tests/replay/` or `tests/test_budget_gate.py` changes result against the step-0 baseline for a reason other than the known `budget_arch_reject-sandboxed` flake. Stop, diagnose, report.
- **SG-2**: the trace rollup cannot be imported or called from `run_host.py` without a sandbox error or a new import outside the passed-through block. Stop; do not move the function or mark modules.
- **SG-3**: a task needs an edit in `role_host.py`, `graph.py`, `feature.py`, or `stages/code/step.py`. Stop.
- **SG-4**: `check_ui.py` reports "skipped". A skip is not a pass. Stop.
- **SG-5**: the R-5 probe needs registry loading the API process does not already do, or raises. Take the documented fallback (fixed sentence only), record it, continue; this one does not need clearance.

## Risks

| Risk | Mitigation |
|---|---|
| The trace-derived role list differs from the proposer bag for a role (double count or miss) | Step 5 test: for a seeded run, every role in `_role_usage` appears in the rollup with equal tokens and dollars. If not equal, SG-1 style stop. |
| A zero-with-tokens rule hides a real free call | In this system a priced model with tokens costs more than zero; the per-call 0.0 shares in research roll up to a positive role sum (R-2). The rule is one function; changing it later is one edit. |
| `Run` gains required fields and many test literals break | Mechanical, type-checker-driven; step 8 owns all of them in one task. |
| Fixture regeneration drags in graph fixtures | It does not: `dump_dashboard_fixtures.py` is separate from `dump_graph_fixtures.py` (skeptic L5). If `tests/test_graph_fixtures_fresh.py` turns red, stop. |
| Header string too long for the layout | Short form `· 3 not priced`; Playwright asserts text, not size. If it wraps badly in the manual walk, report; do not add a prop without asking. |
| `check_ui.py` times out under load | Known card. A timeout in a file this run does not touch is reported, not fixed. |
| Users read the budget as a hard cap on all spend | The notice at start, the sentence on the Cost tab, the README sentence, and the queued card. This is ruling R6's accepted limit. |

## Follow-ups to file (`.workspace/tasks/`)

- `2026-10-06-budget-gate-counts-all-recorded-spend.md` (R6; size M; queued behind US3). Filed by step 15.
- Research-stage spend is in neither the trace nor the role list (N5). One card, size S to M.
- A role priced on some calls only is not marked (N8). One card, size S.
- Orchestrator's, not this run's: the non-gating red-badge CI job (R4).

## Items for GATE 2

1. **Three additive wire fields** (`RunState.budget_threshold_usd`, `budget_counted_usd`; `RunSummary.budget_counted_usd`) and two on the start route (`StartBody.budget_usd`, `StartedRun.budget_notice`).
2. **Zero with tokens reads "not priced"** on the client, for existing data and for opencode's numeric 0.
3. **Header label changes from "spend today" to "spend"**: the sum was never windowed by day.
4. **Role-level "partial" is not shown** (N8); totals only.
5. **The operator start tool gets no budget parameter** (R3: not trivial).
6. **ROADMAP wording** for FR-701, E-19 and SC-10 as in the table above; FR-601 stays open on Gates.
7. **Two `AGENTS.md` updates are the orchestrator's** (the executor edits none): `interfaces/AGENTS.md` gains a Cost row; `src/sdlc/workflows/AGENTS.md` attribute-ownership table gains `RunHost._snapshot_run_state` as a reader of `_budget_threshold`, `_budget_crossings` and `_role_usage` (it records readers by rule, and step 5 adds this one). Both belong in the same integration as the code.
8. **Percent used is counted / current limit**, not total / budget. Spec US1 scenario 3 (budget 40, cost 31, 77 %) is the no-crossing case of the same rule; after one approve the divisor is 80.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind (no `Co-Authored-By:`, no `Claude-Session:`), even where a template prints one.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only. Verify the container is bound to this branch's tree before the baseline (it has been left bound to an old worktree before).
- Never chain two test runs in one shell call. `addopts` already carries `-q`. Stagger heavy suites: benchmark agents are live.
- The reviewer gate is per task and blocking: no task N+1 commit before the reviewer has answered on task N's diff.
- The benchmark improvement plan under `docs/reports/` and the other untracked or modified files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
