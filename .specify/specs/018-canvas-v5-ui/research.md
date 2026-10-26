# Research: round 018, dashboard rework to Pipeline Canvas v5

Inputs:
- [spec.md](spec.md): GATE 1 rulings plus the v5-only ruling S1–S14.
- Advisor consult: `.workspace/tmp/advisor-018-1.md` (D1–D8 and round 2).
- Skeptic consult: `.workspace/tmp/skeptic-018-1.md` (L1–L10 and round 2).
- The v5 prototype, read through its embedded template and script.

Every decision below cites the code it rests on. `F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. `D/` = `src/sdlc/dashboard/`.

## R-1 — Slice order and cutover (Q1, D1, L1)

**Decision.** One branch with ten slices. Each slice ends with `check_ui.py`, the Python fast tier and the clause report green. Each slice retires what it replaces in the same commit as the replacement.

| Slice | Delivers | Replaces / retires |
|---|---|---|
| 0 | Branch from current main; commit the two prototype HTMLs (FR-070); baseline gate counts | — |
| 1 | Tokens (R-10); `data-theme` wiring; raw-colour sweep; v5 header from a route manifest; footer carrying the fleet total; toasts; ⋯ menu (four toggles, session-only); command palette (commands gated by `available`) | Old header and toasts. CONSOLE-2 narrowed to the badge; CONSOLE-27 rewritten onto the footer. **The header keeps today's Start-run button until slice 6** (advisor round 2): removing it earlier leaves no start path and regresses CONSOLE-28. |
| 2 | Run Observe: canvas sinks; traversal and escalation copy (V1–V3); the rail (run block, Path, Events, Cost); inspector; read-only inner loop | Run Graph tab body. Cost tab retired into the rail (S3). CONSOLE-4/6/24/25/26 rewritten. |
| 3 | Decision cards: library card shell; Inbox in v5 form; rail call-to-actions and the canvas gate action over the canvas; the task, tool and budget cards | Inbox entries. CONSOLE-5, CONSOLE-17 to CONSOLE-23 and CONSOLE-29 rewritten. FR-601 closes. |
| 4 | Fleet with v5 columns, plus the fleet summary read route (R-6) | Fleet table and stage strip. CONSOLE-1 rewritten, CONSOLE-3 retired. |
| 5 | Run Board kanban; full Agent Board at its own address | Board tab. CONSOLE-10 to CONSOLE-16 rewritten onto the full board and the kanban. |
| 6 | Graphs catalog route and screen; PipelineConfig panel; Design on the shared canvas at `/graphs/:sha`; read-only knobs; "Run this version" (R-15) opens the start form; the header Start button is removed | Graph editor view. CONSOLE-7 retired; CONSOLE-8, CONSOLE-9 and CONSOLE-28 rewritten. |
| 7 | Compare route and screen | — |
| 8 | Interfaces route and screen | — |
| 9 | Remove the redirects that are no longer needed; documents (FR-074); final gates; verification.md | — |

**Rationale.**
- The header is built from a route manifest. Each nav item carries `available`, and the slice that lands a screen flips it. Compare and Interfaces are hidden, not dead-linked, until slices 7 and 8 (L1 failure mode 1).
- No address is redirected before its replacement lands (D1).

**Alternatives.**
- Header last: rejected. Every slice would then be tested inside a shell that is about to change.
- Backend routes all in one slice: rejected (D1). Each route lands with the screen that reads it.

**Not in this round (v5-only).** The advisor's round 2 puts the alias sweep in slice 9. That is not adopted: the TOKENS-4 alias removal (002 FU-3) is not drawn in v5 and no contract forces it. It stays a follow-up. This also avoids a 100-file sweep (D6).

## R-2 — Addresses (Q2, Q3, S1, S7; D1, D2)

| Address | View | Notes |
|---|---|---|
| `/` | Fleet | unchanged |
| `/inbox` | Inbox | `?item=<runId>/<key>` selects a card. That is v5's list-plus-card layout. |
| `/runs/:id` | Run, Observe | `?rail=path\|events\|cost` (default `path`). `?decision=<key>` opens a card over the canvas. |
| `/runs/:id?tab=board` | Run, Board kanban | Kept: CONSOLE-10's address semantics survive. |
| `/runs/:id?tab=cost` | Redirect to `/runs/:id?rail=cost` | S3. A copied Cost-tab URL still lands on cost. |
| `/runs/:id?tab=gates` | Renders Observe (an unknown tab value, as today) | S2. The tab was never enabled, so it needs no redirect. |
| `/runs/:id/board` | Full Agent Board | S7. Today's BoardTab content, unchanged in behaviour. It stays **run-keyed**: the advisor's project-keyed `#/board/:project` is rejected, because today's board shows the run's pinned plan and filters tasks by `run_id` (002 FR-021, FR-021a, CONSOLE-11). A project-keyed address would change what it shows. |
| `/graphs` | Graphs catalog + PipelineConfig panel | S8 |
| `/graphs/:sha` | Run Design on the shared canvas | `?from=run:<id>` loads the run's pinned graph through `/runs/{id}/graph` (D2: the sha store is backfilled lazily, `D/run_graph.py:157`). |
| `/graphs?sha=X`, `/graphs?from=run:ID` | Redirect to `/graphs/X` or `/graphs/<sha>?from=run:ID` | Today's editor query forms (`F/features/graphs/GraphEditorView.vue:21-26`). |
| `/compare`, `/interfaces` | new | slices 7 and 8 |

