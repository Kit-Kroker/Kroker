# Implementation Plan: Frontend restructure — by-screen features, design-system port, board screen

**Branch**: orchestrator's call (spec dir `002-frontend-screen-restructure`) | **Date**: 2026-09-23 | **Spec**: [spec.md](spec.md) | **Base**: main `5899f77`

**Input**: [spec.md](spec.md) — GATE 1 cleared 2026-09-23 (rulings G1–G9); reviewer-approved (`checklists/spec.md`); amended at plan (FR-018, FR-021a, mock-default assumption — each marked in the spec).

## Summary

Three ordered task groups, one branch. **A** regroups `interfaces/dashboard/frontend/src` by screen (`app/`, `api/`, `shared/`, `features/<screen>/`) as a behaviour-neutral move, adds an import-boundary test, and documents the layout. **B** adopts the prototype's pass-three tokens, reconciles `status_pip`, teaches the showcase to render text slots, and ports 13 design-system components into `interfaces/ui/` under repo conventions. **C** adds `project_key` to the run wire, turns the run page into a tab host (Graph | Board | Gates | Cost, the last two disabled), and builds the read-only Board tab from the existing board routes. Decisions R-1…R-13 are in [research.md](research.md); the source-layout and board-client contracts are in [contracts/](contracts/).

## Technical Context

