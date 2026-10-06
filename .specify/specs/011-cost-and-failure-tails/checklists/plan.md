# Checklist: Plan quality (011, US1 + US2)

Purpose: plan-domain review of `plan.md` (with `spec.md`, `research.md`,
`data-model.md`, `contracts/cost-and-budget.md`, `quickstart.md`) before
/speckit-tasks. Items are unit tests for the plan's requirements quality,
answered by reading the artifacts and the code on main `d1d87b23`.
Created: 2026-10-06 (reviewer, `.workspace/tmp/011-reviewer-plan-1.md` brief).
Re-review 2: 2026-10-06 (`.workspace/tmp/reviewer-011-plan-2.md` brief) — all
six non-PASS items resolved in the plan text (CHK005/008/010/012/014/019/022/
024/025 updated); one new nit appended as CHK027. Tally after re-review:
25 PASS, 1 open nit.

## Requirement Completeness

- [x] CHK001 - Does every in-scope requirement (FR-001, 001a, 001b, 002-009, 014, 015, 015a, 016; SC-001, 002, 003, 007) trace to at least one work-order step? — **PASS**: FR-001→11, FR-001a→4,5,11, FR-001b→4,5,14, FR-002→11, FR-003→8,10,14, FR-004→8,9, FR-005→14, FR-006→2,3, FR-007→1,2,3,14, FR-008→13, FR-009→1,2,3,12, FR-014/SC-007→15, FR-015→rule 2/SG-3, FR-015a→6, FR-016→16; SC-001→4-11, SC-002→1-3,12, SC-003→rule 2 + budget-gate test. [Completeness, plan.md §Work order]
- [x] CHK002 - Is anything planned that the spec does not ask for, and is it disclosed? — **PASS with notes**: header label "spend today"→"spend" and the placeholder change are disclosed (GATE 2 item 3, needed by FR-003's header rule); `PRD.md` edit is conditional and hedged (plan.md §Project Structure line "only if"); `format.tokens()` is implied by FR-003. Nothing material is un-requested. [Coverage, plan.md §Items for GATE 2]
- [x] CHK003 - Does the plan cover both client providers for every new client surface (app-tier rule)? — **PASS**: http mappers + mock seeds/startRun/tickCosts both listed with tests (plan.md §Project Structure, research R-7). [Completeness, spec §Assumptions]
- [x] CHK004 - Are the locked rulings R1-R7 respected (US3-US5 not planned; gate unchanged; dollars-only; both entry points; CI untouched; budget 0 rejected)? — **PASS**: "Not planned" list (plan.md input), rule 2, R-4/R-5 design, not-touched list (R-11). [Consistency, spec §GATE 1 rulings]

## Requirement Clarity

- [x] CHK005 - Is there exactly one source of names, and does it match the code? — **PASS**: data-model.md §1 verified row by row on `d1d87b23` (re-review 2: the three off-by-a-few line cites are corrected — `_role_rollup` now :54, `_snapshot_run_state` now :132, `report_host.py:79-99` in research R-1). Rule 3 makes it binding. [Clarity, data-model.md §1/§4]
- [x] CHK006 - Is the validation rule stated once and shared by both entry points? — **PASS**: `parse_run_budget` is the one rule (R-4); data-model §2.2-2.3; contract §1.1-1.2 tables agree. [Clarity, research R-4]
- [x] CHK007 - Are the price-state semantics ("priced / partial / not priced / no usage") defined unambiguously, including the zero-with-tokens case? — **PASS**: data-model §2.4 rules are exhaustive; contract §3 renders them; opencode's numeric 0 is explicitly handled client-side. [Clarity, data-model §2.4]
- [x] CHK008 - Is "percent used" defined against the current threshold rather than the original budget? — **PASS**: R-3 fixes percent = counted/threshold; CONSOLE-26 words it ("share of the current limit used"); GATE 2 item 8 now states the rule and that spec US1-3 is its no-crossing case. [Clarity, research R-3, plan.md §Items for GATE 2]

## Requirement Consistency

- [x] CHK009 - Do plan, research, data-model and contract agree on the wire additions? — **PASS**: `RunState.budget_threshold_usd`, `budget_counted_usd`; `RunSummary.budget_counted_usd`; `StartBody.budget_usd`; `StartedRun.budget_notice`; TS `RoleCost`, `Run.roles/budgetThreshold/budgetCounted/budgetCrossings/budgetNotice`, `StartRunInput.budget` — identical across all four artifacts. [Consistency, data-model §2]
- [x] CHK010 - Does the plan's tier discipline match the repo's pytest tiers? — **PASS after fix** (re-review 2): quickstart §1 row 1 is now all fast tier, with `tests/test_code_attempt_usage.py` (new) as FR-015a's proof and the expectation "no file deselected"; the two temporal-marked files have their own row `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py` with a non-zero passed count; plan.md §Testing names the deselect trap; contract §6 FR-015 says "under `-m temporal`". All nine row-1 files verified fast (no `pytestmark`/`mark.temporal` in the existing ones). [Consistency, quickstart.md §1; report 1 finding B1 resolved]
- [x] CHK011 - Is the "gate is not touched" rule backed by a correct claim about replay determinism? — **PASS**: golden projections compare command types only (tests/replay/projection.py:24-37) and use STAGE_STARTED/GATE_DECIDED rows, not MODEL_USAGE; the planned edits are query-side, event-payload and additive-model only; no `workflow.patched` marker is needed because no command sequence changes. [Consistency, plan.md rule 2, research R-1/R-3]
- [x] CHK012 - Are the "Existing tests changed on purpose" rows consistent with the structure section's M markers? — **PASS after fix** (re-review 2): the table's closing paragraph now enumerates every M-not-listed file (`test_dashboard_api.py`, `test_run_summary_build.py`, `test_run_summary_model.py`, `http.test.ts`, `mock/index.test.ts`, `format.test.ts`, `entries.test.ts`, the `Run`-literal files) as gaining cases or fields only, with no existing assertion changed; the enumeration matches the structure tree exactly. [Consistency, plan.md §Existing tests]

## Acceptance Criteria Quality

- [x] CHK013 - Is each in-scope FR's proof named, and does every named test file exist or appear as new? — **PASS** (with CHK010's caveat on tier): contract §6 covers FR-001..FR-016 + SC-007; all nine cited existing files exist on the tree; `test_run_budget.py`/`test_cli_budget.py` are correctly new. [Measurability, contracts §6]
- [x] CHK014 - Can quickstart §1/§2 be executed as written and prove what they claim? — **PASS after fix** (re-review 2): the deselect trap is closed (CHK010); every other command matches repo conventions (`-m temporal tests/replay` row, `check_ui.py`, `check_clauses.py`, `check_file_size.py`, manual walk selectors all defined in data-model §2.6). [Measurability, quickstart.md]
- [x] CHK015 - Are the rejection behaviours specified with exact observable outcomes? — **PASS**: exit 2 naming `--budget-usd` (contract §1.2), 422 with `loc` ending `budget_usd` and the R7 hint string (§1.1), inline `start-budget-error` (§4). [Measurability, contract §1]

