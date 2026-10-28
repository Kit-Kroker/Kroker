# Tasks: Dashboard rework to the Pipeline Canvas v5 design

**Input**: `.specify/specs/018-canvas-v5-ui/`:
- `spec.md` (GATE 1 plus v5-only ruling S1–S16);
- `plan.md` (reviewer approved, `.workspace/tmp/reviewer-018-plan-2.md`);
- `research.md` (R-1 to R-16);
- `data-model.md`;
- `contracts/clauses.md`, `contracts/read-routes.md`;
- `quickstart.md`.

**Tests**: required (FR-071, FR-072, FR-062, SC-002, SC-005). Each change is preceded by its RED task. A test marked PIN pins existing behaviour and must pass on first run; a red PIN is a stop-guard.

**Order**: phases follow the plan's slices (research R-1), not story priority. The shell must exist before any screen.

| Phase | Slice | Story |
|---|---|---|
| 1 | 0 | setup |
| 2 | 1 | foundational shell |
| 3 | 1 | US8 |
| 4 | 2 | US1 |
| 5 | 3 | US2 |
| 6 | 4 | US3 |
| 7 | 5 | US4 |
| 8 | 6 | US5 |
| 9 | 7 | US6 |
| 10 | 8 | US7 |
| 11 | 9 | close-out |

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. `D/` = `src/sdlc/dashboard/`. "Names" = `data-model.md`. "Clauses" = `contracts/clauses.md`. "Routes" = `contracts/read-routes.md`.

## Standing rules for every task

- **Names.** `data-model.md` §2–§5 is the only source of new names. Existing names are copied from the files data-model §1 cites. If a needed name is in neither, stop (SG-1). Every phase starts with the data-model §6 name check.
- **v5 only.** Build only what spec S1–S16 and the requirements they rewrite describe. A visible element that the v5 extract (`docs/reports/Pipeline Canvas v5 (standalone).html`) does not draw and no contract forces is a stop (SG-8). Colours, sizes and fonts come from tokens. Layout follows the v5 extract; values never come from its inline literals.
- **Convergence.** A task is not done while `vue-tsc`, Vitest or Playwright is red.
  - JS checks run only through `python scripts/check_ui.py`.
  - Python: `pytest <files>` for the named tests; the full fast tier at each checkpoint.
  - One test run per shell call, never two chained. `addopts` already has `-q`.
