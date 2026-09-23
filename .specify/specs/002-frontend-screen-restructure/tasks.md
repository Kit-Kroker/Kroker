---
description: "Task list for spec 002 — frontend restructure, design-system port, board screen"
---

# Tasks: Frontend restructure — by-screen features, design-system port, board screen

**Input**: `.specify/specs/002-frontend-screen-restructure/`: [spec.md](spec.md) (G1–G9), [plan.md](plan.md), [research.md](research.md) (R-1…R-13), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: REQUIRED. The project's exec protocol is test-first. QA seats write RED tests first, and the reviewer gates each task's diff before the next task is committed. The RED form differs by group:
- **Group A (moves).** The boundary test is the RED/GREEN guard. Each move task's gate is "no test lost, no test changed except import/`vi.mock` paths".
- **Group B (ports).** The component's clause doc and tests are copied first and must fail for the stated reason (module or registration missing). Then the component is added.
- **Group C.** A new behaviour gets a RED unit or app-tier test before its implementation.

**Organization**: phases follow the binding group order A → B → C (R1). Group A delivers US1 (P1), B delivers US2 (P2), and C delivers US3 (P3).

**Standing rules for every task**:
- JS checks run only through `python scripts/check_ui.py` (R4), never npm, npx, vitest or playwright directly. Kill stale preview servers on 4173/4174 before a Playwright run after a rebuild-affecting change (`reuseExistingServer` is on locally).
- `python scripts/check_clauses.py` always exits 0. A task that adds clauses reads its output and requires no `clause with no test:` and no `test cites unknown clause:` line for them.
- Python checks run one pytest invocation per shell call.
- No file may exceed 1000 lines (`python scripts/check_file_size.py`).
- Never re-run `scripts/dump_dashboard_fixtures.py` (R-2).
- Every `vi.mock('<relative path>')` string counts as an import and is rewritten on every move (R-6 trap).
- Commits carry subject and body only, with no attribution trailers. Use `git commit -F <msgfile>`.
- Read `.workspace/tasks/` for known host hazards before any full-suite or temporal-tier run.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files — except the shared `showcase/registry.ts` / `src/index.ts` lines of the Phase 3 ports, which merge serially — and no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 from spec.md

Paths below are relative to the repo root. `FE` = `interfaces/dashboard/frontend/src`, `UI` = `interfaces/ui`, `PROTO` = `C:/Users/start/Downloads/Pipeline management prototype/kroker-ui/interfaces/ui`.

---

## Phase 1: Setup (baseline)

- [x] T001 Record the green baseline on the branch point. Run `python scripts/check_ui.py` and save the output to `.workspace/tmp/002-baseline.txt`, including the vitest-dashboard, vitest-ui and Playwright pass counts (SC-002 baseline). Then run `python scripts/check_clauses.py` and append its summary line. Any red is reported to the orchestrator, not fixed inside this feature.

---

## Phase 2: US1 — by-screen structure (Group A, P1) 🎯 MVP

**Goal**: FR-001–FR-008, SC-001–SC-003. The move is behaviour-neutral.
**Independent test**: quickstart §2.

- [x] T002 [US1] RED/guard: create `FE/app/boundaries.test.ts` per R-5 and contracts/source-layout.md:
  - an exported pure `violations(files: {path; text}[], root)` scanner. It scans whole-file text including `.vue`, extracts specifiers from `from`, side-effect `import`, dynamic `import()`, `vi.mock()` and `import.meta.glob()`, resolves relative specifiers only, and normalizes all paths to `/`.
  - rules: `features/<x>` → `features/<y>` is banned; `shared/`, `api/` → `features/`, `app/` is banned; `features/` → `app/` is allowed only for `app/*.store.ts`.
  - self-tests, each on an in-memory planted violation: cross-screen `features/run/RunView.vue → features/board/BoardTab.vue`; `features/x → app/RunPage.vue`; `shared → features`; `api → app`; a Windows-backslash path; a multi-line import; a `vi.mock` path.
  - the ownership case moved **verbatim** out of `FE/adapters/fleet.test.ts` (case 6), plus an `expect(files.length).toBeGreaterThan(0)` guard on `ui/src`. Its `join(__dirname, '../../../../ui/src')` is unchanged, since `app/` is the same depth as `adapters/`.
  - an additional resolver-based ownership case: no relative import in `UI/src` resolves under `interfaces/dashboard/`.
  - real-tree scans over whichever of `features/`, `shared/`, `api/` exist. There is no file-count guard yet for directories that don't exist.

  Delete case 6 from `FE/adapters/fleet.test.ts` in the same commit. Gate: `check_ui.py` green; vitest-dashboard count = baseline − 1 (the moved case) + the new cases.