## Scenario Coverage

- [x] CHK016 - Does the plan cover the spec's edge cases: closed run N9, budget 0, negative/non-numeric, unpriced-with-budget, `rejected:budget`, just-started run? — **PASS**: totalPrice no-roles rule (data-model §2.4), contract §3 N9 row, §1.1 table, mock seed for `rejected:budget`? — the `rejected:budget` edge renders from the run's status (contract §3 budget-block row); the just-started row is the optimistic startRun row (R-7). [Coverage, spec §Edge Cases]
- [x] CHK017 - Is the open-vs-closed consistency rule (same source, no jump on close) enforced by design? — **PASS**: R-1 uses `_role_rollup` for both (only two MODEL_USAGE emitters exist: report_host.py:91 and stages/code/usage.py:42; the trace is append-only). [Coverage, research R-1]
- [x] CHK018 - Does the FR-008 inbox note work for runs whose gate item predates the fields? — **PASS**: R-9 omits the amount when the run row is unknown. [Coverage, research R-9]

## Non-Functional / Repository Rules

- [x] CHK019 - Does every touched file stay under the 1000-line ceiling, per the plan's numbers and the actual tree? — **PASS**: largest touched `cli.py` 801 (verified), `core/models.py` 545, `mock/index.ts` 464, `app.pw.ts` 446; plan.md §Constraints now says `stages/code/step.py` is 991 (verified) and is not edited. [Non-Functional, plan.md §Constitution Check]
- [x] CHK020 - Do the planned imports respect the layer boundaries (screens/shared/api/ui; workflow sandbox)? — **PASS**: cost.ts imports only api/types; CostTab via slot composition; `_role_rollup` import joins run_host.py's existing passed-through block (run_host.py:21-33, beside build_run_summary). [Non-Functional, plan.md §Constitution Check]
- [x] CHK021 - Are wire changes additive so old runs, histories and summaries still load? — **PASS**: all new model fields default None; old-summary load is itself a proof (contract §6 FR-016); replay projection compares command types only. [Non-Functional, FR-016]
- [x] CHK022 - Is the cross-host attribute-ownership table updated where the plan adds readers? — **PASS after fix** (re-review 2): GATE 2 item 7 routes both `AGENTS.md` updates to the orchestrator — `interfaces/AGENTS.md` (Cost row) and `src/sdlc/workflows/AGENTS.md` (`RunHost._snapshot_run_state` as reader of `_budget_threshold`, `_budget_crossings`, `_role_usage`) — to land in the same integration as the code. [Non-Functional, src/sdlc/workflows/AGENTS.md; report finding N3 resolved]

