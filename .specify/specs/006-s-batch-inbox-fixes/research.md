# Research: 006 S-batch

All facts verified on main `817f819`. Line numbers are as of that commit.

## R1 — B1 warning site and test shape

- **Decision**: `else:` on the existing `if commit.returncode == 0:` in `run_coding_task` (`src/sdlc/stages/code/activities.py:198-204`), using the module logger `_log` (`:29`). Test by monkeypatching `activities._git` with a passthrough that fails only `commit`.
- **Rationale**: the inbox snippet's `log.warning` names a logger that does not exist in this module. A real broken committer identity depends on global git config and container setup and would not fail the same way everywhere.
- **Alternatives**: raise on failure — rejected, changes behaviour the test-freeze design accepts (`freeze.py` documents the `None`). Surface in the activity result or Temporal UI — out of scope (A3).
- **Checked**: crew tasks do not call `run_coding_task` (`code/step.py` branches on `crew_enabled`), and `--allow-empty` makes an empty change set commit successfully, so the warning cannot fire on a legitimate no-checkpoint path.

## R2 — B2 logger, helper, doctor wiring

- **Decision**: `log = logging.getLogger(__name__)` in `routes.py`; warn in `_parse_route`'s drop branch (`:84-87`); factor `_env_ref`; add public `unset_env_targets(path=None)`; doctor calls it after `load_routes()`.
- **Rationale**: `sdlc.notify.routes` is a child of `notifiers.py`'s `"sdlc.notify"` logger, so no second literal is needed. A helper in `routes.py` keeps one definition of a `$VAR` target. Recording drops on the `NotifyRoutes` object instead would break `test_notify_routes_ok_reports_pass`, whose fake `load_routes` returns a stub with only `version` — the new attribute read would raise, be caught as WARN, and fail the PASS assertion.
- **Alternatives**: doctor walks the YAML itself — rejected, two definitions. De-duplicating warnings — rejected (A4): makes tests order-dependent and hides real missed deliveries.
- **Checked**: `routes.py` is never imported by workflow code (`workflows/gates.py` imports only `notify.activities`, `contract`, `schedule`), so logging there has no sandbox implication. The shipped `policy/notifications.yaml` has `$VAR` only in comments, so a clean checkout stays PASS. Doctor exit code is unaffected: WARN is already non-fatal for this check.

## R3 — B3 full drift between the generator and the committed fixture

Generator today: 2 open runs, 3 closed, 1 inbox run with 4 pending rows, `total_open_runs=2`, one `main()` that builds and writes, `OUT` CWD-relative (`scripts/dump_dashboard_fixtures.py:27,31,34`).

Committed file has, and the generator lacks (the "hand rows"):

| Row | Content |
|---|---|
| `runs[graph-run-live]` | full open run with 18-stage `stage_marks`, `graph_sha`, `project_key: null` |
| `closed[graph-run-closed]` | closed row, `project_key: null` |
| `closed_marks["graph-run-closed"]` | 18-stage marks |
| `project_key: "kroker"` | `feature-add-sso`, `feature-dark-mode` |
| `total_open_runs: 3` | generator says 2 |

Generator (models) emits, and the committed file lacks:

| # | Key | Model source | Rows |
|---|---|---|---|
| 1 | `stage_marks: null`, `graph_sha: null` | `core/models.py:540,542` | open `feature-add-sso`, `feature-unpriced` |
| 2 | `graph_sha: null` | `core/models.py:502` | 4 closed rows |
| 3 | `thaw_tests: false` | `core/models.py:165` | 1 decision |
| 4 | `parent_run_id: null` | `pending.py:42,54,68,81` | 4 pending rows |
| 5 | `open_errors: []` | `dashboard/fleet.py:84` | snapshot root |
| — | `project_key: null` | `core/models.py:505,545` | 3 rows — removed again by the omission list |

- **Decision**: teach the hand rows; keep the generator's shape for 1–5 and regenerate once; prune only `project_key` on the three listed runs.
- **Rationale**: `http.ts:71,80,101` reads `stage_marks ?? null` and `project_key ?? null` and never reads `thaw_tests`, `parent_run_id`, `open_errors` or `graph_sha`. `http.test.ts` needs `graph-run-live.stage_marks`, `closed_marks['graph-run-closed']`, and null-or-absent `stage_marks` on `feature-add-sso`; its `project_key` test clones the fixture and injects values itself. `client.test.ts` only round-trips the fixture through a mocked fetch. No test depends on absence of any key, so widening the pruning list to reproduce the stale file byte-for-byte would only preserve drift.
- **Alternatives**: prune 1–5 too so the first regeneration is a zero diff — rejected for the reason above. Sidecar — ruled out at GATE 1.

