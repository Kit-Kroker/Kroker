# Data Model: Cost Visibility and Run Budget (011, US1 + US2)

The only source of names for this run. A task may not introduce a name that is not here; if one is needed, the executor stops and asks. `F/` = `interfaces/dashboard/frontend/src/`, `U/` = `interfaces/ui/`.

## 1. Existing names (unchanged; copied from main `d1d87b23`)

### 1.1 Python

| Name | Where | Shape |
|---|---|---|
| `RoleUsage` | `src/sdlc/core/models.py:135` | `role, model, calls, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd: float \| None` |
| `PipelineConfig.run_budget_usd` | `core/models.py:414` | `float`, `ge=0.0`, 0.0 = off |
| `RunSummary` | `core/models.py:477` | has `roles, cost_usd_total, budget_usd, budget_crossings` |
| `RunState` | `core/models.py:513` | has `roles, cost_usd_total, budget_usd, budget_crossings` |
| `StartBody` | `src/sdlc/dashboard/api.py:67` | `title, description, mode, repo` |
| `StartedRun` | `dashboard/api.py:74` | `run_id` |
| `_role_rollup(trace)` | `src/sdlc/observability/summary.py:54` | `list[RunEvent] -> list[RoleUsage]` |
| `build_run_summary(...)` | `observability/summary.py` | keyword-only builder; has `budget_usd` |
| `_record_attempt_usage` | `src/sdlc/stages/code/usage.py:28` | emits `MODEL_USAGE` for role `dev` |
| `_snapshot_run_state` | `src/sdlc/workflows/run_host.py:132` | builds `RunState` |
| `_budget_threshold`, `_budget_crossings`, `_role_usage` | workflow host state | read only by this run |
| `compute_price`, `PriceUsageInput` | `src/sdlc/pricing.py` | pure, returns `float \| None` |
| `resolved_roles(cfg)` | `src/sdlc/workflows/graph_catalog.py:108` | `dict[str, RoleConfig]` |

### 1.2 TypeScript

| Name | Where | Note |
|---|---|---|
| `Run` | `F/api/types.ts:19` | `cost: number \| null`, `budget: number \| null` stay |
| `StartRunInput` | `F/api/types.ts:102` | `title, description, repo, mode` |
| `GateItem` | `F/api/types.ts:54` | `gate: string`, `runId`, `body` |
| `DashboardApi.startRun` | `F/api/types.ts:137` | `(input: StartRunInput) => Promise<Run>`; signature unchanged |
| `mapRun`, `mapClosed` | `F/api/http.ts:62,84` | |
| `tickCosts` | `F/api/mock/index.ts:24` | |
| `money` | `F/shared/format.ts:1` | `(n: number) => string` |
| `useFleetStore().totalCost` | `F/shared/fleet.store.ts:33` | **changes type**, see §2.4 |
| `StartRunPayload` | `U/src/components/start_run_modal/StartRunModal.vue:6` | `title, repo, mode` |
| `AppHeaderProps.totalCost` | `U/src/components/app_header/AppHeader.vue` | `string`, stays |

## 2. New and changed names

### 2.1 Python wire (additive, all default None)

| Model | Field | Meaning |
|---|---|---|
| `RunState` | `budget_threshold_usd: float \| None = None` | current gate threshold; None = no budget |
| `RunState` | `budget_counted_usd: float \| None = None` | priced dollars the gate compares; None = no budget |
| `RunSummary` | `budget_counted_usd: float \| None = None` | same, at close; None = no budget or a summary from before this change |
| `StartBody` | `budget_usd: float \| int \| str \| None = None` | validated by `parse_run_budget` in a `mode="before"` validator; stored as `float \| None` |
| `StartedRun` | `budget_notice: str \| None = None` | the FR-009 text; None when no budget |

`build_run_summary` gains keyword `budget_counted_usd: float | None = None`.

Changed behaviour, no new name:
- `RunState.roles` and `RunState.cost_usd_total` are built from the trace rollup (research R-1).
- `_record_attempt_usage` omits the `cost_usd` key when the harness reported none (R-2).

### 2.2 `src/sdlc/run_budget.py` (new)

```text
BUDGET_ZERO_HINT: str = "budget must be greater than 0; omit it to run without a budget"
BUDGET_SCOPE_NOTE: str = "counts priced planning-agent spend only. Coding-harness, crew and research-stage spend is not counted."
parse_run_budget(raw: object) -> float          # raises ValueError(message)
budget_notice(cfg: PipelineConfig) -> str | None
```

Rules of `parse_run_budget`: `bool` rejected; `int`/`float` taken as is; `str` stripped and parsed with `float()`; anything else rejected. Then NaN, inf, `< 0` rejected with `budget must be a number greater than 0`; `== 0` rejected with `BUDGET_ZERO_HINT`.

`budget_notice`: None when `cfg.run_budget_usd <= 0`; else `f"Budget ${cfg.run_budget_usd:.2f} {BUDGET_SCOPE_NOTE}"` plus, when the probe finds unpriced planning roles, `f" No price found for: {', '.join(sorted(roles))}."`.

### 2.3 CLI

`start --budget-usd AMOUNT` (dest `budget_usd`, default None, `type=` a wrapper turning `ValueError` into `argparse.ArgumentTypeError`). When set: `cfg.run_budget_usd = args.budget_usd`, and after the run id is printed, `budget_notice(cfg)` is printed on its own line.

### 2.4 TypeScript

`F/api/types.ts` (additive):

```text
interface RoleCost {
  role: string
  model: string
  calls: number
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  cost: number | null        // raw wire value; display goes through shared/cost.ts
}
Run.roles: RoleCost[]
Run.budgetThreshold: number | null
Run.budgetCounted: number | null
Run.budgetCrossings: number
StartRunInput.budget: number | null
Run.budgetNotice: string | null   // set only on the row returned by startRun (from StartedRun.budget_notice); null on polled rows
```

