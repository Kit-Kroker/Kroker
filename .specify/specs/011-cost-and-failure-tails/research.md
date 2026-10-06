# Research: Cost Visibility and Run Budget (011, US1 + US2)

Decisions for the plan. Sources: advisor `.workspace/tmp/advisor-011-1.md`, skeptic `.workspace/tmp/skeptic-011-1.md`, rulings R1 to R7 in [spec.md](spec.md). Every code claim was read on main `d1d87b23`; nothing was run. `F/` = `interfaces/dashboard/frontend/src/`, `U/` = `interfaces/ui/`.

## R-1. Where an open run's role list comes from

- **Decision**: `_snapshot_run_state` (`src/sdlc/workflows/run_host.py:132`) builds `roles` by rolling up the run's trace (`_role_rollup`, `observability/summary.py:54`), the same function the closed summary uses, and sets `cost_usd_total` to the sum of the priced rows of that list (None when no row is priced).
- **Rationale**: ruling R6. The trace is a superset of the proposer bag: `_track_usage` writes both (`report_host.py:79-99`), and the code stage writes only the trace (`stages/code/usage.py:41`). One source for open and closed runs means the tab cannot jump when a run closes. A query handler's result is not history; no command changes.
- **Alternatives**: fold harness usage into `_role_usage` (rejected: that is the bag the gate sums, so it changes gate semantics, FR-015); a client-side merge (rejected: the client has no trace).
- **Check at exec (T-verify)**: `_role_rollup` must be importable in the workflow sandbox the way `run_host.py` already imports `build_run_summary` from the same module; the trace is not truncated during a run.
- **Known gap, stated on screen**: the research stage's own spend goes to a local bag (`stages/research/step.py:252`) and is in neither source (N5). The tab says so (FR-002). Not fixed here.

## R-2. What a missing price looks like, and the one rule for it

- **Decision**: two changes.
  1. Server: `stages/code/usage.py:49` emits `cost_usd` only when the harness reported one (FR-015a). The rollup already treats an absent key as unpriced (`summary.py:63,72`).
  2. Client: one pure module `F/shared/cost.ts` decides the price state of a row and of a total. A row with tokens and a dollar value of null or 0 is **not priced**. A row with no tokens and no dollars is **no usage**. A total is **priced** when every row with tokens is priced, **partial** when some are, **not priced** when none are. Every place that prints dollars goes through it.
- **Rationale**: R2 and R6. The server fix alone is not enough: opencode reports a numeric 0 on subscription models (`harness/opencode.py:216,295`), and 10 summaries already on disk hold `dev: 0.0`. A zero with tokens is never a real price in this system (a call that used tokens on a priced model costs more than zero).
- **Alternatives**: a `priced_calls` counter on `RoleUsage` to mark a role that is priced on some calls only (advisor D7.1). Not taken: the role-level partial mark is out of scope by the amended edge case in the spec (N8); the total-level label needs no new field.
- **Trap**: `role_host.py:249-255` gives later same-model research reports a share of exactly 0.0 on purpose. That is per call; at role level the sum is positive whenever the batch was priced, so the rule holds.

## R-3. Current threshold and "counted toward budget" on the wire

- **Decision**: two additive fields.
  - `RunState.budget_threshold_usd: float | None` = `self._budget_threshold` when a budget is on, else None.
  - `RunState.budget_counted_usd: float | None` and `RunSummary.budget_counted_usd: float | None` = the sum the gate actually compares (priced dollars in `_role_usage`), None when no budget is set.
- **Rationale**: crossings are incremented before the gate is awaited and the threshold is raised after approve (`role_host.py:284,305`), so threshold cannot be derived from `budget_usd` and `budget_crossings` (advisor D1). "Counted toward budget" (R6) must be the number the gate used, not a client guess about which roles are planning agents. The closed summary needs it because "over budget, no gate" is read after the run ends.
- **Percent used** = counted / threshold, not total / budget.
- **Replay safety**: both fields default to None; old histories and summaries load (skeptic L5). `RunSummary` is the retro activity's input; the golden projection compares command types, not payloads (`tests/replay/projection.py:24-37`).
- **Cost**: `fleet-snapshot.json` is pinned by `tests/test_fleet_fixture_fresh.py`; regenerate with `python scripts/dump_dashboard_fixtures.py`. `tests/test_run_state_model.py` lists shared fields.
- **Closed runs have no threshold**: the tab shows budget, crossings and counted; no percent bar.

## R-4. One validation for both entry points

- **Decision**: new top-level module `src/sdlc/run_budget.py` (beside `pricing.py`):
  - `parse_run_budget(raw: object) -> float`: accepts an int, float or numeric string; rejects bool, non-numeric, NaN, inf, negative, and 0. Raises `ValueError` whose message is ready to show. The 0 message is exactly: `budget must be greater than 0; omit it to run without a budget` (R7).
  - `budget_notice(cfg: PipelineConfig) -> str | None`: the FR-009 text (R-5).
- **Use**: CLI `start --budget-usd` with `type=` wrapping it into `argparse.ArgumentTypeError` (argparse then names the flag). `StartBody.budget_usd: float | int | str | None = None` with a `field_validator(mode="before")` calling it, so FastAPI answers 422 with `loc=["body","budget_usd"]`.
- **Rationale**: R3 (one validation), R7. Constructing `PipelineConfig(run_budget_usd=x)` is not the rule: its `ge=0.0` accepts 0 (advisor D3). `core/` stays config and envelopes; neither entry point imports the other.
- **Operator start tool** (`operator/tools.py:541`): untouched. It has no budget parameter in its tool schema; adding one changes an agent-facing tool, which is not trivial (R3).

