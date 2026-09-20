# Bug Fix: canvas run-mode wiring (E75-OQ-1, option (a))

- **Slug**: canvas-run-mode
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Activated the E-76 canvas run mode against live data per the pre-ruled
E75-OQ-1 option (a): flipped the two `graph_wire.Capabilities` defaults
(`validate`, `run_graph` — the only backend change), caught the TS mirror
up to the FINAL E-75/E-77 wire (`outcome` replaces `terminal`;
`skipped`/`cancelled` statuses; nullable `PendingRef.node`;
`not_executable` severity; the `unavailable` union member; wire
`canonical_stage`), swapped the mock to the recorded run_state fixtures
(deleting both `*.provisional.json`), and mapped `stage_marks` /
`closed_marks` for the fleet strip with the FeatureWorkflow linear
fallback intact.

## Changes

Landed as C1 → C2 → C3 (each commit's message carries the full
rationale; see `git log 36baf5b..HEAD`):

| File | Change | Notes |
|------|--------|-------|
| `src/sdlc/dashboard/graph_wire.py` | modified | The two Field defaults → True + docstring history (C3). The ONLY backend change; routes/handlers/projections untouched. |
| `interfaces/.../api/graph-types.ts` | modified | FINAL mirror: `RunOutcomeWire`/`outcome`, `isFinalState`, `GraphStateUnavailable`, statuses + `canonical_stage`, nullable node, `not_executable` (C2). |
| `interfaces/.../api/http-graph.ts` | modified | Outcome-based poll finality; `unavailable` ends the chain (C2). |
| `interfaces/.../api/http.ts`, `api/types.ts` | modified | `Run.stageMarks` (required-with-null); open rows read `stage_marks`, closed graph rows read `closed_marks` (C2). |
| `interfaces/.../composables/stageState.ts`, `adapters/fleet.ts` | modified | E-76 §9.1 rule 1: marks verbatim, absent stage → `skipped`, null → linear fallback; non-canonical keys render nothing, no product-fault log (C2). |
| `interfaces/.../adapters/graph.ts` | modified | Unattributed pendings key nowhere; `CanvasModel.outcome` (additive, gate-accepted) (C2). |
| `interfaces/.../views/RunView.vue` | modified | Honest banners: "not available on this server"; `run-graph-state-unavailable` for registry_drift/retention_expired (C2). |
| `interfaces/.../api/mock/graph.ts`, `mock/index.ts` | modified | Recorded-fixture swap; code-defined transitions (ruling 3); demo seed marks mirror the recorded blocked projection (C2). |
| `interfaces/.../__fixtures__/graph/run_graphs.provisional.json`, `validation.provisional.json` | removed | The recorded `run_state/*` contract replaces them (C2). |
| `interfaces/.../__fixtures__/graph/catalog.json` | regenerated | Capabilities block only (C3; dump script). |
| `interfaces/ui/.../graph_canvas/{types.ts,GraphCanvas.vue,graph_canvas.md,profiles,pw,spec}` | modified | `CanvasStatus` += `skipped`/`cancelled` + classes + clause + coverage (escalation 1, C1). |
| `interfaces/ui/.../issue_list/{IssueList.vue,issue_list.md,profiles,pw,spec}` | modified | `IssueItem.severity` += `not_executable` + class + clause + coverage (escalation 1, C1). |
| `interfaces/ui/app.pw.ts` | modified | Dashboard e2e over the new recorded mock (12-node graph, recorded script; editor flows paste the pre_code scenario) (C2). |
| `tests/test_graph_fixtures_fresh.py`, `scripts/dump_graph_fixtures.py` | modified | Allowed-strays pin → empty set; stale docstring line (C2). |
| `tests/test_dashboard_graph_wire.py`, `tests/test_dashboard_run_graph_routes.py` | modified | Caps pins flipped with rationale (C3). |
| RED suites (both qa seats + adopted pre-draft) | added | `282831b` + `d88ea81`: 27 RED contracts (9 pytest, 16 dashboard, 2 ui), all now green. |

## Tests Added or Updated

- RED contracts (qa-happy, qa-chaos + the adopted pre-draft): caps pins
  (defaults, runtime catalog, served fixture), provisional-deletion,
  outcome-based finality over recorded bodies, `stageMarks` mapping and
  strip rendering (verbatim / absent→skipped / empty→all-skipped /
  null→linear / non-canonical key silent), unattributed-pending keying,
  skipped/cancelled classes, not_executable class, RunView banners,
  mock recorded script (approve→completed, reject→rejected).
- Pre-existing pins moved with rationale (full list in the C2/C3 commit
  messages): old terminal-shaped bodies → outcome; provisional-sourced
  adapter/mock rows → recorded fixtures; the demo-run sha pin; the
  "never polls"/no-capability cases now pin explicit catalogs.

## Local Verification

- `pytest` (fast tier, worktree venv): exit 0 — fully green including
  the 7 formerly-RED caps pins.
- `python scripts/check_ui.py`: exit 0 — typechecks (both workspaces),
  builds, ds-bundle, vitest-dashboard 242/242, vitest-ui 102/102,
  playwright 50/50.
- `uv run --frozen ruff check .` / `ruff format --check .` / `mypy` /
  `scripts/check_file_size.py`: all green.

## Deviations from Assessment

- The assessment's single-commit fallback was not needed: the cleared
  C1/C2/C3 decomposition kept every gate observable-green per commit
  (the RED commits are red by design per the orchestrator's ruling).
- qa-happy self-committed the pytest RED contracts as `282831b`
  contrary to the dispatch instruction ("do not commit"); content was
  verified clean (tests-only, rationale-rich, no attribution trailers)
  and adopted as RED round 1.
- No others. The two E-77-era mirror additions and the ui widenings were
  cleared at the scope gate (escalations 1–2), not silent expansions.

## Follow-ups

- Doc duty (post-'verified'): roadmap tick `docs/roadmap/pipeline-as-data.md:158-162`
  (canvas-run-mode part only), `.specify/specs/001-canonical-stage-graph-sha/spec.md:108`
  phrase, E-75 design §12 E75-OQ-1 "landed" annotation, E-76 spec §5.7
  pointer refresh.
- Out of scope, untouched per the brief: E76-OQ-1/2/4/5, E75-OQ-2/3/4,
  sibling `./runs` readers, fleet-strip TS mirror beyond stage_marks.
