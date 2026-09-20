# Bug Review: canvas run-mode wiring (E75-OQ-1 option (a))

- **Slug**: canvas-run-mode
- **Worktree**: `D:\own\Kroker-bug`
- **Branch**: `fix/canvas-run-mode`
- **Review Scope**: chain `36baf5b..HEAD` (7 commits: `282831b`, `d88ea81`, `3fd1323`, `cefaafe`, `707430c`, `7b36f89`, `2e77b2d`)
- **Reviewer**: Reviewer Seat (Antigravity)
- **Date**: 2026-09-20

---

## 1. Scope Fidelity

- **Backend Changes**: The backend modification is strictly limited to `src/sdlc/dashboard/graph_wire.py:121,124`, flipping `can_validate` (alias `validate`) and `run_graph` Field defaults from `False` to `True`, along with docstring updates documenting the rollout history. No routes, projections, or handlers in `src/sdlc/dashboard/api.py`, `src/sdlc/dashboard/fleet.py`, or `src/sdlc/dashboard/run_graph.py` were modified.
- **Fixture Maintenance**: Only `interfaces/dashboard/frontend/src/api/__fixtures__/graph/catalog.json:1560-1564` had its capabilities block updated via `scripts/dump_graph_fixtures.py`. The provisional fixtures `run_graphs.provisional.json` and `validation.provisional.json` were deleted as prescribed, and the stale docstring line in `scripts/dump_graph_fixtures.py:11` was updated.
- **No Out-of-Scope Drive-bys**: All items explicitly placed out of scope by the brief and assessment remain completely untouched:
  - E76-OQ-1 (gate rename): untouched.
  - E76-OQ-2 (drag refusal): untouched.
  - E76-OQ-4 (revise comment): untouched.
  - E76-OQ-5 (comment loss): untouched.
  - E75-OQ-2/3/4 (crew-child escalations, closed-run replay, pricing): untouched.
  - Sibling `./runs` readers: untouched.
  - Fleet-strip TS mirror beyond `stage_marks`: untouched.

---

## 2. Atomicity & Contract Coherence

- **Wire Model Coherence**:
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:125`: `NodeRunStatus` adds `skipped` and `cancelled`.
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:140`: `NodeRunState` adds `canonical_stage?: string | null` (from E-77).
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:146`: `PendingRef.node` is `string | null` (unattributed pendings).
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:153-157`: `terminal` is completely replaced by `outcome: RunOutcomeWire { state, reason, result }`.
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:160-164`: `GraphStateUnavailable` union member (`kind: 'unavailable'`, `reason: 'registry_drift' | 'retention_expired'`).
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:98`: `Issue.severity` includes `not_executable`.
  - `interfaces/dashboard/frontend/src/api/graph-types.ts:183-185`: `isFinalState()` cleanly defines finality as any state where `state.kind !== 'state' || state.outcome.state !== 'running'`.
- **UI Union Widenings**:
  - `interfaces/ui/src/components/graph_canvas/types.ts:6`: `CanvasStatus` adds `skipped` and `cancelled`.
  - `interfaces/ui/src/components/graph_canvas/GraphCanvas.vue:71-72`: stable CSS classes `--status-skipped` and `--status-quarantined` wired without throwing.
  - `interfaces/ui/src/components/issue_list/IssueList.vue:6,45`: `IssueItem.severity` adds `not_executable` with `.cmp-issue-not_executable` styling.
- **Linear Fallback & Fleet Strip**:
  - `interfaces/dashboard/frontend/src/api/http.ts:71,90`: `stageMarks: s.stage_marks ?? null` (open runs) and `stageMarks: marks ?? null` (closed runs via `closed_marks`).
  - `interfaces/dashboard/frontend/src/api/types.ts:31`: `stageMarks: Record<string, DotState> | null` (required with null).
  - `interfaces/dashboard/frontend/src/composables/stageState.ts:23-26`: if `run.stageMarks != null`, renders marks verbatim in canonical order, marking absent canonical stages as `skipped`. When `run.stageMarks == null` (e.g. `FeatureWorkflow` or pre-dispatch), falls back to the exact linear `activeStages` calculation. Non-canonical marks keys (e.g. `unknown`) render nothing and do not trigger activeStages console error logs.
- **Poll Finality**:
  - `interfaces/dashboard/frontend/src/api/http-graph.ts:80`: `final: isFinalState(state)`. Running outcomes continue polling; completed, rejected, escalated, failed, and unavailable outcomes terminate polling immediately.
- **RunView Banner Honesty**:
  - `interfaces/dashboard/frontend/src/views/RunView.vue:60-63`: Stale "Graph view arrives with E-75" copy removed; honest banner displayed when `run_graph` is unavailable or when `graph_state` degrades to `unavailable` (`run-graph-state-unavailable`).

---

## 3. Test Honesty & Verification