## R-5. The FR-009 notice

- **Decision**: `budget_notice(cfg)` returns None when no budget, else a fixed sentence plus an optional list:
  - Always: `Budget $X.XX counts priced planning-agent spend only. Coding-harness, crew and research-stage spend is not counted.`
  - When any role in `resolved_roles(cfg)` whose key is a proposer role has `compute_price(PriceUsageInput(model=..., input_tokens=1)) is None`: append `No price found for: <roles>.`
- Returned as `StartedRun.budget_notice: str | None` (additive) and printed by the CLI after the run id. The dashboard shows it as a toast after start and as a static line under the budget field in the start form. The Cost tab repeats the fixed sentence whenever a budget is set (FR-001b).
- **Rationale**: R6 wording is fixed by ruling. `compute_price` is pure and never raises (`pricing.py:21`). The probe says only "no price found", never "all priced" (advisor D2).
- **Confirmed by reading**: the API process already calls `resolved_roles(PipelineConfig())` at request time (`dashboard/api.py:238,254`), so the probe needs nothing new there.
- **Fallback**: if resolving roles in the API process raises or needs the registry loaded where it is not, drop the probe and keep the fixed sentence; record it in verification. The fixed sentence alone satisfies R6.
- **Which roles count as planning agents**: the proposer roles `_run_role` serves. T-verify pins the list from `agents/roles.py` rather than guessing.

## R-6. Cost tab composition

- **Decision**: `RunView.vue` gains a typed `#cost` slot exactly like `#board`; the tab is enabled only when the slot is supplied. `app/RunPage.vue` fills it with `features/cost/CostTab.vue`. `CostTab` reads the run from the fleet store and renders with existing `@kroker/ui` parts. No new library component.
- **Rationale**: R-13 of spec 002; `RunView` stays routerless-testable and never imports another screen (advisor D4).
- **Gates** stays disabled. CONSOLE-10's disabled example becomes `?tab=gates`.
- **Fallback**: if an existing part cannot show a "not priced" or "partial" label without a new variant, plain token-styled text in `CostTab` is used; no library change.

## R-7. Client model

- **Decision**: `Run` gains `roles: RoleCost[]`, `budgetThreshold: number | null`, `budgetCounted: number | null`, `budgetCrossings: number`. `Run.cost` is set through `F/shared/cost.ts` so a zero total with tokens is null. Both mappers (`mapRun`, `mapClosed`) and the mock fill them. The optimistic just-started row (`http.ts:234`) carries the requested budget and `roles: []`.
- **Rationale**: FR-001, advisor D7.2. Existing `Run` field names and meanings are unchanged; additions only.
- **Mock**: `tickCosts` (`mock/index.ts:24`) bumps `cost` without touching roles. Decision: it adds its increment to the run's first role when the run has roles, and recomputes `cost` from roles; runs without roles keep today's behaviour. The Cost-tab app-tier tests use non-running seeded runs so no assertion depends on the ticker.

## R-8. Fleet header and fleet row

- **Decision**: `fleet.store.ts` replaces the number `totalCost` with `{ usd: number | null, excluded: number }`: the sum over runs whose `cost` is not null, and the count of runs that have usage but no price. The shell formats `"$12.40 · 3 not priced"`, or `"not priced"` when `usd` is null and runs exist, and passes it through the existing `totalCost` string prop. The library header's default `'$0.00'` becomes `'—'` and its label `spend today` becomes `spend`, with the contract sentence amended, since the sum is over all listed runs and is not windowed by day.
- **Fleet row**: already prints `—` for a null cost (`FleetRow.vue:26`). With R-7 a zero-with-tokens total arrives as null, so the row prints `—`, never `$0.00`. The words "not priced" and the tokens are on the Cost tab, one click away. No fleet-row change and no fleet-row contract change.
- **Rationale**: advisor D6; R2 ("header totals priced runs only and states how many it left out").

## R-9. "What approve grants" on the budget inbox item (FR-008)

- **Decision**: client-side. For a gate item whose gate is `budget`, the inbox entry appends: `Approve raises the limit to $X and the run continues. Any other decision ends the run.` X = `budgetThreshold + budget` from the run's fleet row; when the row is missing, the sentence omits the amount.
- **Rationale**: no workflow text change on the path of the known-flaky scenario; covers runs already open (advisor D5).

## R-10. Start form

- **Decision**: `U/src/components/start_run_modal/StartRunModal.vue` gains one optional text input, `BUDGET (USD)`, and `StartRunPayload.budget: string`. The component blocks submit and shows an inline message when the field is non-empty and not a number greater than 0; empty means no budget. The server stays the authority (422). Contract clauses added in `start_run_modal.md` with spec and pw coverage.
- **Rationale**: SC-002; the modal is a library component, so the change goes through its five files.

## R-11. What is not touched

`role_host.py` (the gate), `graph.py`, `feature.py`, every golden trace and replay history, `.github/workflows/`, `operator/tools.py`, `stages/code/step.py` (991 lines; the only code-stage edit is in `usage.py`), research stage, `F/features/board/`, `F/features/graphs/`. US3 to US5 (R1). No CI change (R4). No retry recorder (R5).
