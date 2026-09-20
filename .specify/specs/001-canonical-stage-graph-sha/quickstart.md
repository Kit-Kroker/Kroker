# Quickstart — validating E-77

Prerequisites: `pip install -e ".[dev]"`. Run one pytest invocation per Bash call; never chain two in one call (project run lesson). Use `uv run` or the project venv consistently.

Walked and ticked 2026-09-20 (E-77 T044) via `.venv\Scripts\python.exe`; temporal rows per-file under a bounded wrapper (hard wall clock + `--timeout-method=thread`, temporal server swept before/after). Commands that had gone stale since planning are corrected in place and marked "(corrected)"; each row records its exit code.

## 1. Fast tier (no Temporal)

| scenario | proves | command | done |
|---|---|---|---|
| resolver, completeness, `unknown` never canonical | FR-001–006, SC-001/002 | `pytest tests/graph/test_graph_node_types.py tests/graph/test_run_view_projections.py` | ✓ rc=0 |
| purity pin still holds (new functions import nothing new) | R1 | `pytest tests/graph/test_graph_purity.py` | ✓ rc=0 |
| re-entry indicator: `None` on the shipped catalog; 0/1 on an injected fail-edge registry; ref format pinned | FR-015/018, SC-007 | `pytest tests/graph/test_fail_reentry.py` (corrected from `test_run_view_projections.py -k reentry`, which collects nothing — T029 landed the tests in their own file) | ✓ rc=0 |
| store: identity immutable, layouts content-addressed, `latest` only via `save`, torn/dangling fallback, Windows retry, registry snapshot, pointer safe-name + reuse | FR-011, FR-019–023, SC-006 | `pytest tests/graph/test_graph_store.py tests/graph/test_graph_store_e77.py` (corrected: the E-77 store clauses live in `test_graph_store_e77.py`) | ✓ rc=0 |
| start helper writes identity + layout + registry + pointer before start; a failure never blocks | FR-011, US1 AS4 | `pytest tests/graph/test_graph_start.py` (corrected from `test_graph_store.py -k start`, which collects nothing) | ✓ rc=0 |
| heatmap byte-identical on today's records; k re-entries → exactly k | FR-017, SC-004/007 | `pytest tests/test_benchmark_heatmap.py` | ✓ rc=0 |
| save/load routes, catalog capabilities, drift → `unavailable` (not 500), retention → pointer | FR-020/021, SC-008, US4 | `pytest tests/test_dashboard_graph_routes.py tests/test_dashboard_run_graph_routes.py` | ✓ rc=0 |
| wire fixtures re-recorded from the real projection (`canonical_stage` per node) | FR-026 | `pytest tests/test_dashboard_graph_state_wire.py` | ✓ rc=0 |
| summary/state models accept and omit `graph_sha`; old `summary.json` parses | FR-009/024 | `pytest tests/core tests/test_benchmark_evidence.py` | ✓ rc=0 |

## 2. Temporal tier

| scenario | proves | command | done |
|---|---|---|---|
| a graph run stamps `graph_sha` on `run_state`, `run_summary` and every record; revise loop → rounds 1, 2; mapped/lens stages kept | FR-007–010, FR-014, US1–3 | `pytest -m temporal tests/graph_workflow/test_graph_view_query.py` | ✓ rc=0 |
| an injected unmapped node type: marks and records read `unknown` | G2, US2 AS2–3 | `pytest tests/graph_workflow/test_record_stamping.py` (corrected from `-m temporal tests/graph_workflow -k unknown`, which collects nothing — the unknown-marks tests are pure unit tests by design; projection-side unknown marks covered in §1 row 1) | ✓ rc=0 |
| benchmark arm: child records and oracle records carry the arm's sha | FR-010, US1 AS5 | `pytest tests/graph_workflow/test_parent_wiring.py` (corrected: single fast-tier test, no temporal mark) | ✓ rc=0 |
| **replay neutrality**: goldens and feature histories unchanged, **not re-recorded** | FR-025, SC-004 | `pytest -m temporal tests/replay/test_capture_feature.py` then `pytest -m temporal tests/replay/test_graph_golden.py` (corrected: split per-file per the T043 standing rule; whole-directory single command is not run on Windows) | ✓ rc=0, rc=0; `git status tests/replay` clean |

## 3. Static gates

- [x] `ruff check .` — all checks passed (rc=0)
- [x] `ruff format --check .` — 1411 files already formatted (rc=0)
- [x] `mypy` — Success: no issues found in 375 source files (rc=0)
- [x] `python scripts/check_file_size.py` (rc=0); `git diff --stat main -- src/sdlc/stages/code/step.py` empty (FR-027)
- [x] `git diff --stat main -- interfaces/`: only `src/api/__fixtures__/graph/catalog.json`, `src/api/__fixtures__/graph/run_state/graph_state.recorded.json`, `src/api/http-graph.test.ts`, `src/api/mock/graph.test.ts` (FR-026)
- [x] `python scripts/check_ui.py` — rc=0, "50 passed", "ui gate passes"
- [x] `pytest tests/test_graph_fixtures_fresh.py` after `python scripts/dump_graph_fixtures.py` — dump rc=0 (needs the conftest dummy keys in env: `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`EXA_API_KEY=test-dummy`, else the agent registry fails closed on `EXA_API_KEY`), dump byte-identical with the committed fixtures (`git status interfaces/` clean), test rc=0

## 4. Manual smoke (optional, dashboard running)

1. `POST /graphs` with `src/sdlc/workflows/graphs/default.graph.yaml` as JSON → note `sha` and `layout_sha`.
2. Move one node's `position` and `POST` again → same `sha`, new `layout_sha`; `GET /graphs/{sha}` returns the new layout.
3. Start a run from the first layout; the run's pointer names the first `layout_sha`; `GET /runs/{id}/graph` renders the first layout.