- [x] T003 [US1] App shell (G1, G6):
  - `git mv` `FE/main.ts`, `FE/App.vue`, `FE/App.test.ts`, `FE/router.ts` into `FE/app/`, and `FE/styles/theme.css` → `FE/app/theme.css`.
  - move `FE/components/AppHeader.vue`, `StartRunModal.vue`, `Toasts.vue` and their `.test.ts` files → `FE/app/shell/`.
  - `FE/stores/ui.ts` → `FE/app/ui.store.ts`; `FE/stores/inbox.ts` → `FE/app/inbox.store.ts`.
  - split `FE/stores/stores.test.ts`: the `inbox store` and `ui store` describes go to `FE/app/shell.stores.test.ts`, each file getting its own copy of the `vi.mock` factory and helpers; the `fleet store` describe stays in place until T004.
  - update `interfaces/dashboard/frontend/index.html` to `src="/src/app/main.ts"`, plus every import and `vi.mock` path.
  - switch on the `app/` file-count guard in `boundaries.test.ts`.

  Gate: `check_ui.py` green (typecheck, build, both vitest runs, both Playwright tiers).
- [ ] T004 [US1] Shared layer (R-6):
  - `FE/stores/catalog.ts` → `FE/shared/catalog.store.ts`; `FE/stores/fleet.ts` → `FE/shared/fleet.store.ts`, with the `fleet store` describe from `stores.test.ts` → `FE/shared/fleet.store.test.ts`. Delete the emptied `stores.test.ts`.
  - `FE/adapters/graph.ts` + `graph.test.ts` → `FE/shared/graphCanvas.adapter.ts` + `.test.ts`.
  - `FE/composables/format.ts` → `FE/shared/format.ts`; `FE/composables/stageState.ts` → `FE/shared/stageState.ts`.
  - split `toStageDots` out of `FE/adapters/fleet.ts` into `FE/shared/stageStrip.adapter.ts`, and move `fleet.test.ts` cases 2–5 → `FE/shared/stageStrip.adapter.test.ts`.
  - split `FE/composables/composables.test.ts`: `format` → `FE/shared/format.test.ts`, `stageStates` → `FE/shared/stageState.test.ts`; the `statusMetaOf` describe stays until T005.
  - switch on the `shared/` file-count guard.

  Gate: `check_ui.py` green; the case count is preserved across splits.
- [ ] T005 [US1] Screens (R-6 table):
  - **fleet**: `FE/views/FleetView.vue` and `FE/components/fleet/FleetTable.vue` + test → `FE/features/fleet/`; the remaining `toFleetRow` → `FE/features/fleet/fleet.adapter.ts` (importing `toStageDots` from shared), with `fleet.test.ts` case 1 → `fleet.adapter.test.ts`; `FE/composables/status.ts` → `FE/features/fleet/status.ts`, with the `statusMetaOf` describe → `status.test.ts`.
  - **run**: `FE/views/RunView.vue` + test and `FE/stores/runGraph.ts` + test → `FE/features/run/` (`runGraph.store.ts`, `runGraph.store.test.ts`).
  - **graphs**: `FE/views/GraphEditorView.vue`, `FE/components/graph/GraphInspector.vue` + test, `schemaCoverage.test.ts`, `FE/stores/graphEditor.ts` + test (→ `graphEditor.store.ts`/`.test.ts`) and `FE/stores/graphEdits.ts` + test → `FE/features/graphs/`.
  - **inbox**: `FE/views/InboxView.vue` → `FE/features/inbox/`.
  - **board**: create `FE/features/board/.gitkeep` (FR-001).
  - update the router's view imports; switch on the `features/` file-count guard.

  Gate: `check_ui.py` green; boundary scans see > 0 files in each layer.
