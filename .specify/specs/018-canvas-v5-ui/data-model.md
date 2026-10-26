# Data model: round 018

This file is the only source of new names. A task that needs a name not listed here stops and asks; it does not invent one (the 010 discipline). Existing names are used exactly as they appear in the files cited. `F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. `D/` = `src/sdlc/dashboard/`.

## 1. Existing names this round relies on (copied, not changed)

| Name | File | Use |
|---|---|---|
| `Run`, `Decision`, `RoleCost`, `InboxItem` (`ClarifyItem`, `GateItem`, `OverrideItem`, `EscalationItem`), `StartRunInput`, `DashboardApi`, `GateOutcome` | `F/api/types.ts` | unchanged shapes except §3.1 |
| `GraphStateResponse`, `RunOutcomeWire`, `PendingRef`, `NodeRunState`, `CatalogWire`, `NodeTypeWire`, `PortWire`, `EdgeRef` | `F/api/graph-types.ts` | unchanged |
| `CanvasNode`, `CanvasEdge`, `CanvasPort`, `CanvasStatus` | `U/src/components/graph_canvas/types.ts` | extended additively (§4.1) |
| `RunGraphs`, `RunNotFound` | `D/run_graph.py` | read-only reuse |
| `SHIPPED`, `resolved_roles` | `src/sdlc/workflows/graph_catalog.py` | read-only import |
| `PipelineConfig`, `GatePolicy`, `HarnessKind`, `RunState`, `RunSummary`, `GateOutcomeSummary` | `src/sdlc/core/models.py` | read-only import |
| `check_adr6_families`, `model_family`, `model_id` | `src/sdlc/agents/loader.py` | read-only import |
| `load_policy`, `ContainmentLayer` | `src/sdlc/harness/containment.py` | read-only import |
| `load_evidence`, `build_runs`, `build_grid`, `build_layers`, `CELL_STAGE_ORDER` | `src/sdlc/benchmarks/{evidence,runs,grid,heatmap,models}.py` | read-only import (never `report.py` at module scope) |
| `DecideBody.thaw_tests` | `D/api.py:64` | sent by the task card only |

## 2. New backend wire models (Python, pydantic, `extra="forbid"` like `graph_wire`)

### 2.1 `D/fleet_summary.py` — `GET /api/fleet/summary` (research R-6)

```text
ArmWire            { harness: str | None, model: str | None }
TraversalWire      { edge: EdgeRef(source, source_port, target, target_port), used: int, max: int | None }
GateTimeoutWire    { gate: str, on_timeout: str }
FleetRunSummaryWire{
  run_id: str
  graph_sha: str | None          # None = legacy run (no graph)
  graph_name: str | None         # a SHIPPED name when the sha matches, else None ("custom")
  arm: ArmWire | None            # None = run input unreadable
  traversals: list[TraversalWire]
  outcome: RunOutcome            # reuse graph_wire's outcome model; None for legacy
  where: list[str]               # current node ids, or [] when final
  gate_timeouts: list[GateTimeoutWire]
}
FleetSummaryWire   { runs: list[FleetRunSummaryWire], unreadable: list[str] }
```

### 2.2 `D/catalog_wire.py` — `GET /api/graphs/shipped` (R-7)

```text
ShippedGraphWire   { name: str, sha: str, description: str | None, when: str | None,
                     nodes: int, gates: int, edges: int }
ConfigCheckWire    { name: Literal["validate_run_roles","check_node_types","containment"],
                     state: Literal["pass","fail","off"], text: str }
ConfigRowWire      { k: str, v: str | None }        # None renders `not measured`
ConfigSectionWire  { title: str, note: str, rows: list[ConfigRowWire] }
ShippedGraphsWire  { graphs: list[ShippedGraphWire], checks: list[ConfigCheckWire],
                     sections: list[ConfigSectionWire] }
```

### 2.3 `D/interfaces_wire.py` — `GET /api/interfaces` (R-8)

```text
CellState          = Literal["yes","no","partial","not_measured","planned"]
MatrixCellWire     { state: CellState, text: str }
MatrixColumnWire   { key: str, name: str, ref: str }
MatrixRowWire      { harness: str, sub: str, planned: bool, cells: list[MatrixCellWire] }
AdapterFactWire    { who: str, severity: Literal["warn","error"], text: str }
InterfaceMatrixWire{ columns: list[MatrixColumnWire], rows: list[MatrixRowWire],
                     facts: list[AdapterFactWire] }
```

Column keys, in order: `layers`, `strict`, `family`, `installed`, `checkpoint`, `session`.

### 2.4 `D/compare_wire.py` — `GET /api/compare` (R-9)

```text
CompareCellWire    { graph: str, sc: float | None, cost_per_case: float | None }
CompareArmWire     { name: str, harness: str, model: str, note: str | None,
                     cells: list[CompareCellWire] }
