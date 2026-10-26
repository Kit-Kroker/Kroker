# Implementation Plan: Dashboard rework to the Pipeline Canvas v5 design

**Branch**: `018-canvas-v5-ui`, cut at T001 from current main (`07232332` or newer) | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md) | **Base**: main `07232332`

**Input**: [spec.md](spec.md).
- GATE 1 cleared 2026-10-26: Q1–Q5 = A.
- Narrowed the same day by the user's **v5-only** ruling (spec S1–S14; S15 added at plan, S16 at plan review), which supersedes the requirements it names.
- Plan-phase errata are recorded in the spec: C11 (tokens and fonts), N3 (card kinds), N5 (decision history), V9 (Compare stage vocabulary).

**Consults**: advisor `.workspace/tmp/advisor-018-1.md` (D1–D8, round 2); skeptic `.workspace/tmp/skeptic-018-1.md` (L1–L10, round 2). Their findings are folded into [research.md](research.md) R-1 to R-16.

**Review**: reviewer plan checklist and analysis, `.workspace/tmp/reviewer-018-plan-1.md`. VERDICT: fixes-needed (doc-level). All four gaps were fixed:
1. the budget-gate cite moves to `role_host.py:290-300`;
2. the R-1 slice table is aligned with clauses.md (CONSOLE-5→3, CONSOLE-8→6, CONSOLE-16→5);
3. R-8 states that the strict parity holds on the shipped policy only;
4. the nits: `step.py:931`, and spec S16 adds v5's "Revise traversals" cost group and the "Decide" fleet label (CONSOLE-52, CONSOLE-53).

Re-review: `.workspace/tmp/reviewer-018-plan-2.md`, **VERDICT: approve**.

Tasks review: `.workspace/tmp/reviewer-018-tasks-1.md` to `-6.md`. Rounds 1–5 returned fixes-needed with doc-level blockers:
- names missing from data-model;
- broken tests not named by any task;
- the `DotState` and `stage_dots` retirement;
- the T063 schema_form and YAML-flow tests;
- app-tier breakers, handled by the standing rule "App-tier tests move with the surface".

Round 6: **VERDICT: approve**.

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. `D/` = `src/sdlc/dashboard/`.

## Summary

The dashboard is replaced screen by screen with v5's information architecture and nothing else:
- Fleet, Inbox and the run in context;
- the run's Graph (Observe/Design on one canvas) and Board;
- Graphs, Compare and Interfaces;
- a rail with Path, Events and Cost;
- a command palette, a ⋯ menu and a footer.

Shipped capabilities that v5 does not draw move into the nearest v5 surface, not out of the product:
- spec 011's cost facts go into the rail;
- spec 002's board detail goes to the full Agent Board behind v5's own link;
- spec 010's inbox kinds go into v5's card form.

FR-601 closes through the rail's per-run call to action and Events.

The backend gains four additive, read-only routes in new `D/` modules over existing stores. No workflow, stage, harness, core or benchmark code changes. Ten slices land on one branch, each green and each retiring what it replaces.

## Technical Context

**Language/Version**: TypeScript 5 / Vue 3 SFCs (`<script setup lang="ts">`); Python 3.13 for the dashboard routes.

**Primary Dependencies**: Vue, Pinia, vue-router (hash history), vue-flow (inside `graph_canvas`), `@kroker/ui`; FastAPI and pydantic on the backend. No new dependency.

**Storage**: None new. The theme and display toggles are session-only (S4). The routes read the graph catalog, `PipelineConfig`, the registry, the containment policy and benchmark records; none of them write.

**Testing**: `python scripts/check_ui.py` is the only JS entry (R4 of 002). The fast-tier `pytest` covers the routes and fixture freshness. Playwright `U/app.<screen>.pw.ts` runs on `VITE_API=mock`. `scripts/check_clauses.py`, `scripts/check_file_size.py` and the new `scripts/check_raw_colours.py` complete the set (quickstart §1).

**Target Platform**: the browser SPA served by the host-side dashboard (`uvicorn interfaces.dashboard.api.main:app`, 127.0.0.1:8500). The dashboard is not a compose service.

**Project Type**: web application: front-end package, design-system package, and a dashboard backend module.

**Performance Goals**: the Fleet poll makes one summary request per refresh, not one per run (R-6). The canvas stays navigable at the shipped graphs' size, and the Events rail is bounded (EC7).