- **Pin Movement Rationale**:
  - `tests/test_dashboard_graph_wire.py:90-95`: Caps pin renamed and updated to `test_catalog_capabilities_are_all_true_after_canvas_run_mode` with rationale explaining post-flip expectations.
  - `tests/test_dashboard_run_graph_routes.py:172-180`: `test_capabilities_stay_false` updated to `test_capabilities_declare_canvas_run_mode_live` with rationale.
  - `tests/test_graph_fixtures_fresh.py:30`: `PROVISIONAL` set emptied with rationale that recorded fixtures replace provisional fixtures.
  - Frontend test pins (`http-graph.test.ts`, `mock/graph.test.ts`, `adapters/graph.test.ts`, `RunView.test.ts`) updated to test the recorded contract and explicit catalog configurations rather than relying on stale defaults.
  - No intended behavior was silently deleted or weakened.
- **RED Suite Integrity**:
  - `282831b` and `d88ea81` captured all RED contracts prior to fixes. All 27 RED contracts across pytest, vitest, and playwright fail on the pre-fix tree for value mismatches/throws and transition to green post-fix.

---

## 4. Commit Hygiene

- **Chain Commits**:
  - `282831b`: `test(dashboard): RED contracts for the canvas run-mode wiring (E75-OQ-1)`
  - `d88ea81`: `test(ui): RED contracts for the canvas run-mode wiring, TS side (E75-OQ-1)`
  - `3fd1323`: `feat(ui): widen CanvasStatus and IssueItem.severity for the FINAL run wire (E75-OQ-1)`
  - `cefaafe`: `feat(dashboard): catch the TS mirror up to the FINAL run wire (E75-OQ-1)`
  - `707430c`: `feat(dashboard): flip validate and run_graph live -- canvas run mode (E75-OQ-1)`
  - `7b36f89`: `docs(bug): canvas-run-mode fix and verification reports`
  - `2e77b2d`: `docs(spec): canvas run-mode wiring delivered -- tick E75-OQ-1 follow-ups`
- **Trailers & Discipline**:
  - Zero attribution trailers (e.g. `Co-authored-by`, `Signed-off-by`) across all 7 commit messages.
  - One-path-per-add discipline adhered to; messages match repository conventions and detail exact design decisions and test rationale.

---

## 5. Documentation Duty

- In `2e77b2d`:
  - `docs/roadmap/pipeline-as-data.md:119,158-162`: Marks canvas-run-mode follow-up delivered; sibling follow-ups (fail-edge axis, E75-OQ-2/3/4) left untouched.
  - `.specify/specs/001-canonical-stage-graph-sha/spec.md:108`: Updated capability status.
  - `docs/superpowers/specs/2026-09-17-graph-queries-design.md:52,379-385`: Records E75-OQ-1 option (a) landing.
  - `docs/superpowers/specs/2026-09-14-graph-canvas-design.md:240`: Updates §5.7 TS mirror pointer.

---

## 6. Verification Gates

- **Caps & Route Tests**:
  `.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_canvas_run_mode_chaos.py tests/test_graph_fixtures_fresh.py tests/test_dashboard_graph_wire.py tests/test_dashboard_run_graph_routes.py -q`
  -> **53 passed** in 10.97s.
- **Python Fast Tier**:
  `.\.venv\Scripts\python.exe -m pytest -q`
  -> **Passed**, zero errors.
- **Static Gates**:
  - `uv run --frozen ruff check .` -> All checks passed.
  - `uv run --frozen ruff format --check .` -> 1436 files already formatted.
  - `uv run --frozen mypy` -> Success: no issues found in 375 source files.
  - `uv run --frozen python scripts/check_file_size.py` -> Clean (exit 0).
- **Frontend Gates (`python scripts/check_ui.py`)**:
  - Workspace typechecks (`vue-tsc --noEmit` on dashboard and @kroker/ui): clean.
  - Builds (`build-dashboard`, `build-ui`, `build-ds-bundle`): clean.
  - Vitest dashboard: **242 passed** (242).
  - Vitest ui: **102 passed** (102).
  - Playwright: **50 passed** (50).
  -> **`ui gate passes`** (exit 0).

---

## Findings

### Blocking
None.

### Minor
None.

### Note
- **Note 1 (file: `interfaces/dashboard/frontend/src/api/mock/index.ts:165-270`)**: Seeded mock data strings contain non-ASCII punctuation encoded in cp1252 / UTF-8 discrepancies (e.g. `—` rendered as `â€”`). These are mocked demo seeds only and do not affect types, runtime behavior, or tests.
- **Note 2 (file: `tests/test_dashboard_canvas_run_mode_chaos.py`)**: Pre-draft adoption was explicitly ruled at the scope gate, verified RED in `red-report-qa-chaos.md`, and documented in commit `d88ea81`.

---

## Verdict

APPROVE

Ack (2026-09-20): da61092 verified, approve.
