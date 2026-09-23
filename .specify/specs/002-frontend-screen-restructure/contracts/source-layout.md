# Contract: dashboard source layout and import boundaries

**Scope**: `interfaces/dashboard/frontend/src/`. Enforced by `src/app/boundaries.test.ts` (R-5). The screen-location table in `interfaces/AGENTS.md` (FR-008) is the human-facing copy of this contract.

## Layers

| Layer | Path | Holds | May import |
|---|---|---|---|
| app shell | `app/` | `main.ts`, `App.vue`, `router.ts`, `RunPage.vue`, `theme.css`, `ui.store.ts`, `inbox.store.ts`, `shell/` (AppHeader, StartRunModal, Toasts bindings), `boundaries.test.ts` | everything below + features (router, views) |
| screens | `features/<screen>/` | view, screen-local components, `<name>.adapter.ts`, `<name>.store.ts`, screen-local helpers, tests | `app/*.store.ts` only (not `RunPage.vue`, `router.ts`, `App.vue`, `shell/*`), `shared/`, `api/`, `@kroker/ui`, npm packages — **never another `features/<other>/`** |
| shared | `shared/` | code used by ≥ 2 screens: `catalog.store.ts`, `fleet.store.ts`, `stageStrip.adapter.ts`, `stageState.ts`, `graphCanvas.adapter.ts`, `format.ts` | `api/`, `@kroker/ui`, packages — **never `features/` or `app/`** |
| API | `api/` | client, transports, polling, errors, wire types, mock, fixtures (unchanged) | `@kroker/ui` types, packages — **never `features/` or `app/`** |

## Screen table (content of the FR-008 table)

| Screen | Route | Folder | View |
|---|---|---|---|
| Fleet | `/` | `features/fleet/` | `FleetView.vue` |
| Decision inbox | `/inbox` | `features/inbox/` | `InboxView.vue` |
| Run detail | `/runs/:id` (route component `app/RunPage.vue`, composition only) | `features/run/` | `RunView.vue` (tab host) |
| Board | tab of `/runs/:id` (`?tab=board`) | `features/board/` | `BoardTab.vue` (slotted into `RunView` by `app/RunPage.vue`) |
| Graphs (editor) | `/graphs` | `features/graphs/` | `GraphEditorView.vue` |

The run page composes the board **in the app layer** (R-13): the `/runs/:id` route component is `app/RunPage.vue` (composition only), which renders `features/run/RunView.vue` and fills its typed `#board` slot with `features/board/BoardTab.vue`. `RunView` never imports `features/board/`. There are **no exceptions** to the cross-screen rule.

## Naming

- Stores `<stem>.store.ts`, adapters `<stem>.adapter.ts`, stems camelCase as today (`runGraph`, `graphEditor`, `stageStrip`, `graphCanvas`).
- Pure helper modules keep a plain name (`graphEdits.ts`, `status.ts`, `format.ts`).
- Tests sit beside their module: `<module>.test.ts`.

## Boundary checks (all in `app/boundaries.test.ts`)

1. **Ownership (verbatim)**: no file in `interfaces/ui/src` contains `from '../../dashboard` or `api/types`; scan root must exist and hold > 0 files.
2. **Ownership (resolver)**: no relative import in `interfaces/ui/src` resolves under `interfaces/dashboard/`.
3. **Cross-screen**: no relative specifier (static, side-effect, dynamic, `vi.mock`, `import.meta.glob`) in `features/<x>/` resolves into `features/<y>/` — no exceptions (the self-tests plant `features/run/RunView.vue → features/board/BoardTab.vue` and expect it reported).
4. **Layering**: nothing in `shared/` or `api/` resolves into `features/` or `app/`; nothing in `features/` resolves into an `app/` module other than `app/*.store.ts`.
5. **Normalization**: all paths are compared with `/` separators (Windows `path.resolve` yields `\`).
6. **Scanner self-test**: the exported `violations()` function flags an in-memory planted violation for each rule.