**The run in context** (Q3, L3) is the run most recently opened in this session. Failing that, it is the newest run in the fleet. With zero runs, the header's run entry is disabled and reads "No runs". With a run that answers 404, the header entry falls back to Fleet. The Observe/Design switch navigates between `/runs/:id` and `/graphs/<pinned sha>?from=run:<id>`.

## R-3 — Decision card kinds (N3, FR-031 to FR-034; D3, L7)

The card kind is derived in the dashboard adapter from fields already on the wire. There is no backend change.

| Card | Wire item | Discriminator | Actions → client call |
|---|---|---|---|
| clarify | `ClarifyItem` | `type: 'clarify'` | accept suggestion, or answer → `answerClarify` (unchanged) |
| gate | `GateItem` | `type: 'gate'`, any other `gate` name | approve / revise (comment) / reject → `decideGate` (unchanged) |
| tool escalation (E-17) | `GateItem` | `gate === 'tool_approval'` (`src/sdlc/stages/code/step.py:656`) | Approve / Deny only → `decideGate(approve \| reject)`. The body is the wire body verbatim; the rule id is inside it (`step.py:182-187`) and is not parsed. |
| budget gate | `GateItem` | `gate === 'budget'` (`src/sdlc/workflows/role_host.py:290-300`, `self._gate("budget", …)`, HARD) | approve "one more increment" / reject "ends the run `rejected:budget`" → `decideGate`. CONSOLE-29's copy is kept. |
| merge override | `OverrideItem` | `type: 'override'` | override / send back → `overrideMerge` (unchanged, spec 010 A3) |
| task gate | `EscalationItem` | `type: 'escalation'` (backend `TaskEscalationPending`, gate `task:<id>`, `src/sdlc/pending.py:58-66,145`) | approve "accept as done" / revise with guidance (+ thaw tests) "retry" / reject "quarantine; the build ends `failed:quarantined-tasks` after the wave" |

**One task card, not two.** "Task escalation" and "per-task gate" are the same backend item (D3, L7). The spec's two bullets collapse into one card. The spec erratum is recorded in spec.md N3.

**The task card's retry defect on main (D3 headline 3).** `resolveEscalation(retry=true)` posts `outcome: 'approve'` (`F/api/http.ts:244-247`). The backend reads APPROVE on a task gate as "accept the task as done" (`step.py:957`). Retry is REVISE (`step.py:931` onward). So the shipped inbox's "Retry" button today marks a failing task done. This is a **main-branch defect** under the standing ruling that main bugs go through the bug crew (see plan, Items for GATE 2). This plan does not carry the bug forward. The new task card calls a new client method, `decideTaskGate(runId, key, outcome, guidance, thawTests)`, which maps actions one-to-one onto `GateOutcome`. `resolveEscalation` is deleted with the old entry component. If the bug crew fixes main first, the rebase meets a deleted call site and nothing else.