## Dependencies & Assumptions

- [x] CHK023 - Are the plan's code claims true on the base? — **PASS**: verified row by row (data-model §1; R-1..R-8 anchors; budget gate arithmetic role_host.py:283-305; threshold init role_host.py:85 / graph.py:169 / feature.py:290; `resolved_roles` already called at request time in the API, api.py:238,254 — research R-5 now records this as "Confirmed by reading"; `compute_price` never raises, pricing.py:21-52). [Assumption, research R-1..R-8]
- [x] CHK027 - (Re-review 2, new) Is the Scale/Scope count right after the folds? — **RESOLVED** (tasks re-review, 2026-10-06): plan.md §Scale/Scope now reads "8 new source and test files", matching the structure tree and data-model §2.5. [Consistency, plan.md §Scale/Scope]
- [x] CHK024 - Is the Run-literal test-file census complete? — **PASS after fix** (re-review 2): plan.md's list now names `F/app/RunPage.test.ts`, `F/shared/stageStrip.adapter.test.ts` and `F/shared/stageState.test.ts` alongside the originals; step 8's type-checker-driven ownership stays as the mechanism. [Assumption, plan.md §Project Structure; report finding N1 resolved]
- [x] CHK025 - Does the fixture regeneration story hold (fresh test, graph fixtures separate)? — **PASS after fix** (re-review 2): `dump_dashboard_fixtures.py` is separate from `dump_graph_fixtures.py`; work-order step 7 now pins the freshness test's row sets (`test_fleet_fixture_fresh.py:36-38`): teach on existing rows where possible, any new row carries an explicit `project_key` and stays out of the pinned sets, and an unavoidable test edit is a planned-edit stop. [Dependency, tests/test_fleet_fixture_fresh.py; report finding N4 resolved]
- [x] CHK026 - Are stop-guards assignable and cleared only by the orchestrator, with the flake baseline recorded first? — **PASS**: SG-1..SG-5; step 0 records the temporal baseline including the known flake before any change. [Assumption, plan.md §Stop-guards]