`F/shared/cost.ts` (new, pure, imports only `api/types`):

```text
type PriceState = 'priced' | 'partial' | 'not-priced' | 'no-usage'
tokensOf(r: RoleCost): number                      // sum of the four token counts
rowPrice(r: RoleCost): { state: 'priced' | 'not-priced' | 'no-usage'; usd: number | null }
totalPrice(roles: RoleCost[], wireTotal: number | null): { state: PriceState; usd: number | null; tokens: number }
priceLabel(p: { state: PriceState; usd: number | null }): string
BUDGET_SCOPE_NOTE: string                          // same sentence as the Python constant
```

Rules:
- `rowPrice`: tokens 0 and `cost` null or 0 → `no-usage`; tokens > 0 and `cost` null or 0 → `not-priced`; else `priced` with `usd = cost`.
- `totalPrice` with roles: sum the priced rows; `priced` if no row is `not-priced`, `not-priced` if no row is `priced`, else `partial`; all rows `no-usage` or no rows → `no-usage`.
- `totalPrice` with **no roles** (N9, old summaries): `wireTotal > 0` → `priced` with that value; otherwise `no-usage`.
- `priceLabel`: `priced` → `money(usd)`; `partial` → `money(usd) + ' (partial)'`; `not-priced` → `not priced`; `no-usage` → `—`.

`F/shared/fleet.store.ts`: `totalCost` becomes `ComputedRef<{ usd: number | null; excluded: number }>`. `usd` = sum of `run.cost` over runs where it is not null, null when there is none; `excluded` = number of runs whose `totalPrice(...).state` is `not-priced` or `partial`.

`F/shared/format.ts`: add `tokens(n: number): string` (thousands separators; `12,340`). `money` unchanged. `budgetPct` keeps its shape but its parameters are renamed `(counted: number, threshold: number)` in the same diff, so the names say what callers pass.

`Run.cost` mapping (both mappers and mock): `totalPrice(roles, s.cost_usd_total).usd`.

Mock switch for the budget gate entry (the mock's inbox seed is pinned at six items by `F/api/mock/index.test.ts` and the badge chain in `U/app.pw.ts`, and nothing at runtime creates a budget gate):

```text
MockOptions.budgetGate?: boolean          // F/api/mock/index.ts; default false
MOCK_BUDGET_GATE_PARAM = 'mockBudgetGate' // exported from F/api/mock/index.ts
```

When `budgetGate` is true, `seedInbox` appends a seventh item: `{ id: 'budget#2', type: 'gate', gate: 'budget', runId: 'feature-graph-demo', round: 2, age: '1m', title: 'Budget (round 2) — graph demo', body: 'Run cost $40.2000 >= budget $40.00' }` (the seeded run has budget 20, one crossing already approved, current limit 40; approving this one raises the limit to $60.00). `F/api/client.ts` passes `budgetGate: new URLSearchParams(window.location.search).has(MOCK_BUDGET_GATE_PARAM)` when it builds the mock (the search part precedes the hash: `/?mockBudgetGate=1#/inbox`). Off by default, so every existing test sees six items.

`U/.../StartRunModal.vue`: `StartRunPayload.budget: string` (trimmed text; `''` = none); prop `initialBudget?: string`.

`F/app/ui.store.ts`: `startBudget: Ref<string>`, reset by `resetStartForm`.

### 2.5 New files

| File | Kind |
|---|---|
| `src/sdlc/run_budget.py` | module |
| `tests/test_run_budget.py` | unit |
| `tests/test_code_attempt_usage.py` | unit, fast tier (FR-015a) |
| `tests/test_cli_budget.py` | unit (parser level, like `tests/test_cli_role_model.py`) |
| `F/shared/cost.ts`, `F/shared/cost.test.ts` | pure helper + test |
| `F/features/cost/CostTab.vue`, `F/features/cost/CostTab.test.ts` | screen + test |

### 2.6 Test ids (Cost tab)

`cost-tab` (root), `cost-row` (one per role, `data-role` attribute), `cost-row-price`, `cost-row-tokens`, `cost-total-price`, `cost-total-tokens`, `cost-budget`, `cost-budget-counted`, `cost-budget-pct`, `cost-budget-crossings`, `cost-budget-note`, `cost-research-note`, `cost-empty`, `cost-no-breakdown`. Start form: `start-budget-input`, `start-budget-error`. Inbox: `gate-budget-note`. Header: existing stats node; no new id.

## 3. Traps

| Habit | Use instead |
|---|---|
| `money(run.cost ?? 0)` | `priceLabel(totalPrice(run.roles, run.cost))` |
| `cost == null ? '—' : money(cost)` on a role row | `rowPrice(row)`; a 0 with tokens is `not priced` |
| percent = cost / budget | counted / threshold |
| `PipelineConfig(run_budget_usd=x)` as the validator | `parse_run_budget(x)` |
| `cost_usd=str(run.cost_usd or 0.0)` | omit the key when None |
| adding dev usage to `_role_usage` | never; that changes the gate (FR-015) |
| editing `stages/code/step.py` | only `stages/code/usage.py` |
| hand-editing `fleet-snapshot.json` | `python scripts/dump_dashboard_fixtures.py` |
| `STATUS-PIP-1` style clause ids | underscores: `START_RUN_MODAL-3` |

## 4. Name check (first task)

Before any edit, confirm each row of §1 by reading the cited line; stop on any difference and report. After the type changes in §2.4, `vue-tsc` (first step of `check_ui.py`) is the proof that both providers fill every new `Run` field.
