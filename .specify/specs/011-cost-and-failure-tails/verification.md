# Verification: 011-cost-and-failure-tails (US1 + US2)

Recorded 2026-10-06 on branch `011-cost-and-failure-tails` (base
`d1d87b23`, head `655a3f2c` + this task's commit). Every row of
quickstart §1 was run once per call at T018; per-task evidence is in the
task commits and their reviewer replies.

## 1. Automated gates (quickstart §1, against baseline.md)

| Row | Command | Result | Baseline | Verdict |
|---|---|---|---|---|
| named fast files | `uv run pytest tests/test_run_budget.py tests/test_cli_budget.py tests/test_dashboard_api.py tests/test_run_state_query.py tests/test_run_state_model.py tests/test_run_summary_build.py tests/test_run_summary_model.py tests/test_fleet_fixture_fresh.py tests/test_code_attempt_usage.py` | **130 passed**, no file deselected | n/a (new row) | green |
| temporal gate files | `uv run pytest -m temporal tests/test_budget_gate.py tests/test_model_usage_capture.py` | **3 passed** (non-zero; not deselected) | 3 passed | identical |
| fast tier | `uv run pytest` | **5684 passed, 11 skipped, 255 deselected**, 3 failed = the recorded baseline git-dependent trio (`test_plans_are_tracked::test_superpowers_scratch_is_still_ignored`, `test_prompt_gate::test_unchanged_prompt_passes_without_calling_a_model`, `test_promptfoo_provider::test_resolve_instructions_git_ref_reads_from_git`) | 5621 passed / same 3 failed / same skips+desel | count rose by exactly the 63 new tests; no new failure |
| lint | `uv run ruff check .` | All checks passed | clean | identical |
| format | `uv run ruff format --check .` | 1673 files formatted | clean | identical |
| types | `uv run mypy` | Success: no issues in 387 source files (0 errors) | 0 errors | identical |
| replay | `uv run pytest -m temporal tests/replay` | **31 passed, 21 skipped, 1 failed** — see the flake row below | 32 passed, 21 skipped | see below |
| host UI | `python scripts/check_ui.py` | **ui gate passes** — install, typecheck ×2, builds, vitest-dashboard 41 files (446+new), vitest-ui 32 files (147+new), ds-bundle, playwright **101 passed**, no skipped step | 39/32 files, 94 pw | green, counts rose only by this run's tests |
| host clauses | `python scripts/check_clauses.py` | **202 declared, 10 untested, 0 dangling**; the 10 are the pre-existing baseline list; CONSOLE-24..29 and START_RUN_MODAL-3 all covered | 195/10/0 | green |
| host size | `python scripts/check_file_size.py` | silent (exit 0) | silent | identical |

### The state of `budget_arch_reject-sandboxed`

At baseline it **passed** (part of the 32). At T018 it **failed 3/3
consecutive runs** (two full-suite runs plus one targeted run) with
exactly the card signature (`2026-10-02-golden-graph-trace-flake.md`:
`At index 11 diff: 'activity:publish_artifact_version' != 'timer'`).
This is SG-3's named exception — the known load-dependent flake, not a
regression by this run: the scenario's code path (`role_host.py`,
`graph.py`, `feature.py`, `tests/replay/`) is byte-identical to base
(forbidden-path audit below), and the same branch code passed the
reviewer's full replay run earlier in this session under lower load.
Recorded, not fixed; US3 of the follow-up S-batch owns making it
deterministic (this 3/3-under-load record strengthens its case).

## 2. Manual walk on the mock (quickstart §2)

Walked programmatically: each row is covered by a same-line-cited
Playwright test against the built mock (`VITE_API=mock` build — the
same provider `npm run dev` serves), all green in the 101-pass run:

| Step | Seen via | Result |
|---|---|---|
| Header spend + "· N not priced" | CONSOLE-27 test | header stats contain "not priced" (seeds: 2 excluded) |
| Cost rows; "not priced" with tokens; partial total; no `$0.00` | CONSOLE-24 + CONSOLE-25 tests | 3 cost-rows on feature-graph-demo; dev reads "not priced"; total "$2.60 (partial)"; no price element reads $0.00 |
| Budget block | CONSOLE-26 test | budget $20.00, limit $40.00, counted $2.60, whole percent, crossings 1, scope note |
| Copy URL, reload | CONSOLE-24 test | `page.reload()` reopens ?tab=cost |
| `?tab=gates` renders Graph, URL untouched | CONSOLE-10 test (amended) | graph-canvas visible, no board tab |
| Closed run, no breakdown | N9 pin (CostTab.test.ts + fixture row feature-audit-export) | "No breakdown recorded for this run." + total $14.02 |
| Start, budget `0` | CONSOLE-28 test | inline "omit it to run without a budget", submit disabled, no run added |
| Start, budget `5` | CONSOLE-28 test | run starts; toast carries the notice (mock returns it); Cost tab shows $5.00 budget |
| `/?mockBudgetGate=1#/inbox` | CONSOLE-29 test (own page load) | gate-budget-note: "Approve raises the limit to $60.00 and the run continues. Any other decision ends the run." |

