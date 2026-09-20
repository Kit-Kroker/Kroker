# Bug Verification: canvas run-mode wiring (E75-OQ-1, option (a))

- **Slug**: canvas-run-mode
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The symptom no longer reproduces in any of its automated equivalents: the
served catalog declares all four capabilities true, the http-provider path
polls the FINAL `outcome` wire and renders run mode (including
`skipped`/`cancelled` nodes, unattributed pendings and the `unavailable`
degradation), the fleet strip renders from served `stage_marks` with the
FeatureWorkflow linear fallback intact, and RunView's copy is honest. All
27 RED contracts from both qa seats (plus the adopted pre-draft) are green,
and every regression gate passes end to end.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix): catalog caps | `.venv\Scripts\python.exe -m pytest tests/test_dashboard_canvas_run_mode_chaos.py tests/test_dashboard_graph_wire.py tests/test_dashboard_run_graph_routes.py tests/test_graph_fixtures_fresh.py -q` | pass | exit 0 — the caps pins that were RED at assessment (defaults, runtime catalog, served fixture) plus the fixture-swap pins all green |
| Reproduction (post-fix): run mode + strip + banners | `python scripts/check_ui.py` (vitest-dashboard 242/242, vitest-ui 102/102, playwright 50/50) | pass | exit 0 — poll finality over recorded FINAL bodies; toCanvas over the recorded graph/state; stageMarks strip rows; RunView banner rows; the app e2e tier renders the recorded 12-node run and drives the gate decision to the recorded completed state |
| New / updated tests | same as above (RED suites now inside the tiers) | pass | 27/27 formerly-RED contracts green (9 pytest + 16 dashboard + 2 ui) |
| Regression suite | `.venv\Scripts\python.exe -m pytest -q` (fast tier) | pass | exit 0, zero failures — incl. route/projection/fleet-mark backend tests unchanged by design, and the replay tier (replay neutrality holds) |
| Lint / type-check / size | `uv run --frozen ruff check .`; `ruff format --check .`; `mypy`; `python scripts/check_file_size.py`; vue-tsc via check_ui (both workspaces) | pass | all exit 0 |

## Output Excerpts

- `pytest -q` → exit 0 (fast tier fully green).
- The four caps/freshness suites → exit 0 (`test_capability_defaults_are_the_ruled_flip`, `test_runtime_catalog_declares_the_ruled_capabilities`, `test_shipped_catalog_fixture_declares_the_ruled_capabilities`, `test_no_provisional_recordings_survive_the_swap`, `test_catalog_capabilities_declare_canvas_run_mode_live`, ... all pass).
- `python scripts/check_ui.py` → exit 0; playwright `50 passed`, vitest-dashboard `242 passed`, vitest-ui `102 passed`.
- Statics → `All checks passed!` (ruff), `1434 files already formatted`, `Success: no issues found in 375 source files` (mypy), file-size exit 0.

## Residual Risks

- No live-server exercise: per the brief's binding constraint (unit/
  component tiers only, no Temporal), the http-provider path was verified
  against the recorded FINAL contract (Python-produced fixtures, pinned
  fresh by `test_graph_fixtures_fresh.py`) and the landed backend route
  tests — not against a running Temporal server. First live use should
  smoke-check `/graphs/catalog` + `/runs/{id}/graph_state`.
- The dashboard e2e tier's counter assertion moved to the showcase +
  adapter tiers (the recorded blocked projection carries no traversals);
  the traversal feature remains pinned, just not at the app tier.
- Doc duty (roadmap tick, E-77 spec card phrase, E-75 design annotation,
  E-76 §5.7 pointer) is deliberately post-verification per the brief.

## Recommendation

Close the bug — verified end to end within the sanctioned tiers. Proceed
to the reviewer gate on the chain `282831b..707430c`, then the doc-duty
commit.
