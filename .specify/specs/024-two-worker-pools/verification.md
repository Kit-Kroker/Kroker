# Verification — round 024 (two worker pools)

## §024-i — the pools exist, routing hard-off (T020, 2026-11-16)

All commands from repo root with `uv run`, on `main` at T019
(`111abf13`) plus the T020 battery fixes (this commit's parent diff:
the axis never-raise guard and two worker source-pin updates,
described below).

| Command | Result |
|---|---|
| `ruff check .` | PASS — all checks passed |
| `ruff format --check .` | PASS — 2144 files formatted (one byte fixed in-flight: the advisor consult's python fence had a double space; consults are ruff-format-scope in this repo) |
| `mypy` | PASS — no issues in 449 source files |
| `python scripts/check_file_size.py` | PASS — no file over the 1000-line ceiling (worker.py 399, pools.py 285) |
| quickstart §1a (the seven 024-i test files) | PASS — rc=0 |
| `pytest -q -m temporal tests/test_pools_failfast.py::test_poller_freshness` | PASS — the R6 proof on the `start_local` dev-server; observed lag 0.26 s (budget 5 s), linger 2.79 s at freshness 3 s, recorded in the test docstring |
| `pytest -q tests/replay/` | PASS — rc=0, no stored history or golden touched |
| `git status --short tests/replay/` | empty |
| `pytest -q` (full fast tier) | 2 failures, both pre-existing baseline ids (`test_sc003_recompute_stored_acceptance`, `test_prompt_shas_did_not_move`); the two `test_read_fixtures_fresh` baseline ids pass on the primary checkout as 023b documented. **Novel ids: none — a strict subset of `baseline-failures.txt`.** |

### Battery-driven fixes (found by the full-tier run, fixed before this file)

1. `measure_code_axis`'s new prune raised `FileNotFoundError` from its
   `finally` when `repo_url` did not exist — the never-raise contract's
   own test caught it (qa-chaos had flagged exactly this corner as
   unspecified and left it unpinned). The prune is now guarded against
   `OSError`.
2. `test_worker_registers_the_post_020_workflow_set` AST-walked the
   `Worker(..., workflows=[...])` literal; T009 moved the list to
   `_ALL_WORKFLOWS` (the 400-line ceiling). The pin now resolves the
   module-level name — same ten-workflow assertion, same intent.
3. `test_worker_validation_runs_before_worker_run` anchored on
   `worker.run()`, which T009's gather replaced. The pin now anchors on
   `asyncio.gather(` — same intent: validation precedes the run loop.

### Platform finding (T010, recorded for 024-ii)

`DescribeTaskQueue` is unimplemented on the `start_time_skipping`
test server (RPC 12). The poller proofs (T010 here, T031/T032/T033 in
024-ii) must use `WorkflowEnvironment.start_local`, the task's
"ephemeral dev-server", per the `test_dashboard_e2e.py` precedent.

### Standing statement

**024-i does not unblock R025; NFR-2 stays open until 024-ii.** The
pools boot and are observable (doctor row, compose overlay), fleet
enablers landed (bench ids, janitor lock, axis prune), but no start
path reads `KROKER_HARNESS_QUEUE` yet — run-level routing is 024-ii
(T021–T042). `docs/operations/worker-pools.md` carries the 024-i
banner saying so. ROADMAP's NFR-2 is deliberately untouched.
