# Feature Specification: Dashboard rework to the Pipeline Canvas v5 design

**Feature Branch**: `018-canvas-v5-ui` (spec directory only; the branch is cut at T001, per the brief)

**Created**: 2026-10-26

**Status**: Approved (2026-10-26). GATE 1 cleared: Q1–Q5 = A (see [GATE 1 rulings](#gate-1-rulings)). It was then narrowed by the user's **v5-only** scope ruling (see [Scope ruling](#scope-ruling--v5-only-user-2026-10-26-after-gate-1), S1–S14), which supersedes the requirements it names. The options not selected are kept below as the record of the fork and are not to be planned.

**Input**: TASK BRIEF "round 018: full dashboard rework per Pipeline Canvas v5" (`.workspace/tmp/r018-task-brief.md`), relayed by the orchestrator on 2026-10-26. The user's ruling of the same day is to rework the dashboard UI fully to the v5 design.

**Base**: specced on main `0acfccde`; re-based at GATE 1 to main `07232332`. The foreign diff (N7) landed on main as `43482262`, `d203ccdb` and `07232332`. T001 cuts `018-canvas-v5-ui` from the current main head (`07232332` or newer — check `git log` first).

## Binding rulings (from the brief, not re-opened here)

- **B1 — Full rework to v5's information architecture.** The current by-screen dashboard (Fleet, Inbox, and a run page with Graph · Board · Cost tabs) is replaced, not reskinned. Inbox and Board are reachable from the top navigation (brief §3 correction).
- **B2 — V1–V10 adopted as-is.** They are code corrections, not matters of taste (feedback report §7).
- **B3 — V11 through the token system.** v5's dark, dense visual language enters only as new or adjusted token values in `interfaces/ui/src/tokens/`. No IBM Plex and no raw literals beside components. FR-1400 to FR-1406 stand: clause contracts per component, named showcase profiles, browser verification through `scripts/check_ui.py`.
- **B4 — The Gates tab is absorbed.** FR-601 closes in this round.
- **B5 — A thin, read-only API tail is in scope.** Additive dashboard read routes over existing stores only. No record-builder changes, no workflow changes, no new record fields. A cell with no source renders `not measured` (FR-915) and is never invented.
- **B6 — Mock fixtures for every new wire contract.** `VITE_API=mock` covers each one, and the fixtures are the test data.
- **B7 — Invisible to the parallel benchmark round.** Nothing under `src/sdlc/benchmarks/` record builders, `src/sdlc/stages/`, or anything that changes run or worker behaviour.
- **B8 — Foreign diff.** The primary tree carries a foreign uncommitted diff. It is never staged, committed, reverted or edited (see finding N7 for its actual extent).
- **B9 — Standing rules.** The 1000-line ceiling per file. The component library imports no domain type, and mapping lives in the dashboard's adapters. Backend work rides the existing dashboard app and keeps the stateless-shell rule (ADR-8 as amended, shared poller precedent).

## Scope ruling — v5 only (user, 2026-10-26, after GATE 1)

**Ruling** (relayed by the orchestrator): "мы делаем только v5 дизайн" — we build only the v5 design. Anything the spec or the GATE 1 rulings kept that v5 does not draw is cut, or reshaped to v5 as drawn. The only exception is what a standing repo contract forces:
- FR-601 must close;
- a shipped capability must not regress. Spec 011's Cost facts and spec 010's inbox kinds are named; spec 002's board detail is treated the same way.

Where a forced item has no v5 home, it goes into the nearest v5 surface. This table supersedes every requirement it names. The requirements are rewritten in place below.

| # | Before this ruling | After (v5 as drawn) | Forced by |
|---|---|---|---|
| S1 | Four run views: Graph · Board · Gates · Cost | **Graph · Board only.** The run's side panel (rail) carries Path · Events · Cost. | v5 header `runTabs` |
| S2 | A Gates view closes FR-601 | **FR-601 closes through v5's per-run decision surface.** The rail shows a "waiting on you" call to action for each of the run's pending items, each opening its decision card over the canvas, as v5 does for the tool escalation. The Events section lists the run's gate decisions where existing data carries them. No Gates tab. | FR-601 (open requirement) |
| S3 | Cost view kept, rail summarises | **The Cost tab is retired. The rail's Cost section is the cost surface.** It carries every spec 011 fact: per-role calls, tokens and dollars, "not priced", a partial total, and the budget's counted, crossings and uncounted figures. These go in v5's per-role and per-stage groups plus the rail's budget block. `?tab=cost` opens the run with the Cost section selected. CONSOLE-24 to CONSOLE-26 are rewritten onto the rail. | spec 011 FR-001/FR-003 (shipped) |
| S4 | Header rebuilt with stats, start run, and theme kept per browser | **v5's header only.** Wordmark, primary nav, secondary nav, run switches, Search ⌘K and ⋯. There are no header run counter, spend stats or Start-run button. CONSOLE-2 is narrowed to the inbox badge. The fleet spend total (spec 011 FR-003) moves to v5's footer, and CONSOLE-27 is rewritten there. The Start button stays until Design's start lands (slice 6), so no window opens without a start path. Starting a run is v5's "Run this version" in Design, which opens the existing start form, with its budget field, for the saved graph. The theme toggle in ⋯ is not persisted. | v5 header, Design toolbar |
| S5 | FU-1 "absorbed" | **FU-1 is superseded, not built as written.** Its wordmark, tab labels and Start-run button are replaced by v5's header. Its theme toggle becomes v5's ⋯ "Light theme". Its toast becomes v5's bottom-centre toast. | — |
| S6 | Fleet with graph sha, last canonical stage and stage strip | **v5's Fleet columns exactly:** Run, Graph, Arm, Outcome, Where / reason, revise traversals, Cost, Elapsed, Open. The stage strip is retired (CONSOLE-3), on the reading that the Observe canvas is PRD FR-601's "per-run stage spine" (GATE 2 item). | v5 Fleet |
| S7 | Board view restyled with list, detail, timeline, versions and counters | **v5's run Board is a kanban by wire status (V7), with an "Open full Agent Board →" link.** The link opens the shipped board (list, detail, evidence, timeline, versions, counter strip) at its own address. | spec 002 board (shipped); v5 draws the link |
| S8 | Graphs with a configuration set per graph | **v5's Graphs:** catalog cards (sha, name, description, when-used, node, gate and edge counts, "Open in Design"), plus one PipelineConfig panel with checks (`validate_run_roles`, `check_node_types`, `containment`) and sections (roles, proposer roles, gates, limits, arms). | v5 Graphs |
| S9 | Design-mode config | **v5 draws per-node PipelineConfig controls in the Design inspector. They render read-only, showing the configured values.** No write route exists and B5 forbids one. | B5 |
| S10 | Compare by graph and configuration, with the pre-registered rule | **v5's Compare:** arms × the two research graphs (SC and $/case per graph), the description line (SC weights, judge), and the "Rework by canonical_stage" heatmap. The configuration dimension and the pre-registered rule are cut. | v5 Compare |
| S11 | Command palette searches runs and graphs | **v5's palette searches commands only.** Review a pending decision, open Inbox, open Fleet, open the run board, switch Observe/Design, design a graph, validate, fit, Compare, Interfaces. Live data fills the labels. | v5 `commands()` |
| S12 | — | **v5's footer bar** (context left, hints right) is in scope. | v5 footer |
| S13 | Inspector with cost and canonical stage | **v5's Observe inspector:** state, activations, configured and answering model, emitted claim-check refs, history, the read-only inner loop, and ports. | v5 inspector |
| S14 | Inbox cards | **v5's card form** (kicker, schema chip, title, where, fields, text area, actions, foot) for v5's kinds plus the forced ones. The merge override and task escalation are forced by spec 010 (shipped). The per-task gate and the budget gate are forced by B2 (V5, V6). | spec 010, B2 |

| S15 | Graph editor with YAML text pane and schema-form node fields | **v5's Design has neither.** Editing is on the canvas: drop, connect, edge `max_traversals` and delete, with read-only knobs (S9). The text pane is removed and CONSOLE-7 is retired. The parse and serialize routes stay served (Design's round trip uses parse). | v5 Design inspector *(added at plan, 2026-10-26)* |
| S16 | — | **v5 also draws** a third rail Cost group, "Revise traversals" (used/max per revise edge, from the graph state's back-edge counts), and a Fleet action label of "Decide" on rows blocked on a gate ("Open run" on the run in context, "Open" otherwise). Both are in scope, because v5 draws them. *(added at plan review, 2026-10-26)* | v5 `costGroups`, Fleet `openLabel` |

GATE 1 rulings still stand where this table does not touch them: Q1 (one round, by screen), Q2 (one canvas, two addresses), Q3 (Board as a run view) and Q5 (Interfaces). Q4 is reshaped by S4 and S5.

## Context and verified findings

Every claim below was checked by reading the code on main `0acfccde` and the v5 prototype. Nothing was run. `F/` = `interfaces/dashboard/frontend/src/`. `V5` = `docs/reports/Pipeline Canvas v5 (standalone).html`, read through its embedded template and script.

| # | Claim | Verified state | Consequence for this spec |
|---|---|---|---|
| C1 | The app has four routes | **True.** `/` Fleet, `/inbox`, `/runs/:id` (RunPage, `?tab=`), `/graphs` (`F/app/router.ts`). | All four are replaced or re-homed (FR-001). |
| C2 | The run page has Graph · Board · Cost tabs, and Gates is disabled | **True.** `F/features/run/RunView.vue:63-90`. Gates is disabled by ruling G7 of spec 002. Cost landed in spec 011. | FR-020 to FR-023. |
| C3 | The header shows the old pass-two look | **True.** `interfaces/ui/src/components/app_header/AppHeader.vue:27-56`: wordmark `SDLC·FACTORY`, upper-case tabs FLEET / INBOX / GRAPHS, no theme toggle. This is the parked 002 follow-up FU-1. | Q4. |
| C4 | The inbox wire has four item variants | **True.** `ClarifyItem`, `GateItem` (with a free `gate` name), `OverrideItem` and `EscalationItem` (`F/api/types.ts:64-122`). The backend's `PendingKind` is `gate · clarify · escalation` (`src/sdlc/graph/run_view.py:42`). | FR-030 to FR-034, N3. |
| C5 | The run outcome set includes `escalated` and has no `halted` | **True.** `OutcomeState = running · completed · rejected · escalated · failed` (`src/sdlc/graph/run_view.py:43`). | V1, V2 (FR-012). |
| C6 | The catalog wire already carries the canonical stage order | **True.** `canonical_stages=list(CANONICAL_STAGES)` (`src/sdlc/dashboard/graph_wire.py:176`). The list has 18 members (`src/sdlc/benchmarks/heatmap.py:33`). | V9 needs no new route (FR-043). |
| C7 | Harness containment layers are declared in code | **True.** `claude_code` declares native and hook (`src/sdlc/harness/claude_code.py:77`). `opencode` declares native only (`src/sdlc/harness/opencode.py:83`). `HarnessKind` is `claude_code · opencode · cursor · crew` (`src/sdlc/core/models.py:26`). | Interfaces cells (FR-050, Q5). |
| C8 | Graph "Capabilities" exist on the wire | **Partly.** `graph_wire.Capabilities` holds graph-editor capabilities (`validate`, `save`, `load`, `run_graph`), not harness capabilities. No harness-capability wire exists. | FR-050 needs one new read route. |
| C9 | The dashboard API serves runs, inbox, decisions, graphs and run graph state | **True.** `src/sdlc/dashboard/api.py:133-348`: `/runs`, `/runs/{id}`, `/inbox`, `/events`, `answer`, `decide`, `/graphs/catalog\|parse\|serialize\|validate`, `POST /graphs`, `/graphs/{sha}`, `/runs/{id}/graph`, `/runs/{id}/graph_state`, `POST /runs`. Board routes are served at `/projects/*`. | Compare, the graphs catalog and Interfaces have no route yet (FR-060). |
| C10 | The console contract stands at CONSOLE-29 | **True.** `interfaces/ui/app.md` ends at CONSOLE-29. | FR-071. |
| C11 | Tokens are pass three | **True, and closer to v5 than the brief assumes** *(erratum, plan phase 2026-10-26)*. `interfaces/ui/src/tokens/tokens.css` is 67 lines, with a dark default, a light scope and the TOKENS-4 aliases. Its grounds, lines, inks and status values are already v5's `THEMES` values: `#0a0c10`, `#0d1015`, `#151a22`, `#1d232d`, `#2b3341`, `#b79de0` waiting violet, and the whole light set. `--font-sans` and `--font-mono` already name IBM Plex Sans and IBM Plex Mono, which `interfaces/dashboard/frontend/index.html` loads. What v5 adds that tokens lack is canvas-specific: node fill, node line, wire, dot grid, and per-status tints for done and running backgrounds. | FR-080 is reworded: the rule is "fonts only through the font tokens", not "no IBM Plex". |

**Findings not in the brief.**

- **N1 — v5's navigation is not the one the brief describes.** The brief names "Pipeline (Observe/Design), Runs, Graphs, Interfaces, plus Inbox and Board". That is v4's top bar plus the feedback report's §3 correction. V5 itself already absorbed that correction, and its header is different:
  - primary: **Fleet**, **Inbox** (with a pending badge), and **Run ‹id›** (the run in context);
  - secondary: **Graphs**, **Compare**, **Interfaces**;
  - on the run screen, a **Graph · Board** switch and, on Graph, an **Observe · Design** switch;
  - a **Search ⌘K** command palette and a **⋯** display menu with four toggles: payload on every edge, terminal routes for every node, dot grid, light theme.

  This spec builds v5's actual navigation. "Runs" is v5's Fleet. "Pipeline" is the run screen's canvas. Board is reachable from the header through the run in context (Q3).
- **N2 — v5 has no Gates and no Cost tab.** V5's run screen has only Graph · Board. Cost moved into the run rail as one of its three tabs (Path · Events · Cost). B4 requires a Gates tab and spec 011's Cost tab is on main. *(Superseded by S1–S3: the run views are Graph · Board. FR-601 closes through the rail's per-run decision surface. The Cost tab is retired into the rail.)*
- **N3 — Some v5 cards have no distinct wire variant.** *(Erratum, plan phase: they do. The tool escalation is a `GateItem` with `gate` `tool_approval`, and the budget gate is a `GateItem` with `gate` `budget`. The "task escalation" and the "per-task gate" are one backend item (`TaskEscalationPending`, gate `task:<id>`), so they are one card with approve, revise (+ thaw tests) and reject. See research R-3. The original text follows as the record.)* V5 shows a **tool escalation** card (approve / deny for one deferred call, V4), a **per-task gate** `task:<id>` (V5) and a **budget gate** (V6). The wire has one `EscalationItem` (retry / quarantine) and one `GateItem` with a free `gate` name. The plan must establish, from existing backend data, how each card is told apart. Any distinction that the existing data cannot supply is rendered as the generic card of its wire variant, never guessed (FR-034).
- **N4 — Some Interfaces cells have no source the dashboard process can read.** "Installed on worker" is measured by `sdlc doctor` inside the worker, not the dashboard. "Checkpoint commit" and "session capture" are adapter behaviours, not declared data. Declaring them would touch `src/sdlc/harness/`, which B7 forbids (Q5).
- **N5 — Gate history on the Gates tab.** *(Erratum, plan phase: `GraphState` carries no decisions. History comes from `RunState.decisions` on live runs and `RunSummary.gates` on closed runs. The client's closed-run mapper drops the latter today and is fixed. See research R-4. The original text follows as the record.)* Spec 010 N3 found that the live client sets every run's decision list to empty. Past decisions are visible on graph runs through the run graph state's events. They are not visible on runs that predate graph execution. The Gates tab therefore shows past decisions only where the existing graph state carries them, and says so otherwise (FR-022).
- **N6 — v5's mock data predates the registry update.** V5 uses `glm-5.2` arms, `claude-sonnet-4.5` arm names (V10) and a `$25` budget (V6). Round 017 retired the glm-5.2 smoke arms. Every model id, arm and budget shown must come from live or fixture data read verbatim, never from v5's literals (FR-014).
- **N7 — The foreign diff is wider than the brief lists.** *(RESOLVED at GATE 1: the diff landed on main as `43482262`, `d203ccdb` and `07232332`. Kept as the record. FR-075 now guards only what is still uncommitted in the primary tree when the branch is cut, for example the untracked `.claude/settings.json` and `tests/test_compose_opencode_cache_mount_net.py`.)* Besides `agents/{adversary,discover,risk}/agent.yaml` and `tests/test_agents_registry.py`, the tree also carries modifications to `pyproject.toml`, `uv.lock`, `src/sdlc/agents/loader.py`, `src/sdlc/workflows/graph_dispatch.py`, `tests/durability/test_activity_fixture.py`, `tests/durability/test_worker_registration.py` and `.specify/specs/017-baseline-unlock/finding-1of56.md`. It also has untracked `.claude/settings.json`, `tests/durability/_upgrade_delta.py` and `tests/test_compose_opencode_cache_mount_net.py`. B8 covers all of them. T001 stages only the two prototype HTML files and this spec directory.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Watch a run on the Observe canvas (Priority: P1)

An operator opens a run and sees its graph exactly as it ran:
- every node with its status;
- port-to-port edges, with traversal counters on revise edges;
- the outcome sinks (completed, rejected, failed, escalated);
- a right-hand rail with the path reached and not reached, the events newest-first, and spend against the optional budget;
- a "decision waiting" call to action when the run is blocked on a person.

Selecting a node opens an inspector with:
- its typed inputs and outputs;
- the model that was configured and the model that answered;
- its cost and its canonical stage;
- its history.

The `code` node opens a read-only view of the per-task loop.

**Why this priority**: The run canvas is the centre of v5 and the screen operators spend most time on. Every V-correction except V7, V8 and V10 is visible here.

**Independent Test**: With the mock provider, open a fixture run in each outcome state. Check that:
- each state's sink is lit;
- the revise counters read their fixture values;
- the inspector of a node with a run override shows both model ids;
- the `code` drill-down lists the loop steps without any edit control.

**Acceptance Scenarios**:

1. **Given** a run that ended on a `halt` port, **When** the operator opens it, **Then** the **failed** sink is lit and shows the node's result string (for example `failed:quarantined-tasks`), and no `halted` sink exists (V1).
2. **Given** a revise edge at its `max_traversals` limit, **When** the operator looks at it, **Then** it states that the next revise escalates the run. **Given** a run that escalated, **Then** the **escalated** sink is lit (V2).
3. **Given** a run that completed through more than one edgeless non-terminal port, **When** it is shown, **Then** the completed sink lists every sink node (V3).
4. **Given** a run with `run_budget_usd` = 0, **When** the rail shows spend, **Then** the budget reads "off" and no percentage is drawn. **Given** a run with a budget set, **Then** spend is shown against it (V6).
5. **Given** a node whose configured model differs from the one that answered, **When** its inspector opens, **Then** both ids are shown verbatim and the difference is marked.
6. **Given** the `code` node, **When** the operator opens its drill-down, **Then** the task loop is shown read-only: worktree, harness session, test freeze, tool escalation, review and QA, repair budget, per-task gate, and board claim.

---

### User Story 2 - Decide everything waiting, from the Inbox and from the run's rail (Priority: P1)

*(S2: "the run's Gates view" below means the rail's per-run decision surface: one "waiting on you" call to action per pending item of the run, each opening its card over the canvas, plus the Events section for past decisions. There is no Gates tab.)*

An operator sees every item waiting on a person across runs, as a card that matches its real kind:
- a clarify question (answer, or accept the suggestion);
- a gate (approve, revise with guidance, reject);
- a merge override;
- a tool escalation (approve or deny one call; a timeout counts as deny);
- a task gate `task:<id>`, which is also what the inbox called a task escalation (one backend item, N3 erratum). Its actions are approve (accept as done), revise with guidance and an optional "thaw tests" (retry), and reject (quarantine, stating that the build ends `failed:quarantined-tasks` after the wave);
- a budget gate (approve one more increment, or reject, which ends the run `rejected:budget`).

On a run's page the Gates view shows the same cards for that run alone, plus the past decisions the run's graph state carries.

**Why this priority**: Decisions stop runs. FR-601 closes on the Gates view (B4). V4, V5 and V6 are card corrections.

**Independent Test**: With the mock provider, resolve one fixture item of each card kind from the Inbox, and one from a run's Gates view. Each leaves both lists and the header badge drops each time.

**Acceptance Scenarios**:

1. **Given** a tool escalation, **When** the operator reads the card, **Then** it offers Approve and Deny only, shows the rule id, and states the timeout behaviour. No Halt action exists (V4).
2. **Given** a per-task gate, **When** the operator rejects it, **Then** the card has already stated, before the action, that the task is quarantined and the build ends `failed:quarantined-tasks` after the current wave (V5).
3. **Given** a budget gate, **When** the operator reads it, **Then** approve is described as one more increment and reject as ending the run `rejected:budget` (V6).
4. **Given** a run with pending items, **When** the operator opens its Gates view, **Then** exactly that run's items are shown with the Inbox's actions. **Given** it has none, **Then** an explicit empty state is shown.
5. **Given** a graph run with decided gates, **When** the Gates view opens, **Then** past decisions are listed in the rail's Events from data the backend already holds. **Given** a run for which no such data exists, **Then** the rail says decision history is not available for this run, rather than showing an empty history (N5).
6. **Given** any spec 010 inbox behaviour (CONSOLE-17 to CONSOLE-23), **When** the reworked Inbox is used, **Then** that behaviour still holds. This covers run-and-key scoping of drafts, races that were already decided, and survival of typed text across a refresh.

---

### User Story 3 - See the fleet of runs and their outcomes (Priority: P1)

An operator lands on Fleet. Each run shows v5's columns (S6):
- run;
- graph;
- arm (harness × model id, verbatim);
- outcome, with the result string;
- where it is, or the reason it ended;
- revise traversal counts;
- cost and elapsed time;
- an Open action.

Outcomes use the real set (running, completed, rejected, escalated, failed), including `rejected:budget`. From a row the operator opens the run.

**Why this priority**: It is the landing screen and the entry to everything else.

**Independent Test**: With the mock provider, check that every fixture outcome renders with its result string and that a row opens its run.

**Acceptance Scenarios**:

1. **Given** fixture runs in each outcome, **When** Fleet opens, **Then** each shows its outcome and result string, and no run shows `halted` (V1).
2. **Given** a run, **When** the operator reads its arm, **Then** the model id matches the run's data byte for byte (V10, N6).
3. **Given** a run whose cost is unpriced, **When** Fleet renders it, **Then** the cost cell reads `not measured` (or the existing unpriced wording), never `$0.00`.

---

### User Story 4 - Watch a run's task board (Priority: P2)

On a run's Board view the operator sees v5's kanban (S7): one column per wire status present (`pending · in_progress · done · failed · blocked · quarantined`), each with a count. Each task card shows its id, its live status (with the authoritative status beside it when they differ) and its fix attempts. "Open full Agent Board →" opens the shipped board at its own address, and every one of today's Board tab behaviours lives there (detail, evidence, timeline, versions, counter strip).

**Why this priority**: The board exists and works. This story restyles it and corrects v5's invented statuses (V7).

**Independent Test**: With the mock provider, check that the board fixtures render every wire status and that no `claimed` or `queued` label appears.

**Acceptance Scenarios**:

1. **Given** a task whose live status differs from its authoritative status, **When** it is shown, **Then** both are visible (V7).
2. **Given** every existing Board behaviour (spec 002 FR-019 to FR-024), **When** the reworked Board view is used, **Then** the behaviour still holds.

---

### User Story 5 - Read and design graphs (Priority: P2)

On Graphs (S8) the operator sees the catalog of shipped graphs (`default`, `default-research`, `seeded`) as cards. Each card shows its sha, name, description, when it is used, its node, gate and edge counts, and "Open in Design". Beside the cards, one PipelineConfig panel shows:
- three checks, each pass, fail or off: `validate_run_roles` (ADR-6), `check_node_types`, `containment`;
- sections for roles (harness × model), proposer roles (model ids), gates (policy, threshold, `on_timeout`), limits (`max_fix_attempts`, `max_tool_escalations`, `max_gate_rounds`, `run_budget_usd`, `gate_timeout_hours`) and arms.

In Design mode the operator edits a graph on the same canvas as Observe:
- a palette from the node-type catalog grouped by `canonical_stage`, with planned types shown dashed and unplaceable;
- connections refused at drop time on a payload mismatch;
- a validation panel matching the backend validator;
- save, undo and redo;
- "Run this version" disabled while there are errors or unsaved changes.

**Why this priority**: The editor exists today (`F/features/graphs/`). The rework re-homes it onto the shared canvas and adds the catalog and configuration read.

**Independent Test**: With the mock provider:
1. open Graphs and check each shipped graph's card and the PipelineConfig panel;
2. switch to Design and try a mismatched connection, which must be refused;
3. place a planned type, which must be refused;
4. save a layout-only change and confirm the sha is unchanged.

**Acceptance Scenarios**:

1. **Given** the registry where reviewer and dev share a provider prefix but run the same weights, **When** the ADR-6 check is shown, **Then** it reads "family check passes on prefix · same model weights" with the real ids from the registry (V8).
2. **Given** a mismatched drop, **When** the operator releases it, **Then** no edge is created and the reason is shown.
3. **Given** a planned node type (for example `outcome.watch`), **When** it is shown in the palette, **Then** it is marked planned. If it has no canonical stage, it is labelled unmapped (V9).
4. **Given** a layout-only change, **When** it is saved, **Then** the content sha is unchanged. **Given** an edge change, **Then** the sha changes on save.
5. **Given** the validation copy for terminal reachability, **When** it is shown, **Then** it reads "rejected, failed or escalated" (V2), and an edgeless non-terminal port warns that it becomes a completion sink (V3).

---

### User Story 6 - Compare arms and graphs (Priority: P3)

On Compare (S10) the operator sees benchmark arms (harness × registry model id, verbatim) against the graphs present in the records (v5 draws `default` and `default-research`). The screen shows:
- the SC composite and $/case per graph;
- a description line with the SC weights and the judge, read from the records;
- the "Rework by canonical_stage" heatmap, ordered by `CANONICAL_STAGES` and showing only the stages present in the data (V9).

Everything is read from stored benchmark records and score outputs.

**Why this priority**: Useful but read-only, and it depends on a new read route.

**Independent Test**: With the mock provider, compare two fixture arms. Check that a cell with no stored value reads `not measured`, and that heatmap columns follow canonical order.

**Acceptance Scenarios**:

1. **Given** an arm with no cost in its stored records, **When** Compare shows it, **Then** the cost reads `not measured`.
2. **Given** stored records, **When** arm names render, **Then** they equal the record's model ids verbatim (V10).

---

### User Story 7 - Check harness interfaces (Priority: P3)

On Interfaces the operator sees one row per harness (`claude_code`, `opencode`, `cursor`, `crew`, plus `pyai` marked planned) against these columns:
- declared containment layers;
- `containment.strict` outcome;
- model family ≠ reviewer;
- installed on worker;
- checkpoint commit;
- session capture.

Each cell is a measured fact or `not measured`. Real adapter facts are shown underneath: opencode has no hook layer, and cursor surfaces neither layer and fails closed.

**Why this priority**: Informational, and partly blocked on data sources (N4).

**Independent Test**: With the mock provider, check that the declared layers match each adapter's declaration and that every cell without a source reads `not measured`.

**Acceptance Scenarios**:

1. **Given** the opencode row, **When** it is shown, **Then** its declared layers are "native" only, and strict reads that the run refuses to start when a rule needs the hook layer.
2. **Given** a column without a dashboard-readable source (Q5), **When** it is shown, **Then** every cell in it reads `not measured`.

---

### User Story 8 - Navigate quickly and set display preferences (Priority: P3)

From any screen the operator opens a command palette (⌘K or Ctrl+K) that lists and filters v5's commands, filled from live data (S11). A ⋯ menu toggles four display preferences:
- payload labels on every edge;
- terminal routes for every node;
- a dot grid;
- light theme.

Preferences last for the session only; they are not persisted (S4). A footer bar shows context on the left and hints on the right (S12).

**Why this priority**: Convenience. It also wires the light theme scope that has been inert since spec 002 (FU-1).

**Independent Test**: Open the palette, filter to "Open Inbox", and land on the Inbox. Toggle light theme; every colour switches to the light token scope.

**Acceptance Scenarios**:

1. **Given** the palette, **When** the operator filters and confirms a command, **Then** that command runs.
2. **Given** light theme is toggled, **When** the operator looks at any screen, **Then** every colour comes from the light token scope.

### Edge Cases

- **EC1 — run without graph state** (predates graph execution, or retention expired). Observe shows the existing "no graph" or "retention expired" banners. The Gates view says history is unavailable.
- **EC2 — registry drift** degrades the projection (E-77 R-10). The canvas shows the degraded state and names the problems rather than drawing a wrong graph.
- **EC3 — unknown node type or payload** in a stored graph. It is drawn as unknown, never coerced to a catalog type.
- **EC4 — a card kind cannot be told apart from existing data** (N3). The generic card of its wire variant is shown with the wire's own actions.
- **EC5 — a decision raced elsewhere.** Same as spec 010 EC2: the operator is told and nothing is recorded twice.
- **EC6 — benchmark store empty or unreadable.** Compare shows an explicit empty or unavailable state, not a blank grid.
- **EC7 — very large graphs or long event lists.** The canvas stays navigable (pan and zoom), and the event rail is bounded or paged.
- **EC8 — a planned type in a stored graph.** Validation reports "not in NODE_TYPES". The graph is not runnable.
- **EC9 — the provider cannot be reached.** Each screen distinguishes "could not load" from "empty".
- **EC10 — budget off (0).** No percentage and no budget bar overflow. The budget gate card never appears from fixtures with the budget off.

## Requirements *(mandatory)*

### Functional Requirements

**Navigation and shell**

- **FR-001**: The dashboard MUST expose v5's information architecture (N1):
  - primary navigation: Fleet, Inbox (with the pending count), and the run in context;
  - secondary navigation: Graphs, Compare, Interfaces;
  - run views: Graph (with an Observe · Design switch) and Board (S1);
  - the full Agent Board at its own address, reached from the Board view (S7);
  - a footer bar (S12).

  Every view MUST have a shareable address that reopens it.
- **FR-002**: Board MUST be reachable from the header in at most two interactions from any screen (Q3).
- **FR-003**: The header MUST be v5's: wordmark, primary and secondary navigation, the run switches, Search ⌘K and ⋯. It MUST carry no run counter, spend stats or Start-run button (S4). Toasts MUST follow v5's bottom-centre placement on tokens (S5).
- **FR-004**: The previous screens and routes MUST be removed once their replacement lands. No dead route or unused screen folder remains at the end of the round. An old address MAY redirect to its replacement.

**Run canvas — Observe**

- **FR-010**: Observe MUST draw the run's stored graph as port-to-port edges with multi-input nodes and labelled port anchors. It MUST show each node's status, and the traversal count against `max_traversals` on every revise edge.
- **FR-011**: Observe MUST show outcome sinks for completed, rejected, failed and escalated, and MUST NOT show a `halted` sink. A `halt` port routes into failed, which shows the node's result string (V1).
- **FR-012**: A revise edge at its limit MUST state that the next revise escalates the run. An escalated run MUST light the escalated sink (V2).
- **FR-013**: The completed sink MUST list every node whose edgeless non-terminal port completed the run (V3). Unrouted failure MUST be shown as a failed outcome naming the node and port.
- **FR-014**: Every model id, arm, harness and budget shown anywhere MUST come from run, registry, record or fixture data, read verbatim. None MAY be copied from the prototype (V8, V10, N6).
- **FR-015**: The run rail MUST show v5's run block (id, state, graph · sha, arm, mode, elapsed, budget) and three sections:
  - Path: reached and not-reached nodes;
  - Events: newest-first, built only from event sources the backend already holds (for example gate decisions, budget crossings and board task changes). A kind with no source is not shown;
  - Cost: the cost surface (S3).

  Spend MUST be shown against `run_budget_usd`, and as "off" when that is 0 (V6).
- **FR-015a**: The rail's Cost section MUST carry every spec 011 fact the Cost tab carried:
  - per role: calls, tokens and dollars;
  - "not priced" for a figure with tokens and no price, and never `$0.00` for it;
  - a total marked partial when it mixes priced and unpriced roles;
  - with a budget: the budget, the dollars counted toward it, the share of the current limit used, the crossings, and the spend the budget does not count; without one, a statement that there is no budget;
  - "No breakdown recorded" for an old closed run.

  It MUST also show per-canonical-stage cost where existing data carries it. `?tab=cost` MUST open the run with this section selected (S3).
- **FR-016**: The node inspector MUST follow v5 (S13): state, activations, the configured and the answering model (marking a difference), emitted claim-check refs, history, the read-only inner loop for `code`, and ports. A field with no source reads `not measured`.
- **FR-017**: The `code` node's inner loop MUST be a read-only section of the Observe inspector, as v5 draws it ("Inside code · read-only"), not a separate page or modal. It MUST show the real task loop steps (feedback report §2.6) and have no edit control.

**Run views — Board, and the per-run decision surface**

- **FR-020**: The run page MUST host exactly the Graph and Board views (S1). FR-601 MUST close through FR-021 and FR-022 (S2, B4).
- **FR-021**: The rail MUST show one "waiting on you" call to action per pending item of the run. Selecting a canvas node that has a pending item MUST open the same card (PRD FR-1205: the gate action stays on the canvas, as v5's `openDecision` draws it). Each MUST open that item's card over the canvas, with exactly the Inbox's card and actions, built from the same shared components and not by importing the Inbox screen.
- **FR-022**: The rail's Events section MUST list the run's past gate decisions only from data the backend already holds:
  - live runs: human decisions only, timed;
  - closed runs: all decisions, untimed, approve or "not approved".

  On an open run it MUST state that automatic and timed-out decisions appear only when the run ends (research R-4). Where no source exists, it MUST say that decision history is not available for this run (N5).
- **FR-023**: The Board view MUST be v5's kanban by wire task status, with live and authoritative status distinguished (V7) and an "Open full Agent Board →" link. The full Agent Board MUST keep every behaviour of today's Board tab (spec 002 FR-019 to FR-024) at its own address (S7). `?tab=board` MUST open the Board view.

**Inbox and decision cards**

- **FR-030**: The Inbox MUST keep every spec 010 behaviour (FR-001 to FR-012 there; CONSOLE-17 to CONSOLE-23).
- **FR-031**: The tool-escalation card MUST offer Approve and Deny only, show the rule id, and state that a timeout counts as not approved. It MUST NOT offer Halt (V4).
- **FR-032**: The task gate card (`task:<id>`, which replaces the task escalation entry) MUST offer three actions, each sending exactly that `GateOutcome`:
  - approve (accept as done);
  - revise with guidance, with a thaw-tests option (the existing decide path accepts `thaw_tests`), as the retry;
  - reject (quarantine).

  The reject consequence MUST be stated before the action (V5). Retry MUST NOT be sent as approve (research R-3: today's mapping does exactly that).
- **FR-033**: The budget gate card MUST describe approve as one more increment and reject as ending the run `rejected:budget` (V6).
- **FR-034**: Each card kind MUST be told apart only from data the backend already produces. A kind that cannot be told apart MUST fall back to its wire variant's generic card (N3, EC4). The plan MUST list the source used for each card kind before any file is written.
- **FR-035**: Every card MUST state its timeout behaviour where the gate's configured `TimeoutAction` is available. It MUST NOT show an invented countdown.

**Fleet**

- **FR-040**: Fleet MUST show v5's columns per run (S6): run, graph, arm, outcome with result string, where or reason, revise traversals, cost, elapsed and Open. It MUST NOT show the stage strip.
- **FR-041**: Fleet MUST render `rejected:budget` and every other result string as served, and MUST NOT show `halted` (V1, V6).
- **FR-042**: An unpriced or unmeasured cost MUST read `not measured` (or the existing unpriced wording), never zero.
- **FR-043**: Anywhere canonical stages are ordered (cost by stage, palette groups), the order MUST follow the served `CANONICAL_STAGES`, showing only stages present in the data (V9). *(V9 erratum, plan phase; GATE 2 item: Compare's heatmap columns are benchmark record stage names in `CELL_STAGE_ORDER`, a different vocabulary. They are shown in that order, present stages only, with no mapping invented. See research R-9.)*

**Graphs and Design mode**

- **FR-044**: Graphs MUST list the shipped graphs with their content sha. Triage and assessment MUST NOT appear.
- **FR-045**: Graphs MUST show v5's single PipelineConfig panel (S8):
  - checks `validate_run_roles` (ADR-6, V8), `check_node_types` and `containment`, each pass, fail or off, with its reason;
  - sections for roles, proposer roles, gates (policy, threshold, `on_timeout`), limits and arms.

  Every value MUST be read from the configuration, the registry or the records. A value with no source reads `not measured`.
- **FR-045a**: In Design mode the per-node PipelineConfig controls v5 draws MUST render read-only, showing the configured values (S9).
- **FR-046**: Design mode MUST share the Observe canvas. Its palette MUST be built from the served node-type catalog grouped by `canonical_stage`, with planned types visible, marked planned and not placeable.
- **FR-047**: A connection whose payloads are not exactly equal (no `Any`, no subtypes, signal ports only to signal ports) MUST be refused at drop time.
- **FR-048**: The validation panel MUST report, using the backend validator's result:
  - gate shape;
  - required in-ports connected;
  - reachability;
  - bounded cycles (`max_traversals` on every back edge);
  - a path to a terminal outcome.

  The terminal copy MUST read "rejected, failed or escalated". An edgeless non-terminal out-port MUST warn that it becomes a completion sink (V2, V3).
- **FR-049**: Save MUST keep the content sha on layout-only changes. "Run this version" MUST be unavailable while there are errors or unsaved changes.

**Compare and Interfaces**

- **FR-050**: Interfaces MUST show the four shipped harnesses, plus `pyai` marked planned, against the six columns of US7. Declared containment layers MUST come from each adapter's own declaration. The "family ≠ reviewer" column is a property of roles, not harnesses (L5). It MUST be filled only on the row of the registry `dev` role's harness, and read `not measured` on every other row. Every cell without a dashboard-readable source MUST read `not measured` (N4, Q5).
- **FR-051**: Interfaces MUST list the real adapter facts (opencode has no hook layer; cursor fails closed) and MUST NOT carry the prototype's Codex or ResearchAgent examples.
- **FR-052**: Compare MUST show arms (harness × registry model id) by graph, with SC composite and $/case per graph, the description line, and the "Rework by canonical_stage" heatmap (S10). All of it MUST be read from stored benchmark records and score outputs. Missing values read `not measured`.
- **FR-053**: The command palette MUST list v5's commands, filled from live data, and filter them by text. It MUST NOT search runs or graphs by id (S11).
- **FR-054**: Starting a run MUST be v5's "Run this version" in Design. It opens the existing start form, including its budget field, for the saved graph. No other start entry point remains (S4).

**Backend read tail**

- **FR-060**: New backend surface MUST be limited to additive, read-only routes on the existing dashboard app over existing stores:
  - the shipped graphs catalog and the PipelineConfig panel (graph store, `PipelineConfig`, the role registry, benchmark arms);
  - the harness interface matrix;
  - Compare (benchmark records and score outputs).

  Any card-kind distinction under FR-034 MAY be added only as a field derived from existing backend data. No existing route's response may change shape except by additive fields.
- **FR-061**: No change MAY touch benchmark record builders, `src/sdlc/stages/`, workflow code, or anything that changes run or worker behaviour (B7). Reading existing stores through existing read functions is allowed.
- **FR-062**: Every new route MUST follow the stateless-shell rule (ADR-8 as amended) and the existing route style. It MUST be covered by fast-tier tests.
- **FR-063**: Every new wire contract MUST have a mock-provider counterpart and fixtures, and the app-tier tests MUST run on them (B6).

**Visual system and components**

- **FR-080**: v5's visual language MUST enter only as new or adjusted values (and, where needed, new semantic names) in `interfaces/ui/src/tokens/`. No colour, size or font literal may appear beside a component. Font families are reached only through `--font-sans` and `--font-mono`, which already name IBM Plex (C11 erratum). No component or stylesheet outside the token file may name a font family. The dark default and the light scope MUST both resolve every token used. `quarantined` and `skipped` MUST keep distinct status treatments (V11, B3).
- **FR-081**: Every new or reworked presentation component MUST:
  - live in the component library and import no domain type;
  - ship its clause contract, named profiles, logic tests and browser tests;
  - be registered in the showcase;
  - be exported from the package entry (FR-1400 to FR-1405).
- **FR-082**: Every dashboard check MUST run through `python scripts/check_ui.py` only (FR-1406).

**Contracts, coverage and housekeeping**

- **FR-070**: The two prototype HTML files MUST be committed on the branch as spec inputs in its first task.
- **FR-071**: Every shipped behaviour of the reworked screens MUST be stated as console clauses and covered by app-tier tests on the mock provider. Each existing clause CONSOLE-1 to CONSOLE-29 MUST be kept (still true), rewritten (same intent, new screen), or retired (behaviour removed, with a recorded reason), as decided in Q1. No clause may be left dangling or untested.
- **FR-072**: Each of V1 to V10 MUST be covered by at least one named clause whose test fails if the correction is reverted.
- **FR-073**: No file MAY exceed 1000 lines. Screen folders MUST NOT import each other, and the component library MUST NOT import the dashboard.
- **FR-074**: On landing, the ROADMAP's FR-601 entry, the README's dashboard paragraph, the dashboard frontend README and the `interfaces/AGENTS.md` screen-location table MUST describe what is on main. Edits to any `AGENTS.md` are proposed in the plan for the orchestrator's approval.
- **FR-075**: Nothing under the foreign diff (N7) MAY be staged, committed, reverted or edited.

### Key Entities

- **Run view model**: a run's graph, node statuses, emitted ports, traversal counts, outcome (`running · completed · rejected · escalated · failed`) with its result string, spend and budget, and events. Read from the existing run and graph-state reads.
- **Outcome sink**: one of completed, rejected, failed or escalated, with the nodes and ports that reach it.
- **Decision card**: one item waiting on a person, of kind clarify, gate, merge override, task escalation, tool escalation, per-task gate or budget gate, with the actions and stated consequences of that kind.
- **Shipped graph**: name, content sha, description, when used, nodes, gates and edges.
- **PipelineConfig panel**: three checks (pass, fail or off, each with a reason) and sections (roles, proposer roles, gates, limits, arms). It is shared by all graphs and is not part of any graph's sha.
- **Node type**: catalog entry with kind (stage or gate), role or none, canonical stage, typed ports with required flag and terminal outcome, and a planned flag.
- **Harness interface row**: a harness with six cells, each a measured fact or `not measured`, and adapter facts.
- **Compare cell**: an (arm, graph) observation with SC composite, cost and per-stage heat, each measured or `not measured`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every view in v5's navigation (Fleet, Inbox, Run Observe, Run Design, Run Board, Graphs, Compare, Interfaces) is reachable from the header in at most two interactions. That is 8 of 8 views, and each address reopens its view. No view v5 does not draw exists, apart from the full Agent Board reached through v5's own link (S7).
- **SC-002**: Each of V1 to V10 is covered by at least one clause test that fails when the correction is reverted (10 of 10).
- **SC-003**: An operator can resolve every decision card kind from both the Inbox and the run's rail without the CLI. Every kind the existing data can tell apart is demonstrated on the mock provider.
- **SC-004**: Zero colour, size or font literals outside the token files and the page's font loader. The existing token check passes, and no component or component stylesheet names a font family (C11 erratum).
- **SC-005**: Every new wire contract has a mock fixture, and every new read route has a fast-tier test (100% of each).
- **SC-006**: Every cell with no source reads `not measured`. A planted missing value in each new read's fixture produces `not measured`, never zero or a blank.
- **SC-007**: The round's diff touches zero files under benchmark record builders, `src/sdlc/stages/`, workflow code or the foreign-diff paths.
- **SC-008**: `python scripts/check_ui.py` and the Python fast tier are green at the end of every task group. Every console clause is either cited by a passing test or retired with a recorded reason, and none is dangling.
- **SC-009**: No route, screen folder or component left unused by the rework remains on the branch at merge.

## Assumptions

Defaults taken where the brief was silent. GATE 1 may overrule any of them.

- **A1 — v5's actual layout is the target, not the brief's paraphrase** (N1). Where v5 and the feedback report's corrections disagree, the corrections win (B2).
- **A2 — The prototype is a picture, not code.** Nothing is copied from its script. Layout, density and interactions are reimplemented on the component library and tokens.
- **A3** *(superseded by S1–S3)*. The run views are Graph and Board. Decisions and cost live in the rail.
- **A4 — The light theme stays supported.** It is reachable from the ⋯ menu for the session. It is not persisted (S4).
- **A5 — Refresh cadence unchanged.** The existing polling discipline stands. No push channel is added.
- **A6 — Operator identity unchanged.** Decisions stay recorded as `human:unknown` (spec 010 Q3, PRD FR-1004).
- **A7 — Design-mode writes are the existing ones.** Save goes through the existing graph save route. "Run this version" uses the existing start-run route with the saved sha. No new write route is added.
- **A8 — Planned node types and the `pyai` row come from the feedback report's §4.** They are presentation-only, with no backend type.
- **A9 — Accessibility.** Keyboard reach for the navigation, palette, cards and canvas selection is what the library components provide, plus palette keyboard navigation. No further accessibility targets.

## Out of scope

- Any change to benchmark record builders, stages, workflows, or the run and worker path (B7).
- New record fields, and any write route beyond those already served.
- Making the `code` drill-down editable, graph references, sub-graphs, and planned node types becoming real.
- Operator identity and authorisation (FR-1004).
- Installing or probing harnesses from the dashboard process (N4).

## GATE 1 rulings

Cleared 2026-10-26 by the orchestrator, under the user's standing delegation to pick the recommended gate options.

| Q | Ruling | Effect on this spec |
|---|---|---|
| Q1 | **A — one round, built screen by screen** | Each slice ends green and retires the screen it replaces. Each clause CONSOLE-1 to CONSOLE-29 is kept, rewritten or retired, with a recorded reason. No feature flag and no second round. FR-004 and FR-071 are resolved. |
| Q2 | **A — one canvas component, two addresses** | Observe lives at the run's address and Design at the graph's address. The switch moves between them. FR-046 is resolved. |
| Q3 | **A — Board is a view of the run in context** | Board is two clicks from the header. FR-002 is resolved. |
| Q4 | **A — FU-1 fully absorbed** | The header and toasts are rebuilt to v5, and the light theme goes live. FR-003 is resolved, and spec 002 FU-1 closes. |
| Q5 | **A — three Interfaces columns live, three read `not measured`** | `src/sdlc/harness/` stays off-limits. FR-050 is resolved. |
| N1–N4 | Stand as written | v5's real information architecture, four run views, card recognition from existing backend data with a generic-card fallback, and the `not measured` Interfaces columns. |
| N7 | Resolved | See N7 and the Base line. |

The agent-context refresh hook is skipped by ruling.

## Open Questions — GATE 1 (as asked)

### Q1 — Delivery shape and the fate of existing coverage

**Context**: FR-004, FR-071. This is the brief's first open question. 29 console clauses and the screen tests of four routes exist today.

**What we need to know**: one round or phased, and how existing coverage moves.

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **One round, sliced by screen** (recommended). Order: tokens and shell, then Run Observe, then Gates and Inbox cards, then Fleet, Board and Cost, then Graphs and Design, then Compare, Interfaces and palette. Each slice ends green and retires the screen it replaces. Clauses are kept where still true, rewritten where the intent moves to a new screen, and retired with a recorded reason where the behaviour goes. | One branch and one merge. The old and new header never coexist on main. A long branch, but each slice is independently green. |
| B | Two rounds. 018 covers the shell, Run, Gates and Inbox (P1), and 019 covers Graphs, Compare and Interfaces (P2 and P3). | Smaller review units, but main carries a mixed old and new UI between rounds. That contradicts B1's "replaced, not reskinned" for the interim. |
| C | One round with a feature flag. The new UI is built beside the old behind a switch, and the switch flips at the end. | No mixed UI, but double maintenance and a dead-code removal task at the end. |

### Q2 — Observe and Design: one canvas route or two

**Context**: FR-046. This is the brief's second open question. In V5 the run screen's Graph view switches between Observe (the run) and Design (a shipped graph picker). Today they are two routes (`/runs/:id`, `/graphs`).

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **One canvas component, two addresses** (recommended). Observe lives at the run's address and Design at a graph's address. The Observe · Design switch moves between them, and Design opened from a run loads that run's pinned graph. | Shareable addresses for both. It reuses today's editor store and run-graph store, and the canvas is built once. |
| B | One route, exactly as V5: mode is in-page state on the run screen. | Closest to the picture, but Design has no address of its own, and editing a graph without any run in context needs a second entry anyway. |
| C | Two separate features with separate canvases, as today. | Least change, but it contradicts §1 "Observe and Design on one canvas". |

### Q3 — Where Board sits in the navigation

**Context**: B1 says Board is "in the nav". V5 puts Board as a view of the run in context, and the board data is keyed per run's plan (spec 002 FR-021a).

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **A run view reached from the header's run-in-context entry** (recommended). The header holds the run in context, and Board is one of its views (two interactions, FR-002). | Matches V5 and the board's per-run data. With no run in context, the header entry opens the most recent run. |
| B | A top-level Board screen showing a project-wide board with a project picker. | A new cross-run screen over the existing `/projects/*` routes. It is more scope, and it duplicates the run Board view. |

### Q4 — The parked app_header and toasts reconcile (spec 002 FU-1)

**Context**: C3, FR-003. This is the brief's third open question.

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **Fully subsumed** (recommended). The header is rebuilt to V5 (wordmark, sentence-case navigation, theme toggle in the ⋯ menu), toasts are reconciled to V5 placement on tokens, and FU-1 closes in this round. | The old header tests are rewritten under Q1. The light scope finally becomes live. |
| B | Only the header; toasts are left as they are. | FU-1 stays half-open. |

### Q5 — Interfaces cells with no source today

**Context**: N4, FR-050. This is the brief's fourth open question. What the dashboard can derive today, read-only:
- declared containment layers (adapter declarations);
- the `containment.strict` outcome (declared layers against the policy rules' minimum layer);
- model family ≠ reviewer (the registry and the ADR-6 check).

What it cannot derive:
- installed on worker (measured inside the worker);
- checkpoint commit and session capture (adapter behaviour, not declared data).

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **Three derivable columns live; the other three render `not measured`, and the gap is named as a follow-up** (recommended). | Honest under FR-915 and B7. Half of the matrix is grey until a follow-up publishes worker facts. |
| B | Also declare checkpoint and session capture as static per-adapter data in `src/sdlc/harness/`. | Fills two columns, but it touches worker code, which B7 forbids during the parallel round. |
| C | Drop the three underivable columns from the screen. | Cleaner screen, but it departs from V5 and hides the gap. |