- **RED tasks** are written by the qa seat and seen failing for the stated reason before the paired task starts. They are committed in the paired task's commit, so no commit on the branch is red. The reviewer gate applies to each RED diff on its own.
- **Commits**: subject and body only. **No attribution trailers of any kind.** Use `git commit -F <msgfile>`, one path per `git add` argument, and no heredocs. Write every file with the Write tool.
- **Reviewer gate** per task, blocking.
- **Read first**: root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`, `interfaces/ui/src/tokens/tokens.md`.
- **Forbidden paths**:
  - `src/sdlc/{benchmarks,stages,workflows,harness,core,graph,agents,board}/` (read-only imports are allowed). This list is deliberately stricter than the diff guard, which checks only `{benchmarks,stages,workflows,harness,core}` (Routes rule 5). A green guard does not license an edit to `graph/`, `agents/` or `board/`;
  - every `AGENTS.md`, `CLAUDE.md`, `docs/adr.md`, until the orchestrator approves the FR-074 proposal;
  - `package.json` and lock files;
  - earlier `.specify/specs/*`;
  - `.claude/settings.json`, `tests/test_compose_opencode_cache_mount_net.py`, and any other path uncommitted in the primary checkout when the branch is cut.
- **No compose actions**: no `docker compose build|up|down|restart`, and no live run starts (L8).
- **App-tier tests move with the surface** (reviewer tasks-4, generalised). An implementation task that changes a surface an existing app-tier test (`U/app.*.pw.ts`) drives must, in the same commit:
  - update that test's selectors and setup to the new surface, keeping the rule it asserts;
  - or, where the same phase's app-tier task rewrites that clause, delete the test and let the app-tier task restore it. A clause untested mid-phase is acceptable: SG-5 checks at phase end. A clause whose rewrite lands in a later phase must instead be updated in place;
  - or, where its clause is retired in that task, delete the test and add the tombstone.

  Name each one in the commit body. The phase's app-tier task then finalises clause wording and adds new clauses. This keeps every commit green (no red commits) and is not SG-3. A test whose rule the new surface cannot yet satisfy is a stop (SG-8), unless this file names an interim (T032, T063).
- **Deleting a library component** (`gate_decision` in T044; `fleet_table`, `fleet_row` and `stage_dots` in T049; `yaml_pane` and `schema_form` in T063) always includes, in the same commit:
  - a grep showing no remaining importer;
  - removing its exports from `U/src/index.ts`;
  - removing its profile import from `U/showcase/registry.ts`;
  - tombstoning its clauses;
  - checking `U/scripts/build-ds-bundle.spec.ts`, and any other spec that probes `dist-ds/<component>/`, for a reference to it, and retargeting any reference to a surviving profile.
- **Styles**: tokens only (`var(--*)`). No hex, `rgb(` or `rgba(` in components or stores. Playwright assertions carry no hex and no pixel values. Clause ids are cited on the same line as the test.
- Line numbers in the spec set are as of main `07232332`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name, test id or rule is needed that the spec set does not define.
- **SG-2** An edit to a forbidden path appears necessary.
- **SG-3** An existing test fails, and neither this file nor Clauses names it as intentionally rewritten or retired. Do not edit it to pass.
- **SG-4** A RED test passes before its implementation, or a PIN is red.
- **SG-5** `python scripts/check_clauses.py` reports a dangling citation, or an untested clause that is not in baseline.md's pre-existing list, at the end of a phase.
- **SG-6** `check_ui.py` reports a skipped step, or a test in an untouched file times out or fails (known load flake: `.workspace/tasks/2026-10-03-check-ui-wrapper-timeout-flake.md`). Report it; do not fix it.
- **SG-7** Any file would exceed 1000 lines.
- **SG-8** A v5 element is ambiguous or not drawn, or a forced item has no v5 home the spec names.
- **SG-9** The diff guard (`KROKER_DIFF_GUARD=1 pytest tests/test_018_diff_guard.py`) fails.

---

## Phase 1: Setup and baseline (slice 0)

- [x] T001 Run `git log --oneline -3 main`. Cut branch `018-canvas-v5-ui` from the current main head (`07232332` or newer) in the worktree the orchestrator names. Stage exactly two files, `docs/reports/Pipeline Canvas v4 (standalone).html` and `docs/reports/Pipeline Canvas v5 (standalone).html`, each with its own `git add` (FR-070), and commit them alone ("docs(018): add Pipeline Canvas v4/v5 prototypes as spec inputs"). Confirm with `git show --stat HEAD` that nothing else was committed (FR-075).
- [x] T002 Commit the spec set `.specify/specs/018-canvas-v5-ui/` (spec, plan, research, data-model, contracts, quickstart, checklists, tasks) as its own commit. Then run quickstart §1 steps 1, 2, 5 and 6 once each, one per shell call, and write `.specify/specs/018-canvas-v5-ui/baseline.md` with:
  - the base sha;
  - each `check_ui.py` step's result;
  - the Vitest pass counts for both workspaces and the Playwright pass count;
  - the fast-tier pass, fail and skip counts, naming any pre-existing failure;
  - the full `check_clauses.py` output, with the list of clauses already untested;
  - the line counts of `U/app.pw.ts`, `U/app.md`, `F/api/mock/index.ts`, `F/api/http.ts`, `D/api.py` and `D/graph_wire.py`.

  Commit baseline.md.

**Checkpoint**: baseline.md holds a green `check_ui.py` (SG-6 otherwise).

---

## Phase 2: Foundational shell (slice 1; blocks every story)

**Purpose**: tokens, theme, the raw-colour gate, the split app-tier tests, and the v5 header, footer and toasts.

### Tokens and theme (R-10)

- [x] T003 RED: in `interfaces/ui/src/tokens/tokens.pw.ts` add tests that `--ground-node`, `--grid-dot`, `--edge` and `--ink-dim` resolve under `:root` and under `[data-theme='light']` (TOKENS-1/TOKENS-3 pattern). Create `tests/test_check_raw_colours.py`, which runs `scripts/check_raw_colours.py` over a temp tree:
  - a `.vue` file with `#fff`, a `.ts` file with `rgba(`, and a `.vue` file naming `'IBM Plex Sans'` each fail with path:line;
  - files under `tokens/`, `api/mock/` and `__fixtures__/` pass.

  Both fail (names missing; script missing).
- [x] T004 Add the four names, with both themes' values from R-10, to `interfaces/ui/src/tokens/tokens.css`, and describe them in `interfaces/ui/src/tokens/tokens.md` (no TOKENS-4 change). Create `scripts/check_raw_colours.py` (exit 1 on any hit; scans `.vue` and `.ts` under `interfaces/ui/src` and `interfaces/dashboard/frontend/src`; exemptions as in T003). Add it as a step in `scripts/check_ui.py`, after the typecheck. T003 goes green. Commit T003 + T004.
- [x] T005 Raw-colour sweep, so the new check passes on the tree:
  - `F/shared/format.ts` (`budgetColor` returns token names);
  - `F/app/ui.store.ts` (toast takes a status kind, not a colour);
  - `F/app/shell/StartRunModal.vue`;
  - the rgba shadows and backdrops in `U/src/components/start_run_modal/StartRunModal.vue` and `U/src/components/toasts/Toasts.vue` (→ `--shadow-overlay`, `--backdrop`);
  - every other hit the check reports.

  Rewrite the hex assertions in `F/app/shell/Toasts.test.ts` and in any `format.test.ts` case to kind or token-name assertions (plan, "Existing tests changed on purpose", item 5). `check_ui.py` is green including the new step. Commit.

### Session prefs and theme wiring (data-model §5)

- [x] T006 RED: create `F/app/prefs.store.test.ts`:
  - the defaults are `theme: 'dark'`, all three toggles off and `runInContext: null`;
  - setting `theme` to `'light'` and mounting `F/app/App.vue` (pattern: `F/app/App.test.ts`) sets `document.documentElement.dataset.theme` to `light`, and setting it back to `'dark'` removes it;
  - nothing is read from or written to `localStorage` (spy).

  Fails (store missing).
- [x] T007 Create `F/app/prefs.store.ts` (data-model §5) and wire `data-theme` in `F/app/App.vue`. T006 goes green. Commit T006 + T007.

### Split the app tier (R-11)

- [x] T008 Split `interfaces/ui/app.pw.ts` by screen into `interfaces/ui/app.{shell,run,inbox,fleet,board,graphs}.pw.ts`. Move each test with its `// clause:` citation unchanged. Put shared setup in `interfaces/ui/app.helpers.ts` (not a `.pw.ts`). Delete `app.pw.ts`. The Playwright pass count and the `check_clauses.py` output equal baseline.md. Commit.

### Header, footer, toasts (S4, S5, S12; Clauses CONSOLE-2, 27, 48, 50)

- [x] T009 RED: rewrite `interfaces/ui/src/components/app_header/app_header.spec.ts` for the rebuilt API (data-model §4.2):
  - primary and secondary items render in order with their labels;
  - `available: false` items are not rendered;
  - the badge renders only when `badge > 0`;
  - the run switch renders only when given, with the Observe and Design segment only when `mode` is set;
  - Search and ⋯ buttons emit `search` and `menu`;
  - no stats element and no Start button exist.

  Rewrite `app_header.md` clauses accordingly: the clauses asserting `SDLC·FACTORY`, uppercase labels or stats become tombstones (Clauses §3). Create `interfaces/ui/src/components/footer_bar/` RED spec `footer_bar.spec.ts`: left and right text render. Both fail.
- [x] T010 Rebuild `U/src/components/app_header/AppHeader.vue`, its `.profiles.ts` and its `.pw.ts` to v5 (wordmark mark "K" + "Kroker", primary and secondary nav, run switch, Search ⌘K, ⋯; tokens only). Create the five files of `footer_bar` and register both in `U/showcase/registry.ts` and `U/src/index.ts`. T009 goes green. Commit T009 + T010.
- [x] T011 RED: update `F/app/shell/AppHeader.test.ts` and create `F/app/nav.test.ts`:
  - `navManifest` lists Fleet, Inbox and run-in-context (primary) and Graphs, Compare and Interfaces (secondary);
  - Compare and Interfaces have `available: false` in this slice;
  - the shell wrapper passes `inbox.items.length` as the badge;
  - with zero fleet runs the run entry is disabled and reads `No runs`;
  - the run entry targets `prefs.runInContext`, else the newest fleet run.

  **The existing Start-run button stays in the shell until T066** (R-1). Assert it is still present. Fails.
- [x] T012 Create `F/app/nav.ts` (with `designAvailable: false`, data-model §5) and update `F/app/shell/AppHeader.vue` and `F/app/App.vue` to render the v5 header from the manifest, plus `FooterBar`. On non-canvas screens the footer's left side is the fleet total (priced runs only, and how many were left out, from `F/shared/fleet.store.ts`) and its right side reads `⌘K commands`. In the same commit (standing rule "App-tier tests move with the surface"), delete the app-shell CONSOLE-2 and CONSOLE-27 tests, which assert `.cmp-app-header .stats`. T015 restores them on the badge and the footer in this phase. Name both in the commit body. T011 goes green. Commit T011 + T012.
- [x] T013 RED: in `interfaces/ui/src/components/toasts/toasts.spec.ts` add tests that a toast renders bottom-centre (a class assertion) and takes its colour from `kind` (`done` or `failed`), not a colour prop. Fails.
- [x] T014 Reconcile `U/src/components/toasts/Toasts.vue`, `.md` and `.profiles.ts` (TOASTS clauses rewritten, Clauses §3), and update `F/app/shell/Toasts.vue` to pass `kind`. T013 goes green. Commit T013 + T014.
- [x] T015 App tier: in `U/app.md` rewrite CONSOLE-2 (badge only) and CONSOLE-27 (footer total), and add CONSOLE-48 and CONSOLE-50 (Clauses). In `U/app.shell.pw.ts` restore the CONSOLE-2 and CONSOLE-27 tests (deleted in T012), rewritten and add tests for 48 and 50, citing on the test line. Add `## Retired clauses` to `U/app.md` (empty for now). Run `check_ui.py`, then `check_clauses.py` (SG-5). Commit.

**Checkpoint**: v5 header and footer on every route; old screens still in place; Start button still present; quickstart §1 green.

---

## Phase 3: User Story 8 — command palette and display menu (slice 1, P3)

**Goal**: ⌘K or Ctrl+K palette with v5's commands, and the ⋯ menu with four session toggles (S11, FR-053, US8).

**Independent test**: `command_palette.spec.ts`, `toggle_menu.spec.ts`, `F/app/commands.test.ts`; app tier CONSOLE-47.

- [x] T016 [P] [US8] RED: create `U/src/components/command_palette/command_palette.spec.ts`:
  - `open: false` renders nothing;
  - typing filters by label (case-insensitive);
  - ArrowDown, ArrowUp and Enter run the highlighted command (emit `run(id)`);
  - Escape and a backdrop click emit `close`.

  Create `U/src/components/toggle_menu/toggle_menu.spec.ts`: each item renders its label, description and a check when `on`; a click emits `toggle(id)`. Both fail.
- [x] T017 [P] [US8] Create the five files of `command_palette` and of `toggle_menu` (data-model §4.2; tokens only). Register them in the showcase and the index. T016 goes green. Commit T016 + T017.
- [x] T018 [US8] RED: create `F/app/commands.test.ts`. `commandsOf(state)` returns v5's commands in v5's order (S11):
  - "Review …" one per pending item of the run in context, with hint `waiting`;
  - "Open Inbox" with hint `<n> pending`;
  - "Open Fleet";
  - "Open run board" with the run id as hint;
  - "Switch to Design" or "Switch to Observe";
  - "Design <graph>" for each shipped graph;
  - "Validate graph";
  - "Fit graph to view";
  - "Compare arms × graphs";
  - "Harness interfaces".

  Commands whose target is not `available` in `navManifest` are omitted. "Switch to Design", "Design <graph>" and "Validate graph" are omitted while `designAvailable` is false (data-model §5); T063 sets it true. Fails.
- [x] T019 [US8] Create `F/app/commands.ts`. Mount `CommandPalette` and `ToggleMenu` in `F/app/App.vue`, bound to `prefs.store` (theme, payloads, terminals, grid) and to global ⌘K or Ctrl+K and Escape. T018 goes green. Commit T018 + T019.
- [x] T020 [US8] App tier: add CONSOLE-47 to `U/app.md`, and a test in `U/app.shell.pw.ts`: Ctrl+K, type "inbox", Enter lands on `/#/inbox`; ⋯ → Light theme sets `data-theme="light"` on `html`. `check_clauses.py`. Commit.

---

## Phase 4: User Story 1 — watch a run on the Observe canvas (slice 2, P1) 🎯 MVP

**Goal**: v5 Observe: sinks, V1–V3 copy, the rail (run block, Path, Events, Cost, including Revise traversals), the inspector, and the read-only inner loop. The Cost tab is retired (FR-010 to FR-017, FR-015a, S1, S3, S13, S16).

**Independent test**: `graph_canvas.spec.ts`, `rail.spec.ts`, `step_list.spec.ts`, `costRail.adapter.test.ts`, `railEvents.adapter.test.ts`, `graphCanvas.adapter.test.ts`, `RunView.test.ts`; app tier CONSOLE-4, 6, 24–26, 30–32, 35, 49, 51, 52.

- [x] T021 [P] [US1] RED: in `U/src/components/graph_canvas/graph_canvas.spec.ts` add:
  - a `kind: 'sink'` node renders its outcome label and `sub`, lit or unlit;
  - `CanvasEdge.payload` renders only when `showPayloads` is on, or the edge is selected, or it is backward;
  - `CanvasEdge.note` renders on the edge;
  - `grid` toggles the dot-grid class.

  Existing GRAPH_CANVAS clauses are PINs. Fails.
- [x] T022 [P] [US1] Extend `U/src/components/graph_canvas/` (`types.ts`, `GraphCanvas.vue`, `.md` new clauses, `.profiles.ts` one profile per sink outcome, `.pw.ts`) per data-model §4.1. Grid dots use `--grid-dot`, wires `--edge`, and nodes `--ground-node`. T021 goes green. Commit T021 + T022.
- [x] T023 [P] [US1] RED: create `U/src/components/rail/rail.spec.ts`:
  - the head renders title, state, rows and the budget (with `limit: null` it renders "off" and no bar);
  - the tabs switch the visible section slot;
  - each `calls` entry renders as a call-to-action button emitting `call(index)`.

  Create `U/src/components/step_list/step_list.spec.ts`: one row per step with name, ref, a status pip and meta; no interactive control. Fail.
- [x] T024 [P] [US1] Create the five files of `rail` and of `step_list`, and register them. T023 goes green. Commit T023 + T024.
- [x] T025 [US1] RED: extend `F/shared/graphCanvas.adapter.test.ts`. `toCanvas` with a graph state appends four sink nodes (completed, rejected, failed, escalated) and never a `halted` one.
  - Outcome `failed` with result `failed:quarantined-tasks` lights `failed` with that sub (V1).
  - Outcome `escalated` lights `escalated` (V2).
  - Outcome `completed` with two edgeless non-terminal ports lists both nodes in the completed sub (V3).
  - A back edge with `used == max` carries the note `next revise escalates the run` (V2).
  - Wire `blocked` maps to the waiting status, never failed (R-10).

  Fails.
- [x] T026 [US1] Implement T025 in `F/shared/graphCanvas.adapter.ts`. T025 goes green. Commit T025 + T026.
- [x] T027 [P] [US1] RED: create `F/features/run/costRail.adapter.test.ts`, porting every case of `F/features/cost/CostTab.test.ts` that asserts a spec 011 fact onto `costRailOf` output (FR-015a):
  - role rows with calls, tokens and dollars;
  - "not priced";
  - a partial total, never `$0.00`;
  - the budget figures, or "no budget";
  - "No breakdown recorded".

  Add the stage group from `NodeRunState.cost_usd` by `canonical_stage` in `CANONICAL_STAGES` order, with closed runs giving `not measured` (R-5a), and the "Revise traversals" group (S16). Fails.
- [x] T028 [P] [US1] Create `F/features/run/costRail.adapter.ts`, reusing `F/shared/cost.ts`. T027 goes green. Commit T027 + T028.
- [x] T029 [P] [US1] RED: create `F/features/run/railEvents.adapter.test.ts` (R-5). From live decisions, pending items, two successive graph states and board events, the result is newest first. Node transitions are labelled `observed`. Closed `RunSummary`-derived decisions come after the timed events, labelled `untimed` and "not approved" where not approved. With no source, the result is the single "Decision history is not available for this run" row. An open run carries the "automatic and timed-out decisions appear when the run ends" note (FR-022). Fails.
- [x] T030 [P] [US1] Create `F/features/run/railEvents.adapter.ts`. T029 goes green. Commit T029 + T030.
- [x] T031 [US1] RED: rewrite `F/features/run/RunView.test.ts` and `F/features/run/RunView.tabs.test.ts` for v5 Observe (Clauses CONSOLE-4, 6, 24–26, 49, 51, 52; the tab-host unit tests touch CONSOLE-10 and CONSOLE-16 behaviour now, but those clauses' app-tier rewrite lands in T055). In `F/app/RunPage.test.ts`, replace the "fills the cost slot with a live CostTab" case with a test that `RunPage` passes no cost slot:
  - the rail renders the run block, and its Path, Events and Cost sections from the adapters;
  - `?rail=cost` and `?tab=cost` select Cost;
  - the tabs are Graph and Board only;
  - the inspector shows configured and answering model ids (the configured model from the registry role, the answering one from `Run.roles[].model`; `not measured` without a source) and marks a difference;
  - the `code` node's inspector shows `StepList` with no button (FR-017);
  - retention-expired and registry-drift reasons render under the run block, and a provider failure reads "could not load" (CONSOLE-51).

  Fails.
- [x] T032 [US1] Rebuild `F/features/run/RunView.vue` to v5 Observe, with the inspector as `F/features/run/RunInspector.vue` (new, screen-local). Update `F/app/RunPage.vue`: drop the Cost slot and keep the Board slot. **Delete `F/features/cost/`** (CostTab and its test, whose cases were ported in T027). The run header's stage strip goes (v5 draws none on the run). If `toStageDots` then has no importer outside tests, leave the shared module for T049 to decide.

**Interims until later slices** (the "App-tier tests move with the surface" rule):
- the existing canvas gate control (`GateDecision` on a pending node) stays in Observe until T043 replaces it with the card, so CONSOLE-5 and CONSOLE-23 stay green;
- the existing `open-copy` link to the current editor stays, as an item in the rail's run block, until T063 replaces it with the Design switch, so CONSOLE-8 stays green;
- in the same commit, update the app-tier tests of CONSOLE-6 and CONSOLE-16 to drop their stage-strip assertions (the rules otherwise unchanged), and CONSOLE-10's for the removed Cost and Gates tabs;
- in the same commit, delete the app-run CONSOLE-24, 25 and 26 tests (they drive the deleted CostTab's `cost-*` test ids). T033 restores them on the rail's Cost section in this phase;
- **CONSOLE-28 is updated in place** in the same commit, because its rewrite is in a later phase (T066). Its modal half is unchanged (the Start button stays until T065). Its tail moves from `?tab=cost` and `cost-budget` to the rail's budget block (`?rail=cost`);
- **verify** CONSOLE-4 and GRAPH_CANVAS-9 (`U/app.run.pw.ts`). T025 appends four sink nodes and maps wire `blocked` to the waiting status. If a node count (for example 12 → 16 `graph-node`) or the blocked class count changes, update the assertion in place, keeping the rule. Record in the commit body the counts observed.

T031 goes green. Commit T031 + T032 (+ those app-tier test edits).
- [x] T033 [US1] App tier: in `U/app.md` rewrite CONSOLE-6, 24, 25 and 26 (restoring the 24–26 tests deleted in T032), keep CONSOLE-4, and add CONSOLE-30, 31, 32, 35, 49, 51 and 52 (Clauses). Mock fixtures in `F/api/mock/graph.ts`, or a new `F/api/mock/runOutcomes.ts` if `graph.ts` would pass 400 lines: a halted-into-failed run, an escalated run, a two-sink completion and a no-budget run. Tests go in `U/app.run.pw.ts`. Each V test asserts the right element and the absence of the wrong one (R-11). If the new seeds land in `F/api/mock/graph.ts`, verify `F/api/mock/graph.test.ts` (seed counts) and adjust only counts that the new seeds change, naming each in the commit body (triage, not SG-3). `check_ui.py`, then `check_clauses.py`. Commit.

**Checkpoint**: US1 is demonstrable on the mock (quickstart §2 items 3 and 5). The Cost tab is gone, and `?tab=cost` lands on the rail.

---

## Phase 5: User Story 2 — decide everything waiting (slice 3, P1)

**Goal**: v5 card form for every kind (R-3), the Inbox list and card, rail call-to-actions and the canvas node action opening the same card, decision history on closed runs. FR-601 closes (FR-020 to FR-022, FR-030 to FR-035).

**Independent test**: `decision_card.spec.ts`, `decisionCard.adapter.test.ts`, `http.test.ts`, `mock/index.test.ts`, `InboxView.test.ts`, `RunView.test.ts`; app tier CONSOLE-5, 17–23, 29, 33, 34, 40, 41.

- [x] T034 [P] [US2] RED: create `U/src/components/decision_card/decision_card.spec.ts`:
  - kicker, schema chip, title, where and the fields render;
  - the text area renders only with `text`;
  - an action with `needsText` is disabled while the text is blank;
  - each action's `title` (its consequence) is rendered visibly before the click, not only as a tooltip;
  - `busy` disables every action;
  - a click emits `act(id, text)`.

  Fails.
- [x] T035 [P] [US2] Create the five files of `decision_card` and register them. T034 goes green. Commit T034 + T035.
- [x] T036 [US2] RED: in `F/api/http.test.ts`:
  - `decideTaskGate(run, key, 'revise', 'g', true)` posts `{key, outcome:'revise', text:'g', thaw_tests:true}`;
  - `approve` and `reject` post no `thaw_tests`;
  - `decideGate` bodies are unchanged (PIN);
  - `mapClosed` maps `gates` into `decisions` (approved → `approve`; not approved → `reject` with comment `not approved`), and an empty `gates` gives `[]`.

  In `F/api/mock/index.test.ts`, rewrite "escalation retry resumes the task" to the corrected mapping (R-3) and add `decideTaskGate` cases. Fails.
- [x] T037 [US2] In `F/api/types.ts` add `decideTaskGate` to `DashboardApi` and **remove `resolveEscalation`** (data-model §3.1). In `F/api/http.ts`, `decide()` gains an optional `thawTests`, sent only when true; add `decideTaskGate`; delete `resolveEscalation`; fix `mapClosed`. In `F/api/mock/index.ts` make the same change, keeping the mock seed. T036 goes green, and `vue-tsc` proves both providers. Commit T036 + T037.
- [x] T038 [US2] RED: create `F/shared/decisionCard.adapter.test.ts`. `decisionCardOf(item, timeouts)` gives, per R-3's table:
  - clarify: accept suggestion only when there is a suggestion, and answer needs text;
  - generic gate: approve, revise (needs text), reject;
  - `tool_approval`: Approve and Deny only, no Halt (V4), with the foot "a timeout counts as not approved";
  - `budget`: approve "one more increment" and reject "ends the run `rejected:budget`" (V6);
  - override: override (needs text) and send back;
  - task (`EscalationItem`): approve "accept as done", revise "retry" (needs text) with a thaw-tests option, and reject "quarantine; the build ends `failed:quarantined-tasks` after the wave" (V5);
  - an unknown gate name falls back to the generic gate (EC4);
  - each action maps to exactly one client call with the right `GateOutcome`;
  - timeout copy only when `timeouts` has the gate, else none (FR-035).

  Fails.
- [x] T039 [US2] Create `F/shared/decisionCard.adapter.ts` (data-model §5). T038 goes green. Commit T038 + T039.
- [x] T040 [US2] RED: rewrite `F/features/inbox/InboxView.test.ts`, and replace `F/features/inbox/entries.test.ts` with `F/features/inbox/InboxCard.test.ts`. The v5 list shows one row per item (kind label, age, title, where), keyed by `entryKey`. Selecting a row shows its `DecisionCard`, and `?item=` reflects the selection. Every spec 010 store rule still holds: run-and-key scoping, already-decided notice, failure keeps the text, in-flight blocks a second send, the three load states, and the incomplete banner (FR-030). The empty state reads "Nothing waiting on you". Fails.
- [x] T041 [US2] Rebuild `F/features/inbox/InboxView.vue` to v5. Delete `ClarifyEntry.vue`, `GateEntry.vue`, `OverrideEntry.vue`, `EscalationEntry.vue` and `InboxEntry.vue`. Adapt `F/app/inbox.store.ts`: its action set gains `decideTaskGate` and drops `resolveEscalation`, with every other rule unchanged. Rewrite the `resolveEscalation` cases of `F/app/inbox.store.test.ts` (the api fake and the action tests) to `decideTaskGate`, with the same guarantees: in-flight guard, run-and-key scoping, 404 notice and failure release. In the same commit (standing rule), delete the app-inbox tests of CONSOLE-17 to 22 and 29, and the inbox half of CONSOLE-23. CONSOLE-23 is one test, so it is deleted whole here because its inbox selectors break first; T043's mention only marks the end of the canvas interim. They drive the deleted entry components' test ids (`inbox-entry`, `inbox-accept`, `gate-revise`, `check-row`, `inbox-override`, `inbox-analysis`, `inbox-quarantine`, `gate-budget-note` …). T044 restores them on the v5 list and card in this phase. Name them in the commit body. T040 goes green. Commit T040 + T041.
- [x] T042 [US2] RED: extend `F/features/run/RunView.test.ts`:
  - each pending item of the run renders a rail call to action (FR-021);
  - clicking one opens its `DecisionCard` over the canvas, and `?decision=<key>` reflects it;
  - clicking a canvas node that has a pending item opens the same card (PRD FR-1205);
  - after a decision and a refresh that no longer lists the item, both the call to action and the node mark are gone;
  - Events lists live decisions with the human-only note, and closed-run decisions as untimed (FR-022).

  Fails.
- [x] T043 [US2] Implement T042 in `F/features/run/RunView.vue`, reading items from `F/app/inbox.store.ts` filtered by run and using `decisionCardOf`. Remove any remaining `gate_decision` use from the run view, which ends the T032 interim. In the same commit (standing rule), delete the app-run CONSOLE-5 tests and the canvas half of CONSOLE-23: they drive `gate-decision` and `gate-approve`. T044 restores them on the card in this phase. Name them in the commit body. T042 goes green. Commit T042 + T043.
- [x] T044 [US2] App tier: rewrite CONSOLE-5, 17–23 and 29, restoring their tests (deleted in T041 and T043), and add CONSOLE-33, 34, 40 and 41 (Clauses), with tests in `U/app.inbox.pw.ts` and `U/app.run.pw.ts`. The mock seed gains one `tool_approval` gate item, one `budget` gate item and a closed run with `gates`, in a new file `F/api/mock/decisions.ts` imported by the mock (`index.ts` stays under 560 lines). If nothing imports `U/src/components/gate_decision/` any more, delete it and tombstone its clauses (Clauses §3). Otherwise keep it. `check_ui.py`, then `check_clauses.py`. Commit.

**Checkpoint**: every card kind resolves from the Inbox and from the rail (SC-003). FR-601 is functionally closed.

---

## Phase 6: User Story 3 — fleet of runs (slice 4, P1)

**Goal**: v5's Fleet columns from one summary request per poll. The stage strip is retired (FR-040 to FR-042, S6, S16, R-6).

**Independent test**: `tests/test_dashboard_fleet_summary.py`, `tests/test_read_fixtures_fresh.py`, `http-read.test.ts`, `fleet.adapter.test.ts`; app tier CONSOLE-1, 39, 53.

- [x] T045 [US3] RED: create `tests/test_dashboard_fleet_summary.py` (Routes §fleet). Reuse the fakes in `tests/test_dashboard_run_graph_routes.py`, reading them first, and cover:
  - a shipped-name match for `default`;
  - a custom sha → `graph_name: None`;
  - a legacy run → null arm, graph and outcome, with empty traversals;
  - an unreadable run listed in `unreadable`;
  - back-edge counts with `max`;
  - the `dev` arm harness and model from `resolved_roles`;
  - `gate_timeouts` from `cfg.gates`;
  - the route is GET-only and performs no `GraphStore.put` (spy).

  Those fakes cover the Temporal side. The route also reads `poller.snapshot()`, and that file offers only `_NoPoller`, so write a minimal snapshot fake (a list of run ids, open and closed) with this test. Create `tests/test_018_diff_guard.py` (Routes rule 5), skipped unless `KROKER_DIFF_GUARD=1`. Fails.
- [x] T046 [US3] Create `D/fleet_summary.py` (data-model §2.1) and `D/read_routes.py`, registering `GET /api/fleet/summary`. Add the single `register_read_routes(...)` call in `D/api.py` `create_router`. T045 goes green, and the diff guard passes with `KROKER_DIFF_GUARD=1`. Commit T045 + T046.
- [x] T047 [US3] Create `scripts/dump_read_fixtures.py`, which builds `F/api/__fixtures__/read/fleet-summary.json` from the T045 test inputs, never live data. Create `tests/test_read_fixtures_fresh.py`, pinned the way `tests/test_graph_fixtures_fresh.py` is. RED, then green in the same commit: the fixture is generated, and the freshness test fails on a hand-edited copy (a test case). Commit.
- [ ] T048 [US3] RED: create `F/api/http-read.test.ts`: `mapFleetSummary` on the recorded fixture gives camelCase `FleetSummary` (data-model §3.2). In `F/features/fleet/fleet.adapter.test.ts`:
  - rows carry v5's columns;
  - the arm reads `harness × model` verbatim (V10);
  - the outcome shows the result string; `rejected:budget` is shown as served and `halted` never appears (V1, V6);
  - unpriced cost reads `unpriced`, never `$0.00`;
  - the open label is `Decide` for runs waiting on a person, `Open run` for the run in context, and `Open` otherwise (S16).

  Add `F/api/mock/fleetSummary.ts` cases to `F/api/mock/index.test.ts`. Rewrite `F/features/fleet/FleetTable.test.ts` and `F/features/fleet/FleetView.test.ts` for the v5 rows. The "one stage dot per canonical stage, 18 marks" case is deleted with CONSOLE-3 (S6). Fails.
- [ ] T049 [US3] Create `F/api/read-types.ts` (fleet part), `F/api/http-read.ts`, `F/api/mock/fleetSummary.ts` and `F/shared/fleetSummary.store.ts`, refreshed with the fleet poll in `F/app/App.vue` (one request per refresh). Rebuild `F/features/fleet/FleetView.vue` and `FleetTable.vue` to v5, and drop `toStageDots` from `F/features/fleet/fleet.adapter.ts`. Then retire the strip completely (S6, SC-009):
- Re-home `DotState`: declare it in `F/api/types.ts` exactly as data-model §5, and point `F/api/http.ts` at it. The `Run.stageMarks` wire field is unchanged.
- Delete `F/shared/stageStrip.adapter.ts`, `F/shared/stageState.ts` and their two tests. Their only importers (`RunView.vue`, `fleet.adapter.ts`) lost the strip in T032 and T048; confirm by grep that nothing else imports them (SG-3 if something does).
- **In this order** (reviewer tasks-3):
  1. Remove the `FleetRowProps` import from `F/features/fleet/fleet.adapter.ts`. The v5 rows do not use it.
  2. Delete `U/src/components/fleet_table/` and `U/src/components/fleet_row/`, after a grep shows their only importers were the rebuilt `F/features/fleet/FleetTable.vue` and `fleet.adapter.ts`. Tombstone their clauses.
  3. Delete `U/src/components/stage_dots/` (its last importer was `fleet_row/FleetRow.vue`) and tombstone its clauses (Clauses §3).
  4. In the same commit, remove the three components' exports from `U/src/index.ts` (including the `DotState`/`StageDot` type exports) and their profile imports from `U/showcase/registry.ts` (standing rule "Deleting a library component").
  5. Retarget `U/scripts/build-ds-bundle.spec.ts` (DS_BUNDLE-1..3) from `dist-ds/stage_dots/every-state.html` and `.cmp-stage-dot` to a surviving profile and its class: `dist-ds/status_pip/running.html` and `.cmp-status-pip`. Confirm after `check_ui.py`'s ds-bundle step that the file exists and contains the class. If not, pick another surviving profile and name it in the commit body.

In the same commit (standing rule), delete the app-fleet CONSOLE-3 test (`stage-dot` ×18). T050 tombstones the clause in this phase. Verify the CONSOLE-1 test: if the v5 rebuild changes `fleet-view`, `fleet-row` or `fleet-empty`, update it in place (T050 rewrites the wording). Name both in the commit body. Verify `F/app/App.poll.test.ts`: if its api fake lacks `getFleetSummary`, add it as `vi.fn(async () => ({ runs: [], unreadable: [] }))` and change nothing else (named in the commit body). T048 goes green. Commit T048 + T049.
- [ ] T050 [US3] App tier: rewrite CONSOLE-1, **retire CONSOLE-3** (tombstone with Clauses' reason), and add CONSOLE-39 and CONSOLE-53, with tests in `U/app.fleet.pw.ts`. Extend CONSOLE-35's test with the `rejected:budget` fleet row. `check_ui.py`, then `check_clauses.py`. Commit.

---

## Phase 7: User Story 4 — run board (slice 5, P2)

**Goal**: v5 kanban on the run's Board view, and the full Agent Board at `/runs/:id/board` with every spec 002 behaviour (FR-023, S7, V7).

**Independent test**: `kanban.spec.ts`, `kanban.adapter.test.ts`, `BoardTab.test.ts`; app tier CONSOLE-10–16, 36.

- [ ] T051 [P] [US4] RED: create `U/src/components/kanban/kanban.spec.ts`: columns render with title, count and cards; a card shows id, optional title, tag and meta; the `link` renders when given. Fails.
- [ ] T052 [P] [US4] Create the five files of `kanban` and register them. T051 goes green. Commit T051 + T052.
- [ ] T053 [US4] RED: create `F/features/board/kanban.adapter.test.ts`:
  - columns come only from the wire statuses present (`pending · in_progress · done · failed · blocked · quarantined`), never `claimed` or `queued` (V7);
  - a task whose `status` differs from `authoritative_status` shows both in its tag;
  - meta carries the fix attempts.

  Fails.
- [ ] T054 [US4] Create `F/features/board/kanban.adapter.ts` and `F/features/board/BoardKanban.vue`. The latter reuses `board.store.ts`, its banners and its empty state, and links "Open full Agent Board →" to `/runs/:id/board`. Add the route in `F/app/router.ts`: `/runs/:id/board` renders `BoardTab.vue`, unchanged except for a back link to the run. `F/app/RunPage.vue` fills the Board slot with `BoardKanban`. In the same commit, update the app-tier tests of CONSOLE-10 to CONSOLE-16 so that each drives the surface its rule now lives on (the kanban, or `/runs/:id/board`), per the standing rule. T055 finalises the wording. T053 goes green; every `BoardTab.test.ts` and `board.store.test.ts` test is a PIN. Commit T053 + T054.
- [ ] T055 [US4] App tier: rewrite CONSOLE-10 to 16 onto the kanban and the full board, and add CONSOLE-36, with tests in `U/app.board.pw.ts`. `check_ui.py`, then `check_clauses.py`. Commit.

---

## Phase 8: User Story 5 — graphs and Design (slice 6, P2)

**Goal**: Graphs catalog and PipelineConfig panel, and Design on the shared canvas at `/graphs/:sha` with read-only knobs. "Run this version" starts only the shipped default (R-15). The header Start button and the YAML pane go (FR-044 to FR-049, FR-045a, FR-054, S8, S9, S15).

**Independent test**: `tests/test_dashboard_read_routes.py` (shipped), `catalog_card.spec.ts`, `GraphsView.test.ts`, `graphEditor.store.test.ts`, `DesignView.test.ts`; app tier CONSOLE-8, 9, 28, 37, 38, 42–44.

- [ ] T056 [US5] RED: create `tests/test_dashboard_read_routes.py` with the shipped-graphs cases of Routes §shipped:
  - node, gate and edge counts per shipped YAML (`seeded` has 0 gates);
  - `validate_run_roles` pass and fail with a monkeypatched role map;
  - the same-weights note when `model_id` values are equal (V8);
  - every limits row present, or `None` when the `PipelineConfig` field is missing;
  - no `GraphStore.put` (spy).

  Fails.
- [ ] T057 [US5] Create `D/catalog_wire.py` and register `GET /api/graphs/shipped` in `D/read_routes.py`. Extend `scripts/dump_read_fixtures.py` to `F/api/__fixtures__/read/graphs-shipped.json`. T056 and the freshness test go green. Commit T056 + T057.
- [ ] T058 [P] [US5] RED: create `U/src/components/catalog_card/catalog_card.spec.ts`: kicker, name, sha, description, when, counts, and an action emitting `act`. A `null` description or when renders `not measured`. Fails.
- [ ] T059 [P] [US5] Create the five files of `catalog_card` and register them. T058 goes green. Commit T058 + T059.
- [ ] T060 [US5] RED: create `F/features/graphs/GraphsView.test.ts`:
  - one card per shipped graph;
  - "Open in Design" navigates to `/graphs/<sha>`;
  - the PipelineConfig panel renders the three checks (pass, fail or off) and the five sections, with `not measured` for null values;
  - the V8 note renders with the fixture's ids.

  Add `F/api/http-read.test.ts` and mock cases for `getShippedGraphs`. Fails.
- [ ] T061 [US5] Create `F/features/graphs/GraphsView.vue` and add the read types, mappers and `F/api/mock/shippedGraphs.ts`. Route `/graphs` renders `GraphsView`. Set `navManifest` Graphs to `available` (if not already). T060 goes green. Commit T060 + T061.
- [ ] T062 [US5] RED: create `F/features/graphs/DesignView.test.ts` and rewrite `F/features/graphs/graphEditor.store.test.ts` for v5 Design (Clauses CONSOLE-8, 9, 37, 38, 42, 43):
  - the palette is built from the catalog, grouped by `canonical_stage` in `CANONICAL_STAGES` order;
  - planned types (feedback §4) are shown dashed, refuse placement, and those with no stage read `unmapped` (V9);
  - a drop with unequal payloads is refused with a reason and creates no edge;
  - the inspector edits an edge's `max_traversals` and round-trips through parse;
  - node PipelineConfig knobs render read-only with the configured values (S9);
  - the validation panel shows gate shape, required inputs, reachability, bounded cycles and terminal reach (no references check), with "rejected, failed or escalated" copy and the completion-sink warning (V2, V3);
  - undo and redo work;
  - a layout-only save keeps the sha and an edge change alters it;
  - "Run this version" is enabled only for the saved, unchanged shipped `default` graph and states its reason otherwise (R-15);
  - `/graphs/:sha?from=run:<id>` loads through `getRunGraph`;
  - `/graphs?sha=X` and `/graphs?from=run:ID` redirect.

  Rewrite `F/features/graphs/GraphInspector.test.ts` for the S15 inspector: edge `max_traversals` edit, node delete and read-only knobs. Its schema-form node-field cases (the E-76 corners) are deleted with S15 and named in the commit body. Fails.

- [ ] T063 [US5] Create `F/features/graphs/DesignView.vue` on the shared `GraphCanvas`. Adapt `F/features/graphs/graphEditor.store.ts` and `GraphInspector.vue` to S15 (no YAML pane, no schema-form node fields). Delete `GraphEditorView.vue`. In this commit, all named in the commit body:
- **CONSOLE-7:** delete the app-graphs CONSOLE-7 test and the YAML paste helper in `U/app.helpers.ts`, and tombstone CONSOLE-7 in `U/app.md` (not T066);
- **CONSOLE-9 (orchestrator ruling):** delete its app-graphs test, which loads through the YAML flow. T066 restores it on Design. The clause is untested mid-phase, which is acceptable because SG-5 checks at phase end;
- **CONSOLE-8:** delete its app-graphs test, which clicks the `open-copy` link removed here, on the same terms. T066 restores it on the Design switch;
- **`F/features/graphs/schemaCoverage.test.ts`:** delete it with `schema_form`. It is coverage of the component, and nothing is left to cover once the component is gone and the S15 inspector is read-only;
- remove the `open-copy` interim link from the rail. Add the `/graphs/:sha` route and the two redirects in `F/app/router.ts`, and set `designAvailable` to true in `F/app/nav.ts`. The Observe/Design switch in the header navigates between `/runs/:id` and `/graphs/<pinned sha>?from=run:<id>`. If nothing imports `U/src/components/yaml_pane/` or `schema_form/` any more, delete them and tombstone their clauses; otherwise keep them. T062 goes green. Commit T062 + T063.
- [ ] T064 [US5] RED: in `F/features/graphs/DesignView.test.ts` add that "Run this version" opens the existing start form (`StartRunModal`) with its budget field, and that the started run's budget shows in its rail (CONSOLE-28). In `F/app/shell/AppHeader.test.ts`, assert that **no** Start button remains. Fails.
- [ ] T065 [US5] Wire "Run this version" to the existing `ui.store` start form, sending no graph field (R-15). Remove the Start button from `F/app/shell/AppHeader.vue`. In the same commit (standing rule), delete the CONSOLE-28 app test (wherever T008 placed it), which opens the form via `start-btn`. T066 restores it, opened from "Run this version", in this phase. Name it in the commit body. T064 goes green. Commit T064 + T065.
- [ ] T066 [US5] App tier: CONSOLE-7 is already tombstoned (T063). Rewrite CONSOLE-8 and CONSOLE-9 and **restore their tests** (deleted in T063):
  - CONSOLE-8: the header's Design switch opens `DesignView` holding the run's 12 nodes;
  - CONSOLE-9: load `/#/graphs/<sha>?from=run:feature-graph-demo`, edit an edge's `max_traversals`, and the parse round trip commits.

  Also rewrite CONSOLE-28 and restore its test (deleted in T065), opened from "Run this version", with the budget shown in the rail, and add CONSOLE-37, 38, 42, 43 and 44, with tests in `U/app.graphs.pw.ts`. Set the planned node types in a mock fixture `F/api/mock/plannedTypes.ts` (presentation-only, A8). `check_ui.py`, then `check_clauses.py`. Commit.

---

## Phase 9: User Story 6 — Compare (slice 7, P3)

**Goal**: arms × graphs, SC and $/case per graph, the description line, and the heatmap in record-stage order (FR-052, S10, R-9).

**Independent test**: `tests/test_dashboard_compare.py`, `heatmap.spec.ts`, `CompareView.test.ts`; app tier CONSOLE-45.

- [ ] T067 [US6] RED: create `tests/test_dashboard_compare.py` (Routes §compare) over a fixture tree under `tests/fixtures/compare/`:
  - an empty root → `available: False` with `root`;
  - two arms × two graphs;
  - a truncated JSONL line is skipped, with no 500;
  - an unpriced arm → `cost_per_case: None`;
  - `heat_columns` ⊆ `CELL_STAGE_ORDER`, in that order;
  - importing the module does not import `sdlc.benchmarks.report`.

  Fails.
- [ ] T068 [US6] Create `D/compare_wire.py`, register `GET /api/compare`, and extend the fixture dump to `F/api/__fixtures__/read/compare.json`. T067 and the freshness test go green. Commit T067 + T068.
- [ ] T069 [P] [US6] RED: create `U/src/components/heatmap/heatmap.spec.ts`: a column header per column; cells render a value, `low_n` (muted) or blank; colour comes from a token scale, with no literal. Fails.
- [ ] T070 [P] [US6] Create the five files of `heatmap` and register them. T069 goes green. Commit T069 + T070.
- [ ] T071 [US6] RED: create `F/features/compare/CompareView.test.ts`:
  - one row per arm with name and note, and SC and $/case per graph;
  - `null` reads `not measured`;
  - the description line comes from the wire;
  - the heatmap columns are in wire order;
  - `available: false` renders the empty state naming `root`.

  Add mapper and mock cases. Fails.
- [ ] T072 [US6] Create `F/features/compare/CompareView.vue`, the compare read types, mapper and `F/api/mock/compare.ts`, and the `/compare` route. Set `navManifest` Compare to `available`. T071 goes green. Commit T071 + T072.
- [ ] T073 [US6] App tier: add CONSOLE-45, with tests in `U/app.compare.pw.ts`. `check_ui.py`, then `check_clauses.py`. Commit.

---

## Phase 10: User Story 7 — Interfaces (slice 8, P3)

**Goal**: five harness rows by six columns, three of them `not measured`, family filled on the dev row only, and the adapter facts (FR-050, FR-051, Q5, R-8).

**Independent test**: `tests/test_dashboard_interfaces.py`, `check_matrix.spec.ts`, `InterfacesView.test.ts`; app tier CONSOLE-46.

- [ ] T074 [US7] RED: create `tests/test_dashboard_interfaces.py` (Routes §interfaces):
  - columns in key order;
  - claude_code layers `native + hook`, opencode `native`, cursor `none`, crew `per role harness`;
  - `installed`, `checkpoint` and `session` are `not_measured` on every row;
  - pyai is all `planned`;
  - `family` is filled only on the registry dev harness's row;
  - the strict parity test against `rules_unenforceable` loads `policy/containment.yaml` and runs inside a temp dir (R-8 note);
  - importing the module writes nothing (a filesystem spy).

  Fails.
- [ ] T075 [US7] Create `D/interfaces_wire.py`, register `GET /api/interfaces`, and extend the fixture dump to `F/api/__fixtures__/read/interfaces.json`. T074 and the freshness test go green. Commit T074 + T075.
- [ ] T076 [P] [US7] RED: create `U/src/components/check_matrix/check_matrix.spec.ts`: a header per column with name and ref; cell marks for yes, no, partial, not measured and planned; planned rows dimmed; facts with severity. Fails.
- [ ] T077 [P] [US7] Create the five files of `check_matrix` and register them. T076 goes green. Commit T076 + T077.
- [ ] T078 [US7] RED: create `F/features/interfaces/InterfacesView.test.ts` from the recorded fixture: five rows, the `not measured` cells, the family cell on one row only, and two facts. Add mapper and mock cases. Fails.
- [ ] T079 [US7] Create `F/features/interfaces/InterfacesView.vue`, the read types, mapper and `F/api/mock/interfaces.ts`, and the `/interfaces` route. Set `navManifest` Interfaces to `available`. T078 goes green. Commit T078 + T079.
- [ ] T080 [US7] App tier: add CONSOLE-46, with tests in `U/app.interfaces.pw.ts`. Every command in `commandsOf` is now available; extend CONSOLE-47's test to run "Compare arms × graphs" and "Harness interfaces". `check_ui.py`, then `check_clauses.py`. Commit.

---

## Phase 11: Close-out (slice 9)

- [ ] T081 Remove the `/graphs?sha=` and `/graphs?from=` redirects if quickstart §2 shows no in-app link still producing them. Otherwise keep them and list them in verification.md. Confirm that `?tab=cost` still lands on the rail (CONSOLE-24). Update `F/app/boundaries.test.ts` only if a new screen folder needs an entry, and name the change in the commit. Commit.
- [ ] T082 Documents (FR-074; plan "Document changes"):
  - `ROADMAP.md` FR-601: closure evidence on this round, proposed `[x]`, and "Last verified" prepended;
  - `README.md` dashboard paragraph: the v5 screens, plus `SDLC_RUNS_ROOT` and `KROKER_RUNS_BIND` for Compare (R-16);
  - `interfaces/dashboard/frontend/README.md`: current status and screens.

  Write the proposed `interfaces/AGENTS.md` screen table, the stale `stage_dots/` clause-naming example in `interfaces/ui/AGENTS.md:10` (propose a surviving component, for example `status_pip/`), and the ADR-8 note into `verification.md` §Proposals; do not edit those files (SG-2) until the orchestrator approves. Commit.
- [ ] T083 Run the full quickstart §1, each step in its own shell call, and walk quickstart §2 on the mock build. In `.specify/specs/018-canvas-v5-ui/verification.md` record:
  - each gate's result against baseline.md;
  - the clause report (0 dangling; untested ⊆ baseline);
  - for each of CONSOLE-30 to CONSOLE-39, the reviewer's revert check: which line was reverted, and that the test failed (R-11);
  - the deleted components and routes (SC-009);
  - the diff guard result (SC-007);
  - the largest touched file's line count.

  Commit.

---

## Dependencies and execution order

- Phase 1 → Phase 2 → everything else. Phase 2's T008 split must precede every app-tier task.
- Phase 3 (US8) needs Phase 2 only. It sits in slice 1 by plan.
- Phase 4 (US1) → Phase 5 (US2): the cards open over the Observe canvas, and the rail exists.
- Phase 6 (US3) needs Phase 2. It uses `prefs.runInContext` (T007) and the inbox store (T041) for "Decide".
- Phase 7 (US4) needs Phase 4 (RunPage slots).
- Phase 8 (US5) needs Phase 4 (shared canvas extensions) and Phase 6 (`D/read_routes.py`, the fixture dump, the diff guard).
- Phases 9 and 10 need Phase 6's backend scaffolding. They are independent of each other.
- Phase 11 comes last.
- Rebase checkpoints against main before Phase 6 and before Phase 9 (plan, Risks).

### Parallel opportunities

The `[P]` pairs are library components with no dashboard dependency. They can be built and reviewed in parallel with the dashboard task before them:
- T016/T017;
- T021/T022, T023/T024, T027/T028, T029/T030;
- T034/T035;
- T051/T052;
- T058/T059;
- T069/T070;
- T076/T077.

The executor seat is one, so "parallel" means review can overlap, not that commits interleave.

### Requirement coverage

| Requirement | Tasks |
|---|---|
| FR-001–004, SC-001, SC-009 | T009–T015, T054, T061, T063, T072, T079, T081 |
| FR-010–017, FR-015a | T021–T033 |
| FR-014 (ids verbatim) | T031 (inspector model ids), T048 (arm, V10), T056 (registry ids, V8), T071 (compare arms) |
| FR-020–023, FR-030–035, SC-003 | T034–T044, T051–T055 |
| FR-040–043 | T045–T050, T027, T062 |
| FR-044–049, FR-045a, FR-054 | T056–T066 |
| FR-050–053 | T016–T020, T067–T080 |
| FR-060–063, SC-005–SC-007 | T045–T047, T056–T057, T067–T068, T074–T075 |
| FR-070, FR-075 | T001 |
| FR-071, FR-072, SC-002, SC-008 | T008, T015, T020, T033, T044, T050, T055, T066, T073, T080, T083 |
| FR-073 | every task (SG-7); T081 |
| FR-074 | T082 |
| FR-080–082, SC-004 | T003–T005, T014, and every component task |

## Implementation strategy

- **MVP**: Phases 1, 2 and 4 (shell plus Observe). That alone shows the v5 run canvas with honest outcomes (V1–V3) and the cost rail.
- Phase 5 then closes FR-601, the round's open requirement. Stop for an orchestrator check after Phase 5 if the run is long.
- Every later phase is one screen, independently demonstrable on the mock.