## R4 — B3 test scope

- **Decision**: two tests (freshness; omission-list shape). Importlib-load the script as `tests/test_graph_fixtures_fresh.py` does.
- **Rationale**: the graph test's stray/tamper cases exist because it guards a directory tree. Here it is one file and one equality.
- **Accepted cost**: any new defaulted field on `RunState`, `RunSummary`, `FleetSnapshot` or the pending models turns the test red until the fixture is regenerated. That is the purpose (SC-004).

## R5 — B4 gotcha candidates

Advisor-derived from the current code; the executor re-verifies each before it goes into `AGENTS.md`. `[doc]` = already stated at WHAT level, keep out or one-line pointer.

Fail-and-continue (E-29), `stages/research/step.py` unless noted:
1. A degraded brief still records PASS with a judged score (`:269-271, 297, 354-367`).
2. A synthesis failure discards successful findings: one `try` wraps fan-out and synthesis (`:254-271`).
3. After (2), refine restarts sub-question ids at `sq-0` and inherits the already-spent budget file (`:315`, `stage.py:127,238`).
4. Budget/usage exhaustion returns a finding with `failed` False and zeroed usage: the all-failed check and the merge gap branch do not see it, and spend before the cap is not folded in (`stage.py:243,277-282`, `merge.py:41-51,72`).
5. Exhaustion discards all partial work of that sub-question (`stage.py:277`).
6. REVISE past the cap, or an exception during refine, falls through to retain + judge + PASS (`:306-307, 331-332, 345-368`).
7. Verify is the one non-fail-soft call: outside any `try`, single attempt (`:72-75, 273, 333`).
8. Human rejection records no benchmark row (`:303-304`).
9. `[doc]` An ungrounded brief skips the human gate and clears the digest.

Verifier rules, `stages/research/verify.py` unless noted:
1. Only `grounded_findings` are verified and hashed (`:72, 91`).
2. Pages are keyed by sha256 of the exact URL string; any URL variant is `source_unavailable` (`:29, 73-78`).
3. Only `get_page` writes pages; quotes from search snippets always fail; a failed page write is only logged (`agents/research/exa_wrapper.py:27-65`).
4. "Fetched this run" means this workflow id: a restart with the same id inherits pages and spent budgets (`:32-36`, `budget_store.py:38-39`).
5. Pages dir is `$SDLC_RUNS_ROOT` or CWD-relative `runs/`; fetch and verify must share environment and CWD (`:35`).
6. The digest hashes `(source_url, claim)` pairs while merge dedupes on `(url, quote, claim)` (`:91`, `merge.py:65`).
7. All degraded briefs share one constant non-empty digest; `""` is the only ungrounded sentinel (`step.py:340, 345`).
8. Retain re-runs the verifier (file I/O) in workflow context (`step.py:346`, `retain.py:19`) — verified from reading only.
9. `[doc]` Nothing loosens EXTRACTED_TEXT without a test.

Budget enforcement, `stages/research/budget_store.py` unless noted:
1. Caps apply to estimated tool cost from constants; LLM tokens are priced separately and not enforced against it (`deps.py:27-28, 89-91`).
2. No rollback across scopes: the run counter keeps a charge the sub-question scope refuses (`:121-122`).
3. The run scope ignores count caps (`:114-120`).
4. `scope == "run"` collapses to one charge; its caller catches `BudgetExceeded` only (`:110-113`, `toolset.py:16-67`).
5. Activity retries inherit the persisted, already-spent allowance (`stage.py:237`, `step.py:63`).
6. A lock older than 10 s is stolen; acquire timeout raises `TimeoutError`, which the exhaustion handler does not catch (`:59-63`).
7. The budget write is not atomic; truncated JSON wedges the scope (`:87`).
8. `[doc]` `request_limit` caps total model requests per sub-question.
9. Two stale docstrings (A5): `deps.py:8-12` describes the persisted counter as a future, unwired "Task 8 concern", and `toolset.py:26` says a disk-persisted counter is "(deferred)". Both are out of date: `budget_store.py` implements it.

Planner spot-checks: E-29 item 2 (`step.py:254-271`) and item 4 (`stage.py:277-282`) confirmed by reading.

## R6 — B5/B6 premises