## 3. Command line (quickstart §3, in kroker-dev)

| Command | Seen |
|---|---|
| `uv run python -m sdlc.cli start --title t --budget-usd 0` | exit **2**, stderr `argument --budget-usd: budget must be greater than 0; omit it to run without a budget` |
| `uv run python -m sdlc.cli start --title t --budget-usd abc` | exit **2**, stderr `argument --budget-usd: budget must be a number greater than 0` |

No Temporal connection was made for either rejection. The optional live
start with `--budget-usd 5` is the orchestrator's check, not run here
(it spends tokens; the wiring is pinned by test_cli_budget.py and
test_dashboard_api.py).

## 4. Stop-guards and deviations

- **No stop-guard fired.** SG-4-adjacent events were each diagnosed and
  resolved within the task that caused them: T003's fixture staleness
  (T005's named deliverable), T008's CONSOLE-2 label ripple (one
  assertion updated per the branch-green rule; reviewer approved),
  T009's CONSOLE-10 navigation (reviewer ruled it moves into T009's
  commit; done, amend-resubmitted), T014's field.pw removal-selector
  ripple (the file's own documented mechanism), T014/T010/T015
  graphs-editor inspector timeouts (known load-flake card; passed on
  immediate re-run every time; SG-6 reported pattern).
- **R-5 probe outcome: kept, fallback not used.** `budget_notice`
  probes `resolved_roles(cfg)` + `compute_price` in-process; the test
  environment loads the real registry fine (tests/test_run_budget.py
  green against it, including "no 'No price found' with the registry
  defaults").
- **Deviations from tasks.md letter, each reviewer-approved**: the
  three ripples above (single-assertion/existing-mechanism edits to
  app.pw.ts and field.pw.ts outside the tasks that own those files'
  clause work); T012's `_start_config` extraction adds one module-level
  function to cli.py (explicitly allowed by the task text).
- **Commit rule honored throughout**: subject + body only, `git commit
  -F <msgfile>`, one path per `git add`, **no attribution trailers of
  any kind** (one `--amend` of T009's commit, directed by the reviewer's
  fixes-needed reply, before any push).
- **Forbidden paths**: `git diff --name-only d1d87b23..HEAD` (68 files)
  contains none of: role_host.py, graph.py, feature.py,
  stages/code/step.py, tests/replay/*, tests/test_budget_gate.py,
  operator/, research stage, .github/, boundaries.test.ts, router.ts,
  features/board/, features/graphs/, fleet_row/, any AGENTS.md,
  CLAUDE.md, package.json/lock files, earlier specs, docs/reports.
- **Known red accepted at base**: the three git-dependent fast-tier
  failures (in-container git cannot work in a worktree bind; recorded
  at baseline, unchanged).

## 5. Task ledger

T001–T018 all committed and reviewer-approved (T009 after one
fixes-needed round). Commits: 8db42b91 (T001), f1567a02 (T002),
7caf2c2d (T003), 4e0c3e8f (T004), 1008ff7a (T005), a335acd4 (T006),
36e7ed00 (T007), 046cd1e2 (T008), 4f172578 (T009, amended), bfa458af
(T010), 0e0d6228 (T011), 73b5d81d (T012), 397ec4e8 (T013), e0f2c6a0
(T014), 95abad90 (T015), d9db9a2e (T016), 655a3f2c (T017), plus this
T018 commit. tasks.md marked `[X]` for all eighteen.

## 6. Cards filed (gitignored inbox, listed for the orchestrator)

`2026-10-06-budget-gate-counts-all-recorded-spend.md` (M; cites N5, N6,
R6; queued behind the flake fix), `2026-10-06-research-spend-not-in-trace-or-roles.md`,
`2026-10-06-role-priced-on-some-calls-not-marked.md`.

## 7. Orchestrator-owned AGENTS.md updates (GATE 2 item 8, not done here)

1. `interfaces/AGENTS.md` screen table gains the Cost row: "Cost | tab
   of `/runs/:id` (`?tab=cost`) | `src/features/cost/` | `CostTab.vue`".
2. `src/sdlc/workflows/AGENTS.md` attribute-ownership table gains
   `RunHost._snapshot_run_state` as a reader of `_budget_threshold`,
   `_budget_crossings` and `_role_usage`.