- [ ] T006 [US1] Delete and document (FR-007a, FR-008):
  - delete `FE/constants.ts`, `FE/constants.test.ts` and `FE/adapters/inbox.ts`.
  - assert `FE/components/`, `views/`, `stores/`, `adapters/`, `composables/`, `styles/` no longer exist, and that no test file sits outside `app/`, `api/`, `shared/`, `features/`.
  - in `interfaces/AGENTS.md`, add the screen-location table and layer rules from contracts/source-layout.md (Screen, Route, Folder, View; the Run row names `features/run/RunView.vue` as the route component until T039 switches it to `app/RunPage.vue` and updates the row; naming rule) and replace its `src/adapters/` references.

  Gate: quickstart §2 in full; vitest-dashboard count ≥ the T001 baseline.

**Checkpoint US1**: group A green. The reviewer gates the whole group diff before Phase 3.

---

## Phase 3: US2 — design-system port (Group B, P2)

**Goal**: FR-009–FR-016, SC-004.
**Independent test**: quickstart §3.

**Port recipe (T010–T022)**:
1. RED: copy `PROTO/src/components/<name>/<name>.md`, `.profiles.ts`, `.spec.ts`, `.pw.ts` into `UI/src/components/<name>/`, add the `showcase/registry.ts` line (in prototype order, primitives first) and the `src/index.ts` export(s) with public prop types. `check_ui.py` must fail because the component module is missing.
2. GREEN: copy `<Name>.vue`, then conform it to R7: clause IDs with underscores matching the directory, same-line `// clause:` citations, no hex or px in `.pw.ts` assertions, no hex in `<style>`, section per G9. `check_ui.py` is green, and the `check_clauses.py` output has no line for `<NAME>-*`.

- [ ] T007 [US2] Tokens (G2, R-7): replace `UI/src/tokens/tokens.css`, `tokens.md` and `tokens.pw.ts` with the `PROTO` versions in one commit. No existing component file is edited. Gate: `check_ui.py` green (existing presentation specs unchanged); `check_clauses.py` lists no `TOKENS-*` line. If TOKENS-2/3 fail on the light scope, check the `selectorText` quote serialization and fix it in the test only (R-7 watchpoint).
- [ ] T008 [US2] status_pip (G3, R-8): replace `UI/src/components/status_pip/status_pip.md`, `.profiles.ts`, `.spec.ts` and `.pw.ts` with the `PROTO` versions, keep `StatusPip.vue` unchanged, and set `group: 'Fleet'` in the profiles (FR-015). Gate: `check_ui.py` green; no `STATUS_PIP-*` clause line. Ignore a stale `dist-ds/status_pip/all-kinds.html`.
- [ ] T009 [US2] RED — showcase slots (R-9): add `UI/showcase/showcase.md` (`SHOWCASE-1`: a profile's text slots render inside its stage) and `UI/showcase/showcase.pw.ts`, which asserts that `#showcase-button-primary .showcase-stage` contains the text `Run this version` (the prototype's button `primary` profile slot). `// clause: SHOWCASE-1` goes on the same line. Must fail: button is not registered and slots are not rendered.
- [ ] T010 [US2] Port **button** (Primitives; slots) by the port recipe, **plus** the GREEN half of T009: `UI/showcase/Showcase.vue` renders `p.slots` through a `v-for` dynamic-slot `<template #[name]>{{ text }}</template>` inside `<component>`, with text interpolation and never `v-html`; `build-ds-bundle` needs no change. Gate: T009's test and button's own tests are green; no `SHOWCASE-1` or `BUTTON-*` line in `check_clauses.py`.
- [ ] T011 [P] [US2] Port **tag** (Primitives; slots).
- [ ] T012 [P] [US2] Port **surface** (Primitives; slots).
- [ ] T013 [P] [US2] Port **segmented_control** (Primitives).
- [ ] T014 [P] [US2] Port **filter_chip** (Primitives).
- [ ] T015 [P] [US2] Port **field** (Forms).
- [ ] T016 [P] [US2] Port **check_row** (Data).
- [ ] T017 [P] [US2] Port **status_tag** (Status; imports StatusPip — after T008).
- [ ] T018 [P] [US2] Port **stat** (Data; imports StatusPip — after T008).
- [ ] T019 [P] [US2] Port **list_row** (Data; slots).
- [ ] T020 [P] [US2] Port **detail_pane** (Data) with `DetailSection.vue` as a sibling. Export both `DetailPane` and `DetailSection` (plus `DetailField`) from `UI/src/index.ts` (G8).
- [ ] T021 [P] [US2] Port **timeline** (Data; imports StatusPip — after T008; `empty` slot).
- [ ] T022 [P] [US2] Port **tab_bar** (Shell).

  Note: the [P] marks mean the files are independent. Every port edits `registry.ts` and `index.ts`, so parallel ports are merged serially.
