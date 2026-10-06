# Baseline: 011-cost-and-failure-tails (T001)

Recorded 2026-10-06 in the worktree `D:\own\Kroker-wt011`, branch
`011-cost-and-failure-tails`, before any source edit.

## Base and binding

- Base sha: `d1d87b23` (`git rev-parse --short HEAD`); `main` and
  `origin/main` also at `d1d87b23`, so main has NOT moved past the base and
  the T001 diff check against later main is vacuous.
- Branch head equals the base: no source file differs from base at this
  point; the only untracked content is this spec set.
- `kroker-dev` binding: in-container git is non-functional for this
  worktree (`.git` points at the host main repo), so the binding was proved
  by content hash instead, as ruled by the orchestrator:
  - host `git rev-parse --short HEAD` → `d1d87b23` (expected until first commit)
  - `md5sum src/sdlc/core/models.py` → host `588d88b7447187d9febccf87bcc82a01`
    = container `588d88b7447187d9febccf87bcc82a01`
  - `md5sum .specify/specs/011-cost-and-failure-tails/tasks.md` → host
    `cf430a0fb095301a94e545cae1cbd7b8` = container `cf430a0fb095301a94e545cae1cbd7b8`
  - Equal ⇒ binding OK.
- `src/sdlc/core/models.py` is clean in this tree (the primary checkout's
  pending edit is not here — tripwire passed).

## Container gates (kroker-dev, one command per call)

| Command | Result |
|---|---|
| `uv run pytest` | `3 failed, 5621 passed, 11 skipped, 255 deselected` in 686.75 s |
| `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py` | `3 passed` in 46.29 s (non-zero passed count; not deselected) |
| `uv run pytest -m temporal tests/replay` | `32 passed, 21 skipped, 171 deselected` in 107.28 s |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `1668 files already formatted` |
| `uv run mypy` | `Success: no issues found in 386 source files` (0 errors) |

Pre-existing fast-tier failures at base (recorded, not caused by this run):

- `tests/test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`
- `tests/test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`
- `tests/test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`

All three read git state; the container's `/app` is a worktree bind whose
`.git` file points at the host repo, so in-container git operations fail.
They are expected to keep failing identically throughout this run; any
OTHER fast-tier failure after a change is SG-4.

`budget_arch_reject-sandboxed` (the known flake, card
`2026-10-02-golden-graph-trace-flake.md`): **passed** at baseline (part of
the 32 replay passes; a targeted `-k budget_arch` run confirmed the case
executes). Its state may flip under load; a failure that matches the card's
signature is recorded, not fixed (SG-3 wording).

## Host gates

| Command | Result |
|---|---|
| `python scripts/check_ui.py` | `ui gate passes` — install, typecheck, typecheck-ui, build-dashboard, build-ui, vitest-dashboard, playwright-browser, ds-bundle, vitest-ui, playwright all green, no skipped step |
| `python scripts/check_clauses.py` | `195 clauses declared, 10 untested, 0 dangling`. Untested (pre-existing, none CONSOLE-*/START_RUN_MODAL-*): ARCH-1.4, CODE-1.6, CODE-1.7, MERGE-1.6, MERGE-1.7, MERGE-1.8, MERGE-1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6 |
| `python scripts/check_file_size.py` | silent (green); no file over the 1000-line ceiling |

UI counts at base: **vitest-dashboard 446 tests / 39 files passed;
vitest-ui 147 tests / 32 files passed; Playwright 94 passed**.
`PLAYWRIGHT_BROWSERS_PATH` resolves to `D:/own/.pw-browsers` (exists; the
script sets it on win32 when unset).

## Name check (data-model §4)

Every row of data-model §1 was read at its cited location; all match, no
stop-guard:

- `RoleUsage` — `core/models.py:135`, fields exactly as listed
  (`cost_usd: float | None = None` at :149).
- `PipelineConfig.run_budget_usd` — `core/models.py:414`
  `Field(default=0.0, ge=0.0)`.
- `RunSummary` — `core/models.py:477`; has `roles` (:493),
  `cost_usd_total` (:494), `budget_usd` (:495), `budget_crossings` (:496).
- `RunState` — `core/models.py:513`; has `roles` (:533),
  `cost_usd_total` (:534), `budget_usd` (:535), `budget_crossings` (:536).
- `StartBody` — `dashboard/api.py:67` (`title, description, mode, repo`).
- `StartedRun` — `dashboard/api.py:74` (`run_id`).
- `_role_rollup(trace)` — `observability/summary.py:54`,
  `list[RunEvent] -> list[RoleUsage]`; treats an absent `cost_usd` key as
  unpriced (:63,71).
- `build_run_summary(...)` — `observability/summary.py:76`, keyword-only,
  has `budget_usd`; `cost_usd_total` = priced sum or None (:130,152).