**thaw_tests.** `DecideBody.thaw_tests` exists (`D/api.py:64`). It is applied only on REVISE (`src/sdlc/channels/contract.py:125`) and read only by the task gate. The client sends it only from the task card. `decide()` in `http.ts` gains an optional `thawTests` that is sent only when true, so every other call's body is unchanged.

**Timeout copy (FR-035).** Shown only where existing data has it. The run's `cfg.gates[name].on_timeout` comes through the cached `RunGraphs` input (`D/run_graph.py:116-165`) and is served by the fleet summary route (R-6) as `gate_timeouts`. A gate absent from cfg reads the code default, REJECT (`src/sdlc/workflows/gates.py:200-202`). The tool escalation's timeout reads "a timeout counts as not approved" (`EscalationOutcome.TIMEOUT`, V4). The budget gate reads its cfg entry if present, else `not measured`.

**Collision check (D3 caveat).** No shipped graph or node type names a gate `budget` or `tool_approval`: a grep of `src/sdlc/workflows/graphs/*.yaml` and `src/sdlc/graph/node_types.py` found none. Graph gate names are the node ids (`architecture`, `plan`, `research`). A unit test pins this against the served catalog.

## R-4 — Decision history in the rail (FR-022, N5; D5, L6)

- **Live run:** `RunState.decisions` (`src/sdlc/core/models.py:543`), already mapped by `mapRun` (`F/api/http.ts:99`).
- **Closed run:** `RunSummary.gates` (`GateOutcomeSummary`: gate, round, decided_by, approved; `models.py:468-500`). These are already on the closed wire, but `mapClosed` sets `decisions: []` (`http.ts:128`). The mapper is changed to fill them. Revise and reject cannot be told apart, so non-approved rows read "not approved".
- **Neither:** "Decision history is not available for this run."

`GraphState` carries no decisions and no events (`D/graph_wire.py:456-465`). Spec N5 is corrected.

**Live gap (advisor round 2).** On an open run, `RunState.decisions` holds only human decisions. `_gate_decisions` is written only by the human signal path (`src/sdlc/workflows/gates.py:111-113`). Policy and timeout decisions go to the trace only, and reach `RunSummary.gates` at run end. The rail states this under the live history: "Human decisions only while the run is open. Automatic and timed-out decisions appear when it ends." Closing the gap would need a workflow change (`gates.py:247`), which FR-061 forbids. It is named as a follow-up, not built.

**Ordering.** Open-run events are timed and listed newest first. Closed-run decisions are untimed and listed after the timed events, in round order, labelled "untimed".

## R-5 — The rail's Events section (FR-015; advisor blocking item 1)

There is no live event feed. `events.jsonl` is written at run end (`src/sdlc/observability/activities.py:31`). Adding a workflow query is forbidden (FR-061). FR-015 as rewritten already says "only from sources the backend already holds", so no user decision is needed. Events are composed client-side, newest first, from:

1. gate decisions (R-4), with timestamps where the wire has them;
2. pending items for this run (opened), from the inbox state;
3. node status transitions observed between graph-state polls. This covers only transitions observed while the page is open, and is labelled "observed";
4. board task events, when the run has a project key (`/projects/{p}/events?subject=…`, already served);
5. budget crossings (count only, `Run.budgetCrossings`);
6. the outcome, once final.

Tool escalations appear as pending gate items (item 2). An event kind with no source is not drawn.

## R-5a — Shipped states that v5 does not draw: their v5 home (skeptic round 2 (d))

