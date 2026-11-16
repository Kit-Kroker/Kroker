# Verification — round 025 (the SC-2 instrument and the fleet runs)

## §025-A — the instrument, Part A close-out (T014, 2026-11-16)

All commands from the repo root with `uv run`, on `main` after the Part A
merge (T001–T014, commits `9d12ba14`..`066d43f9`). No workflow, gate,
containment, `pre_tool`, env-allowlist or ADR-6 file was touched
(FR-009); every change is additive and defaulted (FR-010), checked by the
legacy-load tests of T002/T003 and the replay proof of T012.

| Command (quickstart "Part A") | Result |
|---|---|
| `pytest -q tests/test_run_summary_build.py tests/test_run_summary_model.py tests/test_operator_time.py tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py` | PASS — 56/56 (the five named files) |
| `pytest -q` (full fast tier) | **8059 tests, 2 failures, 0 errors, 22 skipped** — both failures pre-existing baseline ids (`test_sc003_recompute_stored_acceptance`, `test_prompt_shas_did_not_move`, both in `.specify/specs/024-two-worker-pools/baseline-failures.txt`; the two `test_read_fixtures_fresh` baseline ids are worktree-only artifacts and pass here, as 023b/024 documented). **Novel ids: none — a strict subset of the baseline.** The mid-round fixture-drift failure (expected at the T010 boundary) is green again after T011's regeneration |
| `ruff check .` | PASS — all checks passed |
| `ruff format --check .` | PASS — 2166 files already formatted |
| `mypy` | PASS — no issues in 451 source files |
| `pytest -q tests/replay` | PASS — 183 tests, 0 failures, 0 errors, 0 skipped; no stored history or golden changed |
| `pytest -q -m temporal -k "replay or golden"` | PASS — 70 tests, 0 failures, 0 errors, 24 skipped (all pre-existing by-design skips: on-demand capture guards 003/009/012/020, no-stored-records) |
| `python scripts/check_file_size.py` | PASS — `core/models.py` 645, `summary.py` 226, `sc_rollup.py` 418 (< 450 per its task), `operator_time.py` 116 |
| `mkdocs build --strict` (`uv run --no-sync`) | PASS — fleet-runs.md in nav, worker-pools cross-link resolves |
| drift guard `tests/test_fleet_fixture_fresh.py` | PASS after T011 — one fixture file regenerated, defaulted keys only (`operator_instrumented: false` on the four closed rows) |
| research R8 (`grep -n "extra=" src/sdlc/core/models.py`) | SETTLED — no output: no model forbids (or pins) extras; pydantic default `ignore` applies, so pre-025 JSON loads unchanged |

### Red→green ledger (Part A)

| Task | RED at | GREEN at |
|---|---|---|
| T001/T002 summary fields | `9d12ba14` / `cde4c933` (15 failing) | `4a13a561` (legacy loads) → `ff0be20c` (builder; all 40) |
| T005 operator_time | `93a19dc2` (16 failing on import) | `e7ccc9d5` (16/16) |
| T007 SC-2 rows | `ea012545` (16 failing) | `61bff51f` |
| T009 commit set | `1d457c0f` (9 failing) | `f51216a5` |

Reviewer verdicts, in order: T001 approve · T002 approve · T003 approve ·
T004 fixes (mypy narrowing, format) → approve · T005 fixes (ruff) →
approve · T006 approve · T007 fixes (ruff) → approve · T008 approve ·
T009 approve · T010 approve · T011 approve · T012 approve · T013 approve.

### Fleet commit candidate

`066d43f9` — HEAD after the Part A merge (T013). Part B (T020 onward)
freezes a dedicated clean checkout at this commit; the smoke stamp and
every scored run must carry it (FR-024; the commit set in the rollup must
be exactly one). **Superseded at T021/T022: the frozen fleet commit is
`93120693`** (Part A close-out plus the spec evidence through the freeze;
`066d43f9` remains an ancestor of it).

## §025-B — the fleet runs (T020–T033)

### Pre-smoke infrastructure casualty — not scored, not part of the fleet

`bench-todo-api-greenfield-1794831076-c77ecc` — dispatched 2026-11-16
13:11 local from the fleet checkout, before the harness queue was present
in the dispatching CLI's environment. Single root cause: the CLI env
lacked `KROKER_HARNESS_QUEUE`, so `spec.harness_queue` was `None` and
every harness-class activity was scheduled on `ai-sdlc`, where the core
worker correctly refuses them — `setup_integration_branch` failed the
child `GraphWorkflow`, `measure_code_axis` failed the parent
`BenchmarkWorkflow`. Both failures are that one misconfiguration; the
pools themselves were healthy (ACTIVITY-type DescribeTaskQueue: `core` on
`ai-sdlc`, `harness` on `ai-sdlc-harness`). Terminal-failed at 3.4 s,
**$0.00 spend** (no model or judge call ran), no smoke stamp written.
Quarantined to
`kroker-fleet-runs-025-evidence/pre-smoke-infra-casualty-bench-todo-api-greenfield-1794831076-c77ecc`
(outside the runs root, so `benchmark score --all` cannot ingest it).
Fix, host-side only (gitignored `.env` in the primary and fleet
checkouts): `KROKER_HARNESS_QUEUE=default` — the sentinel resolving to
`HARNESS_QUEUE_DEFAULT` — so every later dispatch routes harness-class
activities and passes the CLI's `require_harness_poller` guard before
starting. The scratch repos were untouched (each still exactly one clean
`init` commit on `main`).
