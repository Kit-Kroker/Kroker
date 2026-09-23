# Research: Frontend restructure — by-screen features, design-system port, board screen

**Plan**: [plan.md](plan.md) · **Spec**: [spec.md](spec.md) · **Base**: main `5899f77`

Phase 0 of `/speckit-plan`. Every decision below was put to the advisor seat (consult 1, `.workspace/tmp/advisor-002-1.md`) and its load-bearing anchors were re-read by the planner before being recorded. GATE 1 rulings G1–G9 are binding and are not re-decided here.

## R-1 — Where `project_key` enters the run wire (G4, FR-020a)

- **Decision**: Add `project_key: str | None = None` to both `RunState` and `RunSummary` (`src/sdlc/core/models.py:477`, `:510`). Set it in `RunHost._snapshot_run_state` (`src/sdlc/workflows/run_host.py:148`) from `self._cfg.project_key if self._cfg else None`, and in `_retro` (`run_host.py:103`) via a new `project_key` kwarg on `build_run_summary` (`src/sdlc/observability/summary.py:137`) fed from the `cfg` `_retro` already receives. Frontend: `Run.projectKey: string | null` (required field), mapped as `s.project_key ?? null` in `mapRun`/`mapClosed` (`api/http.ts:62`, `:81`).
- **Rationale**: Both models are plain `BaseModel` (default `extra="ignore"`), so the field is additive. Queries emit no commands; `build_run_summary` is pure workflow code; Temporal's nondeterminism check compares activity type/id, not input payloads — `graph_sha` was added by the same route (`run_host.py:116`). The SPA reads runs only through `GET /api/inbox` (a whole `FleetSnapshot`) and the `/api/events` SSE, so the two models are the whole wire; `dashboard/api.py` needs no change.
- **Consequences recorded for tasks**:
  - Retained pre-change *closed* runs answer `run_summary` by replay with the new worker code, so they will usually show their real `project_key`, not null. Tests pin the null path at the JSON level (key absent or null), never "old closed run → banner".
  - `Run.projectKey` stays **required**: `vue-tsc` then flags every non-test `Run` literal (`api/http.ts:210-215` start-run fallback; ~8 literals in `api/mock/index.ts`). Test files are outside tsc (`tsconfig.json:20`).
  - `tests/test_run_state_model.py:58` checks the two models share field names — adding the field to both keeps it green; add `project_key` to its shared set.
  - `src/sdlc/workflows/AGENTS.md:28` (state-ownership table) gains `RunHost._snapshot_run_state` as a `_cfg` reader and the missing `GraphWorkflow.run` writer.
- **Alternatives rejected**: a run-scoped `/api` board route (G4 chose A); deriving the key in the dashboard poller (would re-read config the run already holds).

## R-2 — `fleet-snapshot.json` drift (FR-020a fixtures)

