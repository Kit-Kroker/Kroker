# Quickstart — validating E-77

Prerequisites: `pip install -e ".[dev]"`. Run one pytest invocation per Bash call; never chain two in one call (project run lesson). Use `uv run` or the project venv consistently.

## 1. Fast tier (no Temporal)

| scenario | proves | command |
|---|---|---|
| resolver, completeness, `unknown` never canonical | FR-001–006, SC-001/002 | `pytest tests/graph/test_graph_node_types.py tests/graph/test_run_view_projections.py` |
| purity pin still holds (new functions import nothing new) | R1 | `pytest tests/graph/test_graph_purity.py` |
| re-entry indicator: `None` on the shipped catalog; 0/1 on an injected fail-edge registry; ref format pinned | FR-015/018, SC-007 | `pytest tests/graph/test_run_view_projections.py -k reentry` |
| store: identity immutable, layouts content-addressed, `latest` only via `save`, torn/dangling fallback, Windows retry, registry snapshot, pointer safe-name + reuse | FR-011, FR-019–023, SC-006 | `pytest tests/graph/test_graph_store.py` |
| start helper writes identity + layout + registry + pointer before start; a failure never blocks | FR-011, US1 AS4 | `pytest tests/graph/test_graph_store.py -k start` |
| heatmap byte-identical on today's records; k re-entries → exactly k | FR-017, SC-004/007 | `pytest tests/test_benchmark_heatmap.py` |
| save/load routes, catalog capabilities, drift → `unavailable` (not 500), retention → pointer | FR-020/021, SC-008, US4 | `pytest tests/test_dashboard_graph_routes.py tests/test_dashboard_run_graph_routes.py` |
| wire fixtures re-recorded from the real projection (`canonical_stage` per node) | FR-026 | `pytest tests/test_dashboard_graph_state_wire.py` |
| summary/state models accept and omit `graph_sha`; old `summary.json` parses | FR-009/024 | `pytest tests/core tests/test_benchmark_evidence.py` |

## 2. Temporal tier

| scenario | proves | command |
|---|---|---|
| a graph run stamps `graph_sha` on `run_state`, `run_summary` and every record; revise loop → rounds 1, 2; mapped/lens stages kept | FR-007–010, FR-014, US1–3 | `pytest -m temporal tests/graph_workflow/test_graph_view_query.py` |
| an injected unmapped node type: marks and records read `unknown` | G2, US2 AS2–3 | `pytest -m temporal tests/graph_workflow -k unknown` |
| benchmark arm: child records and oracle records carry the arm's sha | FR-010, US1 AS5 | `pytest -m temporal tests/graph_workflow/test_parent_wiring.py` |
| **replay neutrality**: goldens and feature histories unchanged, **not re-recorded** | FR-025, SC-004 | `pytest -m temporal tests/replay` |

## 3. Static gates

- `ruff check .` then `ruff format --check .`
- `mypy` (scoped to `src/`; no new errors in touched files)
- `python scripts/check_file_size.py`: `stages/code/step.py` must be unchanged (FR-027)
- `git diff --stat main -- interfaces/`: only `src/api/__fixtures__/graph/**/*.json`, `src/api/http-graph.test.ts`, `src/api/mock/graph.test.ts` (FR-026)
- `python scripts/check_ui.py` (typecheck + Vitest + Playwright via the sanctioned wrapper)
- `pytest tests/test_graph_fixtures_fresh.py` after `python scripts/dump_graph_fixtures.py`

## 4. Manual smoke (optional, dashboard running)

1. `POST /graphs` with `src/sdlc/workflows/graphs/default.graph.yaml` as JSON → note `sha` and `layout_sha`.
2. Move one node's `position` and `POST` again → same `sha`, new `layout_sha`; `GET /graphs/{sha}` returns the new layout.
3. Start a run from the first layout; the run's pointer names the first `layout_sha`; `GET /runs/{id}/graph` renders the first layout.
