# Baseline: round 018 (slice 0)

Branch `018-canvas-v5-ui`, base sha `07232332` ("agents: run adversary,
discover and risk on zai:glm-5.3-flash"), recorded 2026-10-27. The
round's code starts from a docs-only diff (two prototype HTMLs, the spec
set, a pre-commit accommodation), so every count below is the state of
main at the base.

## check_ui.py (quickstart §1 step 1)

All steps green on the recorded run (second full run; see "Flake at
baseline" below):

| Step | Result |
|---|---|
| install (`npm ci`) | passed |
| typecheck (dashboard) | passed |
| typecheck-ui (@kroker/ui) | passed |
| build-dashboard | passed |
| build-ui | passed |
| vitest-dashboard | passed — 526 tests / 43 files |
| playwright-browser (chromium) | passed |
| ds-bundle | passed |
| vitest-ui | passed — 150 tests / 32 files |
| playwright | passed — 101 tests (2.4m) |

`ui gate passes`.

**Flake at baseline.** The first full run failed one Playwright test —
`app.pw.ts:96` "an inspector edit applies through the parse and
commits" (CONSOLE-9), click intercepted by the inspector hint under
load. It passes in isolation (1.7 s) and did not reproduce on the full
rerun above. Filed as
`.workspace/tasks/2026-10-27-console9-inspector-click-flake.md`.

## Fast tier (quickstart §1 step 2)

`pytest` (default addopts, fast unit tier):
**36 failed, 6544 passed, 15 skipped, 275 deselected** (27m19s).

All 36 are pre-existing on the base and unrelated to this round's
docs-only diff. Attribution: the parallel benchmark baseline round is
rewriting the shared benchmark/dev-eval corpus and records (assertions
show `mismatched oracle_id in deveval-geotext`, `no junit report`,
`deveval-mini-calc: rejected (reference)`), plus the user's uncommitted
working-tree test file. The full list, for later checkpoints to diff
against:

- tests/research/test_research_dead_attempts.py::test_concurrent_thread_appends
- tests/test_benchmark_cli.py::test_dispatch_accept_offline_writes_record_and_prints_verdict
- tests/test_benchmark_corpus.py::test_committed_records_match_their_cases
- tests/test_benchmark_offline_checks.py::test_reference_check_passes_on_mini_calc
- tests/test_benchmark_offline_checks.py::test_reference_check_fails_when_reference_broken
- tests/test_benchmark_offline_checks.py::test_floor_check_returns_fewer_tests_passed_than_reference
- tests/test_benchmark_offline_checks.py::test_tree_check_passes_on_a_copy_of_the_reference
- tests/test_benchmark_offline_checks.py::test_tree_check_fails_per_test_when_tree_broken
- tests/test_benchmark_offline_checks.py::test_tree_check_needs_no_reference_dir_in_the_case
- tests/test_benchmark_record_compat.py::test_stored_benchmark_records_compat_and_trace_none
- tests/test_benchmark_stored_scores.py (16 cases: stored_cat_cafe_* and stored_todo_api_*)
- tests/test_compose_opencode_cache_mount_net.py (4 param cases; the user's uncommitted file)
- tests/test_deveval_corpus.py (3 cases: deveval-hone, deveval-particle-swarm-optimization, deveval-stocktrends)
- tests/test_grade_oracle.py::test_test_command_receives_only_the_filtered_environment
- tests/test_prompt_migration.py::test_prompt_shas_did_not_move
- tests/test_todo_api_case_loads.py::test_todo_api_case_file_exists_and_loads

A checkpoint's fast tier is compared against this list; movement inside
it (the parallel round mutating records) is environmental, not this
round's.

## check_clauses.py (quickstart §1 step 5)

Full output:

```
clause with no test: ARCH-1.4
clause with no test: CODE-1.6
clause with no test: CODE-1.7
clause with no test: MERGE-1.6
clause with no test: MERGE-1.8
clause with no test: MERGE-1.9
clause with no test: PLAN-1.4
clause with no test: RETRO-1.6
clause with no test: REVIEW-1.6
202 clauses declared, 9 untested, 0 dangling
```

The nine above are the clauses already untested on the base; they are
the only untested clauses permitted at later phase gates.

## check_file_size.py (quickstart §1 step 6)

`python scripts/check_file_size.py --full`: clean (no output, exit 0).

## Line counts (physical lines)

| File | Lines |
|---|---|
| interfaces/ui/app.pw.ts | 548 |
| interfaces/ui/app.md | 166 |
| interfaces/dashboard/frontend/src/api/mock/index.ts | 539 |
| interfaces/dashboard/frontend/src/api/http.ts | 284 |
| src/sdlc/dashboard/api.py | 382 |
| src/sdlc/dashboard/graph_wire.py | 579 |
