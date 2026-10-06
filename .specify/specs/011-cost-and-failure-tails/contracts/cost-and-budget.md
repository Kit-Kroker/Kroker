# Contract: Cost tab and run budget (011, US1 + US2)

Behaviour, clause wording and the requirement-to-proof table. Names are in [data-model.md](../data-model.md); decisions in [research.md](../research.md). `F/` = `interfaces/dashboard/frontend/src/`, `U/` = `interfaces/ui/`.

## 1. Server

### 1.1 `POST /runs`

Request adds optional `budget_usd`. Response adds optional `budget_notice`.

| Request `budget_usd` | Result |
|---|---|
| absent or `null` | run starts with no budget; `budget_notice` null; today's behaviour |
| `5`, `5.5`, `"5"` | run starts with `run_budget_usd` 5 / 5.5 / 5; `budget_notice` is the FR-009 text |
| `0`, `"0"` | 422, `loc` ends in `budget_usd`, message contains `omit it to run without a budget` |
| `-1`, `"abc"`, `true`, `"NaN"`, `"inf"` | 422, `loc` ends in `budget_usd`; no run is started |

The starter is called with a `PipelineConfig` whose only difference from the default is `run_budget_usd`.

### 1.2 `python -m sdlc.cli start --budget-usd AMOUNT`

Same table. A rejected value exits with argparse's usage error (exit code 2) naming `--budget-usd` and carrying the same message; nothing is started and no Temporal connection is needed to reject it. An accepted value prints the notice on its own line after the run id.

### 1.3 Live run state and closed summary

- `RunState.roles` lists every role with a `MODEL_USAGE` event so far, `dev` included. `RunState.cost_usd_total` is the sum of the rows whose `cost_usd` is not None, or None.
- `RunState.budget_threshold_usd` and `budget_counted_usd` are None without a budget. With one: threshold starts at the budget and rises by the budget on each approve; counted is the gate's own sum.
- `RunSummary.budget_counted_usd` is the gate's sum at close, None without a budget.
- A code attempt whose harness reported no cost produces a `MODEL_USAGE` event with no `cost_usd` key; the role's `cost_usd` stays None unless another attempt was priced.
- The budget gate itself is unchanged: same sum, same threshold arithmetic, same gate text (FR-015).

## 2. Client

### 2.1 Mapping

`mapRun` and `mapClosed` fill `roles` (snake to camel, missing → `[]`), `budgetThreshold` (closed → null), `budgetCounted`, `budgetCrossings` (missing → 0), `budgetNotice: null`, and `cost` via `totalPrice`. `startRun` sends `budget_usd` only when `input.budget` is not null, and returns a row with `budget` = the requested budget, `roles: []`, `budgetNotice` = the response's notice.

### 2.2 Mock

Seeds at least: one running run with three roles of which one is `not-priced` (tokens, cost 0) and a budget with one crossing; one closed run all priced with no budget; one closed run with a total and `roles: []` (N9); one run with `roles` all `not-priced`. `startRun` honours `input.budget` (budget on the new row, `budgetNotice` set to the fixed sentence when a budget is given). `tickCosts` keeps `cost` equal to the sum of priced roles for runs that have roles.

## 3. Cost tab (`F/features/cost/CostTab.vue`)

Props: `runId: string`. Reads the run from the fleet store.

| State | Rendered |
|---|---|
| run not loaded | `cost-empty` with `Loading…` |
| run loaded, `roles` empty, total `no-usage` | `cost-empty`: `No usage recorded yet.` Budget block still shown when a budget is set. |
| `roles` empty, wire total > 0 (N9) | `cost-no-breakdown`: `No breakdown recorded for this run.` plus the total |
| roles present | one `cost-row` per role in wire order: role, model, calls, `cost-row-tokens` (in / out / cache read / cache write, via `tokens`), `cost-row-price` (`priceLabel(rowPrice(r))`) |
| always with roles | `cost-total-tokens`, `cost-total-price` (`priceLabel(totalPrice(...))`) |
| always | `cost-research-note`: `The research stage has its own search, fetch and cost limits; they are separate from the run budget, and its own spend is not listed here.` |

Budget block (`cost-budget`):

| Run | Rendered |
|---|---|
| `budget` null | `No budget. Set one when starting a run (--budget-usd or the start form).` |
| open, budget set | budget; current limit (`budgetThreshold`); `cost-budget-counted`: `counted toward budget $X`; `cost-budget-pct`: counted / threshold, whole percent; `cost-budget-crossings`; `cost-budget-note`: `Budget ` + `BUDGET_SCOPE_NOTE` |
| closed, budget set | budget; `cost-budget-counted` when not null; crossings; `cost-budget-note`; no percent |
| closed with outcome `rejected:budget` | as above; the run's status already shows the outcome |

A not-priced row prints the words `not priced`, never `$0.00` and never a blank.

## 4. Other surfaces

- **Run page**: `RunView` enables the Cost tab only when a `#cost` slot is supplied; `?tab=cost` selects it and round-trips like `?tab=board`; `RunPage` supplies the slot. Gates stays disabled.
- **Header**: `"$12.40"` when nothing is excluded; `"$12.40 · 3 not priced"`; `"not priced"` when runs exist and none is priced; `"—"` when there are no runs. Label `spend` (was `spend today`).
- **Start form**: optional `BUDGET (USD)` input. Empty → no budget. Non-empty and not a number > 0 → `start-budget-error` shown with the same two messages as the server, submit blocked. After a successful start with a budget, the notice is shown as a toast.
- **Inbox budget item**: under the gate control, `gate-budget-note`: `Approve raises the limit to $X and the run continues. Any other decision ends the run.` (`X` omitted with `the limit` when the run row is unknown.) Only for `item.gate === 'budget'`.