- [ ] T023 [US2] Group B close-out: `check_ui.py` green; `check_clauses.py` shows no line for any of the 13 prefixes plus `TOKENS`, `STATUS_PIP`, `SHOWCASE`; `UI/src/index.ts` exports all 13 components (plus `DetailSection`); the registry order matches the prototype's, with existing sets keeping their G9 sections.
- [ ] T024 [US2] PARKED — G2b record import: copy `records/2026-09-23-design-foundations/` into `records/` once the orchestrator supplies the source path (spec Open items). Does not gate anything.

**Checkpoint US2**: group B green; reviewer gate.

---

## Phase 4: US3 — board screen (Group C, P3)

**Goal**: FR-017–FR-024 (incl. 020a/020b/021a/023a), SC-005, SC-006.
**Independent test**: quickstart §4–§5.

### Backend run wire (G4, R-1)

- [ ] T025 [P] [US3] RED:
  - `tests/test_run_state_model.py`: add `project_key` to the shared-field set; `RunState.project_key` defaults to `None`.
  - `tests/test_run_summary_model.py`: `RunSummary.project_key` defaults to `None`, and a payload without the key parses.
  - `tests/test_run_summary_build.py`: `build_run_summary(..., project_key="kroker")` sets it; omitting it gives `None`.
  - `tests/test_run_host.py`: `_snapshot_run_state` returns `project_key` from `_cfg.project_key`.

  Commands (one per call): `pytest tests/test_run_state_model.py`, `pytest tests/test_run_summary_model.py`, `pytest tests/test_run_summary_build.py`, `pytest tests/test_run_host.py`.
- [ ] T026 [US3] Implement `project_key: str | None = None` on `RunState` and `RunSummary` (`src/sdlc/core/models.py`), the `build_run_summary(project_key=…)` kwarg (`src/sdlc/observability/summary.py`), `_retro` passing `cfg.project_key`, and `_snapshot_run_state` setting `self._cfg.project_key if self._cfg else None` (`src/sdlc/workflows/run_host.py`). Update the `_cfg` row in `src/sdlc/workflows/AGENTS.md` (add the `_snapshot_run_state` reader and the `GraphWorkflow.run` writer). Gates: the T025 commands, `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`.

### Frontend run wire (FR-020a, FR-020b)

- [ ] T027 [US3] RED in `FE/api/http.test.ts`: `mapSnapshot` maps `project_key` to `Run.projectKey` for open and closed rows; an absent or null key gives `null`, never `"default"`. `check_ui.py` fails.
- [ ] T028 [US3] Implement:
  - `Run.projectKey: string | null` (required) in `FE/api/types.ts`; the `mapRun`/`mapClosed` mapping; `projectKey: null` in the `startRun` fallback (`http.ts`).
  - the `FE/api/mock/index.ts` runs: one with a board project, one `null`, one whose project 404s, one with an empty board.
  - a hand-edit of `FE/api/__fixtures__/fleet-snapshot.json` to add `project_key` on open and closed rows, both set and absent.
  - export `API_MODE` from `FE/api/client.ts`.
  - add a `'/projects'` proxy in `interfaces/dashboard/frontend/vite.config.ts`.
  - file the dump-script drift as `.workspace/tasks/<date>-dashboard-fixture-dump-drift.md`.

  Gate: `check_ui.py` green.