- **Retention-expired, registry-drift and no-graph banners** (E-77, CONSOLE-6) appear as a note under the rail's run block, and the canvas shows its empty state.
- **"Could not load" versus "empty"** (spec 010, EC9) is told apart on every screen in its main area.
- **Closed-run per-stage cost.** It reads `not measured`: closed runs carry record-vocabulary stage names with no canonical stage, and no mapping is invented (R-9). Open runs group `NodeRunState.cost_usd` by `canonical_stage`.
- **The per-run stage spine** (PRD FR-601, "per-run stage spine") is the Observe canvas. Retiring the fleet strip (CONSOLE-3) rests on that reading, which is a GATE 2 item.
- **The canvas gate action** (PRD FR-1205: "gate approve/reject through the standard FR-301/302 machinery" in run mode) is kept. Selecting a node with a pending item opens the same card over the canvas, as v5's `openDecision` does. The rail's call to action is a second entry to the same card.

## R-6 — Fleet columns and the N+1 problem (S6; advisor items 2, 3)

v5's Fleet needs, per run, the graph name, the arm, the revise traversals, the result string and the location. Only `status`, `blocker`, `cost` and `age` are on the fleet wire today. Polling `graph_state` per row every 5 s is an N+1 (D, item 2).

**Decision.** Add one read route, `GET /api/fleet/summary`. It returns one `FleetRunSummaryWire` per run in the poller's current snapshot, built from the cached `RunGraphs` (`D/run_graph.py`) and its existing LRU, bounded to the snapshot size:
- `graph_sha`;
- `graph_name`: a shipped name when the sha matches `SHIPPED` (`src/sdlc/workflows/graph_catalog.py:33-40`), else null, which renders "custom";
- `arm`: harness and model of the `dev` role, from `GraphRunInput.cfg.roles`;
- `traversals`: the back edges with used and max;
- `outcome`: state, reason and result;
- `where`: the current nodes, or the terminal reason;
- `gate_timeouts`.

The route is stateless per request apart from the existing cache. The fleet poll calls it once per refresh, not once per row.

**Alternatives.** Fold the fields into the existing snapshot: rejected, because it changes `FleetSnapshot`, which the poller, SSE stream and CLI share. Per-row graph_state: rejected (N+1).

## R-7 — Graphs catalog and PipelineConfig panel (S8; D4)

`GET /api/graphs/shipped` returns `ShippedGraphsWire`:
- **Graphs:** for each `SHIPPED` graph, the name, `content_sha()`, node count, gate count (catalog `kind == 'gate'`) and edge count. Description and "when used" are a static table in the dashboard module, keyed by name. Its text follows `graph_catalog.py`'s own docstrings (for example `default-research` is used when `research_enabled`). An unknown name reads `not measured`.
- **Panel:** built from `PipelineConfig()` defaults, merged through `resolved_roles(cfg)` (`graph_catalog.py:108-122`).
  - Checks:
    - `validate_run_roles` / `check_adr6_families` (`src/sdlc/agents/loader.py:220`), reported pass or fail with the reason. The V8 "same weights" note is derived with `model_id()`.
    - `check_node_types`, reported pass when the served `NODE_TYPES` validate.
    - `containment`, reported off, or on with its `strict` state, from `PipelineConfig`.
  - Sections:
    - roles (harness × model);
    - proposer roles;
    - gates (policy, threshold, `on_timeout`), from `cfg.gates`;
    - limits (`max_fix_attempts`, `max_tool_escalations`, `max_gate_rounds`, `run_budget_usd`, `gate_timeout_hours`; a field `PipelineConfig` lacks reads `not measured`);
    - arms, from the benchmark config's arm list when readable, else `not measured`.

Nothing is written. The `GraphStore` is not touched (shas are computed in memory).

## R-8 — Interfaces (Q5, S8; D4, L5, advisor item 5)

`GET /api/interfaces` returns `InterfaceMatrixWire`. The rows are `claude_code`, `opencode`, `cursor` and `crew`, plus `pyai` marked planned. The columns are v5's six.