- **Decision**: Hand-edit `interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json` to add `project_key` — a real key on at least one open and one closed row, `null`/absent on at least one of each — and file the dump-script drift to `.workspace/tasks/` as a follow-up. Do **not** re-run `scripts/dump_dashboard_fixtures.py`.
- **Rationale**: The fixture holds hand-added graph rows the script never emits (`graph-run-live` line 56, `graph-run-closed` line 156, `closed_marks` line 177; verified). Regenerating deletes them and breaks `http.test.ts`/`client.test.ts`. Reproducing them in the script is the better long-term fix but is out of this feature's scope.
- **Alternative rejected**: extend the dump script now (advisor's preferred) — larger, touches fixtures other suites depend on, and is not required by any FR.

## R-3 — Board transport location (FR-019, FR-020)

- **Decision**: Feature-local. `features/board/board.api.ts` holds the `BoardApi` interface, `createHttpBoardApi(base = '')`, `createMockBoardApi()`, and one exported `boardApi` selected by the same mode rule as `api/client.ts:9`. Wire types in `features/board/board.types.ts`; hand-authored fixtures in `features/board/__fixtures__/`. Errors via `api/errors.ts` (`HttpStatusError`, `isNotFound`); polling via `api/poll.ts` (`startPoll`). To keep one source for the mode rule, group C exports `API_MODE` from `api/client.ts` (one-line addition) and both files use it.
- **Rationale**: The board is single-screen, so R6 allows it to stay local; extending `DashboardApi` would churn `types.ts`/`http.ts`/`mock/index.ts` (415 lines) and every `vi.mock('../api/client')` double. Nothing enumerates `DashboardApi` methods (grep for `keyof DashboardApi`, `satisfies DashboardApi`, `Object.keys(api` — only the two factories and `client.ts`). The board also lives under a different base path (`/projects`).
- **Error classification**: 404 → permanent banner (FR-022: unknown project, no plan — `board/api.py:93-102`); any other status or network error → transient "connection lost — retrying" (FR-023a). Branch on `isNotFound(e)`, never on message text. The board routes are always mounted (the board app *is* the root app, `interfaces/dashboard/api/main.py:42`), so "surface unavailable" in practice is 5xx → transient.
- **Alternative rejected**: extend `DashboardApi` like the graph surface.

## R-4 — Tab state in the URL (FR-017)

- **Decision**: Query param `/#/runs/:id?tab=board`, delivered to `RunView` as a route prop. The run route's `props: true` becomes a function returning `{ id, tab }` (`tab` only when `r.query.tab` is a string). `RunView` computes the active tab as the matching enabled tab or `'graph'`. Tab selection calls `router.replace` with `tab` removed for Graph. Unknown or disabled values render Graph and leave the URL untouched.
- **Rationale**: `RunView.test.ts:65`/`:84` mount `RunView` with props and a `RouterLink` stub only (verified) — `useRoute()` inside `RunView` would be undefined and break both tests (FR-007). A prop keeps them unchanged. A query change does not change `id`, so the graph store's `watch(() => props.id)` (`RunView.vue:27`) does not restart. `replace`, not `push`: tab switches do not pile up history; a copied URL still reopens Board (SC-005).
- **Obtaining the router for `replace`**: `useRouter()` is also absent in those tests; the tab-select handler must tolerate a missing router (optional call) so the existing tests stay green, and the new tab tests install a memory router.
- **Panels**: `v-if`, not `v-show` — vue-flow measures its container; a `display:none` canvas can mis-fit on re-show. The run-graph store keeps its `RunView` mount/unmount lifecycle; the board store starts/stops on the Board panel's own mount/unmount (FR-023 for both leave-tab and leave-page).
- **Alternative rejected**: nested child routes `/runs/:id/board` (needs a `<RouterView>` in `RunView`, remounts per tab, forces a real router into the existing tests).

## R-5 — Cross-feature boundary test and ownership move (FR-004, FR-005, SC-003)

- **Decision**: One file, `src/app/boundaries.test.ts`, with:
  1. The existing ownership case moved **verbatim** from `adapters/fleet.test.ts` (its `join(__dirname, '../../../../ui/src')` is unchanged because `src/app/` is the same depth as `src/adapters/`), plus a `files.length > 0` guard. A missing root already fails (ENOENT); an empty tree is the vacuous-pass case the guard closes.
  2. A **new, additional** ownership case using a real resolver: any relative import in `ui/src` that resolves under `interfaces/dashboard/` is a violation. The verbatim case's substring match (`"from '../../dashboard"`) only catches files directly under `ui/src/`; R2 forbids rewriting it, so strength is added beside it.
  3. A pure exported `violations(files, root)` scanner: whole-file text (not per line — multi-line imports exist, e.g. `stores/graphEditor.ts:9-13`), `.vue` included, specifiers from `from '…'`, side-effect `import '…'`, dynamic `import('…')`, `vi.mock('…')`, `import.meta.glob('…')`. Only relative specifiers are resolved. Rules: a file in `features/<x>/` must not resolve into `features/<y>/` (x ≠ y); `shared/` and `api/` must not resolve into `features/` or `app/`. `features/*` → `app/*.store.ts` is **allowed** (G6 put the `ui` store in the shell and `runGraph` imports it; the router imports views — a layer cycle, not a module cycle); `features/*` → any other `app/` module is banned (rule 6 below).
  4. The scanner is tested against an in-memory planted violation (never a committed violating file), then run over the real tree expecting `[]`. File-count guards are per directory and only for directories that exist at that task: `ui/src` from A1; `app/` from A2; `shared/` from A3; `features/` from A4 (the guard is switched on by the task that creates the directory).
  5. **Path normalization**: every source path and every resolved specifier is normalized to `/` (`p.replaceAll('\\', '/')`) before any rule is evaluated — `path.resolve` returns backslashes on Windows, and a POSIX-only matcher would pass every planted violation there.
  6. **features → app is narrow**: a file in `features/` may import only `app/*.store.ts` (the shell stores G6 placed there). Importing any other `app/` module (`RunPage.vue`, `router.ts`, `App.vue`, `shell/*`) is a violation — otherwise `features/run` could reach `features/board` transitively through `app/RunPage.vue` (skeptic 5).
- **Rationale**: Regex-per-line misses multi-line imports; `vi.mock` paths are real module references and are where stale paths hide.

## R-6 — Module mapping for group A (FR-001–FR-003, FR-006, FR-007a)

- **Decision** (whole-file moves; the only split is the one R6 forces):

| Today (`frontend/src/`) | Target | Notes |
|---|---|---|
| `main.ts`, `App.vue`, `App.test.ts`, `router.ts`, `styles/theme.css` | `app/` | theme wiring = the `tokens.css` + `theme.css` imports in `main.ts` |
| `components/AppHeader.vue`, `StartRunModal.vue`, `Toasts.vue` + tests | `app/shell/` | G1, unchanged |
| `stores/ui.ts`, `stores/inbox.ts` | `app/ui.store.ts`, `app/inbox.store.ts` | G6 |
| `stores/catalog.ts`, `stores/fleet.ts` | `shared/catalog.store.ts`, `shared/fleet.store.ts` | cross-screen |
| `adapters/fleet.ts` → `toStageDots` | `shared/stageStrip.adapter.ts` | fleet + run |
| `adapters/fleet.ts` → `toFleetRow` | `features/fleet/fleet.adapter.ts` | imports `toStageDots` from shared |
| `composables/stageState.ts` | `shared/stageState.ts` | whole file (module-level report-once state stays isolated) |
| `composables/status.ts` | `features/fleet/status.ts` | only `toFleetRow` uses it — FR-003's parenthetical listed "status" among shared modules; its opening rule ("follow the verified import graph, not the brief's sketch") supersedes the sketch, and the spec parenthetical is corrected at plan |
| `composables/format.ts` | `shared/format.ts` | `money` used by the shell |
| `adapters/graph.ts` + `adapters/graph.test.ts` | `shared/graphCanvas.adapter.ts` + `shared/graphCanvas.adapter.test.ts` | run + graphs |
| `views/FleetView.vue`, `components/fleet/FleetTable.vue` + test | `features/fleet/` | |
| `views/RunView.vue` + test, `stores/runGraph.ts` + test | `features/run/` (`runGraph.store.ts`) | |
| `views/GraphEditorView.vue`, `components/graph/GraphInspector.vue` + test, `schemaCoverage.test.ts`, `stores/graphEditor.ts` + test, `stores/graphEdits.ts` + test | `features/graphs/` (`graphEditor.store.ts`, `graphEdits.ts`) | `graphEdits` is pure helpers — no `.store` suffix |
| `views/InboxView.vue` | `features/inbox/` | placeholder screen |
| — (new) | `features/board/.gitkeep` | FR-001: board folder created empty-ready in A; replaced by real files in C3 |
| `constants.ts`, `constants.test.ts`, `adapters/inbox.ts` | deleted | G6 / FR-007a |
| `api/**` | unchanged | content and paths |

- **Test splits (R2: each `describe`/case travels with its module, count preserved)**: `adapters/fleet.test.ts` → case 1 to `features/fleet/fleet.adapter.test.ts`, cases 2–5 to `shared/stageStrip.adapter.test.ts`, case 6 to `app/boundaries.test.ts`. `stores/stores.test.ts` → `fleet store` to `shared/fleet.store.test.ts`; `inbox store` + `ui store` to `app/shell.stores.test.ts`. `composables/composables.test.ts` → `format` to `shared/format.test.ts`, `stageStates` to `shared/stageState.test.ts`, `statusMetaOf` to `features/fleet/status.test.ts`. Each split file carries its own copy of the `vi.mock` factory and `mkRun`/`run` helper.
- **Every other test moves whole beside its module**: `App.test.ts` → `app/`; `components/AppHeader.test.ts`, `StartRunModal.test.ts`, `Toasts.test.ts` → `app/shell/`; `components/fleet/FleetTable.test.ts` → `features/fleet/`; `views/RunView.test.ts`, `stores/runGraph.test.ts` (→ `runGraph.store.test.ts`) → `features/run/`; `components/graph/GraphInspector.test.ts`, `schemaCoverage.test.ts`, `stores/graphEditor.test.ts` (→ `graphEditor.store.test.ts`), `stores/graphEdits.test.ts` → `features/graphs/`; `api/**` tests stay. A5 asserts no test file remains outside `app/`, `api/`, `shared/`, `features/`.
- **Naming**: existing camelCase stems are kept (`runGraph`, `graphEditor`, `stageStrip`, `graphCanvas`) with `.store.ts` / `.adapter.ts` suffixes; recorded in the `interfaces/AGENTS.md` table.
- **Trap**: `vi.mock('<relative path>')` strings (App.test, StartRunModal.test, RunView.test, GraphInspector.test, graphEditor.test, runGraph.test, stores.test) silently fall through to the real (HTTP) `api` if stale. Every `vi.mock` path is rewritten like an import.

## R-7 — Token adoption shape (G2, FR-009)

- **Decision**: B1 adopts `tokens.css`, `tokens.md`, `tokens.pw.ts` from the prototype **together in one task**. B2 (status_pip) is a separate, later task.
- **Rationale**: Main's TOKENS-2 exempts only `:root` from its hex scan (main `tokens.pw.ts:24`); the new `[data-theme='light']` block carries hex values, so the new `tokens.css` without the new `tokens.pw.ts` fails TOKENS-2. Status-pip colour rules already live in main's `tokens.css` (`:31-37`), `StatusPip.vue` has only size/pulse styles, and main's `status_pip.pw.ts` asserts classes and animation only — all survive B1. `document.documentElement.dataset.theme` stays unset; TOKENS-3 parses rules and never switches theme, so the light scope is inert until FU-1.
- **Watchpoint (skeptic 9)**: the prototype's `tokens.pw.ts` compares `selectorText` against `'[data-theme="light"]'` by string equality. Chromium serializes attribute-selector values with double quotes, so this matches the source's single-quoted `[data-theme='light']`; if TOKENS-2/3 fail on the light scope, the first thing to check is that serialization — fix by normalizing quotes in the test, never by editing the tokens.

## R-8 — status_pip reconcile (G3, FR-015)

- **Decision**: Replace `status_pip.md`, `.profiles.ts`, `.spec.ts`, `.pw.ts` with the prototype versions; **keep `StatusPip.vue`** (the prototype ships none because main's is unchanged — its spec still imports `./StatusPip.vue`); set `group: 'Fleet'` in the profiles (prototype says `'Status'`; G9/FR-015). Must land before `status_tag`, `stat`, `timeline` (the only ported components that import another: `../status_pip/StatusPip.vue`).
- **Known noise**: the retired `all-kinds` profile leaves a stale `dist-ds/status_pip/all-kinds.html` on dev machines (gitignored, not cleaned). Harmless — the ds-bundle spec checks only `stage_dots/every-state.html`.

## R-9 — Showcase text slots (FR-014, new gap)

- **Decision**: Extend `interfaces/ui/showcase/Showcase.vue` to render a profile's text slots with a dynamic-slot `v-for` template inside `<component>` (text interpolation, never `v-html`). Add `showcase/showcase.md` with `SHOWCASE-1` ("a profile's text slots render inside its stage") and a small `showcase/showcase.pw.ts` citing it. Lands before the first slot-using port (button).
- **Rationale**: `Showcase.vue:21` ignores `Profile.slots` (verified); button, tag, surface, list_row and timeline profiles use text slots and their `.pw.ts` assert on showcase articles. `scripts/build-ds-bundle.ts` copies the rendered showcase's `.showcase-stage` HTML, so fixing the template fixes the bundle (no DS_BUNDLE change). No ported component needs `provide`/`route` (only the deferred app_header uses `RouterLink`) — not implemented.
- **Check**: `check_clauses.py` scans UI citations in `*.spec.ts`/`*.pw.ts` under `interfaces/`; confirm `showcase/*.pw.ts` is inside its scan root and in the Playwright `testMatch`, or place the clause doc/test where both see it.

## R-10 — Group-B port task shape and DoD (FR-010–FR-014, FR-016)

- **Decision**: One task per component (or small same-group batches), each adding **its own** `showcase/registry.ts` line (prototype order: primitives first) and `src/index.ts` export in the same task — a `.pw.ts` looks up `#showcase-<name>-<profile>`, which exists only once registered. Existing sets keep their positions/sections. Order: button, tag, surface, segmented_control, filter_chip, field, check_row, status_tag, stat, list_row, detail_pane (+ `DetailSection` export, G8), timeline, tab_bar.
- **Port rule**: copy verbatim, then conform to R7; the prototype's tests were never run ("written without running Node") — each task runs them.
- **DoD per component**: `python scripts/check_ui.py` green; `python scripts/check_clauses.py` output shows no `clause with no test: <NAME>-*` and no dangling line for it (the script always exits 0 — the DoD reads its report); the component's `.pw.ts` has no hex or px assertion (prototype grep: none found; component `<style>` px is allowed, hex is not — TOKENS-2).

## R-11 — Board data access (G5, FR-021, FR-021a)

- **Decision**: Load order for a run with a `projectKey`:
  1. `GET /projects/{p}` → artifacts + stats (stats unused; G5c derives counters client-side).
  2. `GET /projects/{p}/artifacts/plan` → plan versions; pick the newest whose `run_id` is this run; its **`id`** (not `n`) is the `plan_version` (verified: `board_host._board_publish` returns `result.version_id`, the `artifact_version` surrogate id, and task rows key off it). None → omit `plan` (current plan).
  3. `GET /projects/{p}/tasks?run_id=<run>&plan=<id>` → task rows.
  4. For each artifact key from step 1: `GET /projects/{p}/artifacts/{key}` → keep versions with `run_id` = this run (G5d).
  5. On task selection: `GET /projects/{p}/tasks/{task_id}?plan=<id>` (evidence, G5e) and `GET /projects/{p}/events?subject=task:<task.plan_version>:<task_id>` (timeline, G5b; subject built from the task row).
- **Polling**: tasks (step 3) poll via `startPoll` while the Board panel is mounted; artifacts/versions load once per mount; selection fetches on select.
- **Clauses**: dashboard `*.test.ts` files are invisible to `check_clauses.py` (it scans `*.spec.ts`/`*.pw.ts`). Board behaviour clauses therefore go in `interfaces/ui/app.md` as `CONSOLE-10…` and are cited in `interfaces/ui/app.pw.ts` (app tier, `VITE_API=mock`). Adapter/store unit tests stay uncited, like every other dashboard test.

## R-12 — Dev proxy and app tier (FR-020b)

- **Decision**: Add `'/projects': { target: 'http://127.0.0.1:8500', changeOrigin: true }` to `server.proxy` in `interfaces/dashboard/frontend/vite.config.ts`. No preview-proxy work: the app Playwright tier (`interfaces/ui/playwright.config.ts:20-30`) builds with `VITE_API=mock` and never reaches a backend, so board app-tier tests run on the board mock.
- **Barrel**: group C imports ported components from `@kroker/ui` (resolves to `ui/src/index.ts` via package exports and the Vite alias); existing deep imports are left alone.

## Planner verification log (anchors re-read, main `5899f77`)

- `fleet-snapshot.json` rows `graph-run-live` (56), `graph-run-closed` (156), `closed_marks` (177) — absent from `dump_dashboard_fixtures.py`. ✔
- `RunView.test.ts:65`, `:84` mount with props + `RouterLink` stub, no router. ✔
- `board_host.py:45-47` `_plan_version` = "surrogate artifact_version.id of the current plan"; `_board_publish` returns `result.version_id`. ✔
- `run_host.py:103-116` (`_retro` builds the summary with `cfg` in scope), `:129-160` (`_snapshot_run_state` reads `self._cfg`). ✔

## R-13 — R6 vs. the run tab host (advisor consult 2, `.workspace/tmp/advisor-002-2.md`)

- **Decision**: Slot composition in the app layer. `RunView` (in `features/run/`) is the tab host and owns `TABS`, the `?tab` logic and `router.replace`. It exposes one typed named slot, `defineSlots<{ board?: (p: { runId: string; projectKey: string | null }) => unknown }>()`. The run route's component becomes `app/RunPage.vue`, which renders only `<RunView :id :tab>` with `<template #board="{ runId, projectKey }"><BoardTab :run-id :project-key /></template>`. The R-4 props function moves to that route. `RunView` never imports `features/board/`; R6 stays absolute, with no allowlist.
- **Rules that follow**:
  1. **Board is disabled without the slot.** The Board tab is `disabled: !useSlots().board`. A `RunView` mounted without the slot (the existing `RunView.test.ts`, any direct mount) shows the four labels with Board, Gates and Cost disabled and Graph active.
  2. **Render the slot only once the run is known.** Render it when `run` is defined (`fleet.getOrLoad` can be `undefined` on a cold shared link); otherwise show a neutral "loading run…" line. Rendering early would give a false "no project" banner. `BoardTab` watches `projectKey` and restarts its store when it changes.
  3. **The board store lives with the panel.** The slot sits inside `<section v-if="active === 'board'" data-testid="run-tab-board">`. `BoardTab`'s own mount/unmount starts and stops the board store (FR-023).
  4. **Keep the graph layout.** The Graph panel wrapper stays a flex column child (`display:flex; flex-direction:column; flex:1; min-height:0; gap:8px`) so `.canvas-wrap` keeps its growth. `data-testid="run-view"` stays on `RunView`'s root `<main>`, and banners and `open-copy` stay inside it (the app-tier locators are scoped to it).
  5. **New tests.** `features/run/RunView.tabs.test.ts` uses a string-template probe slot; `app/RunPage.test.ts` checks the composition with `features/board/board.api` mocked; and the boundary self-tests include `features/run/RunView.vue → features/board/BoardTab.vue` as a planted violation that must be reported.
- **Alternatives rejected**:
  - **A (a named boundary exception).** It makes R6 conditional and data-dependent.
  - **C (the component passed as a route prop).** It's untyped, triggers the reactive-component warning, and couples the router to screen internals.
  - **D (`app/RunPage.vue` as the tab host).** It puts run-screen behaviour in the shell, against FR-001.