### Board transport, adapter, store (R-3, R-11, data-model §2–§4)

- [ ] T029 [US3] RED in `FE/features/board/board.api.test.ts` (delete `.gitkeep`):
  - URL building for steps 1–6 (contracts/board-client.md), including `run_id`, `plan` and `subject` encoding.
  - `pickPlanVersion` chooses the newest `id` (not `n`) with a matching `run_id`, else `undefined`.
  - `isNotFound`-based 404 classification per step.
  - `createMockBoardApi` covers every fixture scenario in the contract.
- [ ] T030 [US3] Implement `FE/features/board/board.types.ts`, `board.api.ts` (http, mock and selection via `API_MODE`) and the `__fixtures__/` scenarios. Gate: `check_ui.py` green.
- [ ] T031 [P] [US3] RED in `FE/features/board/board.adapter.test.ts`: `toTaskRow` (label = task id; `pulsing` only for `in_progress`/`blocked`; `diverged`), `toTaskDetail` (fields plus evidence), `toTimeline` (oldest first, nulls as `undefined`), `toVersionRows` (run filter, newest first), and `toCounters` ("this run", zero state).
- [ ] T032 [US3] Implement `FE/features/board/board.adapter.ts` (pure). Gate: `check_ui.py` green.
- [ ] T033 [US3] RED in `FE/features/board/board.store.test.ts`, with `./board.api` mocked:
  - every data-model §4 transition: `no_project`; 404 on step 1 or step 3; a step-2 404 falling back; a step-4 404 skipping a key; a non-404 failure during `loading` retrying; `empty`; `ready`; a poll failure keeping data; a poll-time 404 on step 3.
  - `stop()` clearing the poll and the selection.
  - selection fetching detail and events.
  - the selected task refreshing on a `row_version` change.
- [ ] T034 [US3] Implement `FE/features/board/board.store.ts` (Pinia, `startPoll`; the initial load runs inside the poll loop until its first success). Gate: `check_ui.py` green.

### Tab host and board view (R-4, R-13)

- [ ] T035 [US3] Barrel probe (plan C6): import one ported component from `@kroker/ui` in a dashboard source file and run `check_ui.py`. On `TS2307`, add `"@kroker/ui": ["../../ui/src/index.ts"]` to `interfaces/dashboard/frontend/tsconfig.json` `paths`. Keep the import only if T037 uses it.
- [ ] T036 [US3] RED — `FE/features/run/RunView.tabs.test.ts`, using a string-template probe slot: Graph is the default; `tab: 'board'` renders the probe; Board is disabled without the slot; Gates and Cost are disabled and don't switch; selecting Graph unmounts the probe; an unknown `tab` renders Graph; the slot waits for the run ("loading run…"); "run not found" shows after the fleet's first fetch. The existing `FE/features/run/RunView.test.ts` must stay green unchanged. Must fail: `RunView` has no `tab` prop or TabBar yet.
- [ ] T037 [US3] GREEN — the tab host only, in `FE/features/run/RunView.vue` and `FE/app/router.ts`:
  - `RunView.vue` gets a `tab` prop, `TABS`, the ported `TabBar`, and a typed `#board` slot (`defineSlots`) with slot props `{ runId, projectKey }`.
  - the header (title plus StageDots) sits above the tabs (FR-018 amended); graph content goes in a flex-column Graph panel under `v-if`.
  - on tab select, call `router.replace` when a router is present.
  - the run route still points at `RunView`, but `props: true` becomes the R-4 props function, so `?tab` reaches it. Board stays disabled here because no slot is supplied yet.

  Gate: `check_ui.py` green — `RunView.tabs.test.ts` green, `RunView.test.ts` unchanged and green, app-tier canvas tests green.