| Column | Source | State |
|---|---|---|
| Containment layers | each adapter's `containment` class attribute (`src/sdlc/harness/claude_code.py:77`, `opencode.py:83`, `cursor.py`). Crew reads "per role harness". | live |
| containment.strict | Derived: the rules in the policy file (`harness/containment.py:load_policy`, read-only) whose `layer` is not in the row's declared layers → "refuses: hook rules" when non-empty, "starts" when empty. A parity test pins this against `rules_unenforceable` (see the note below the table). `apply_containment` is never called, because it writes files (D4). | live |
| Family ≠ reviewer | **The ADR-6 check is per role, not per harness** (L5). The cell is filled only on the row whose harness is the registry's `dev` harness, with the registry check's result and the V8 note. Every other row reads `not measured` (the check is undefined for a harness the dev role does not use). | live (one row) |
| Installed on worker | measured inside the worker (N4) | `not measured` |
| Checkpoint commit | adapter behaviour, not declared data | `not measured` |
| Session capture | adapter behaviour, not declared data | `not measured` |

**The strict parity is policy-specific, not structural** (reviewer gap 3):
- The test covers claude_code and opencode on the shipped policy only. It loads `policy/containment.yaml` itself and never builds an approximation.
- `opencode.py:115-118` also marks native rules unenforceable when they carry the `path_outside_worktree` or `host_not_allowlisted` predicates. A layer-only derivation would call those enforceable. `claude_code.py:138` always returns `[]`.
- On today's policy the two derivations agree. A policy edit that adds such a native rule breaks the parity test on purpose. The derivation must then follow the adapter's predicate rule, or the column reads `not measured`.

The facts are the two real adapter facts (opencode has no hook layer; cursor fails closed). They are static text in the dashboard module, sourced from `ARCHITECTURE.md` "adapter reality".

Importing the adapter modules to read one class attribute is a read-only import. It does not change worker behaviour (B7). A test asserts the import has no side effect on the policy or the filesystem.

## R-9 — Compare (S10; D4, advisor item 8)

`GET /api/compare` reads the benchmark records under the runs root through the existing pure readers: `load_evidence` (`src/sdlc/benchmarks/evidence.py:104`), `build_runs` (`runs.py:423`), `build_grid` (`grid.py:221`) and `build_layers` (`heatmap.py:182`). `report.py` is never imported at module scope (D4).

It returns `CompareWire`:
- availability, and the root path read;
- the description line (SC weights and judge, from the records);
- per arm (harness × registry model id, verbatim) and per graph: SC composite and $/case, each a number or `not measured`;
- the heatmap layer: rows, columns, and cells that are a value, `low_n` or blank.

