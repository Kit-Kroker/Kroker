# Feature Specification: Cost Visibility and Failure Tails (audit item 6)

**Feature Branch**: `011-cost-and-failure-tails` (spec directory only; no branch is cut until exec)

**Created**: 2026-10-06

**Status**: Approved (2026-10-06). GATE 1 cleared with rulings R1 to R5 (see [GATE 1 rulings](#gate-1-rulings)). **This run's scope is US1 and US2 only.** US3, US4 and US5 are kept as the record and marked *exec: split S-batch run, queued behind US1+US2*; they are not to be planned or tasked in this run.

**Input**: TASK BRIEF "audit item 6: cost and failure behaviour (Стоимость и поведение при отказах)", relayed by the orchestrator on 2026-10-06.

**Base**: main `d1d87b23`.

## Context and verified findings

The audit says: a run has no budget (E-19) and no price (SC-10), so the user does not know how many tokens a run will spend; and three known reliability tails are still open. Every anchor in the brief was re-read in code on main `d1d87b23`. Nothing was run. `F/` = `interfaces/dashboard/frontend/src/`.

### Theme A: cost and budget

| # | Claim (from the brief) | Verified state | Consequence for this spec |
|---|---|---|---|
| A1 | `run_budget_usd` exists, 0.0 = off | **True.** `src/sdlc/core/models.py:414`, `Field(default=0.0, ge=0.0)`. Crossing it raises a hard `budget` gate; approve adds one more increment of the same amount, reject ends the run `rejected:budget` (`role_host.py:279,305`, `run_host.py:110,145`, `graph.py:169`, `feature.py:290`). | The mechanism is built. This spec adds no new gate. |
| A2 | The budget is hard to set | **Worse than the brief says: it cannot be set per run from any entry point.** `cli.py:428` builds `PipelineConfig()` and only overlays `--role-model`; the dashboard start (`dashboard/api.py:349`) and the operator start tool (`operator/tools.py:541`) pass `PipelineConfig()` untouched. There is no environment or file source. `StartBody` (`api.py:67`) has no budget field. Only tests and `benchmarks/workflow.py` build a config with a budget. | Finding N1. The first requirement is a way to set it at all. |
| A3 | No budget surface in the dashboard API or CLI | **True.** Zero hits for "budget" in `dashboard/` and none for the field in `cli.py`. | FR-005 to FR-007. |
| A4 | Run counters live in `RunSummary.roles` | **True.** `RoleUsage` (`models.py:135`) holds per-role calls and four token counts. `cost_usd` is `None` until a call is priced: a pricing miss never drops tokens. `RunSummary` and the live `RunState` both carry `roles`, `cost_usd_total` (None, never 0.0, when pricing failed), `budget_usd` and `budget_crossings`. | The data for a breakdown already exists on both open and closed runs. |
| A5 | The Cost tab is a disabled placeholder; the header shows total cost | **True.** `F/features/run/RunView.vue:67` (ruling G7 of spec 002); `interfaces/ui/app.md` CONSOLE-10 pins `?tab=cost` as a disabled value that renders Graph. Header total: `F/shared/fleet.store.ts:33`. | US1. |
| A6 | The client carries cost | **Partly.** `F/api/http.ts:74,96` map `cost_usd_total` and `budget_usd` onto each fleet row. Per-role `roles` are **not** mapped, and a run just started is given `cost: null, budget: null` (`http.ts:234`). `F/api/types.ts:34-35` has only the two scalars. A `budgetPct` helper exists (`F/shared/format.ts:5`) and nothing in the shell visibly uses a budget. | Both providers (http, mock) need the per-role breakdown, FR-004. |
| A7 | Research has its own budgets (FR-107) | **True and separate.** Stage-scoped `max_searches` / `max_fetches` / `max_cost_usd` (default 1.0 per sub-question, 4.0 per run). | Out of scope; the Cost tab must label them as not the run budget. |
| A8 | FR-701 says "E-19 remains the general version" | `ROADMAP.md:323`: E-33 delivered counters, the budget gate and increments. What E-19 still adds is not written down anywhere: `ROADMAP.md:536` lists it only as "run budgets (**E-19**)". The nearest written items are FR-922 per-phase budgets (E-55, open, `:383`) and SC-10 (`:461`). | Q1 pins the reading. This spec does not claim to close E-19 unless Q1 says option (d). |
| A9 | Prices are often unknown | **True, measured.** 38 of the 79 `summary.json` under `runs/pipeline/` carry a priced total. The benchmark audit (F5, `docs/reports/2026-10-06-benchmark-improvement-plan.md`, read only) reports $0.00 on all 200 opencode code records with tokens present, no cost or tokens on review records, and research near half of measured dollars. | The display contract (Q3) is load-bearing, FR-003. |
| A10 | Budget gate is a gate kind the inbox can show | Not verified end to end. 010 delivered the inbox for clarify, gate, override and escalation items; whether a `budget` gate renders with a usable explanation (amount spent, threshold, what approve grants) was not read. | Plan task: read it, then FR-008. |

### Theme B: the three tails

| # | Card | Verified state | Consequence |
|---|---|---|---|
| B1 | golden-trace flake (M) | Card text confirmed (`.workspace/tasks/2026-10-02-golden-graph-trace-flake.md`): `budget_arch_reject-sandboxed` projects `activity:publish_artifact_version` where the golden has `timer`, plus one extra trailing item. Reproduced 3/3, then passed 2/2 with no code change. The temporal CI step is `continue-on-error: true` (`.github/workflows/ci.yml:49`), so main never goes red on it. The `budget_arch_reject` scenario sets `run_budget_usd` (`tests/replay/scenarios.py:372`), so **the flake sits on the budget gate path this spec is about**. | US3. Cause is not yet known. |
| B2 | judge retry stacking (S) | The judge activity runs with `RECORD_ACT`, `maximum_attempts=5` (`workflows/benchmark_host.py:35,150`); the provider client keeps the SDK default of 2 retries, so up to 15 calls per judge request. `single_retry_layer()` (`agents/model_ids.py:119`) is reusable as is. `tests/durability/_http_stub.py` exists for the bound check. | US4. |
| B3 | attempt budget tuning (S) | Budgets confirmed: `AGENT_ACTIVITY_MAX_ATTEMPTS = 3` and `CLARIFY_FANOUT_MAX_ATTEMPTS = 3` (`agents/roles.py:40,58`); research has a six-attempt sub-question activity with 2 s initial interval, coefficient 2.0 (`stages/research/step.py:59-63`) and other 1 to 3 attempt activities. **The evidence the card wants is not in `runs/pipeline/`**: `events.jsonl` carries `model_usage` and gate events but no retry or activity-failure events (`observability/trace.py:16-28`). The only place that records attempts is Temporal history. | US5. Where to harvest is a plan task, and the answer may be "nothing recorded yet", in which case the tail's first deliverable is the recording, not a number. |

### Additional findings

- **N1: the budget is unreachable per run.** See A2. Everything the user asked for in theme A ("how much will I spend") starts with a way to set a budget on a run at the moment it starts. No fork option avoids this except (b).
- **N2: a "run price" in dollars alone lies.** A run on a subscription or coding-plan model shows `cost_usd_total = None` or $0.00 while burning real tokens. `RunSummary.cost_usd_total` is already `None`-not-zero by design; the fleet header total, however, sums `r.cost ?? 0` (`fleet.store.ts:33`), so unpriced runs silently count as free in the one number every page shows. FR-003 covers the header too.
- **N3: the budget gate counts only priced dollars.** A budget in USD cannot trip on a model whose calls come back unpriced. A user who sets one on a coding-plan run gets no protection and no warning. FR-009 requires the screen to say so; a token budget is raised as Q-extra under Q3.
- **N4: the benchmark's own plan wants "fixed budget per run, tokens and turns reported per arm" (Phase 4.2).** Not a conflict: it is the same budget plus token reporting. FR-003's token fallback is what makes it consistent. The plan document is read only here and is never edited.

### Post-gate findings (2026-10-06, advisor and skeptic consults; verified in code)

These correct A4 and A6 above. Ruled on 2026-10-06 as R6 and R7 (`.workspace/tmp/011-escalation-1.md`).

- **N5: an open run's role list leaves out the coding harness.** The live state builds `roles` and `cost_usd_total` from the proposer-agent bag only (`workflows/run_host.py:159`, written solely by `_track_usage`, `report_host.py:56`). Coding attempts record their usage as trace events and never enter that bag (`stages/code/usage.py:28-50`). The `dev` role therefore appears only when the run closes, when the summary is rebuilt from the trace (`observability/summary.py:55`). The research stage's own spend goes to a local bag (`stages/research/step.py:252`) and reaches neither.
- **N6: the budget gate counts the same partial bag.** `_check_budget` (`role_host.py:281`) sums that bag, so coding-harness, crew and research-stage dollars never count toward a budget. A run can finish far over its budget with zero crossings.
- **N7: a missing harness price is written as zero.** `stages/code/usage.py:49` emits `cost_usd=str(run.cost_usd or 0.0)`, and opencode itself reports a numeric 0 on subscription models. Of the summaries on this machine, the `dev` role is `None` in 28 and exactly `0.0` in 10. On the wire a real zero and a missing price look the same, so "never `$0.00` for a missing price" (R2) needs a rule the wire does not give for free.
- **N8: a role priced on some calls and not others is not marked.** `merge_usage` keeps a running sum once any call is priced (`observability/usage.py:34`), so "partial" is knowable for a total (some roles unpriced) but not inside one role.
- **N9: closed runs written before role tracking carry an empty role list** with a non-empty total; the tab must render that as "no breakdown recorded".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what a run costs and what it is allowed to cost (Priority: P1)

On a run's page, the Cost tab is live. A person opening it sees the run's spend per role, the total, the budget (or "no budget"), how much of it is used, and how many times the budget gate has been raised. When some calls could not be priced, the tab says so and shows tokens, so the total never reads as free.

**Why this priority**: This is the audit's first complaint, "the user does not know how many tokens they will spend". The data exists on every run; nothing shows it.

**Independent Test**: On the mock provider, open `?tab=cost` for a run with a priced role, an unpriced role, and a budget; assert all three states render, and that an unpriced role shows tokens and the words "not priced", not `$0.00`.

**Acceptance Scenarios**:

1. **Given** a run whose roles are all priced, **When** the Cost tab opens, **Then** each role shows calls, tokens and dollars, and the total equals the sum.
2. **Given** a run where one role is unpriced, **When** the tab opens, **Then** that role shows tokens and "not priced", the total is labelled partial, and no figure reads `$0.00` for a role that had calls.
3. **Given** a run with budget 40, no crossing yet, and 31 counted toward the budget, **When** the tab opens, **Then** it shows 77 % used and the number of budget crossings so far. (Percent is counted over the current limit; after one approve the limit is 80. R6, plan research R-3.)
4. **Given** a run with no budget, **When** the tab opens, **Then** it says "no budget" and offers the setting rule from US2, not a blank.
5. **Given** a closed run, **When** the tab opens, **Then** it renders from the run's summary, identically.

---

### User Story 2 - Set a budget when starting a run (Priority: P1)

A person starting a run, from the command line or the dashboard (Q4), can state a budget in dollars. The run honours it: crossing it raises the existing budget gate, and the fleet row and Cost tab show it.

**Why this priority**: Without this the budget gate shipped in E-33 is dead code for every real user (N1).

**Independent Test**: Start a run through each chosen entry point with a budget; assert the started run's config carries it and its fleet row reports it. Start without one; assert today's behaviour is unchanged (off).

**Acceptance Scenarios**:

1. **Given** a start request with budget 5, **When** the run starts, **Then** its configured budget is 5 and the fleet row's budget is 5.
2. **Given** no budget in the request, **When** the run starts, **Then** the budget is off, exactly as today.
3. **Given** a negative or non-numeric budget, **When** the request is made, **Then** it is rejected before any run starts, with a message that names the field.
4. **Given** a budget on a run whose model is unpriced, **When** the run starts, **Then** the person is told the budget counts priced dollars only (N3).

---

### User Story 3 - Stop the golden-trace test from flaking (Priority: P2)

> **exec: split S-batch run, queued behind US1+US2 (R1).** Lands first in that follow-up run: it sits on the budget scenario and validates US2's path. CI policy is not changed (R4).

`budget_arch_reject-sandboxed` passes or fails depending on machine load. After this story it either passes deterministically or its cause is fixed in the code, and the decision about whether CI shows the temporal tier is made explicitly (Q5).

**Why this priority**: A flake on the budget gate path undermines the verification of US1 and US2, and the CI tier hides it.

**Independent Test**: Run the case repeatedly under load (the card's three failing environments) and get a stable result; the fix is the card's "pin the timer" or the investigated race, whichever the plan proves.

**Acceptance Scenarios**:

1. **Given** the scenario, **When** it is replayed N times under artificial load, **Then** it passes N of N times (N set in the plan).
2. **Given** the root cause is a real nondeterminism in the workflow, **When** fixed, **Then** the golden changes only if the new behaviour is intended and the change is recorded.

---

### User Story 4 - Bound the benchmark judge's retries (Priority: P2)

> **exec: split S-batch run, queued behind US1+US2 (R1).**

A judge call against a provider that always answers 429 makes at most as many HTTP requests as the activity budget, not three times as many.

**Why this priority**: Small, independent, and a cost bug: stacked retries spend quota during exactly the failure that exhausts it.

**Independent Test**: Point the judge at the always-429 stub; count requests; assert the count is at most the activity attempt budget.

**Acceptance Scenarios**:

1. **Given** the always-429 stub, **When** one judge request runs, **Then** the stub sees at most 5 requests.
2. **Given** a successful judge call, **When** it runs, **Then** its output is unchanged.

---

### User Story 5 - Set the attempt budget from evidence, not a guess (Priority: P3)

> **exec: split S-batch run, queued behind US1+US2 (R1).** A retry recorder is in that run's scope only if the Temporal history (benchmark :7234, pipeline :7233) lacks what the evidence table needs (R5). This run's plan does not build it.

Retry attempts and backoff for model calls are chosen from recorded failures: how often a model call exhausted its attempts on 429 or 5xx, and how long the bursts lasted. If no such record exists, this story first makes one.

**Why this priority**: It is data-gated. It can end in "keep the numbers" with evidence, which is a valid result.

**Independent Test**: A written evidence table with counts and burst lengths from real histories, the decision derived from it, and the retry-bound tests moved to the new numbers.

**Acceptance Scenarios**:

1. **Given** the harvested histories, **When** the table is built, **Then** it states how many model calls exhausted their attempts and the longest burst.
2. **Given** the decision changes a number, **When** the tests run, **Then** the bound tests assert the new number and the baseline counts are re-recorded.

---

### Edge Cases

- A budget is set, the run crosses it, the person approves: the threshold rises by one more increment of the same amount (A1). The Cost tab shows the current threshold, not only the first one.
- A role is priced on some calls and unpriced on others: the run does not record this (N8), so the row shows its dollars without a partial mark. Marking it is out of scope; "partial" applies to totals only.
- Budget set on a run that never makes a priced planning-agent call: it can never trip; FR-009 warns at start and the tab says so.
- A run closes well over its budget with zero crossings because the spend was in the coding harness: the tab shows total, counted toward budget, and the sentence that explains the difference (FR-001b).
- A run closed with `rejected:budget`: the Cost tab and fleet row show the outcome and the final spend.
- Two runs share a role name: each tab shows only its own run.
- The run state is not yet available (just started): the tab shows loading, then zero calls, not an error.
- A very small budget (0.01): accepted; it crosses on the first priced planning-agent call.
- A budget of exactly 0: rejected (R7).
- CLI flag given twice or with a unit suffix: rejected with a message, never guessed.

## Requirements *(mandatory)*

### Functional Requirements

**Cost visibility (US1)**

- **FR-001**: The run page's Cost tab MUST be enabled and show, for the open or closed run: per-role calls, tokens (input, output, cache read, cache write), dollars; the run total; the budget; percent used; budget crossings. Both client providers (http, mock) MUST supply the same per-role data.
- **FR-002**: The Cost tab MUST state that the research stage's own search, fetch and cost limits are separate from the run budget, and that the research stage's own spend is not in the run's role list (N5).
- **FR-001a** (R6): An open run's role list MUST include every role the run has recorded usage for so far, including the coding harness, and its total MUST equal the sum of its priced rows. A closed run with a total but no recorded roles (N9) MUST say "no breakdown recorded".
- **FR-001b** (R6): When a budget is set, the Cost tab MUST show the dollars counted toward the budget next to the total, and say which spend the budget does not count.
- **FR-003**: Wherever a dollar figure for a run, role or fleet total is shown, a missing price MUST NEVER display as `$0.00`. A dollar value of zero on a row that has tokens is a missing price (R6, N7). Display rule (R2): dollars where priced; tokens ALWAYS shown per role and for totals; a "not priced" label on any role or total without a price; a "partial" label on a total that mixes priced and unpriced rows. The fleet header total counts priced runs only and states how many runs it left out (N2). The rule applies to the Cost tab, the fleet row and the header.
- **FR-004**: The Cost tab MUST NOT invent a price. Dollars come only from the run's recorded usage; a run with none shows "not priced".
- **FR-005**: `interfaces/ui/app.md` MUST gain clauses (next free number is CONSOLE-24) that pin the tab's states, and CONSOLE-10 MUST be amended so `?tab=cost` is no longer a disabled value; tests in `interfaces/ui/app.pw.ts` MUST cover each clause on the mock provider.

**Budget setting (US2)**

- **FR-006**: A person MUST be able to state a run budget in dollars when starting a run, from both the command line's start command and the dashboard's start request (R3). Absent means off, today's behaviour unchanged. The operator start tool is left as is unless the plan finds the change trivial.
- **FR-007**: A budget less than or equal to zero (R7: an explicit 0 is rejected with the hint "omit the flag to run without a budget"), or not a finite number, MUST be rejected before the run starts, naming the field. Both entry points share one validation (R3).
- **FR-008**: When the budget gate is raised, the item the person sees MUST say how much has been spent, the threshold, and what approving grants. (Depends on A10; if the existing item already does, this becomes a test, not a change.)
- **FR-009**: When a run is started with a budget, the start response and screen MUST say what the budget counts today (R6): priced planning-agent dollars only, not the coding harness, crew or research stage. When a planning role's model has no known price, the warning MUST also name that role. The budget stays dollars-only for the alpha; there is no token budget (R2 sub-ruling), and this warning is how the gap is documented to the person.

**Tails (US3 to US5; exec: split S-batch run, queued behind US1+US2, R1; not planned in this run)**

- **FR-010**: `budget_arch_reject-sandboxed` MUST be deterministic under load, by pinning the timer in the scenario or by fixing the cause the plan proves.
- **FR-011**: CI treatment of the temporal tier is decided (R4): it stays advisory (`continue-on-error`). No CI change is planned in this run or as a side effect of the flake fix; a non-gating red-badge job is a follow-up card the orchestrator files.
- **FR-012**: A judge request against an always-429 provider MUST make at most as many HTTP requests as the judge activity's attempt budget.
- **FR-013**: The attempt-budget decision MUST cite its evidence: counts of exhausted model calls and burst lengths, and where they were read. If no record exists, the first deliverable is the record.

**Scope guards**

- **FR-014**: SC-10 (assessment economics per repo-size band) and FR-922/E-55 (per-phase budgets) are out of scope: they need per-phase budgets and measured runs that do not exist. The spec MUST state what the alpha ships instead (US1 and US2) and what SC-10 still waits for (E-55 budgets plus runs per size band).
- **FR-015a** (R6): The code stage MUST record a missing harness price as missing, never as 0.0.
- **FR-015**: No requirement here changes the research stage's budgets, the budget gate's semantics, or FR-602 (MCP).
- **FR-016**: Each changed file stays under 1000 lines; no cross-stage calls; new wire fields are additive so existing runs and histories still load.

### Key Entities

- **Run cost view**: what the Cost tab shows for one run: role rows, total, budget, percent used, crossings, priced-or-partial flag.
- **Role usage row**: one role's calls, tokens and optional dollars (exists as `RoleUsage`).
- **Run budget**: an optional dollar amount fixed at start; crossing raises the budget gate; each approval grants one more increment.
- **Price state**: per row and per total: priced, partial, or not priced. Never inferred from a zero.
- **Retry evidence record**: per model-call activity: attempts used, final result, error class, and timestamps, enough to measure burst length.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can read a run's spend per role and its budget status in one tab, for open and closed runs, with no figure of `$0.00` shown for a role that had calls and no price.
- **SC-002**: A person can start a run with a budget in one step from each chosen entry point, and the budget is visible on that run within one refresh.
- **SC-003**: With a budget set, a run whose priced spend crosses it stops at the budget gate 100 % of the time in tests, and a run without one behaves exactly as before.
- **SC-004**: `budget_arch_reject-sandboxed` passes N of N consecutive runs under load (N in the plan), versus 0 of 3 failing environments before.
- **SC-005**: One judge request against an always-429 provider produces at most 5 provider requests, down from up to 15.
- **SC-006**: The attempt-budget decision is accompanied by a table of real counts and burst lengths, or by a recorded finding that none exist and a recorder that makes them.
- **SC-007**: ROADMAP states plainly what E-19 still means after this item, and that SC-10 waits on E-55 plus data.

## Assumptions

- The Cost tab and budget setting are the alpha for theme A; no pre-run estimate is attempted, since no data supports one.
- Dollar budgets are enough for the alpha; token budgets are Q3's extra, not assumed.
- The live run state already exposes `roles`, `cost_usd_total`, `budget_usd` and `budget_crossings` to the dashboard backend (read from the model, not run); only the client mapping is missing.
- Providers http and mock both implement every new client method (app-tier rule).
- All Python verification runs in `kroker-dev`; UI checks run `python scripts/check_ui.py` from the repo root on the host; heavy suites are staggered while benchmark agents are live.
- The benchmark improvement plan is read only context and is never edited.
- Integration is fast-forward main and push; commits carry no attribution trailers (standing ruling, CLAUDE.md).

## GATE 1 rulings

Ruled by the user via the orchestrator on 2026-10-06 (`.workspace/tmp/gate1-ruling-item6.md`). Binding.

| # | Question | Ruling |
|---|---|---|
| R1 | Q1 + Q2, run shape | **Split.** This run ships US1 + US2 only. US3, US4, US5 run as a follow-up S-batch, queued behind US1+US2, with the flake (US3) first. |
| R2 | Q3, display contract | **Option B.** Dollars where priced; tokens always, per role and for totals; "not priced" and "partial" labels; the fleet header totals priced runs only and says how many it left out. Never `$0.00` for a missing price. Budget stays dollars-only; FR-009 documents the gap; no token budget now. |
| R3 | Q4, where a budget is set | **Both** a CLI start flag and an optional field in the dashboard start request, one shared validation (FR-007). Operator start tool untouched unless trivial. Absent = off. |
| R4 | Q5, CI temporal tier | **Stays advisory.** No CI changes in this run. The red-badge job is the orchestrator's follow-up card. |
| R6 | Escalation 1 (N5 to N7): the gate counts only part of the spend | **P1: honest display now, gate unchanged.** The Cost tab shows everything the run recorded, open or closed; an open run's role list is built from the trace, as a query-side change only. A row with tokens and a dollar value of zero or none reads "not priced", and the code stage stops writing a missing price as 0.0. The budget is settable as R3 rules. FR-009's warning states exactly what the gate counts today: planning-agent dollars only, not the coding harness, crew or research stage. The Cost tab shows "counted toward budget" next to the total. FR-015 stands. "Budget gate counts all recorded spend" is a new inbox card queued behind the flake fix (US3). |
| R7 | Budget of 0 | **Rejected** at either entry point with the hint "omit the flag to run without a budget". Absent = off. |
| R5 | Q6, retry recorder | **Conditionally in the follow-up run's US5**, only if Temporal history lacks the evidence. Not built by this run's plan. |

Scope guards FR-014, FR-015, FR-016 stand unchanged. E-19's "general version" is not claimed closed by this run (A8); the ROADMAP wording for SC-007 follows R1 to R3.

**Success criteria in this run:** SC-001, SC-002, SC-003, SC-007. SC-004, SC-005, SC-006 belong to the follow-up run.

## GATE 1 questions

Kept as the record of the fork. Recommendations were mine; the rulings above supersede them.

**Q1. Scope fork.**

| Option | Alpha ships | Cost |
|---|---|---|
| **a (recommended)** | US1 + US2: Cost tab live, budget settable at start, SC-10/E-55 written down as blocked on data | M for theme A |
| b | Tails only (US3 to US5); cost stays not-alpha | S + S + M; leaves the audit's headline complaint open |
| c | US1 only; tails stay queued | S to M; budget stays unreachable (N1), so the tab would show "no budget" on every real run |
| d | Full E-19 including per-phase budgets | L, register-sized; its definition is not written (A8); needs E-55 |

(c) is the weakest: it makes the visibility real but leaves the budget dead (N1). (d) cannot be planned until E-19 is defined.

**Q2. Tails: same spec or a split run?** Recommended: **split**. B2 is S and independent, B3 is data-gated and may end as "build the recorder first", B1 is M. Riding with theme A would hold the user-facing win behind a measurement. If split, US3 to US5 stay here as the record and exec follows as an S-batch; one exception is worth considering: B1 sits on the budget-gate scenario, so it should land before or with US2's tests.

**Q3. Cost display when a price is unknown.**

| Option | Behaviour |
|---|---|
| a | Tokens only, no dollars at all |
| **b (recommended)** | Both: dollars where priced, tokens always; "not priced" and a partial-total label where not; fleet header totals priced runs and says how many it left out |
| c | Hide the dollar figure when any price is unknown |

(b) is the only option consistent with the benchmark plan's "tokens and turns reported per arm" and with E-33's rule that tokens survive a pricing miss. Sub-question if (b): add a token budget now, or leave the budget in dollars (N3)? Recommended: dollars only now, document the gap.

**Q4. Where a budget is set.** Recommended: **both** a CLI `start` flag and an optional field in the dashboard start request, sharing one validation (FR-007); the operator start tool is left as is unless the plan finds it trivial. Alternative: CLI only (smaller, but the dashboard is where runs are started most), or config-only, which does not solve N1.

**Q5. Un-hide the temporal CI tier?** It changes CI policy, not a test. The step is `continue-on-error: true` because of a separate assessment e2e deadlock (`ci.yml:44-48`). Recommended: **not in this spec**. Fix the flake (FR-010) and record in the plan that the tier stays advisory until the deadlock is fixed; offer a non-gating red-badge job as a follow-up. Un-hiding now would turn an unrelated deadlock into a blocker on every push.

**Q6. Anything else.** Two findings the brief did not name, both affecting how Q1 to Q4 read: N1 (the budget has no entry point at all today) and the fact that retry evidence is not in `runs/` (B3). Should the plan treat a retry recorder as in scope for US5, or as its own card? Recommended: in scope for US5 only if the plan finds the Temporal history on :7234 lacks what B3 needs.
