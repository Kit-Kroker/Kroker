# interfaces/ — AGENTS.md

Router only. Deep context lives in each sub-package.

## Tree layout

Two packages:

- **`ui/`** — the `@kroker/ui` design-system package. Presentation components
  that accept display primitives and know nothing of Kroker's domain. Source
  exports only; no `dist/`, no compiled declarations.
- **`dashboard/frontend/`** — the `sdlc-dashboard` npm package. Consumes
  `@kroker/ui`. Organised by screen (`src/app/`, `src/api/`, `src/shared/`,
  `src/features/<screen>/`); each screen's mapping module
  (`<screen>.adapter.ts`) is where `Run`/board wire shapes meet display
  primitives.

## Screen locations (dashboard)

| Screen | Route | Folder | View |
|---|---|---|---|
| Fleet | `/` | `src/features/fleet/` | `FleetView.vue` |
| Decision inbox | `/inbox` | `src/features/inbox/` | `InboxView.vue` |
| Run detail | `/runs/:id` (route component `src/app/RunPage.vue`, composition only) | `src/features/run/` | `RunView.vue` (tab host) |
| Board | tab of `/runs/:id` (`?tab=board`) | `src/features/board/` | `BoardTab.vue` |
| Graphs (editor) | `/graphs` | `src/features/graphs/` | `GraphEditorView.vue` |

The screen-location table mirrors the stage table in the root `AGENTS.md`:
a contributor reads one row and opens one folder. The run page composes
the board in the app layer (R-13): the `/runs/:id` route component is
`app/RunPage.vue` (composition only), which renders `features/run/
RunView.vue` and fills its typed `#board` slot with
`features/board/BoardTab.vue`; `RunView` never imports `features/board/`.

## Layers and import boundaries (dashboard)

Enforced by `src/app/boundaries.test.ts`:

| Layer | Path | May import |
|---|---|---|
| app shell | `app/` | everything + features (router, views) |
| screens | `features/<screen>/` | `app/*.store.ts` only (not `RunPage.vue`, `router.ts`, `App.vue`, `shell/*`), `shared/`, `api/`, `@kroker/ui`, npm — **never another `features/<other>/`** |
| shared | `shared/` | `api/`, `@kroker/ui`, packages — never `features/` or `app/` |
| API | `api/` | `@kroker/ui` types, packages — never `features/` or `app/` |

Naming: stores `<stem>.store.ts`, adapters `<screen>.adapter.ts` (stems
camelCase: `runGraph`, `graphEditor`, `stageStrip`, `graphCanvas`); pure
helpers keep a plain name (`graphEdits.ts`, `status.ts`, `format.ts`);
tests sit beside their module.

Transport: a surface used by one screen keeps its client inside that screen.
`features/board/board.api.ts` holds the board's HTTP and mock clients and
its wire types. It picks between them with `API_MODE` from `api/client.ts`,
the same rule that picks `api`, so the two can't disagree. It reuses
`api/errors.ts` (`isNotFound`) and `api/poll.ts` (`startPoll`). Surfaces that
several screens read go through `DashboardApi` in `api/`.

## The cardinal rule

**`ui/` must never import from `dashboard/`.** If a component's props cannot
be constructed as a literal (with no import from `dashboard/`), a domain type
has leaked into the component and must be removed. The screen mapping modules
(`dashboard/frontend/src/features/<screen>/<screen>.adapter.ts`) and the
shared adapters (`src/shared/*.adapter.ts`) are where the boundary is
maintained.

## Node toolchain

The single entry point for every JavaScript check is:

```
python scripts/check_ui.py
```

Do not invoke `npm`, `npx`, `vitest`, or `playwright` directly in CI or in
`scripts/verify.py`. The wrapper handles install, typecheck, both Vitest
workspaces, and both Playwright tiers — including the Windows detail that
`npm` is `npm.cmd`.

## File-size ceiling

The 1000-line ceiling already covers `interfaces/` via `scripts/check_file_size.py`.
No change to that script is needed; no file in this tree may exceed 1000 lines.

## Component contracts

Each component carries its own clause document at
`ui/src/components/<name>/<name>.md`. Those documents are **not** inlined
here. Read the component directory for its contract.