- `_record_attempt_usage` — `stages/code/usage.py:28`; emits MODEL_USAGE for
  role `dev`; today writes `cost_usd=str(run.cost_usd or 0.0)` at :49 (the
  FR-015a bug).
- `_snapshot_run_state` — `workflows/run_host.py:132`; roles/total today
  from `_role_usage` only (:140-161).
- `_budget_threshold` / `_budget_crossings` — `role_host.py:85-86` (init
  0.0/0), set to `cfg.run_budget_usd` at run start by `graph.py:169` and
  `feature.py:290`; raised by `+=` on approve (`role_host.py:305`); gate
  text `Run cost ${total:.4f} >= budget ${threshold:.2f}` (:296).
- `compute_price`, `PriceUsageInput` — `pricing.py:13,21`; pure, returns
  `float | None`, never raises.
- `resolved_roles(cfg)` — `workflows/graph_catalog.py:108`,
  `dict[str, RoleConfig]`; imports `..agents.roles.REGISTRY` lazily.
- `Run` — `F/api/types.ts:19`; `cost: number | null` (:34),
  `budget: number | null` (:35).
- `StartRunInput` — `F/api/types.ts:102` (`title, description, repo, mode`).
- `GateItem` — `F/api/types.ts:54` (`gate: string`, `runId`, `body`).
- `DashboardApi.startRun` — `F/api/types.ts:137`.
- `mapRun` / `mapClosed` — `F/api/http.ts:62,84`; map `cost_usd_total` /
  `budget_usd` at :74-75 / :96-97; optimistic row `cost: null,
  budget: null` at :231-236.
- `tickCosts` — `F/api/mock/index.ts:24` (bumps `cost` only on running
  rows; `feature-graph-demo` seed: cost 2.6, budget 20).
- `money` — `F/shared/format.ts:1`; `budgetPct(cost, budget)` at :5
  (parameters to be renamed `counted, threshold` in T006).
- `useFleetStore().totalCost` — `F/shared/fleet.store.ts:33`, today a
  number via `reduce((a, r) => a + (r.cost ?? 0), 0)`.
- `StartRunPayload` — `U/src/components/start_run_modal/StartRunModal.vue:6`
  (`title, repo, mode`).
- `AppHeaderProps.totalCost` — `U/src/components/app_header/AppHeader.vue`
  `string`, default `'$0.00'` (:13), label `spend today` (:60).

## T-verify confirmations (research R-1, R-5)

- **Sandbox import (R-1)**: `run_host.py` already imports
  `build_run_summary` from `..observability.summary` inside its single
  `with workflow.unsafe.imports_passed_through():` block (:21-32).
  `_role_rollup` lives in that same module, so it joins that import line —
  no new import block, no module marking. SG-5 not triggered.
- **Trace not truncated**: `ReportHost` creates `_trace` once
  (`report_host.py:28`) and only `_emit` appends (:41); nothing else writes
  or clears it anywhere in `src/`.
- **Proposer role list for R-5**: `agents/roles.py` `STAGE_ROLES`
  (:204-219) maps stage→role; its values are the proposer roles
  `_run_role` serves: `clarify, architect, planner, devops_planner,
  reviewer, analyst, qa, merge_verdict` (always) plus optional
  `research, deep_review, handoff, adversary, discover, risk` (present iff
  the folder ships — all six folders ship in this tree, so all 14 are live
  here). `agents/loader.py` separately pins `PROPOSER_ROLES` (the 8
  non-optional) and `HARNESS_ROLES = {dev, test, devops}` which are never
  planning roles. This is the set `budget_notice`'s probe uses.
- **API probe context (R-5)**: `dashboard/api.py` calls
  `resolved_roles(PipelineConfig())` at request time (graph validate ~:238
  and graph save ~:254), so role resolution already works in the API
  process; the start route today calls `start_run(idea, PipelineConfig(),
  wf_id)` (~:349) with no budget.

## Line counts at base (ceiling watch)

| File | Lines |
|---|---|
| `src/sdlc/cli.py` | 801 |
| `src/sdlc/core/models.py` | 545 |
| `src/sdlc/workflows/run_host.py` | 166 |
| `interfaces/dashboard/frontend/src/api/http.ts` | 245 |
| `interfaces/dashboard/frontend/src/api/mock/index.ts` | 464 |
| `interfaces/ui/app.md` | 137 |
| `interfaces/ui/app.pw.ts` | 446 |

(`stages/code/step.py` is at 991 and is not edited by this run.)

## Other pins

- Mock seeds: 10 runs; `feature-graph-demo` is the budget/graph demo
  (budget 20); inbox seed has exactly six items; `MockOptions` has only
  `simulateLive`.
- The start route (`POST /runs`) fleet-capacity path is intact
  (`check_fleet_capacity` before `start_run`).
- `tests/test_fleet_fixture_fresh.py` pins row sets by run id (read again
  at T005).