**Language/Version**: TypeScript 5 / Vue 3.4 (SFC `<script setup>`), Python 3.12+ for the one backend change
**Primary Dependencies**: Vue, Pinia, vue-router (hash history), Vite 5, Vitest 1.6 + `@vue/test-utils` (jsdom), Playwright (two tiers: showcase on 4173, dashboard app on 4174 built with `VITE_API=mock`), vue-flow (graph canvas); backend FastAPI + pydantic + Temporal (unchanged surface except one model field)
**Storage**: N/A (board SQLite read through existing routes)
**Testing**: `python scripts/check_ui.py` only for JS (install → typecheck ×2 → builds → vitest-dashboard → ds-bundle → vitest-ui → playwright); `python scripts/check_clauses.py` report (advisory, always exits 0 — read the output); backend: `pytest` fast tier, `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`
**Target Platform**: browser SPA served by the dashboard backend; developer host is Windows (PowerShell 5.1 / Git Bash — see Execution notes)
**Project Type**: web application (frontend package + design-system package + small backend change)
**Performance Goals**: none new; board polling reuses `startPoll` cadence and backoff
**Constraints**: R1–R9 and G1–G9 (spec); 1000-line ceiling; no hex/px in Playwright assertions; clause IDs with underscores, same-line citations; `ui/` never imports `dashboard/`; no cross-screen imports
**Scale/Scope**: ~70 dashboard files moved/split; 13 components × 5 files ported; ~15 new board/run files; 2 backend models + 2 builders + 1 fixture

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles) — no constitution gates apply. The binding constraints are the repo rules the spec already lifts into R1–R9 (root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`, `src/sdlc/workflows/AGENTS.md`). Post-design re-check: no design element violates them; the one tension found (R6 vs. the run tab host) is resolved in R-13 without an exception.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/002-frontend-screen-restructure/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/  source-layout.md, board-client.md
├── checklists/ requirements.md, spec.md (+ plan.md, tasks.md from the reviewer)
└── tasks.md    (/speckit-tasks)
```

### Source Code (after the feature)

```text
interfaces/dashboard/frontend/src/
├── app/            main.ts, App.vue, router.ts, RunPage.vue (R-13), theme.css,
│                   ui.store.ts, inbox.store.ts, shell/{AppHeader,StartRunModal,Toasts}.vue,
│                   boundaries.test.ts, *.test.ts
├── api/            unchanged (client.ts gains `API_MODE` export in C)
├── shared/         catalog.store.ts, fleet.store.ts, stageStrip.adapter.ts, stageState.ts,
│                   graphCanvas.adapter.ts, format.ts (+ tests)
└── features/
    ├── fleet/      FleetView.vue, FleetTable.vue, fleet.adapter.ts, status.ts (+ tests)
    ├── run/        RunView.vue (tab host), runGraph.store.ts (+ tests)
    ├── board/      BoardTab.vue, board.adapter.ts, board.store.ts, board.api.ts,
    │               board.types.ts, __fixtures__/ (+ tests)
    ├── inbox/      InboxView.vue
    └── graphs/     GraphEditorView.vue, GraphInspector.vue, graphEditor.store.ts,
                    graphEdits.ts, schemaCoverage.test.ts (+ tests)

interfaces/ui/
├── src/tokens/     tokens.css, tokens.md, tokens.pw.ts        (pass three, B1)
├── src/components/ status_pip/ (reconciled, B2) + 13 new dirs (B4–B6)
├── src/index.ts    + 13 component exports (+ DetailSection, prop types)
└── showcase/       Showcase.vue (text slots), showcase.md, showcase.pw.ts, registry.ts

src/sdlc/core/models.py            RunState.project_key, RunSummary.project_key
src/sdlc/workflows/run_host.py     _snapshot_run_state + _retro pass project_key
src/sdlc/observability/summary.py  build_run_summary(project_key=…)
records/2026-09-23-design-foundations/   (G2b — parked until a source path is supplied)
```

**Structure Decision**: layered screens per [contracts/source-layout.md](contracts/source-layout.md); `api/` content untouched in A; the board transport is feature-local (R-3).

## Task groups

Order is binding (R1). Each group ends green on `python scripts/check_ui.py` (R3); the group-C backend slice also ends green on the Python gates. Commit per task.

### Group A — by-screen structure (behaviour-neutral)

- **A0 Baseline.** Run `check_ui.py`; record the vitest-dashboard and vitest-ui pass counts and the Playwright count in the task note (SC-002 baseline). No edits.
- **A1 Boundary test first.** Create `app/boundaries.test.ts` with the exported `violations()` scanner (path-normalized, R-5 rule 5; narrow features→app rule, R-5 rule 6), its planted-violation self-tests (one per rule, including `features/run/RunView.vue → features/board/BoardTab.vue` and `features/x → app/RunPage.vue`), the verbatim ownership case (moved out of `adapters/fleet.test.ts`, + non-empty guard on `ui/src`), and the resolver ownership case. Real-tree scans cover whatever of `features/`, `shared/`, `api/` exists; per-directory file-count guards switch on in the task that creates each directory (R-5 item 4).
- **A2 App shell.** Move `main.ts`, `App.vue` (+test), `router.ts`, `styles/theme.css`, the three shell wrappers (+tests) into `app/` / `app/shell/` (G1); `stores/ui.ts`, `stores/inbox.ts` → `app/*.store.ts` (G6); split `stores/stores.test.ts` (inbox + ui cases → `app/`). Update `index.html`'s entry script path and every import / `vi.mock` path.
- **A3 Shared.** `stores/catalog.ts`, `stores/fleet.ts` → `shared/*.store.ts`; `adapters/graph.ts` → `shared/graphCanvas.adapter.ts` (+test); `composables/format.ts`, `stageState.ts` → `shared/`; split `toStageDots` into `shared/stageStrip.adapter.ts`; split `composables.test.ts`, `stores.test.ts` (fleet case), `adapters/fleet.test.ts` (dot cases) accordingly (R-6).
- **A4 Screens.** fleet, run, graphs, inbox folders per the R-6 table; `toFleetRow` + `status.ts` to fleet. Create `features/board/` empty-ready with a tracked `features/board/.gitkeep` (FR-001: "created empty-ready in A, filled in C"), so the FR-008 table's Board row names an existing folder after A; C3 deletes the `.gitkeep` when it adds the first board file.
- **A5 Delete + docs.** Delete `constants.ts`, `constants.test.ts`, `adapters/inbox.ts` (FR-007a); confirm `components/`, `views/`, `stores/`, `adapters/`, `composables/`, `styles/` are gone; add the screen-location table + layer rules to `interfaces/AGENTS.md` and replace its `src/adapters/` references (FR-008). Gate: `check_ui.py` green, dashboard pass count ≥ A0, boundary test sees > 0 feature files.

A2–A4 may be one commit each or one combined commit; each must leave typecheck and vitest green (the boundary test's real-tree scans guard every intermediate state).

### Group B — design-system port

- **B1 Tokens (G2).** Replace `tokens.css`, `tokens.md`, `tokens.pw.ts` with the prototype's in one task (R-7). Existing presentation specs must stay green with no edits.
- **B1b Record import (G2b) — PARKED.** Blocked on the source path (spec Open items). Does not gate B2+.
- **B2 status_pip (G3).** Replace `.md/.profiles.ts/.spec.ts/.pw.ts`; keep `StatusPip.vue`; `group: 'Fleet'` (R-8).
- **B3 Showcase slots.** `Showcase.vue` renders text slots; `showcase/showcase.md` `SHOWCASE-1` + `showcase/showcase.pw.ts` (R-9).
- **B4 Primitives**: button, tag, surface, segmented_control, filter_chip.
- **B5 Forms/Status**: field, check_row, status_tag, stat.
- **B6 Data/Shell**: list_row, detail_pane (+DetailSection, G8), timeline, tab_bar.

Every port task: copy the prototype's 5 files verbatim → conform to R7 → add its `registry.ts` line (prototype order, primitives first; G9 sections) and `src/index.ts` export(s) with public prop types → DoD per R-10. `status_tag`, `stat`, `timeline` depend on B2.

### Group C — board screen

- **C1 Run wire (backend, G4).** Models + `_snapshot_run_state` + `build_run_summary`/`_retro` (R-1); extend `tests/test_run_state_model.py` shared set; tests for `project_key` present/absent in both builders; `workflows/AGENTS.md:28` ownership row. Python gates green.
- **C2 Frontend run wire.** `Run.projectKey` (required); `mapRun`/`mapClosed`; `startRun` fallback; mock runs (one with a board project, one `null`, one 404 project, one empty); `fleet-snapshot.json` hand-edit (R-2); drift note to `.workspace/tasks/`; `/projects` dev proxy (R-12); `API_MODE` export from `api/client.ts`.
- **C3 Board transport + types + mock.** `board.types.ts`, `board.api.ts` (http + mock + selection), `__fixtures__/` per the board-client contract; unit tests for URL building, plan-version pin, 404 vs transient classification.
- **C4 Board adapter.** Pure mapping per data-model §3; unit tests.
- **C5 Board store.** State machine per data-model §4 — 404 is permanent only on steps 1 and 3; step-2 404 falls back to the current plan; step-4 404 skips a key; transient failures during the initial load retry inside the poll loop; the selected task's detail and events refresh when its `row_version` changes. Polling via `startPoll`. Unit tests cover every transition, stop on unmount, and keeping data on a transient failure.
- **C6 Tab host.** First, prove the barrel resolves: import one ported component from `@kroker/ui` and run the typecheck step; on `TS2307`, add `"@kroker/ui": ["../../ui/src/index.ts"]` to `interfaces/dashboard/frontend/tsconfig.json` `paths` (the package is a workspace symlink with `exports`, so bundler resolution is expected to work — verify, don't assume). Then `RunView` gains the `tab` prop, `TABS`, TabBar and the typed `#board` slot (R-13); title + StageDots stay in the header (FR-018 amended); graph content moves into a flex-column Graph panel (`v-if`); Board disabled without the slot, Gates/Cost disabled (G7); new `app/RunPage.vue` route component with the R-4 props function supplies `#board`; existing `RunView.test.ts` green unchanged; new `RunView.tabs.test.ts` and `app/RunPage.test.ts`. A run that is still unknown after the fleet's first fetch shows "run not found" in the Board panel, not an endless "loading run…" (data-model §5).
- **C7 BoardTab view.** Props `{ runId, projectKey }`; starts/stops the board store on its own mount/unmount and restarts on `projectKey` change. ListRow/StatusTag task list, DetailPane + DetailSection (fields, evidence) + Timeline, version rows, Stat counter strip labelled "this run", banners/empty/connection-lost states.
- **C8 App-tier clauses.** `interfaces/ui/app.md` `CONSOLE-10…` (tab URL round-trip, board list + selection, each FR-022 banner, empty state, Graph unchanged after switching back) cited in `interfaces/ui/app.pw.ts` against the board mock (R-11).
- **C9 Close-out.** Full `check_ui.py`, Python gates, `check_clauses.py` report clean for every new clause, file-size check; spec Status note; living docs untouched until merge (R9).

## Execution notes (for the executor brief)

- JS checks: `python scripts/check_ui.py` only (R4). Set `PLAYWRIGHT_BROWSERS_PATH=D:/own/.pw-browsers` (the script defaults it on Windows). `reuseExistingServer` is on locally — kill stale preview servers on 4173/4174 before a Playwright run after a rebuild-affecting change, or a stale bundle is tested.
- Never re-run `scripts/dump_dashboard_fixtures.py` (R-2).
- `vi.mock('<relative>')` paths are imports — rewrite them on every move (R-6 trap).
- Board clause citations go in `interfaces/ui/app.pw.ts`; dashboard `*.test.ts` citations are invisible to `check_clauses.py`.
- Read `.workspace/tasks/` for known host hazards before any full-suite or temporal-tier run.
- `src/vite-env.d.ts` stays at the `src/` root; `index.html`'s entry becomes `/src/app/main.ts`.
- The dashboard `tsconfig.json` maps only `@kroker/ui/*`; if `vue-tsc` does not resolve the bare `@kroker/ui` barrel (C6/C7), add `"@kroker/ui": ["../../ui/src/index.ts"]` to `paths` rather than falling back to deep imports.

## Complexity Tracking

| Tension | Why needed | Simpler alternative rejected because |
|---|---|---|
| Test files split across modules in A (R-6) | R6 forces `adapters/fleet.ts` to split; R2 requires tests to travel with their code | keeping combined test files would make `shared/` tests import `features/` (layering violation) |
| Extra app-layer route component `app/RunPage.vue` (R-13) | keeps R6 absolute while the run page hosts the board tab | a named boundary exception would make R6 a negotiable rule |
| Fixture hand-edit instead of regeneration (R-2) | the dump script no longer reproduces the fixture | regenerating deletes hand-added graph rows other suites pin |