- B5: `tests/test_promptfoo_provider.py:116-139` — `time.monotonic()` around `subprocess.run([sys.executable, "-c", "import sdlc.eval.promptfoo.provider"])`, `assert elapsed < 8.0`. Unchanged from the inbox description.
- B6: `LensOutcome` / `LensPresence` in `src/sdlc/stages/review/lenses.py:28,35`; `TaskResult.lens_outcomes` in `workflows/models.py:66`. `run_adversary` returns None before any record when disabled or agent missing (`review/step.py:193`); its record is at `:213-231`. The reviewer record is guarded on a non-None report (`:145`). Agreement-matrix empty state at `src/sdlc/benchmarks/agreement_matrix.py:148-153`. Premise holds post-005.
- `.workspace/` is ignored (`.gitignore:4`): draft sections are working-tree deliverables (A2).

## Consult disposition

| Source | Claim | Disposition |
|---|---|---|
| advisor D1 | `__name__` logger, warn in `_parse_route`, no de-dup | Adopted (D2). |
| advisor D2 | public helper + `_env_ref`; isolation patch on the PASS test | Adopted (D2). Stub-shape reasoning re-checked at `test_doctor_checks_delegated.py:135-140`. |
| advisor D3 | single-object `build()`; anchor `OUT` on repo root; five extra drift axes + `total_open_runs`; generator shape wins; two tests; guarded omission pop | Adopted (D3, R3). Drift axes re-checked: none of `thaw_tests`/`parent_run_id`/`open_errors` occurs in the committed file; `total_open_runs` 3 vs 2 confirmed. |
| advisor D4 | monkeypatch `_git` passthrough; three cases | Adopted (D1). |
| advisor D5 | 27 gotcha candidates (23 + 4 already-documented) | Adopted as candidates (R5); executor re-verifies each. |
| advisor spec | AC3.1/SC-003 first-regeneration conflict | Adopted → spec A1. |
| skeptic L1 | warning visible only in worker log; no spurious path | Adopted → spec A3. |
| skeptic L2 | repeated warnings per load; no sandbox exposure; no secret | Adopted → spec A4. |
| skeptic L3 | doctor must tolerate the stub `load_routes` fake | Adopted; satisfied by the helper design. |
| skeptic L4 | "only `project_key` absence is inexpressible" is wrong; must prune more or regenerate | Adopted, regenerate branch (R3). Skeptic listed 3 axes; advisor's 5 is the complete set. |
| skeptic L5 | `.workspace/` ignored → B5/B6 cannot be commits | Adopted → spec A2, D5. Orchestrator direction concurs. |
| skeptic L6 | no forced edit to `code/step.py`, no dependency change | Confirmed. |
| advisor task count | 14, fold if slack needed | 14 kept; within the 10–14 budget. |

Rejected: none.

## Reviewer plan findings (`.workspace/tmp/reviewer-006-plan-1.md`, fixes-needed, no blocking)

| Finding | Disposition |
|---|---|
| F1 dead citation path for the agreement matrix | Fixed in R6. |
| F2 "deferred" wording true for `toolset.py` only | Fixed: R5 budget item 9, plan D4, spec A5, T011 now state each docstring's actual staleness. Re-read at `deps.py:8-12`, `toolset.py:26`. |
| F3 doctor's git-identity FAIL text says the failure is "SILENTLY" swallowed and cites `activities.py:197-202` | Adopted: plan D1 and T003 correct that sentence in the B1 commit. Text confirmed at `doctor/checks.py:207-214`. Corrected by the tasks review (below): one test does assert on it. |
| F4 root keys reorder on regeneration | Adopted: plan D3 and SG-1 are judged on parsed data; the `closed_marks` block move is expected. |
| F5 no fail-soft test for the helper raising | Adopted: one case added to T006(b) and plan D2. |

## Reviewer tasks findings (`.workspace/tmp/reviewer-006-tasks-1.md`, fixes-needed, one blocking)

| Finding | Disposition |
|---|---|
| F1 (blocking) rewording the git-identity FAIL detail breaks `test_identity_unresolvable_reports_fail_naming_the_silent_consequence` (`tests/doctor/test_doctor_checks_binaries.py:72-88`, `assert "silently" in r.detail.lower()`); the planner's earlier "no test asserts on it" came from a case-sensitive grep and was wrong | Fixed: T002 renames and re-pins that test as part of the RED set; T003 keeps "warning" and "anchor" in the detail and drops "silently"; plan D1 states it. A case-insensitive sweep of `tests/doctor` finds no other assertion on the text. |
| F2 plan scale line said 3 test modules | Fixed: 4. |
| F3 SG-4 named no modules | Fixed: SG-4 lists the four. |
| F4 plan Status line | Fixed with F1. |
