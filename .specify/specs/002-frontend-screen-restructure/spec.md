# Feature Specification: Frontend restructure — by-screen features, design-system port, board screen

**Feature Branch**: `002-frontend-screen-restructure` (spec directory; branch is the orchestrator's call)

**Created**: 2026-09-23

**Status**: Approved — GATE 1 cleared 2026-09-23 (user, relayed by the orchestrator). OQ-1…OQ-9 resolved as rulings G1–G9 below; the reasoning and rejected alternatives stay in **Resolved decisions** at the end. One ruling (G2b, record import) is blocked on a source path — see **Open items**.

**Input**: Orchestrator TASK BRIEF (re-send), three ordered parts in one spec: (A) group `interfaces/dashboard/frontend/src` by screen; (B) port the design-system components missing from `interfaces/ui/` out of the prototype copy at `C:/Users/start/Downloads/Pipeline management prototype/kroker-ui/`; (C) add the Agent Board screen as a tab of the run view. Every factual claim in the brief was treated as a hypothesis and checked on main `5899f77` — see **Verified context**.

## Binding rulings

From the brief (not re-opened here):

- **R1 Order.** Task groups run A → B → C. B's components are C's props vocabulary.
- **R2 Tests travel.** In A, every test moves with the code it covers; nothing is rewritten to make a move pass.
- **R3 Green per group.** Both Vitest workspaces and both Playwright tiers are green at the end of each task group.
- **R4 One toolchain entry.** Tasks invoke JavaScript checks only through `python scripts/check_ui.py` — never npm, npx, vitest or playwright directly.
- **R5 The cardinal rule holds.** `ui/` never imports from `dashboard/`; the existing ownership test stays green throughout.
- **R6 No cross-feature imports.** A screen folder never imports another screen folder. Anything two screens need lives in the shared layers (the frontend analogue of the root cross-stage ban).
- **R7 Repo conventions bind** for every ported component: flat `components/<name>/` layout, underscore clause IDs matching the directory, same-line `// clause: NAME-N` citations, no hex values or pixel measurements in Playwright assertions, 1000-line ceiling per file.
- **R8 Gates and cost tabs** are out of scope (confirmed by G7: disabled tabs, no content).
- **R9 Docs describe main.** ARCHITECTURE/ROADMAP change only for landed state; in-flight detail lives in this spec.

User GATE 1 (2026-09-23):

- **G1 (was OQ-1) Shell wrappers = A.** `AppHeader.vue`, `StartRunModal.vue`, `Toasts.vue` move **unchanged** into `app/shell/`, their tests alongside; `components/` is dropped.
- **G2 (was OQ-2) Tokens = A.** The prototype's `tokens.css`, `tokens.md`, `tokens.pw.ts` are adopted wholesale as the **first task of group B** — pass-three names and values, the `[data-theme='light']` scope, and the pass-two deprecated aliases (TOKENS-4). The visible restyle of existing screens is accepted.
  - **G2b** Import `records/2026-09-23-design-foundations/` from the prototype copy into the repo's `records/`. *Blocked:* the directory is not in the prototype copy (see Open items).
- **G3 (was OQ-3) Drift = reconcile status_pip only.** status_pip is reconciled in group B (board needs `in_progress`; under G2 its styles arrive with `tokens.css`, so its clause doc, profiles and tests follow). **app_header and toasts are deferred** to follow-up **FU-1** (Follow-ups, below).
- **G4 (was OQ-4) Board reach = A.** The dashboard run wire gains `project_key` (small backend change in the fleet snapshot); the dev server proxies `/projects`; the board API module calls the existing board routes.
- **G5 (was OQ-5) Board data = recommended on all five points:** (a) task id is the row label, title join is follow-up **FU-2**; (b) a task's events are fetched with the `subject` filter when it is selected; (c) the counter strip is derived client-side from the run's tasks and labelled "this run"; (d) project artifacts come from project detail, versions are fetched per key, and only this run's are kept; (e) task evidence is a detail-pane section.
- **G6 (was OQ-6) Placement = recommended.** `ui` and inbox stores → app shell; catalog and fleet stores, the stage-strip and graph-canvas mappings, and formatting → shared. **Deletion approved:** `constants.ts` + `constants.test.ts` and `adapters/inbox.ts` are deleted.
- **G7 (was OQ-7)** Gates and Cost are **disabled tabs with no content**.
- **G8 (was OQ-8)** `DetailSection` is **exported from the package entry** alongside `DetailPane`.
- **G9 (was OQ-9)** Ported components use the **prototype's sections**; existing components keep theirs; no regrouping.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A contributor finds a screen's code in one place (Priority: P1)

A contributor (human or agent) changing the Fleet, Run, Inbox or Graphs screen opens one folder and finds that screen's view, its domain-to-display mapping, its state, and its tests side by side. They can tell from a single table in the interfaces guide where each screen lives, and a check stops them if they reach into another screen's folder.

**Why this priority**: Parts B and C add roughly fifteen components and a new screen. Landing them into today's type-grouped tree (`views/`, `stores/`, `adapters/`, `components/`) would spread the board across five folders. The restructure is the ground the other two parts stand on, and it is behaviour-neutral, so it is safe to land first.

**Independent Test**: Run the full UI check after group A. Every existing test passes from its new location; the app's four routes render exactly as before; the screen-location table names a folder for each route; and an intentional cross-screen import is rejected.

**Acceptance Scenarios**:

1. **Given** the restructured tree, **When** a contributor looks up "Run detail" in the interfaces guide, **Then** the table names exactly one folder, and that folder contains the run view, its state, its mapping and its tests.
2. **Given** the restructured tree, **When** the full UI check runs, **Then** the number of passing dashboard tests is at least the pre-restructure count and no test was deleted to get there.
3. **Given** a file in one screen folder that imports from another screen folder, **When** the dashboard tests run, **Then** a boundary test fails and names the offending file.
4. **Given** the design-system package, **When** the ownership test runs from its new location, **Then** it still scans the whole `ui/` source tree and still passes.

---

### User Story 2 — A designer sees every board building block in the showcase (Priority: P2)

A designer or contributor opens the design-system showcase and finds the thirteen new building blocks (button, segmented control, surface, status tag, tag, filter chip, field, list row, detail pane, timeline, check row, stat, tab bar) under their sections, each with named example profiles, each with a clause document describing its contract, and each covered by logic and presentation tests that cite those clauses.

**Why this priority**: The board screen is composed from these pieces. Porting them as documented, tested, showcased components first means Part C only maps data to props.

**Independent Test**: Run the full UI check after group B. Each ported component renders every profile in the showcase; the clause checker reports every clause covered; the component is importable from the package entry.

**Acceptance Scenarios**:

1. **Given** the showcase, **When** it is opened, **Then** each ported component appears under its section with one article per profile, each article carrying the agreed showcase id.
2. **Given** a ported component's clause document, **When** the clause checker runs, **Then** every clause heading is matched by at least one same-line citation in that component's tests.
3. **Given** the dashboard, **When** it imports a ported component from the package entry, **Then** the import resolves without reaching into `dashboard/` from `ui/`.
4. **Given** the existing screens, **When** the ported components and any token changes land, **Then** every pre-existing presentation test still passes (the G2 restyle changes token values, not structure).

---

### User Story 3 — An operator watches a run's task board from the run page (Priority: P3)

An operator on a run's page switches from the graph to a Board tab and sees the run's tasks with their status, fix attempts and errors; selects a task to see its detail and history; sees the artifact versions the run produced; and sees a small counter strip summarising the board. Gates and Cost appear as the remaining tabs, disabled (G7).

**Why this priority**: The value the first two parts unlock. It depends on both and on the board-data rulings (G4, G5).

**Independent Test**: With the mock API, open a run, switch to Board, and verify tasks, selection detail, timeline, versions and counters render from fixture data; switch back to Graph and verify the graph view is unchanged.

**Acceptance Scenarios**:

1. **Given** a run whose project has a current plan, **When** the operator opens the Board tab, **Then** one row per task of that run is listed with its status mark, fix-attempt count and error indicator.
2. **Given** the task list, **When** the operator selects a task, **Then** a detail pane shows the task's fields and a timeline of its board events, newest last.
3. **Given** the Board tab, **When** it loads, **Then** a counter strip shows task counts by status, total fix attempts, tasks with errors and diverged tasks, derived from this run's tasks and labelled "this run" (G5c).
4. **Given** a run whose project has no board data, or a server without the board surface, **When** the Board tab opens, **Then** a plain banner explains the absence; nothing throws; the Graph tab still works.
5. **Given** the Board tab is open, **When** the operator switches back to Graph, **Then** the graph, gate decisions and pending-inbox links behave exactly as before the tab host existed.

### Edge Cases

- **Ownership test depth.** The `ui/`-never-imports-`dashboard/` test resolves the `ui/` tree by a relative path from its own file (`adapters/fleet.test.ts`). Moving it one directory deeper silently changes what it scans; the move must keep it scanning the same tree, and a missing tree must fail the test, not pass it vacuously.
- **Shared mapping used by two screens.** Run detail uses the fleet mapping's stage-strip function and the graph mapping's canvas function; the graph editor's state uses the graph mapping's key helpers. These cannot stay in either screen folder (R6).
- **Dead modules.** `constants.ts` is imported only by its own test; `adapters/inbox.ts` has no importer; `budgetPct`/`budgetColor` are used only in tests. G6: `constants.ts` + its test and `adapters/inbox.ts` are deleted; `budgetPct`/`budgetColor` move with the formatting module unchanged.
- **Token dependency of ported components.** All thirteen ported components reference token names that do not exist on main (see Verified context). Porting a component before its tokens exist renders it with unresolved properties — invisible failures that structural tests do not catch.
- **Status kinds the pip cannot draw.** The board's task statuses include `in_progress`; main's status pip has no style for it, so a board row would render an empty mark.
- **Board keyed by project, run page keyed by run.** The board surface answers per project and per plan version; the run page knows only the run id and repo.
- **Board surface not proxied in development.** The dev server proxies only `/api`; the board serves at `/projects/*` on the same backend.
- **Board unavailable.** No project, no current plan (the board answers 404), or the board store missing — the tab degrades to a banner.
- **Large event histories.** Project-wide board events are unbounded by run; a timeline must not render the whole project's history for one task.
- **Retained graph-view banners.** Run detail's existing banners (error, capability off, state unavailable, no graph, connection lost) must keep their test ids and wording inside the Graph tab.
- **Empty but reachable board.** The board answers normally but has zero tasks for this run (a new plan, or no board writes yet). The tab shows an explicit empty state with a zeroed counter strip — not a banner, not an exception. *(Added 2026-09-23, spec-review finding 3.)*

## Requirements *(mandatory)*

### Functional Requirements

**Group A — by-screen structure (behaviour-neutral)**

- **FR-001**: The dashboard source MUST be organised as: an application shell layer (app entry, root component, router, theme wiring, shell-level state); the shared API layer (client, HTTP and graph transports, polling, errors, wire types, mock API, fixtures) unchanged in content; a shared layer for code used by two or more screens; and one folder per screen — fleet, run, board (created empty-ready in A, filled in C), inbox, graphs.
- **FR-002**: Each screen folder MUST hold that screen's view, its screen-local components, its mapping module (named `<screen>.adapter.ts`, formerly `adapters/<screen>.ts`), its state module(s) (named `<name>.store.ts`, formerly `stores/<name>.ts`), and the tests covering them.
- **FR-003**: The mapping MUST follow the verified import graph, not the brief's sketch. Specifically: the graph editor view, its inspector, the schema-coverage test and the editor/edit-history state go to `graphs`; the fleet table wrapper and the per-row mapping go to `fleet`; run detail and its run-graph state go to `run`; the inbox view goes to `inbox`; and every module imported by two or more screens (catalog state, fleet state, the stage-strip mapping, the graph canvas mapping, money formatting) goes to the shared layer; the run-status meta (`statusMetaOf`) is fleet-local because only the fleet row mapping uses it. *(Corrected at plan 2026-09-23: the draft listed "status" as shared; the verified import graph makes it fleet-local.)* Per G6: the `ui` store (toasts, start-run form) and the inbox store (used only by the shell for the header count and polling) go to the app shell.
- **FR-004**: No file in one screen folder MAY import from another screen folder. A dashboard test MUST enforce this by scanning the screen folders and failing with the offending path.
- **FR-005**: The existing ownership test (R5) MUST continue to scan the whole design-system source tree after it moves, and MUST fail if that tree is not found.
- **FR-006**: The three shell wrappers (`components/AppHeader.vue`, `StartRunModal.vue`, `Toasts.vue`) MUST move unchanged into `app/shell/` with their tests (G1); `components/` MUST NOT exist after group A.
- **FR-007**: Every route (`/`, `/inbox`, `/runs/:id`, `/graphs`) MUST render the same DOM test ids and behaviour after A as before; no test assertion is edited except import paths and the ownership test's scan-root resolution.
- **FR-007a**: `constants.ts`, `constants.test.ts` and `adapters/inbox.ts` MUST be deleted (G6); no other module is deleted in group A.
- **FR-008**: `interfaces/AGENTS.md` MUST gain a screen-location table (screen → route → folder → view file), mirroring the stage table in the root `AGENTS.md`, and its references to `src/adapters/` MUST be updated to the new layout.

**Group B — design-system port**

- **FR-009**: The prototype's `tokens.css`, `tokens.md` and `tokens.pw.ts` MUST be adopted wholesale as the first task of group B, before any dependent component (G2): pass-three names and values, the light scope, and the pass-two deprecated aliases (TOKENS-4) so no existing component has to change in the same task. Every token name a ported component references MUST resolve in both the dark default and the light scope. Existing components' presentation tests MUST stay green.
- **FR-009a**: `records/2026-09-23-design-foundations/` MUST be imported into `records/` (G2b) — blocked on a source path (Open items); the plan carries it as a parked task that does not gate group B.
- **FR-010**: The thirteen components absent from main MUST be ported: button, check_row, detail_pane, field, filter_chip, list_row, segmented_control, stat, status_tag, surface, tab_bar, tag, timeline. Each lands as `components/<name>/` with the component file(s), `<name>.md`, `<name>.profiles.ts`, `<name>.spec.ts`, `<name>.pw.ts`.
- **FR-011**: `detail_pane` MUST ship `DetailSection` as a sibling file in the same directory; and it MUST be exported from the package entry alongside `DetailPane` (G8).
- **FR-012**: Each ported component's clause IDs MUST use the directory name in upper case with underscores (`LIST_ROW-1`, `TAB_BAR-2`), and every clause MUST be cited on the same line as a covering test; the clause checker MUST pass.
- **FR-013**: No ported Playwright file MAY assert a hex colour or a pixel measurement; the existing token check that forbids hex in component stylesheets MUST pass for every ported component.
- **FR-014**: Each ported component's profile set MUST be registered in the showcase registry (`showcase/registry.ts` — not `src/profile.ts`, which only defines the descriptor types), with the prototype's section for it (Primitives, Forms, Status, Data, Shell, Feedback; primitives registered first; existing components keep their sections — G9), and each ported component (and its public prop types) MUST be exported from the package entry `src/index.ts`.
- **FR-015**: The three drifted components (app_header, status_pip, toasts) are handled per G3: status_pip is reconciled in group B (its clause doc, profiles, logic and presentation specs follow the pass-three styles that arrive with `tokens.css`); app_header and toasts are NOT changed (follow-up FU-1). The status pip MUST be able to draw every board task status (`pending`, `in_progress`, `done`, `failed`, `blocked`, `quarantined`) before group C renders one. status_pip keeps its current showcase section `Fleet` even though its profiles file is replaced (G9: no regrouping; the prototype's `group: 'Status'` is not carried over). *(Added 2026-09-23, spec-review finding 1.)*
- **FR-016**: The design-system bundle step (`ds:bundle`) and its spec MUST stay green with the new components included.

**Group C — board screen**

- **FR-017**: Run detail MUST become a tab host using the ported tab bar, with tabs Graph, Board, Gates, Cost; Gates and Cost are disabled tabs with no content (G7). The active tab MUST be reflected in the URL so a board link is shareable, and Graph MUST be the default.
- **FR-018**: The run title and stage strip MUST stay in the run page header above the tab bar, visible on every tab; the graph-specific content ("open copy in editor", the banners, the graph canvas with gate decisions and pending links) MUST move into the Graph tab unchanged. Every existing test id is kept. *(Amended at plan 2026-09-23, advisor D3: moving the title into the Graph tab would leave the Board tab without a run title.)*
- **FR-019**: The board screen folder MUST contain the Board tab view, a board mapping module (board tasks, artifact versions, board events, board stats → list-row, detail-pane, timeline and stat props), a board state module, and a board API module; the mapping MUST be pure and unit-tested without a DOM.
- **FR-020**: The board API module MUST call the existing board routes (`/projects/{project}/...`) using the run's `project_key` from the run wire (G4), and MUST have a mock counterpart with fixtures so the tab renders under the mock API.
- **FR-020a**: The dashboard run wire (fleet snapshot run summary and single-run read) MUST carry the run's `project_key` (G4); the frontend `Run` type, HTTP mapping, mock API and recorded fixtures MUST carry it too. A run whose project key is unavailable MUST map to an explicit absent value (the Board tab then shows its banner), never to `"default"` by guess.
- **FR-020b**: The dashboard dev server MUST proxy `/projects` to the backend as it proxies `/api` (G4); production is already one origin.
- **FR-021**: The Board tab MUST show: a task list (one row per task of the run, filtered by `run_id`, labelled by task id — G5a), a detail pane for the selected task with its fields, an evidence section (G5e) and a timeline of that task's events fetched with the `subject=task:<plan_version>:<id>` filter on selection (G5b), the run's artifact versions (project artifacts from project detail, versions per key, kept where `run_id` is this run — G5d), and a counter strip derived client-side from the run's tasks and labelled "this run" (G5c).
- **FR-021a**: Board tasks MUST be read from the plan version this run published — the newest `plan` artifact version whose `run_id` is this run, passed as `plan=<version id>` — falling back to the project's current plan only when the run published none. A project re-planned after this run MUST NOT show this run a false empty board. *(Added at plan 2026-09-23, advisor D8.3.)*
- **FR-022**: The Board tab MUST degrade to a banner — never an exception — when the project is unknown, has no current plan, or the board surface is unavailable; the other tabs MUST keep working.
- **FR-023**: The board state MUST stop any polling it started when the tab or run page is left, matching the run-graph state's start/stop discipline.
- **FR-023a**: A transient board fetch failure while the tab is open MUST show a non-blocking "connection lost — retrying" state and retry, and MUST NOT evict data already rendered — mirroring the run-graph state's connection-lost discipline. Only the FR-022 conditions produce the permanent banner. *(Added 2026-09-23, spec-review finding 2.)*
- **FR-024**: The Board tab MUST NOT write to the board (the board's claim/transition routes are agent routes); it is read-only.

**Cross-cutting**

- **FR-025**: Every file touched or created MUST stay under the 1000-line ceiling.
- **FR-026**: Every task in the eventual plan MUST verify through `python scripts/check_ui.py` only (R4); the G4 backend change verifies through the repo's Python gates (fast-tier pytest, ruff, mypy, file size).

### Key Entities

- **Screen folder**: one per routed screen (fleet, run, board, inbox, graphs); owns view, local components, mapping, state, tests; imports only the shell, shared and API layers and the design-system package.
- **Shared layer**: modules needed by two or more screens — cross-screen state (catalog, fleet), cross-screen mappings (stage strip, graph canvas), formatting.
- **Design-system component**: a presentation component taking display primitives only; ships a clause document, profile set, logic spec and presentation spec.
- **Board task** (backend `BoardTask`): project, plan version, task id, run id, live status, authoritative status, fix attempts, error, branch, updated-at. Has **no title or description** field.
- **Artifact version** (`ArtifactVersion`): project, artifact key, version number, run id, content URI, supersedes, created-at.
- **Board event** (`BoardEvent`): project, subject (`artifact:<key>` or `task:<plan_version>:<id>`), actor (`workflow:<run_id>` or `agent:<name>`), authority, from/to status, time, detail.
- **Board stats** (`BoardStats`): per project — tasks by authoritative status, total fix attempts, tasks with error, diverged tasks, event count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every routed screen, a contributor can locate all of its code by reading one table row and opening one folder (5 of 5 screens).
- **SC-002**: After each task group, the full UI check passes with zero failing and zero skipped-by-this-change tests; the dashboard test count after group A is ≥ the count before it.
- **SC-003**: Zero cross-screen imports and zero `ui/`→`dashboard/` imports, each enforced by an automated test that fails on a planted violation.
- **SC-004**: 13 of 13 ported components appear in the showcase with at least one profile each, and the clause checker reports 100% of their clauses cited.
- **SC-005**: An operator reaches a run's board from its page in one interaction (one tab selection), and a copied board URL reopens on the Board tab.
- **SC-006**: Every board-unavailable condition listed in the edge cases produces a visible explanation rather than an empty or broken tab (verified by one test per condition). The empty-but-reachable board (zero tasks for this run) is one more such condition and shows an explicit empty state. *(Added 2026-09-23, spec-review finding 3.)*
- **SC-007**: No new file exceeds 1000 lines.

## Assumptions

- The four existing routes and their paths stay as they are; the board is a tab of `/runs/:id`, not a new top-level route.
- The restructure is a move, not a refactor: no behaviour, wording or styling changes in group A.
- The prototype copy is the source for component code, clause documents, profiles and tests, but repo conventions win wherever they conflict (R7); the prototype's own README records that it was written without running Node, so every ported test is re-verified here.
- The prototype's FR references (E-89 block, FR-1400/FR-1404) are carried as-is in the ported clause documents unless GATE 1 asks for renumbering.
- The HTTP transport is the default; `VITE_API=mock` selects the mock API, and the app Playwright tier builds with it. The board transport follows the same selection. Board fixtures are hand-authored from the backend models until a recorder exists. *(Corrected at plan 2026-09-23, advisor D2: the draft said mock was the default.)*
- Localhost binding remains the backend's containment; the board tab adds no auth and no writes.
- Keyboard and accessibility behaviour of the tab bar, list rows and detail pane is what the ported components provide (their clause documents); this feature sets no additional accessibility requirements beyond keeping those clauses green. *(Added 2026-09-23, spec-review finding 4.)*

## Verified context (hypotheses from the brief, checked on main `5899f77`)

| Brief hypothesis | Verdict | Evidence |
|---|---|---|
| Target shape app/ api/ shared/ features/<screen> with fleet, run, board, inbox, graphs | Holds, with corrections below | `src/` today: `views/` (Fleet, Run, Inbox, GraphEditor), `stores/`, `adapters/`, `components/`, `composables/`, `api/`, `styles/` |
| `shared/` = composables used by 2+ screens (format, status) | **Partly false** | `status.ts` and `stageState.ts` are used only by `adapters/fleet.ts`; `money` (format) is used only by the shell's AppHeader wrapper. But the **stage-strip mapping** (`toStageDots`, fleet + run), the **graph mapping** (`toCanvas`, run + graphs; key helpers used by the graphs state), the **catalog store** (shell, fleet, run, graphs) and the **fleet store** (shell, fleet, run) are all cross-screen — the shared layer must hold state and mappings, not just composables (→ G6) |
| `stores/ui.ts`, `constants.ts` need an owner | Confirmed; plus two more | `ui.ts` (toasts + start-run form) is used by the shell wrappers and `runGraph` store. `constants.ts` is imported only by `constants.test.ts` (dead). `adapters/inbox.ts` has no importer (dead). `budgetPct`/`budgetColor` are test-only |
| `components/` AppHeader, StartRunModal, Toasts are duplicates of `@kroker/ui` | **False** | Each imports its `@kroker/ui` namesake and binds shell stores to it (e.g. AppHeader wraps `@kroker/ui/components/app_header/AppHeader.vue` with fleet/inbox/ui stores and `money`). They are store-binding shells, not copies; deleting them would remove the bindings (→ G1). Each has its own test |
| FleetTable and GraphInspector live in their feature folders | Holds | `components/fleet/FleetTable.vue` (wrapper binding fleet + catalog stores), `components/graph/GraphInspector.vue` (+ `schemaCoverage.test.ts`) |
| Grep test for ui-never-imports-dashboard exists | Holds, location matters | It is a case inside `adapters/fleet.test.ts`, resolving `ui/src` by relative path from its own directory (FR-005) |
| Prototype has no `profile.ts`; wire into `src/profile.ts` | **Half false** | Prototype indeed lacks `src/profile.ts`. On main, `src/profile.ts` only defines `Profile`/`ProfileSet`/`defineProfiles`/`profileId`; registration happens in `showcase/registry.ts` (FR-014) |
| Showcase groups Primitives/Forms/Status/Data/Shell/Feedback/Graph | **Differs** | Main uses Fleet, Modals, Graph, Shell, Feedback. Prototype new components use Primitives(5), Data(5), Status(2), Forms(1), Shell, Feedback (→ G9) |
| `src/index.ts` exports | Thin today | Exports only `profile`, StatusPip, StageDots; the dashboard deep-imports component paths. The prototype `index.ts` exports all new components and **exports DetailSection publicly** (→ G8) |
| Prototype `tokens.css` may differ | **Differs fundamentally** | Main = "pass two" (37 lines, gold accent, 7 status colours). Prototype = "pass three" (67 lines): new names (`--ground-shell/canvas/raised`, `--ink-inverse`, `--status-waiting/idle`, five `--status-*-tint`, `--shadow-overlay`, `--backdrop`, `--text-xs…xl`, `--space-1…5`, `--radius-sm/md/lg`), new values, a `[data-theme='light']` scope, pass-two names kept as deprecated aliases (TOKENS-4), and new status-pip class rules (`in_progress`, `waiting`, `idle`; hollow pending/quarantined). **All 13 ported components reference pass-three-only names.** Its source record `records/2026-09-23-design-foundations/` is absent from the repo (→ G2) |
| app_header / status_pip / toasts drift | **Confirmed, heavily** | app_header: 231 differing lines in the .vue (Kroker wordmark, sentence-case tabs "Runs/Inbox/Pipelines", Button for Start run, theme toggle) + new `app_header.theme.spec.ts`. status_pip: prototype has **no .vue** (styles moved to tokens.css), .md/.profiles/.pw/.spec all differ. toasts: 91 differing lines (inverse-ink, centred, colour as leading mark) + new `toasts.mark.spec.ts` (→ G3) |
| Timeline / Stat props vocabulary | Confirmed, with coupling | `Timeline` and `Stat` render `StatusPip` internally with a status-kind string — they inherit the status-pip reconcile (FR-015) |
| RunView structure | Single-screen view, no tabs | Header (title, StageDots, open-copy link), five banners, GraphCanvas with GateDecision / pending-inbox slots; starts/stops the run-graph store and a 1 s clock |
| Board API exposes tasks / versions / events | Holds, keyed by **project**, not run | `sdlc/board/api.py`: `GET /projects`, `/projects/{p}`, `/projects/{p}/artifacts/{key}` (versions), `…/versions/{id}/markdown`, `/projects/{p}/tasks?status&run_id&plan`, `/projects/{p}/tasks/{id}` (task + evidence), `/projects/{p}/events?since&subject`, `/projects/{p}/stats`; writes: claim + status patch (agent routes). Served by the same process as `/api` but at root `/projects/*` (`interfaces/dashboard/api/main.py`) |
| Dashboard api/ layer has board types | **False** | No board types, routes or mock in `frontend/src/api/`. The dev proxy forwards only `/api` (`vite.config.ts`) |
| Run → board project | **Gap** | Board rows carry `project` = `PipelineConfig.project_key` (default `"default"`); the dashboard `Run` wire carries `repo` but no project key (→ G4) |

## Resolved decisions (user-gated 2026-09-23)

The questions as put to GATE 1, kept verbatim for traceability; each line opens with its ruling.

- **[G1 → A] OQ-1 — The three shell wrappers are bindings, not duplicates.** `components/AppHeader.vue`, `StartRunModal.vue`, `Toasts.vue` bind shell stores to their `@kroker/ui` namesakes. **Recommended: (A)** move them into the app-shell layer unchanged (e.g. `app/shell/`), tests alongside, and drop `components/`. (B) Inline all three bindings into the root component and fold their three tests into the root component's test. (C) Delete as the brief says and bind in each consumer — rejected unless chosen: only the root component consumes them.
- **[G2 → A, plus record import (G2b)] OQ-2 — Token pass three.** Every ported component needs pass-three token names. **Recommended: (A)** adopt the prototype's `tokens.css`/`tokens.md`/`tokens.pw.ts` wholesale as the first task of group B (new names, new values, light scope, pass-two aliases per TOKENS-4). This is a **visible restyle of all existing screens** (gold accent removed; "blocked" shares the waiting colour; quarantined becomes a red ring) with no structural test change expected. (B) Additive only: add pass-three names mapped onto pass-two values (no visual change; the tint values are still new; the prototype look is deferred to a follow-up restyle). (C) As A but without the light scope. Also: the prototype's value source `records/2026-09-23-design-foundations/` is not in the repo — import it into `records/`, or cite the prototype copy?
- **[G3 → recommended] OQ-3 — Drifted app_header / status_pip / toasts.** **Recommended:** reconcile **status_pip** in group B (required: board task statuses, and under OQ-2 A its styles already arrive with tokens.css — the component doc, profiles and tests must follow); **defer app_header and toasts** to a named follow-up (they are product-visible changes — wordmark, tab labels "Runs/Inbox/Pipelines", theme toggle, toast placement — not needed by the board). Alternative: reconcile all three now, including updating main's `app_header.spec.ts`/`.pw.ts` that assert the old wordmark/labels, and wiring the theme toggle through the `ui` store.
- **[G4 → A] OQ-4 — How the Board tab reaches the run's board.** The board is keyed by project; the run wire has no project key; the SPA's dev proxy forwards only `/api`. **Recommended: (A)** add the run's `project_key` to the dashboard run wire (small backend change in the fleet snapshot) and proxy `/projects` in dev; the board API module calls the existing board routes. (B) Add one run-scoped dashboard route under `/api` that composes the board store for a run (one origin, one request, more backend work). (C) Frontend-only: assume project `default` — rejected unless chosen: silently wrong for any non-default project.
- **[G5 → recommended on (a)–(e)] OQ-5 — Board data gaps vs. the mapping's needs.** (a) `BoardTask` has no title — **recommended:** show the task id as the row label; a title join from the plan artifact is a follow-up. (b) Tasks filter by `run_id`, but **events** cannot (actor `workflow:<run_id>` identifies workflow writes only; agent writes are `agent:<name>`) — **recommended:** fetch a task's events with the existing `subject=task:<plan_version>:<id>` filter when it is selected, rather than the project's whole history. (c) **Stats** are project-wide — **recommended:** derive the counter strip client-side from the run's task list (counts by status, fix attempts, errors, diverged) and label it "this run"; project stats are not shown. (d) **Artifact versions** are listed per artifact key only — **recommended:** list the project's artifacts from the project detail, fetch versions per key, and keep versions whose `run_id` is this run. (e) Task evidence (qa/review/deep_review) is available from task detail — **recommended:** show it in the detail pane as a section.
- **[G6 → recommended, deletion approved] OQ-6 — Placement of shared state, shared mappings and dead code.** **Recommended:** shell-only state (`ui` store: toasts, start-run form) → app shell; cross-screen state (catalog, fleet) and cross-screen mappings (stage strip incl. status meta and stage states; graph canvas incl. key helpers) → shared layer, as `*.store.ts` / `*.adapter.ts`; formatting → shared. The inbox store is used only by the shell (header count and polling) → app shell. **Dead code:** delete `constants.ts` + its test and `adapters/inbox.ts` (no importer; the inbox screen is a placeholder today) — or keep them, moved, if GATE 1 prefers zero deletions in a move-only group.
- **[G7 → recommended] OQ-7 — Gates and Cost tabs.** **Recommended:** present them in the tab bar as disabled tabs (the ported tab bar supports a disabled item) so the run page's structure is final; no content, no data. Alternatives: omit them until built; or bring one in scope (Gates could list the run's pending gate decisions already served by the run-graph state).
- **[G8 → recommended] OQ-8 — `DetailSection` exposure.** The brief says private sibling; the prototype exports it from the package entry. The board detail pane needs sections (fields, evidence, timeline). **Recommended:** export it from the package entry alongside `DetailPane` (the dashboard may not deep-import a "private" file under R5's spirit). Alternative: keep it private and give `DetailPane` a sections prop.
- **[G9 → recommended] OQ-9 — Showcase sections.** **Recommended:** ported components use the prototype's sections (Primitives, Forms, Status, Data, Shell, Feedback), registered primitives first; existing components keep their current sections (Fleet, Modals, Graph, Shell, Feedback) — no regrouping churn. Alternative: regroup existing components into the new taxonomy in the same group.

## Follow-ups (named, out of scope)

- **FU-1 — app_header and toasts pass-three reconcile (G3).** Port the prototype's app_header (Kroker wordmark, sentence-case tabs "Runs / Inbox / Pipelines", Button for Start run, theme toggle — APP_HEADER-3 in `app_header.theme.spec.ts`) and toasts (inverse-ink, centred, colour as a leading mark — TOASTS-2/3 in `toasts.mark.spec.ts`). Must update main's `app_header.spec.ts`/`.pw.ts` where they assert the old wordmark or uppercase labels, and wire `document.documentElement.dataset.theme` from the `ui` store (the light scope from G2 is inert until then).
- **FU-2 — Board task titles (G5a).** Join task titles from the plan artifact (or add a title to `BoardTask`) so board rows stop showing bare task ids.
- **FU-3 — Remove the pass-two alias block (TOKENS-4)** one release after G2, once every component reads pass-three names (prototype README, "Apply" step 6).

## Open items

- **G2b source missing.** `records/2026-09-23-design-foundations/` is not in the prototype copy (`C:/Users/start/Downloads/Pipeline management prototype/` holds only `kroker-ui/interfaces/ui/` and a README), and a search of Downloads, the user profile and `D:/own` (depth 6) finds no directory of that name. The orchestrator/user must supply its location; until then the import task is parked, and the prototype README is cited as the values' provenance. It does not gate group B (the token files are self-contained).