**Stage vocabulary (V9 erratum).** The benchmark heatmap's columns are record stage names in `CELL_STAGE_ORDER` (`src/sdlc/benchmarks/models.py:443`: `plan`, `merge`, `tool_approval` …), not `CANONICAL_STAGES` (`planning`, `quality_gate` …). V9 assumed one vocabulary. Compare shows the records' own columns in `CELL_STAGE_ORDER`, only those present (V9's "present in the data" holds). The palette and the catalog keep `CANONICAL_STAGES`. Inventing a record-to-canonical mapping is rejected: it would be a new scoring rule (B5, FR-915). This is flagged for GATE 2.

**Runs root.** The host dashboard reads `runs/` relative to its working directory unless `SDLC_RUNS_ROOT` is set. With compose's default named volume, the host cannot see the worker's runs (`docker-compose.yml`, `KROKER_RUNS_BIND`). The empty state names the root path it read (EC6). The README documents `KROKER_RUNS_BIND`.

**Concurrency with the parallel round (L8).** The reads tolerate partial files: they skip undecodable lines and missing fields, and never raise into a 500 for a record mid-write. Tests use fixtures only.

## R-10 — Tokens (FR-080, C11; D6, L4)

The palette is already v5 (C11). The changes:

- **New names, both themes:**
  - `--ground-node` (`#141920` / `#fbfaf7`);
  - `--grid-dot` (`#1f2630` / `#d3cfc4`);
  - `--edge` (`#465163` / `#8d9198`);
  - `--ink-dim` (`#636c7c` / `#868a91`).

  TOKENS-3 requires every themed token in both scopes.
- **The meaning of "blocked" (D6 conflict).** The wire's node status `blocked` (a running node waiting on a person, `src/sdlc/graph/run_view.py:146`) maps to `--status-waiting`, violet. v5's red "blocked" key is used only where it means failure or rejection: sinks, failed outcome, reject actions. It maps to `--status-failed`. Board task `blocked` stays on the existing pip class (waiting).
- **Theme wiring.** `F/app/App.vue` sets `document.documentElement.dataset.theme` from a session-only prefs store (S4, A4). The library never sets it (`U/src/tokens/tokens.md`).
- **Raw-colour sweep (SC-004; D6, L4):**
  - `F/shared/format.ts:15-19` (`budgetColor` → token names);
  - `F/app/ui.store.ts:22` and the `Toasts.test.ts` hex assertions (toast colour → a status kind);
  - `F/app/shell/StartRunModal.vue:21-29`;
  - the rgba shadows and backdrops in `U/src/components/start_run_modal/StartRunModal.vue` and `toasts/Toasts.vue` (→ `--shadow-overlay`, `--backdrop`).

  A new script check, `scripts/check_raw_colours.py`, fails on hex, `rgb(`, `rgba(` or a font-family name in `.vue` and `.ts` files under `U/src` and `F/`. Exempt are `tokens/`, `api/mock/`, `__fixtures__/` and test files' fixture literals. `check_ui.py` gains it as a step. TOKENS-2 only sees stylesheet hex (D6).
- **Fonts.** Only through `--font-sans` and `--font-mono` (C11 erratum). `index.html` keeps loading Plex.

## R-11 — Clauses (FR-071, FR-072; D7, L9)

- **Retired clauses** become a bullet tombstone under `## Retired clauses` in `U/app.md`: `- ~~CONSOLE-3~~ retired 018: <reason>`. The checker matches only `#{2,4}` headings (`scripts/check_clauses.py:17`), so a tombstone is neither declared nor untested. Any test still citing a retired id shows as dangling, which is the signal wanted.
- **Rewritten clauses** keep their number when the intent survives on a new surface (for example CONSOLE-24, Cost, now in the rail). The heading text changes and a `(rewritten 018: …)` line follows it.
- **New clauses** start at CONSOLE-30. V-corrections are `### CONSOLE-3x` with the V number first in the body, for example "V1 — …", so they are greppable.
- **Test placement.** CONSOLE citations count only in `*.pw.ts` and `*.spec.ts` (`check_clauses.py:46`). `U/app.pw.ts` (548 lines) is split by screen in slice 1: `app.shell.pw.ts`, `app.run.pw.ts`, `app.inbox.pw.ts`, `app.fleet.pw.ts`, `app.board.pw.ts`, `app.graphs.pw.ts`, `app.compare.pw.ts`, `app.interfaces.pw.ts`. `playwright.config.ts` already matches `**/*.pw.ts`.
- **The V bar (FR-072, SC-002).** The checker proves citation, not failure on revert (D7). Each V test asserts the corrected behaviour together with the absence of the wrong one on a fixture that would show it. For example, V1: a halted fixture run shows the failed sink with its result string, and no element carries a `halted` label. The reviewer verifies, per V clause, that reverting the adapter line makes the test fail. This is recorded in verification.md.

The full clause disposition table is [contracts/clauses.md](contracts/clauses.md).

## R-12 — Library vs app (D8)

| Piece | Lives in |
|---|---|
| Outcome sinks, port anchors, edge labels, dot grid, traversal pill | `U/src/components/graph_canvas` (extended: `CanvasNode.kind?: 'node' \| 'sink'`, no domain type) |
| Rail frame (run block, segmented tabs, list rows, cost bars) | new library component `rail` |
| Decision card shell (kicker, schema chip, title, where, fields, text area, actions with consequence titles, foot) | new library component `decision_card`. `gate_decision` stays for any remaining canvas use until slice 3 retires it. |
| Inner-loop step list | new library component `step_list` |
| Kanban | new library component `kanban` |
| Command palette | new library component `command_palette` |
| ⋯ menu | new library component `toggle_menu` |
| Heatmap | new library component `heatmap` (cells: value / low_n / blank) |
| Matrix grid (Interfaces) | new library component `check_matrix` |
| Catalog card | new library component `catalog_card` |
| Header | `U/src/components/app_header` rebuilt (APP_HEADER clauses rewritten) |
| Toasts | `U/src/components/toasts` reconciled (TOASTS clauses rewritten) |
| Footer | new library component `footer_bar` |
| Card kind → actions and copy | `F/shared/decisionCard.adapter.ts`, used by the inbox and run screens (D8: not inside `features/inbox`) |
| Session prefs, theme wiring, run in context | `F/app/prefs.store.ts`, `F/app/App.vue` |

Each new library component follows the five-file rule: `.vue`, `.md`, `.profiles.ts`, `.spec.ts`, `.pw.ts`. Each is registered in `U/showcase/registry.ts` and exported from `U/src/index.ts` (FR-081).

## R-13 — Backend module placement (L10.2)

`D/graph_wire.py` is 579 lines and `D/api.py` is 382. New wire models and builders go in new modules:
- `D/fleet_summary.py` (R-6);
- `D/catalog_wire.py` (R-7);
- `D/interfaces_wire.py` (R-8);
- `D/compare_wire.py` (R-9).

Routes register on the existing router through one small `D/read_routes.py`, added from `create_router`. No file under `src/sdlc/benchmarks/`, `src/sdlc/stages/`, `src/sdlc/workflows/`, `src/sdlc/harness/` or `src/sdlc/core/` is modified (FR-061, SC-007). A guard test lists the branch diff's paths against a deny-list.

## R-14 — Mock provider and fixtures (B6, FR-063)

`F/api/mock/index.ts` is 539 lines. New fixtures and mock methods go in new files under `F/api/mock/` (`fleetSummary.ts`, `shippedGraphs.ts`, `interfaces.ts`, `compare.ts`). Each holds at least one fixture per edge case its screen must render:
- `not measured` cells;
- an empty compare;
- a `custom` graph;
- a halted-into-failed run (V1);
- an escalated run (V2);
- a multi-sink completion (V3);
- the tool, budget and task cards.

Python wire models are pinned by recorded fixtures under `F/api/__fixtures__/` with a freshness test, as `tests/test_graph_fixtures_fresh.py` does today. Existing graph fixtures are not regenerated: `CatalogWire` and `graph_wire.Capabilities` are not changed (L2).

## R-15 — "Run this version" (S4, FR-054; advisor round 2 c)

`POST /runs` (`D/api.py:348-382`, `StartBody`) takes no graph. The server picks a shipped graph from `PipelineConfig` through `graph_catalog`. A custom saved sha cannot be started without a new write parameter, which B5 forbids. So:
- "Run this version" is enabled only when the canvas holds the shipped `default` graph, unchanged and saved. It opens the existing start form (title, description, mode, repo, budget; CONSOLE-28 survives).
- On any other sha it is disabled, with the reason "the server starts the shipped default graph only".

This is flagged for GATE 2 as the one place v5 draws behaviour the server lacks.

**The alternative, if the user wants v5's full behaviour** (advisor round 2 (c)):
- add `graph_sha: str | None` to `StartBody` and `StartRunInput`;
- the dashboard starter loads the sha from `GraphStore` and builds the `GraphRunInput` with the same checks as `build_run_input`, duplicated in `D/` and pinned by a parity test for the three shipped graphs. `src/sdlc/workflows/` stays untouched;
- an unhonoured sha is a 422, never a silent fallback to `default`.

This changes a write route, so it needs a user ruling against B5. It is not planned unless that ruling is given.

## R-16 — Environment for the host dashboard (advisor item 7)

Registry discovery, the containment policy and `runs/` are all cwd-relative. The quickstart and the README name the variables to set (`SDLC_RUNS_ROOT` if present in code, else cwd at the repo root; `KROKER_RUNS_BIND` for compose). Each new route reports the root it read in its empty state, so a configuration gap reads as such, not as a data bug.