## 5. Clauses

### 5.1 `U/app.md` (assembled console)

**CONSOLE-10 (amended)**: replace `disabled (?tab=cost)` with `disabled (?tab=gates)`. Nothing else changes.

**CONSOLE-24**: The run page's Cost tab lists one row per role with its calls, tokens and dollars, and a total; `?tab=cost` opens it and a copied URL reopens it. [FR-001, FR-701]

**CONSOLE-25**: A role or total that has tokens and no price reads "not priced", and a total that mixes priced and unpriced roles is marked partial; no such figure reads `$0.00`. [FR-003, FR-701]

**CONSOLE-26**: With a budget, the Cost tab shows the budget, the dollars counted toward it, the share of the current limit used, the number of crossings, and which spend the budget does not count; without one it says there is no budget. [FR-001b, FR-701]

**CONSOLE-27**: The header's spend figure totals priced runs only and states how many runs it left out. [FR-003]

**CONSOLE-28**: The start form accepts an optional budget; a budget that is not a number greater than zero blocks the start with a message, and a run started with a budget shows that budget on its Cost tab. [FR-006, FR-007]

**CONSOLE-29**: A budget gate entry in the inbox says what approving grants. [FR-008, FR-701]

Failure modes gains one sentence: a closed run recorded before role tracking shows its total with "No breakdown recorded".

### 5.2 `U/src/components/start_run_modal/start_run_modal.md`

**START_RUN_MODAL-1 (amended)**: emits `submit` with `{ title, repo, mode, budget }`.

**START_RUN_MODAL-3**: The budget field is optional; when it is non-empty and not a number greater than zero the component shows an inline message and blocks submission. [FR-1400]

### 5.3 `U/src/components/app_header/app_header.md`

Failure modes: `Omitting stats renders fallback placeholders` stays true; the spend placeholder is `—`. The label is `spend`. No new clause.

## 6. Requirement to proof

| Requirement | Proof | Tier |
|---|---|---|
| FR-001 | CONSOLE-24 in `app.pw.ts`; `CostTab.test.ts` rows, total | app + unit |
| FR-001a | `tests/test_run_state_query.py`: a state with a `dev` trace event lists `dev`, total = sum of priced rows; `CostTab.test.ts` N9 case | py + unit |
| FR-001b | CONSOLE-26; `tests/test_run_state_query.py` threshold and counted before and after an approve; `tests/test_run_summary_build.py` counted | app + py |
| FR-002 | `CostTab.test.ts` research note present in every state | unit |
| FR-003 | `cost.test.ts` (every rule of data-model §2.4); CONSOLE-25; CONSOLE-27; `fleet.store.test.ts` totalCost shape | unit + app |
| FR-004 | `cost.test.ts`: no rule returns dollars the row did not carry; mock test: `cost` equals sum of priced roles after a tick | unit |
| FR-005 | `check_clauses.py` output lists CONSOLE-24..29 covered; CONSOLE-10 test uses `?tab=gates` | script |
| FR-006 | `tests/test_dashboard_api.py` start with budget reaches the starter's cfg; `tests/test_cli_budget.py` parser and start config | py |
| FR-007 | `tests/test_run_budget.py` table of §1.1; API 422 cases; CLI exit 2 cases; CONSOLE-28; `start_run_modal.spec.ts` START_RUN_MODAL-3 | py + unit + app |
| FR-008 | CONSOLE-29 in `app.pw.ts` behind the mock switch; `entries.test.ts` budget note only on budget gates; `mock/index.test.ts` six items by default, seven with the switch | app + unit |
| FR-009 | `tests/test_run_budget.py` notice text, None without budget, role list when unpriced; API returns it; CLI prints it | py |
| FR-015a | new fast-tier `tests/test_code_attempt_usage.py`: `_record_attempt_usage` with a fake context and a `HarnessRunResult` emits no `cost_usd` key when the harness cost is None, and the key when it is 0.0 or more; a rollup of the no-key event leaves `dev` unpriced. `tests/test_model_usage_capture.py` (temporal tier) stays green, unedited | py |
| FR-015 | `tests/test_budget_gate.py` unchanged and green **under `-m temporal`** (the file is temporal-marked; a plain run deselects it); `git diff` shows no edit under `workflows/role_host.py` | py + review |
| FR-016 | `check_file_size.py`; `tests/test_fleet_fixture_fresh.py` green after regeneration; `tests/test_run_summary_model.py` loads a summary without the new field | script + py |
| SC-007 | ROADMAP diff: FR-701 line, E-19 line, SC-10 line | review |

## 7. Not at the app tier

A budget gate entry exists on the mock only behind the switch of data-model §2.4 (`?mockBudgetGate=1`); CONSOLE-29's app-tier test and the manual walk open the inbox with it. The clause scanner reads only `*.spec.ts` and `*.pw.ts`, so CONSOLE-29 must be cited from `app.pw.ts`; the unit test in `entries.test.ts` is extra, not the clause's proof.

The mock cannot return a 422, so the server's rejection is proved in Python and the form's own block is proved at the app tier (CONSOLE-28). The notice's "No price found for" list is proved in Python only.