HeatCellWire       { state: Literal["value","low_n","blank"], value: float | None, n: int }
HeatRowWire        { name: str, cells: list[HeatCellWire] }
CompareWire        { available: bool, root: str, description: str | None,
                     graphs: list[str], arms: list[CompareArmWire],
                     heat_columns: list[str],     # CELL_STAGE_ORDER members present
                     heat_rows: list[HeatRowWire] }
```

### 2.5 `D/read_routes.py`

`register_read_routes(router, poller, graphs, *, runs_root: Path) -> None` adds the four GET routes above. It is called once from `create_router` in `D/api.py`. That is the only edit to `api.py`.

## 3. Client additions (`F/api/`)

### 3.1 Additive changes to existing types

- `Decision` gains nothing. Closed-run gates map into the existing fields: `outcome` is `'approve'`, or `'reject'` with `comment: 'not approved'`; `decider` is `decided_by`. `mapClosed` stops returning `[]` (R-4).
- `DashboardApi` gains:
  - `decideTaskGate(runId: string, key: string, outcome: GateOutcome, guidance: string, thawTests: boolean): Promise<void>`;
  - `getFleetSummary(): Promise<FleetSummary>`;
  - `getShippedGraphs(): Promise<ShippedGraphs>`;
  - `getInterfaces(): Promise<InterfaceMatrix>`;
  - `getCompare(): Promise<Compare>`.
- `DashboardApi.resolveEscalation` is **removed** in slice 3, together with its only caller (`EscalationEntry.vue`), and replaced by `decideTaskGate` (R-3). Its mock and tests go with it.

### 3.2 New client types (`F/api/read-types.ts`)

These are camelCase mirrors of §2, one per wire model: `FleetSummary`, `FleetRunSummary`, `Arm`, `Traversal`, `GateTimeout`, `ShippedGraphs`, `ShippedGraph`, `ConfigCheck`, `ConfigSection`, `ConfigRow`, `InterfaceMatrix`, `MatrixColumn`, `MatrixRow`, `MatrixCell`, `CellState`, `AdapterFact`, `Compare`, `CompareArm`, `CompareCell`, `HeatRow`, `HeatCell`. Mappers live in `F/api/http-read.ts`. Mocks live in `F/api/mock/{fleetSummary,shippedGraphs,interfaces,compare}.ts` (R-14).

## 4. Library display primitives (`U/src/components/`)

No domain types (FR-1400). Every component has the five files and a showcase registration.

### 4.1 `graph_canvas` (extended)

- `CanvasNode.kind?: 'node' | 'sink'` (default `'node'`).
- `CanvasNode.sink?: { outcome: 'completed' | 'rejected' | 'failed' | 'escalated'; lit: boolean; sub: string }`.
- `CanvasEdge.payload?: string` (shown when the ⋯ toggle is on, or the edge is selected or a revise loop).
- `CanvasEdge.note?: string` (for example "next revise escalates the run").
- Props `showPayloads: boolean`, `showTerminals: boolean`, `grid: boolean`.

### 4.2 New components

| Directory | Component | Key props (display primitives only) |
|---|---|---|
| `rail` | `Rail.vue` | `head: { title, state, stateKind, rows: {k,v}[], budget: { spent, limit \| null, pct \| null, note } }`, `tabs: TabItem[]`, `active`, slots per section, `calls: { label, kind }[]` (call-to-actions) |
| `decision_card` | `DecisionCard.vue` | `kicker`, `schema`, `title`, `where`, `fields: {k,v,mono?}[]`, `text?: { label, hint, value, required }`, `actions: { id, label, title, variant, needsText? }[]`, `foot`, `busy` |
| `step_list` | `StepList.vue` | `steps: { name, ref, status: CanvasStatus, meta }[]` |
| `kanban` | `Kanban.vue` | `columns: { id, title, status, count, cards: { id, title?, tag, tagKind, meta }[] }[]`, `link?: { label, to }` |
| `command_palette` | `CommandPalette.vue` | `open`, `commands: { id, label, hint }[]`; emits `run(id)` and `close` |
| `toggle_menu` | `ToggleMenu.vue` | `items: { id, label, desc, on }[]`; emits `toggle(id)` |
| `heatmap` | `Heatmap.vue` | `columns: string[]`, `rows: { name, cells: { state, value, n }[] }[]` |
| `check_matrix` | `CheckMatrix.vue` | `columns: {key,name,ref}[]`, `rows: { name, sub, planned, cells: { state, text }[] }[]`, `facts: { who, severity, text }[]` |
| `catalog_card` | `CatalogCard.vue` | `kicker`, `name`, `sha`, `description`, `when`, `counts: {label,n}[]`, `action: { label }` |
| `footer_bar` | `FooterBar.vue` | `left`, `right` |

`app_header` is rebuilt with props `primary: NavItem[]`, `secondary: NavItem[]`, `runSwitch?: { tabs, active, mode?: 'observe'\|'design' }` and `badge`. Here `NavItem = { id, label, to, badge?, available }`. The old props `inboxCount` and `stats` are removed (S4). `toasts` keeps its API, with `kind` replacing a raw colour (R-10).

## 5. Dashboard state (new or changed)

| Name | File | Holds |
|---|---|---|
| `usePrefsStore` | `F/app/prefs.store.ts` (new) | `theme: 'dark'\|'light'`, `payloadsEverywhere`, `terminalsEverywhere`, `grid` (session-only, S4), and `runInContext: string \| null` |
| `navManifest` | `F/app/nav.ts` (new) | `NavItem[]` with `available` flags (R-1) |
| `useFleetSummaryStore` | `F/shared/fleetSummary.store.ts` (new) | `byRun: Record<string, FleetRunSummary>`, refreshed with the fleet poll |
| `decisionCardOf` | `F/shared/decisionCard.adapter.ts` (new) | `InboxItem` → `DecisionCard` props plus the action → client call map (R-3) |
| `railEventsOf` | `F/features/run/railEvents.adapter.ts` (new) | sources in R-5 → event rows |
| `costRailOf` | `F/features/run/costRail.adapter.ts` (new) | `Run.roles`, budget, per-node cost by `canonical_stage`, and the graph state's back-edge traversals → rail Cost groups: role, stage, "Revise traversals" (FR-015a, S16; reuses `F/shared/cost.ts`) |
| `kanbanOf` | `F/features/board/kanban.adapter.ts` (new) | board tasks → kanban columns by wire status |
| `DotState` | `F/api/types.ts` (re-homed in T049) | `'pending' \| 'active' \| 'done' \| 'blocked' \| 'failed' \| 'skipped'`, copied verbatim from `U/src/components/stage_dots/StageDots.vue:4`. It stays only as the value type of the unchanged `Run.stageMarks` wire field, so that `stage_dots` can be deleted. |
| `commandsOf` | `F/app/commands.ts` (new) | app state → v5 command list (S11), filtered by `navManifest` availability and `designAvailable` |
| `designAvailable` | `F/app/nav.ts` | a boolean beside `navManifest`, not rendered as a nav item. It is false until the Design route lands (T063), and gates the "Switch to Design", "Design <graph>" and "Validate graph" commands and the header's Observe/Design switch |

`F/features/cost/` is deleted in slice 2. Its logic moves to `costRail.adapter.ts`, and its tests are rewritten against the rail (CONSOLE-24 to CONSOLE-26 rewritten).

## 5a. New files (beyond those named above)

| File | Purpose |
|---|---|
| `interfaces/ui/app.helpers.ts` | shared app-tier Playwright setup, moved out of `app.pw.ts` (T008). Not a `.pw.ts`. |
| `interfaces/ui/app.{shell,run,inbox,fleet,board,graphs,compare,interfaces}.pw.ts` | app-tier tests by screen (R-11) |
| `F/features/run/RunInspector.vue` | the Observe inspector (S13), screen-local |
| `F/features/board/BoardKanban.vue` | the run's Board view (S7) |
| `F/features/graphs/GraphsView.vue`, `F/features/graphs/DesignView.vue` | the Graphs catalog and the Design view (S8, Q2) |
| `F/features/compare/CompareView.vue`, `F/features/interfaces/InterfacesView.vue` | the new screens |
| `F/features/inbox/InboxCard.test.ts` | replaces `entries.test.ts` |
| `F/api/mock/runOutcomes.ts` | Observe outcome fixtures (V1–V3, no budget), used only if `F/api/mock/graph.ts` would pass 400 lines |
| `F/api/mock/decisions.ts` | the `tool_approval` and `budget` gate items and a closed run with `gates` |
| `F/api/mock/plannedTypes.ts` | the planned node types for the Design palette (A8, presentation only) |
| `F/api/__fixtures__/read/{fleet-summary,graphs-shipped,compare,interfaces}.json` | recorded wire fixtures (Routes rule 4) |
| `tests/fixtures/compare/` | the Compare route's input tree |
| `scripts/check_raw_colours.py`, `scripts/dump_read_fixtures.py` | R-10, Routes rule 4 |

## 6. Name check (first task of every slice)

The executor checks that every name a slice introduces (type, function, store, component, prop, or file) appears in §2 to §5a. A name that appears in code and not here is a stop.