- [ ] T038 [US3] RED — `FE/features/board/BoardTab.test.ts` and `FE/app/RunPage.test.ts`, both with `./board.api` / `features/board/board.api` mocked:
  - `BoardTab.test.ts` covers the props `{ runId, projectKey }`; the store starting on mount, stopping on unmount, and restarting on a `projectKey` change; task rows (`ListRow` + `StatusTag`); selection showing `DetailPane` fields, an evidence `DetailSection` and a `Timeline`; version rows; the `Stat` strip labelled "this run"; the `no_project` and `not_found` banners; the empty state; the connection-lost line.
  - `RunPage.test.ts` checks that `RunPage` renders `BoardTab` inside RunView's board panel and enables the Board tab.

  Must fail: `BoardTab.vue` and `RunPage.vue` don't exist yet.
- [ ] T039 [US3] GREEN — the board view and app-layer composition:
  - `FE/features/board/BoardTab.vue` as specified by T038.
  - `FE/app/RunPage.vue` renders only `<RunView>` and fills `#board` with `BoardTab` (R-13).
  - `FE/app/router.ts` switches the run route's component to `RunPage`, keeping the R-4 props function.
  - `interfaces/AGENTS.md`: the screen table's Run row now names `app/RunPage.vue` as the route component.

  Gate: `check_ui.py` green (the T038 tests, the boundary test including its planted `RunView → BoardTab` case, and the app-tier canvas tests).

### App tier

- [ ] T040 [US3] RED, then GREEN in the app tier. Add clauses `CONSOLE-10…` to `UI/app.md` and cite them in `UI/app.pw.ts`, running against the board mock:
  - `?tab=board` opens Board and a copied URL reopens it (SC-005);
  - the task list renders and selection shows detail, evidence and timeline;
  - the counter strip reads "this run";
  - each FR-022 banner and the empty state (SC-006);
  - a transient failure shows "connection lost";
  - after switching back, Graph is unchanged, and `?tab` is cleared;
  - `?tab=cost` and `?tab=nonsense` render Graph.

  Gate: `check_ui.py` green; `check_clauses.py` shows no `CONSOLE-*` line.
---

## Phase 5: Polish & cross-cutting

- [ ] T041 Feature close-out (quickstart.md §1–§4, `.specify/specs/002-frontend-screen-restructure/spec.md` Status line):
  - run quickstart §1–§4 in full: `check_ui.py`, `check_clauses.py`, `check_file_size.py --full`, and the Python gates.
  - confirm `features/board/.gitkeep` is gone.
  - update the spec Status line with the delivered date.
  - leave ARCHITECTURE/ROADMAP untouched until merge (R9).
  - report the final pass counts against the T001 baseline.

---

## Dependencies & execution order

- T001 → Phase 2 (T002 → T003 → T004 → T005 → T006) → Phase 3 → Phase 4. Each phase ends with a reviewer gate.
- Phase 3: T007 → T008 → T009 → T010 → {T011…T022} (T017, T018, T021 need T008 — already satisfied) → T023. T024 is parked.
- Phase 4: T025 → T026; T027 → T028; T029 → T030; T031 → T032; T033 → T034 (needs T030, T032); T035 → T036 → T037 (needs T028); T038 → T039 (needs T034, T037); T040 (needs T039); Phase 5: T041 after T040.
- T025/T026 (backend) may run in parallel with T027–T034 (frontend), but T028's fixtures assume the wire shape T026 lands.

## Parallel opportunities

- Phase 3 ports marked [P] touch disjoint component directories; their shared `registry.ts` and `index.ts` lines merge serially.
- Phase 4: the backend slice (T025–T026) in parallel with the board adapter (T031–T032).

## Implementation strategy

MVP = Phase 2 (US1): a behaviour-neutral restructure, shippable alone. US2 adds the vocabulary. US3 needs both.