**Constraints**:
- 1000-line ceiling;
- no screen imports another screen, and the library imports no dashboard code;
- tokens only, with no colour or font literal beside components;
- no hex or pixel values in Playwright assertions;
- same-line clause citations;
- no edits under `src/sdlc/{benchmarks,stages,workflows,harness,core}/`;
- no compose build or restart (L8).

**Scale/Scope**:
- about 10 new library components;
- one rebuilt header and one reconciled toast;
- 4 backend modules and 4 routes;
- about 25 new or rewritten console clauses;
- 3 retired console clauses, plus CONSOLE-7 (S15);
- 6 dashboard screen folders reshaped, and `features/cost/` deleted.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md`, `interfaces/AGENTS.md` and `interfaces/ui/AGENTS.md`.

| Rule | Status after design |
|---|---|
| Screens import only `app/*.store.ts`, `shared/`, `api/`, `@kroker/ui` | Holds. The shared card mapping is `F/shared/decisionCard.adapter.ts`, and both the inbox and run screens use it (R-12). The full Agent Board stays in `features/board/`, composed by the app layer as today (R-13 of 002). |
| `ui/` never imports `dashboard/` | Holds. Every new component takes display primitives (data-model §4). |
| New library component ⇒ five files and showcase registry | Planned for every component in data-model §4.2. |
| New shipped surface ⇒ CONSOLE clauses and app-tier coverage | [contracts/clauses.md](contracts/clauses.md). |
| 1000-line ceiling | `U/app.pw.ts` (548) is split by screen in slice 1. `F/api/mock/index.ts` (539) gets new fixtures in new files. `D/graph_wire.py` (579) and `D/api.py` (382) gain only the router hook (R-13). |
| The producer owns its artifacts; no cross-stage calls | Not touched: no stage code changes. |
| Tokens only | R-10, plus the new raw-colour check. |

There is no violation, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/018-canvas-v5-ui/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   clauses.md, read-routes.md
├── checklists/  requirements.md (+ plan.md, tasks.md from the reviewer)
├── baseline.md  (slice 0), verification.md (slice 9)
└── tasks.md     (/speckit-tasks)
```

### Source code (after the round)

```text
docs/reports/Pipeline Canvas v4 (standalone).html   N (T001, spec input)
docs/reports/Pipeline Canvas v5 (standalone).html   N (T001, spec input)

src/sdlc/dashboard/
├── api.py               M  one call: register_read_routes(...)
├── read_routes.py       N
├── fleet_summary.py     N
├── catalog_wire.py      N
├── interfaces_wire.py   N
└── compare_wire.py      N
scripts/
├── check_raw_colours.py N
├── check_ui.py          M  + raw-colour step
└── dump_read_fixtures.py N
tests/
├── test_dashboard_read_routes.py   N
├── test_dashboard_fleet_summary.py N
├── test_dashboard_interfaces.py    N  (incl. strict parity)
├── test_dashboard_compare.py       N
├── test_read_fixtures_fresh.py     N
├── test_check_raw_colours.py       N
└── test_018_diff_guard.py          N

interfaces/ui/
├── app.md                     M  dispositions + CONSOLE-30..53 + Retired clauses
├── app.pw.ts                  D  → app.{shell,run,inbox,fleet,board,graphs,compare,interfaces}.pw.ts
├── src/tokens/tokens.css|md   M  four new names, both themes
├── src/index.ts, showcase/registry.ts  M
└── src/components/
    ├── graph_canvas/          M  sinks, payload labels, notes, grid
    ├── app_header/            M  rebuilt to v5
    ├── toasts/                M  v5 placement, kind not colour
    ├── start_run_modal/       M  token sweep only
    ├── rail/ decision_card/ step_list/ kanban/ command_palette/
    │   toggle_menu/ heatmap/ check_matrix/ catalog_card/ footer_bar/   N
    └── gate_decision/ stage_dots/ yaml_pane/ schema_form/  D if unused (verify per slice)

interfaces/dashboard/frontend/src/
├── api/  types.ts M · http.ts M · read-types.ts N · http-read.ts N
│         mock/{fleetSummary,shippedGraphs,interfaces,compare}.ts N · __fixtures__/read/ N
├── app/  App.vue M · router.ts M · nav.ts N · prefs.store.ts N · shell/* M · RunPage.vue M
├── shared/ decisionCard.adapter.ts N · fleetSummary.store.ts N · format.ts M
└── features/
    ├── fleet/    reshaped to v5 columns
    ├── inbox/    v5 list + card (entries replaced)
    ├── run/      Observe + rail + inspector + inner loop; railEvents/costRail adapters
    ├── board/    kanban view + full Agent Board (existing BoardTab content)
    ├── graphs/   catalog + PipelineConfig panel + Design on shared canvas
    ├── compare/  N
    ├── interfaces/ N
    └── cost/     D (logic → run/costRail.adapter.ts)

README.md, interfaces/dashboard/frontend/README.md, ROADMAP.md   M (slice 9, FR-074)
interfaces/AGENTS.md (screen table)   proposed edit, orchestrator approval (FR-074)
docs/adr.md (ADR-8 note for file-backed read routes)   proposed edit, orchestrator approval
```

**Structure Decision**: the existing by-screen layout, with two new screen folders (`compare`, `interfaces`) and one deleted (`cost`).

## Work order

Slices are listed in [research.md](research.md) R-1. `/speckit-tasks` turns each slice into tasks. Every slice starts with the data-model §6 name check and ends with quickstart §1.

| Slice | Done when |
|---|---|
| 0 | Branch cut from current main; the HTMLs committed alone; baseline.md records gate counts and the untested-clause list. |
| 1 | Tokens, theme and raw-colour check land. The header, the footer (with the fleet total), toasts, ⋯ menu and command palette are v5. The Start button stays until slice 6. `app.pw.ts` is split. CONSOLE-2 and CONSOLE-27 are rewritten; CONSOLE-47, 48 and 50 are green. |
| 2 | Observe, rail, inspector and inner loop land. `features/cost/` is deleted. CONSOLE-4/6/24/25/26/30/31/32/35/49/51/52 are green. |
| 3 | Cards, Inbox and rail call-to-actions land. `resolveEscalation` is removed and `decideTaskGate` added. `mapClosed` maps gates. CONSOLE-5/17–23/29/33/34/40/41 are green. FR-601 closes. |
| 4 | The fleet summary route and the v5 Fleet land. CONSOLE-1, CONSOLE-39 and CONSOLE-53 are green; CONSOLE-3 is retired. |
| 5 | The kanban and the full Agent Board land. CONSOLE-10 to CONSOLE-16 and CONSOLE-36 are green. |
| 6 | The shipped-graphs route, Graphs and Design land. "Run this version" opens the start form, and the header Start button is removed. CONSOLE-8/9/28/37/38/42/43/44 are green; CONSOLE-7 is retired. |
| 7 | The Compare route and screen land. CONSOLE-45 is green. |
| 8 | The Interfaces route and screen land. CONSOLE-46 is green. |
| 9 | Stale redirects are pruned. Documents are updated. verification.md records the V revert checks and the quickstart §2 walk. |

## Existing tests changed on purpose

Every change is listed per slice in tasks.md, and each points to its clause disposition. The classes are:

1. Tests of retired clauses (CONSOLE-3, 7, 27) are deleted with their tombstone.
2. Tests of rewritten clauses move to the split `app.<screen>.pw.ts` and change their selectors. The asserted rule stays the same, except for CONSOLE-21, whose rule is corrected (R-3).
3. Unit tests of replaced components (`AppHeader`, `Toasts`, the inbox entries, `CostTab`, `FleetTable`, `GraphEditorView`, `RunView` tab tests) are rewritten for the replacement.
4. The `F/api/mock/index.test.ts` case "escalation retry resumes the task" is rewritten to the corrected mapping.
5. `Toasts.test.ts` hex assertions become kind assertions (R-10).
6. These files are named in the task that breaks them (tasks review finding 2):
   - `F/app/inbox.store.test.ts` (T041);
   - `F/features/fleet/FleetTable.test.ts` and `FleetView.test.ts` (T048);
   - `F/app/RunPage.test.ts` (T031);
   - `F/features/graphs/GraphInspector.test.ts` (T062);
   - `F/shared/stageStrip.adapter.test.ts` and `F/shared/stageState.test.ts` (T049, deleted with their modules; `DotState` is re-homed in `F/api/types.ts` so `stage_dots` can go);
   - `F/app/App.poll.test.ts` and `F/api/mock/graph.test.ts`, verified and adjusted only if needed (T049, T033).

## Document changes (FR-074, slice 9)

| File | Change |
|---|---|
| `ROADMAP.md` FR-601 | Closed on this round: the inbox plus the run rail's per-run decisions and history. "Last verified" is prepended. FR-601 is proposed `[x]` for GATE 3. |
| `README.md` dashboard paragraph | Describes the v5 screens and the env needed for Compare and Interfaces (R-16). |
| `interfaces/dashboard/frontend/README.md` | Current status and screen list. |
| `interfaces/AGENTS.md` screen table | New rows. **Proposed, needs orchestrator approval.** |
| `docs/adr.md` ADR-8 | A one-line amendment: read routes over file-backed stores (benchmark records, policy, registry) are allowed and stay stateless. **Proposed, needs orchestrator approval.** |

## Risks

| Risk | Mitigation |
|---|---|
| A long branch diverges from a busy main (L1) | A rebase checkpoint before slices 4 and 7; the deny-list guard keeps conflicts in UI files. |
| The header switch lands before its targets (L1) | The route manifest's `available` flags (R-1). |
| A retired clause reads as untested or dangling (L9) | Tombstones outside headings (R-11). |
| The retry→approve defect is carried forward (R-3) | The task card uses the new `decideTaskGate`, with a unit test that asserts REVISE on retry. Main gets the bug crew (GATE 2 item 1). |
| `blocked` is painted red (D6) | R-10 mapping, plus a pip test for each wire status. |
| Compare is empty on a host whose runs live in a compose volume | The empty state names the root; README (R-16). |
| Route reads race the parallel benchmark's writes (L8) | Tolerant readers; tests on fixtures only; no compose actions. |
| The V-clause bar is citation only (D7) | The reviewer's revert check per V clause, recorded in verification.md. |
| Node is missing in the run env | `check_ui.py` skips with exit 0. A skip is reported and stops the slice. |

## Items for GATE 2

1. **Main defect: inbox "Retry" on a task escalation approves the task (marks it done).** `F/api/http.ts:244-247` vs `src/sdlc/stages/code/step.py:931,957` (R-3). Under the standing ruling, main bugs go through the bug crew. Recommendation: open `herdr-v3-bug` on main now. It is an operator hazard today, independent of this round. This plan replaces the call site in slice 3 either way.
2. **v5-only deltas** (spec S1–S16). The ones that change shipped behaviour:
   - the Gates tab is not built. FR-601 closes on the PRD text ("fleet, per-run stage spine, decision inbox") via the rail's call to action, the canvas gate action and Events (S2). The ROADMAP records that closure evidence;
   - the Cost tab is retired into the rail (S3);
   - the header stats and Start-run button are removed, and starting is via Design (S4). CONSOLE-2 is narrowed, and CONSOLE-27 moves to the footer;
   - the stage strip is retired (S6, CONSOLE-3). **This needs the user's acknowledgement** that the Observe canvas is the PRD's "per-run stage spine" (skeptic finding);
   - the board detail moves behind "Open full Agent Board" (S7);
   - the YAML editor pane is removed (S15, CONSOLE-7);
   - the theme is not persisted (S4).
3. **Live decision history is human-only** (R-4). Policy and timeout decisions appear only after the run ends. The rail says so. Closing the gap needs a workflow change (`gates.py:247`), and is filed as a follow-up.
4. **"Run this version" starts only the shipped `default` graph** (R-15). The server has no graph-pinned start, and B5 forbids adding a write parameter. The alternative is an additive `graph_sha` on the start body, with dashboard-side checks and a parity test (R-15). It is not planned without a ruling.
5. **V9 erratum.** Compare's heatmap uses record-stage columns (`CELL_STAGE_ORDER`), not `CANONICAL_STAGES` (R-9).
6. **Interfaces "family" column** is filled on the dev harness row only (R-8, L5).
7. **Proposed doc edits needing approval:** the `interfaces/AGENTS.md` screen table and the ADR-8 amendment.
8. **Not built (v5-only):** the TOKENS-4 alias sweep (002 FU-3 stays open) and theme persistence.
9. **Advisor proposal rejected:** a project-keyed full board address. The board stays run-keyed at `/runs/:id/board` to keep CONSOLE-11's semantics (R-2).

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind.
- Commit with `git commit -F <msgfile>`, one path per `git add` argument, and no heredocs. Every file is written with the Write tool.
- Never chain two test runs in one shell call.
- Tests first per task, in the same commit as the code (no red commits).
- The reviewer gate is per task and blocking.
- Never stage `.claude/settings.json`, `tests/test_compose_opencode_cache_mount_net.py` or any other path that was uncommitted when the branch was cut (FR-075).
- No `docker compose build|up|restart|down` in this round (L8).
- `AGENTS.md` and ADR edits only after the orchestrator approves them (FR-074).

## Complexity Tracking

No constitution or repository-rule violation to justify.
