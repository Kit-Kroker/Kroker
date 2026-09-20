# E-76 — graph canvas (FR-1205) — design

| | |
|---|---|
| Epic | E-76 (pipeline-as-data, phase 1, Track B) → FR-1205 |
| Date | 2026-09-14 |
| Status | reviewer-approved (2026-09-14, r2 after one FIXES-NEEDED round); pending user gate on E76-OQ-1…E76-OQ-5 |
| Normative text | `PRD.md` §6 FR-1205 (FR-1202 boundary, FR-301/302 gates); `ROADMAP.md` §2 FR-1400…FR-1406 |
| Framing | `docs/roadmap/pipeline-as-data.md` E-76 row; OQ-11 (localhost-bind containment until E-60) |
| Consultation log | `.workspace/tmp/e76-consult-q1.md`, `e76-consult-q2.md`, `e76-consult-q3.md` (planner↔advisor); `e76-skeptic-r1.md`, `e76-skeptic-r2.md`; `e76-review-r1.md`, `e76-review-r2.md` (uncommitted scratch; dispositions in §13) |

## 1. Purpose and deliverable

E-76 ships the graph canvas: **one renderer, two modes**.

- **Run mode** (RunView, `/runs/:id`, read-only): per-node status, cost and
  durations; traversal counters on loop edges (`2/3`); backward edges drawn
  curved; live approve / revise / reject on a pending gate node through the
  existing FR-301/302 surface (`decideGate` → `POST /runs/{id}/decide`).
- **Edit mode** (new route `/graphs`): load a `PipelineGraph` from YAML or a
  saved sha, edit it on the canvas with a palette and a schema-driven
  inspector, view/edit the YAML text, validate, save.

It also **defines the wire contract** that E-75 (graph queries), E-73
(validate) and E-77 (store) later implement, ships the pure, workflow-free
subset of that contract as real routes, and replaces `Run.stageIdx` so the
fleet strip is keyed by canonical stage **name**.

Everything that decides legality stays in Python. TypeScript renders, edits a
working copy, and asks.

## 2. Decisions

### 2.1 User rulings (2026-09-14, binding)

| # | Ruling |
|---|---|
| U1 | **Save** is an endpoint returning the new `content_sha`. The mock holds saved graphs in memory; E-75/E-77 back it with `graphs/<sha>.yaml`. |
| U2 | **Placement.** Run mode is RunView's body at `/runs/:id`. Edit mode is a new `/graphs` route. "Open this run's graph in the editor" loads a *copy*; nothing ever writes back to a run. |
| U3 | **Gate actions.** A pending gate node offers approve / revise / reject with a comment (revise requires one) via the existing `decideGate(runId, key, outcome, comment)`. |
| U4 | **Stage strip** renders all 18 `CANONICAL_STAGES` (served by the API, never a TS copy), matched by `canonical_stage` name; a stage with no node in the run's graph is `skipped`. |
| U5 | **Shape-broken text** opens in an editable YAML pane with its shape errors; the canvas is disabled until the text parses. |
| U6 | **Save is allowed for any well-shaped graph**, legality errors included. The response carries validation; the editor flags the graph not-runnable. |
| U7 | **Graphless runs** (legacy `FeatureWorkflow`, OQ-10 grace-retention): `graph()` returns a typed `no_graph`; RunView shows an explicit empty state; the strip still works from `current_stage`. Nothing is synthesized. |
| U8 | **Inspector** is a schema-driven form over pydantic `model_json_schema()` served by the catalog; unsupported constructs fall back to a snippet field. No schema field names are written in TS. **Amended 2026-09-14 (user):** the snippet is JSON (`JSON.parse`), not YAML — TS has no YAML parser and a client YAML parse is D1's dialect drift. |
| U9 | **API reach.** E-76 ships the pure routes (`GET /graphs/catalog`, `POST /graphs/parse`, `POST /graphs/serialize`) as thin wrappers over a pure `sdlc/dashboard/graph_wire.py`. `graph()`, `graph_state()`, validate, save and load stay E-75/E-73/E-77; the http provider reports them *unavailable*, never crashes. |

### 2.2 Design decisions (advisor consensus, Q1/Q2)

| # | Decision |
|---|---|
| D1 | **Server-authoritative conversion.** YAML never parses in TS. `parse` (text or graph JSON → graph + sha, or shape errors), `serialize` (graph → `to_yaml` text) and `validate` are server calls. No js-yaml: PyYAML is YAML 1.1 (`on`/`yes` → bool), js-yaml is 1.2, so a client parse would render a graph the server reads differently. |
| D2 | **Graph JSON is the working copy; YAML is an import/export view.** `serialize` runs only when the YAML pane opens or on export; `parse` runs only on an explicit apply. Never re-serialize under the user's cursor. |
| D3 | **Catalog as data, including the compatibility rule's output.** The catalog carries, per out-port, the `connectable` list of `(type, in_port)` pairs for which Python's `ports_compatible` holds. TS does a membership lookup; it never evaluates the rule. |
| D4 | **The mock is a recording, not a simulator.** Parse/serialize/catalog fixtures are generated from the real Python by a dump script and pinned by a freshness pytest. Anything the recording does not contain is answered as *unrecorded*, never as success. Validate and run-state fixtures are hand-written and marked **PROVISIONAL** until E-73/E-74. |
| D5 | **Split placement (FR-1400).** Presentation components live in `@kroker/ui` over our own primitives (never re-exported vue-flow types); `dashboard/frontend/src/adapters/graph.ts` maps wire shapes onto them; stores and views stay dashboard-side. |
| D6 | **Wire shapes are pydantic models in `sdlc/dashboard/graph_wire.py`**, used by the pure routes now and by E-75's routes as `response_model=` later, so E-75 cannot drift from the fixtures. Not in `sdlc/graph/` (its purity pin enumerates files; the catalog needs `CANONICAL_STAGES`, which sits on the benchmarks import cycle). |
| D7 | **Server-supplied keys only.** TS never formats `gate_key` (`"node#round"`), never computes `content_sha`, never computes back edges. `pending[].key`, `sha` and `back_edges` arrive from the server. |
| D8 | **Transport for run state** is `subscribeGraphState(runId, cb)` on the API interface, implemented by a 2 s poll while RunView is mounted (NFR-3: 5 s). E-75 may swap in per-run SSE behind the interface. Run state is **not** folded into the fleet SSE snapshot. |
| D9 | **Capabilities are server-declared.** The catalog carries `capabilities: {validate, save, load, run_graph}`; E-76's routes serve all `false`. E-73/E-75/E-77 flip them. The editor disables unavailable actions with the owning epic named, instead of probing for 404s. |
| D10 | **Duplicate YAML keys and aliases are rejected** in `sdlc.graph.io.from_yaml` (the E-72 review minor owned here): a `SafeLoader` subclass rejects anchors and aliases **at compose time** (before any node graph is built) and a duplicate key or `<<` merge key at every mapping level at construct time. Graphs need none; this also closes alias-expansion bombs on an unauthenticated route. |
| D11 | **Canvas operations never round-trip.** Add, connect, move and delete mutate the working copy locally and cannot produce a shape error by construction: a new node's id is the catalog's Python-computed `default_id` plus a `_n` suffix, ports come from the catalog, and the position writer drops non-finite coordinates. Only the inspector's *apply* — where a user types values — goes through `parse({graph})`, guarded by an edit epoch. |

## 3. Verified anchors and corrections to the brief

- **FR-1400…FR-1406 are not in `PRD.md` §6.** They exist only as
  `ROADMAP.md:403-411` (all `[x]`, E-89). This spec cites them from there.
- **The strip is not "15-stage".** `constants.ts` `STAGES` has **14** names;
  `benchmarks/heatmap.py:25` `CANONICAL_STAGES` has **18**; `http.ts:9-14`
  carries its own TS copy of the 18. **Existing defect:** `http.ts:69`
  computes `stageIdx` as an index into the 18-list while
  `adapters/fleet.ts:8-13` renders it against the 14-list, so a live run at
  `clarify` (18-list index 5) lights the 14-list's `architecture` mark.
  U4 removes both TS lists; the fix is by construction.
- **No gate UI exists to reuse.** `RunView.vue` and `InboxView.vue` are
  placeholders ("implemented in Plan 2"). The FR-301/302 surface available
  is `DashboardApi.decideGate` → `POST /runs/{run_id}/decide`
  (`src/sdlc/dashboard/api.py:165-177`), guarded server-side by
  `resolve_key` + the reply-kind check.
- **The server does not require a revise comment.** `channels/contract.py:115`
  passes `reply.text` through as guidance when present; an empty revise is
  accepted. U3's "revise requires a comment" is UI-only (E76-OQ-4).
- **`from_yaml` raises on shape failure** (`sdlc/graph/io.py:34-50`), so only
  a well-shaped graph becomes a `PipelineGraph`; a legality-broken one does
  (spec D5). For `ValidationError`, `__cause__.errors()` gives structured
  `loc`/`msg`; YAML-level failures carry `problem_mark` line/column.
- **Parse is shape-only**, so duplicate node ids and duplicate edges parse
  (E-72 §5). `GraphEdge` has no id; identity is the endpoint 4-tuple.
- **`yaml.safe_load` is last-wins on duplicate keys** — verified in the
  E-72 review minors task (item 3).
- **`@kroker/ui` has no runtime dependencies today** (only
  `devDependencies`); the root `package.json` declares npm workspaces for
  both packages. E-76 adds the package's first runtime dependencies (§10.3).
- **`dagre` 0.8.5 is unmaintained** (last publish 2022-06). The maintained
  fork is `@dagrejs/dagre` (3.1.1). `@vue-flow/core` is 1.48.2, peer
  `vue ^3.3.0` (repo has `^3.4.21`). *Correction to the brief's "dagre":*
  use `@dagrejs/dagre`.
- **The dashboard fixture precedent** (`scripts/dump_dashboard_fixtures.py`)
  chose hand-written adaptation over codegen (its D3) but has **no
  freshness test**. E-76 adds one for its own fixtures (§6.3) and files the
  missing one for `fleet-snapshot.json` as an inbox task, not scope here.
- **Python dashboard tests are flat** (`tests/test_dashboard_*.py`), not a
  `tests/dashboard/` package.
- **Hypotheses to verify in the plan's first task** (not yet checked):
  `@vue-flow/core/dist/style.css` contains only structural rules (if it
  carries colour literals, it is not imported and the canvas ships its own
  structural rules; the default *theme* file is never imported); `@dagrejs/dagre`
  ships ESM usable by Vite 5; vue-flow renders under the showcase's Vite
  root without extra config; the FR-1405 ds-bundle preview of `graph_canvas`
  renders with vue-flow's structural CSS inlined (DS_BUNDLE-3 requires
  standalone previews).

## 4. Architecture

```
sdlc.graph (E-72, frozen)          sdlc.benchmarks.heatmap.CANONICAL_STAGES
        │                                   │ (function-local import)
        ▼                                   ▼
sdlc/dashboard/graph_wire.py  ── pure pydantic wire models + projections
        │                 │
        │                 └── scripts/dump_graph_fixtures.py ──► __fixtures__/graph/*.json
        ▼                                                          (freshness pytest)
sdlc/dashboard/api.py  (E-76: /graphs/catalog, /graphs/parse, /graphs/serialize)
        │              (E-75/E-73/E-77 later: validate, save, load, run graph, run state)
        ▼
DashboardApi (types.ts) ── http.ts (real routes; unavailable per capabilities)
        │                └ mock/ (recording over fixtures + PROVISIONAL canned state)
        ▼
Pinia stores: catalog.ts · graphEditor.ts · runGraph.ts · fleet.ts (strip)
        ▼
adapters/graph.ts · adapters/fleet.ts   (wire → display primitives)
        ▼
@kroker/ui: graph_canvas · node_palette · schema_form · yaml_pane · issue_list · gate_decision · stage_dots(unchanged)
        ▼
views: RunView.vue (run mode) · GraphEditorView.vue (/graphs, edit mode)
```

**Import direction** is the existing one: `ui/` never imports `dashboard/`;
adapters are the only place wire types meet primitives.

## 5. Wire contract

All shapes below are pydantic models in `graph_wire.py`; the TS mirror in
`api/types.ts` is **structural and hand-written** (D3 precedent), pinned by
the generated fixtures. `role` and `gate` inside `GraphWire` are
`Record<string, unknown>` in TS: the canvas never learns `RoleConfig` fields.
Status markers: **FINAL** (E-76 owns and ships), **PROVISIONAL** (E-76
defines, a later epic implements and may amend through that epic's spec).

### 5.1 Shared

```ts
type GraphWire = { schema_version: 1; nodes: NodeWire[]; edges: EdgeWire[] }   // model_dump(mode="json", exclude_defaults=True)
type NodeWire  = { id: string; type: string; role?: Record<string, unknown>; gate?: Record<string, unknown>;
                   position?: { x: number; y: number }; label?: string }
type EdgeWire  = { source: string; source_port: string; target: string; target_port: string;
                   max_traversals?: number; label?: string }
type EdgeRef   = { source: string; source_port: string; target: string; target_port: string }
type ShapeError = { loc: (string | number)[]; msg: string; line?: number; column?: number }
```

### 5.2 Catalog — `GET /graphs/catalog` (FINAL, shipped)

```ts
type CatalogWire = {
  node_types: NodeTypeWire[]            // sorted by type
  canonical_stages: string[]            // benchmarks CANONICAL_STAGES, in order
  schemas: { GraphNode: JsonSchema; GraphEdge: JsonSchema }   // $defs embed RoleConfig/GateConfig
  capabilities: { validate: boolean; save: boolean; load: boolean; run_graph: boolean }
  max_graph_bytes: number              // the parse/serialize body cap (UTF-8 bytes)
}
type NodeTypeWire = {
  type: string; kind: 'stage' | 'gate'; role: string | null; canonical_stage: string | null
  default_id: string                    // Python: type with '.' -> '_'; tested to match ID_PATTERN
  ports: { name: string; direction: 'in' | 'out'; payload: string | null; required: boolean; multiplicity: 'one' | 'many' }[]
  connectable: Record<string /* out-port name */, { type: string; port: string }[]>   // from ports_compatible
}
```

`schemas` serves `GraphNode` and `GraphEdge` only; `RoleConfig`/`GateConfig`
arrive through their `$defs`. No display metadata (`display_name`,
`description`) is added to `NodeTypeSpec` in E-76; the palette shows `type`
grouped by `kind` and `canonical_stage`.

### 5.3 Parse — `POST /graphs/parse` (FINAL, shipped)

Body: `{ yaml: string }` **or** `{ graph: object }` (exactly one). The graph
form runs `PipelineGraph.model_validate` — the inspector's apply path (§8.3).

```ts
type ParseWire =
  | { ok: true;  graph: GraphWire; sha: string }      // graph is normalized (sorted) by the model
  | { ok: false; shape_errors: ShapeError[] }
```

- `200` for both outcomes (a parse result is data, not a failure).
- `413` when the UTF-8 body exceeds `MAX_GRAPH_BYTES` (**256 KiB**, served as `catalog.max_graph_bytes`; the store measures UTF-8 bytes with `TextEncoder` — a Node global under Vitest's jsdom environment — and refuses before sending); `422` for a body that is neither form.
- YAML-level failures (bad YAML, duplicate key, alias, non-mapping,
  `schema_version`) produce one `ShapeError` with `loc: []` and
  `line`/`column` when PyYAML supplies a mark. Model failures map
  `__cause__.errors()` one-to-one (`loc`, `msg`), in pydantic's order.

### 5.4 Serialize — `POST /graphs/serialize` (FINAL, shipped)

Body `{ graph: object }` → `{ ok: true, yaml: string }` (exactly
`to_yaml`) or `{ ok: false, shape_errors }`. Same size cap.

### 5.5 Validate — `POST /graphs/validate` (PROVISIONAL, E-73 + E-75)

```ts
type ValidationWire = {
  issues: Issue[]            // deterministic order (NFR-10)
  back_edges: EdgeRef[]      // E-73's dominance-based back edges
}
type Issue = {
  code: string               // stable machine code
  severity: 'error' | 'warning'
  message: string
  target: { kind: 'graph' }
        | { kind: 'node'; id: string }
        | { kind: 'edge'; edge: EdgeRef }
        | { kind: 'port'; node: string; port: string }
}
```

A graph is **runnable** iff no issue has `severity: 'error'`. E-76 files
these needs to the E-73 track now (§11) and ships a forcing test (§10.1).

### 5.6 Save / load — `POST /graphs`, `GET /graphs/{sha}` (PROVISIONAL, E-75/E-77)

```ts
type SaveWire =
  | { ok: true; sha: string; validation: ValidationWire | null }   // null until validate exists (U6)
  | { ok: false; shape_errors: ShapeError[] }                      // the store re-checks shape on save
type LoadWire = { ok: true; sha: string; graph: GraphWire } | { ok: false; reason: 'not_found' }
```

### 5.7 Run graph and run state (PROVISIONAL, E-75 on E-74)

> **Superseded by E-75** (`2026-09-17-graph-queries-design.md` §7.4): `terminal` is replaced by `outcome`, `NodeRunState.status` adds `skipped`/`cancelled`, `PendingRef.node` is nullable. The TS mirror caught up with the canvas run-mode wiring (landed 2026-09-20, bug flow `canvas-run-mode`).

`GET /runs/{run_id}/graph`, `GET /runs/{run_id}/graph_state`:

```ts
type GraphResponse =
  | { kind: 'graph'; sha: string; graph: GraphWire; back_edges: EdgeRef[] }
  | { kind: 'no_graph'; reason: 'legacy_run' }                                  // U7

type GraphStateResponse =
  | { kind: 'no_graph'; reason: 'legacy_run' }
  | { kind: 'state'
      graph_sha: string                          // MUST equal GraphResponse.sha
      nodes: Record<string, NodeRunState>        // keyed by node id (a running graph passed validate)
      edges: { edge: EdgeRef; traversals: number }[]   // only traversed edges; absent = 0
      current_nodes: string[]
      pending: { node: string; key: string; kind: 'gate' | 'clarify' | 'escalation' }[]
      terminal: null | 'done' | 'failed' | 'escalated' }

type NodeRunState = {
  status: 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale'
  round: number
  started_at: string | null; ended_at: string | null   // client computes elapsed; no ticking fields
  cost_usd: number | null                             // null != 0
}
```

Rules carried into E-75: no field may change without a state change (so a
future SSE fingerprint dedupe holds, `api.py:122-155`); `max_traversals` is
**not** repeated in state (the adapter joins it from the pinned graph);
`pending[].key` is the verbatim key the inbox already carries.

### 5.8 Fleet row (PROVISIONAL addition, E-75)

`Run.stageIdx` is **removed**. `Run` gains `activeStages: string[]` (a
graph can fan out, so more than one canonical stage may be active). Optional,
E-75-supplied: `stages?: { name: string; state: DotState }[]`, a server-side
projection that lets the fleet row show `skipped` for graph runs (§9).

The roadmap line "`Run.stageIdx` … becomes `currentNodes: string[]`" is
refined: `current_nodes` belongs to `GraphStateResponse` (RunView data);
`Run` carries stage names. The landing commit updates that roadmap line.

## 6. Python changes

### 6.1 `sdlc/graph/io.py` — duplicate keys and aliases (D10)

- `_StrictLoader(yaml.SafeLoader)` — **a subclass; never register on
  `yaml.SafeLoader`** (that would change every `safe_load` in the process).
  A comment states it must remain a `SafeLoader` subclass.
- **Compose time** (`compose_node` override): an `AliasEvent`, or any event
  carrying an `anchor`, raises `ComposerError` before the composer resolves
  it — rejecting later, in the constructor, would already have composed an
  alias graph.
- **Construct time** (`construct_mapping` override): a duplicate key in any
  mapping (top-level, inside `role:`/`gate:`, inside a list item, flow
  mappings included) or a `<<` merge key raises `ConstructorError`. Merge is
  rejected, not honoured, so there is no flatten-order subtlety.
- Raises `yaml.constructor.ConstructorError` / `ComposerError` (both
  `YAMLError`), so the existing `except yaml.YAMLError` maps them to
  `GraphSchemaError` unchanged; the mark survives on `__cause__`.
- `from_yaml` uses `yaml.load(text, Loader=_StrictLoader)`.
- The io module docstring and E-72 spec §7.2 gain one line each (artifact
  boundary). Module-level imports are unchanged, so `test_graph_purity.py`
  is untouched.

### 6.2 `sdlc/dashboard/graph_wire.py` (new, pure)

Module-level imports: stdlib, `pydantic`, `sdlc.graph`, `sdlc.core.models`
only — pinned by an AST purity test. `CANONICAL_STAGES` is imported inside
`catalog()`.

| name | purpose |
|---|---|
| models | `ShapeError`, `NodeTypeWire`, `CatalogWire`, `Capabilities`, `ParseOk`/`ParseErr` (`ParseWire`), `SerializeWire`, and PROVISIONAL `Issue`, `ValidationWire`, `SaveWire`, `LoadWire`, `GraphResponse`, `GraphStateResponse`, `NodeRunState` |
| `catalog(registry=NODE_TYPES) -> CatalogWire` | node types, `connectable` via `ports_compatible` over every (out-port, in-port) pair, `canonical_stages`, schemas, capabilities all `False` |
| `parse_text(text) -> ParseWire` | wraps `from_yaml`; maps `GraphSchemaError.__cause__` |
| `parse_object(obj) -> ParseWire` | wraps `PipelineGraph.model_validate` |
| `serialize(obj) -> SerializeWire` | validate then `to_yaml` |
| `MAX_GRAPH_BYTES = 256 * 1024` | the route cap |

No Python validate stub: a fake "no issues" is worse than none.

### 6.3 Routes and fixtures

- `api.py` `create_router` gains `GET /graphs/catalog`,
  `POST /graphs/parse`, `POST /graphs/serialize`, each a thin call into
  `graph_wire` with `response_model=`. Read-only, no workflow, no store;
  OQ-11 localhost-bind containment unchanged.
- `scripts/dump_graph_fixtures.py`: `build() -> dict[relpath, object]` and
  `main()` writing `interfaces/dashboard/frontend/src/api/__fixtures__/graph/`:
  `catalog.json` and `scenarios/<name>.json` = `{name, yaml, parse, serialize}`
  for the scenario set: `pre_code` (E-72 fixture), `dangling_edge`,
  `duplicate_node_id`, `incompatible_ports`, `bad_yaml`, `bad_schema_version`,
  `role_typo`, `duplicate_top_level_key`, plus `objects/<name>.json` =
  `{name, graph, parse}` recordings of `parse_object` for the exact graph
  objects the Playwright inspector flows produce (e.g. `pre_code` with one
  gate's `policy` set to `soft`; one with an invalid id typed).
- Hand-written, marked `PROVISIONAL until E-73/E-74` in the file:
  `validation.provisional.json` (per scenario name) and
  `run_graphs.provisional.json` (graph runs and their scripted state steps).

## 7. Frontend: API, providers, stores

### 7.1 `DashboardApi` additions

```ts
getCatalog(): Promise<CatalogWire>
parseGraph(input: { yaml: string } | { graph: GraphWire }): Promise<ParseWire>
serializeGraph(graph: GraphWire): Promise<SerializeWire>
validateGraph(graph: GraphWire): Promise<ValidationWire>          // only if capabilities.validate
saveGraph(graph: GraphWire): Promise<SaveWire>                    // only if capabilities.save
loadGraph(sha: string): Promise<LoadWire>                         // only if capabilities.load
getRunGraph(runId: string): Promise<GraphResponse>                // only if capabilities.run_graph
subscribeGraphState(runId: string, cb: (s: GraphStateResponse) => void): () => void
```

Calling a method whose capability is `false` is a programming error in the
store (it throws `CapabilityUnavailable`); views gate on capabilities first.

### 7.2 Providers

- **http**: the three shipped routes for real; the rest implemented against
  the PROVISIONAL paths but unreachable while capabilities are `false`.
  `getCatalog()` is fetched once and cached for the session.
- **mock**: capabilities all `true` (so every flow is exercisable headless). The
  recorded `catalog.json` carries Python's all-`false`; the mock overrides it
  explicitly, and a Vitest pins the override.
  - `getCatalog` returns `catalog.json`.
  - `parseGraph({yaml})`: exact-text lookup among recorded scenarios; a miss
    returns `{ok:false, shape_errors:[{loc:[], msg:'mock: unrecorded input'}]}`.
  - `parseGraph({graph})`: lookup of the object among `objects/*.json`
    recordings by a key-sorted JSON stringification (a lookup key only —
    never a sha, never a canonical form); a miss returns
    `{ok:false, shape_errors:[{loc:[], msg:'mock: unrecorded graph'}]}`.
    Never an echo of success: a Playwright flow that applies an unrecorded
    edit fails visibly. On a miss the mock `console.warn`s the lookup key and
    the nearest recording's name. The sorted-key string is used **only**
    inside this lookup — never for dirty tracking, identity or display; the
    mock module exports nothing that computes it (Vitest-pinned).
    Recordings hit only if the Playwright flow (i) starts from a fully
    positioned scenario, (ii) does not drag, drop or Tidy before Apply, and
    (iii) the form writes only touched fields (SCHEMA_FORM-4). Fixtures are
    imported as JSON, never compared as text.
  - `serializeGraph`: the recorded `serialize` for a recorded graph, else
    `JSON.stringify(graph, null, 2)` (valid YAML, visibly non-canonical).
    Playwright never asserts its exact text.
  - `validateGraph`: canned result for the current scenario (set by the last
    recorded parse); an edited graph keeps the last scenario's result.
  - `saveGraph`: stores the graph in memory under the recorded sha or
    `mock-sha-<n>`; `loadGraph` reads it back. Never hashes in TS.
  - `getRunGraph`/`subscribeGraphState`: from `run_graphs.provisional.json`;
    one seeded graph run steps through its script on a timer; `decideGate`
    on its pending key advances the script (approve → next node; revise →
    loop edge traversal +1; reject → terminal `failed`). Seeded legacy runs
    return `no_graph`.

### 7.3 Stores

- `catalog.ts`: loads once; exposes `canonicalStages`, `nodeTypes`,
  `capabilities`, `connectable(from, to)` lookup.
- `graphEditor.ts`: the edit state machine (§8.1), working copy, selection,
  validation, dirty tracking against the last parsed/saved sha.
- `runGraph.ts`: per-RunView instance; `start(runId)` fetches graph +
  subscribes; `stop()` unsubscribes. The view calls `stop` in
  `onBeforeUnmount` and on `runId` change; `start` while started stops first.
  State is held in a `shallowRef` and replaced wholesale, skipped when its
  JSON fingerprint is unchanged. `graph_sha` mismatch → error state and
  `stop()`.
- **Polling discipline (http `subscribeGraphState`):** a recursive
  `setTimeout` chain, never `setInterval`, checking a `cancelled` flag before
  each fetch and before each callback; an in-flight fetch is aborted by
  `AbortController` on unsubscribe. `terminal !== null` delivers that state
  and ends the chain. `404` ends the chain. Other failures back off
  (2 s → 4 → 8 … capped 30 s; every delay, including the steady 2 s, carries
  ±20 % jitter so tabs never poll in lockstep) and after 3 consecutive failures the store
  shows "connection lost — retrying"; a success resets both.
- **Gate decisions in flight** are tracked in the store by `pending.key`, not
  in component state. An incoming state that still lists an in-flight key
  does not clear it. The key clears when (a) a state no longer lists it, or
  (b) `decideGate` fails with a non-404 error (toast, controls re-enable).
  A `404` (another surface won the FR-302 race) shows a toast and keeps the
  controls busy until the next state; if that state still lists the key,
  busy clears.
- `fleet.ts`: unchanged API; strip computed in the adapter from
  `catalog.canonicalStages`.

## 8. Edit mode (`/graphs`)

### 8.1 States

| state | meaning | canvas | YAML pane |
|---|---|---|---|
| `empty` | nothing loaded | palette only, "paste YAML or load" | editable |
| `text_broken` | last apply failed parse | disabled, error banner | editable; shape errors listed by `loc` path and line |
| `graph_loaded` | working copy is a well-shaped graph | enabled, issues decorate elements | on open: `serialize(working copy)` |

Transitions: apply text → `parse({yaml})` → `graph_loaded` | `text_broken`.
Load sha → `graph_loaded`. "Open copy" from RunView → `/graphs?from=run:<id>`
→ `getRunGraph` → `graph_loaded` with no sha association (saving yields a
new sha).

### 8.2 Canvas operations

- **Add** from palette: a new node with id `default_id` (served), suffixed
  `_2`, `_3`… if taken; position at the drop point.
- **Connect**: drag out-port → in-port. vue-flow's `isValidConnection`
  consults **only** `catalog.connectable` (type-level, from Python). Every
  graph-dependent rule — multiplicity, duplicates, required inputs,
  reachability, cycles — is left to `validate` after the drop. This fence is
  a clause (GRAPH_CANVAS-6) so "just add the multiplicity check" fails review.
- **Move**: updates `position` (cosmetic, sha-stable). The store's position
  writer keeps the previous value and logs when `x` or `y` is non-finite
  (`NaN`/`Infinity` serialize as JSON `null` and would fail `NodePosition`):
  unmeasured node sizes, a degenerate zoom, or a drop before the viewport
  initializes can all produce one.
- **Tidy**: re-layout all nodes with dagre (§8.4).
- **Delete**: a node (and its incident edges), or an edge **by canvas key**
  (4-tuple + occurrence index), never by 4-tuple — deleting one of two
  text-loaded duplicate edges deletes one.
- **Clear label**: removes the `label` field; never writes `''`.
- **Inspect**: select node/edge → inspector (§8.3).

**Edit mechanics register.** A guard in the editor is an *edit mechanic*,
not a legality copy (FR-1202), only when all three hold: (1) it protects the
editor's own addressing or reversibility — it would still be needed if
`validate.py` dropped the corresponding rule; (2) it removes no
expressiveness — every graph remains reachable (at least via text apply) and
nothing validate would accept is blocked; (3) it reports nothing as a
validation result — no `Issue`, no "illegal" wording, no effect on the
runnable badge. The register is exactly:

- **M1 connect onto an existing 4-tuple** is a no-op that selects the
  existing edge (the 4-tuple is edge identity; a second bare copy is
  unaddressable on the canvas). Self-loops are **not** guarded — whether a
  node may feed itself is topology, validate's. A self-loop edge renderer is
  presentation work.
- **M2 rename onto an id used by another node** is refused inline: "'A' is
  already used by another node, so renaming would merge their edges" (the
  cascade would irreversibly merge edge sets). Renaming to its own id is a
  no-op.
- **M3 rename a node whose own id is duplicated** renames without rewriting
  edges, with the notice "edges stay with 'A': the id was ambiguous" (those
  edges cannot be attributed to one copy).
- **M4 non-finite positions** are dropped by the position writer (above).

Anything not in the register — multiplicity overflow, required inputs,
cycles, duplicate ids from text — is validate's, and the canvas lets it
happen. Adding a guard means adding it here against the three criteria.

**Edit epoch.** Every mutation of the working copy (canvas operation,
inspector apply success, text apply success, load) increments `epoch`. After
a canvas operation (D11) the store only schedules a debounced (400 ms)
`validateGraph` if `capabilities.validate`. Every async response —
`parseGraph`, `serializeGraph`, `validateGraph` — is tagged with the epoch at
dispatch and **discarded** if the epoch has moved. A discard caused only by
`move` shows no banner (the debounce re-requests). A discarded inspector
apply keeps the form's pending values and shows "the graph changed — apply
again". While a text or inspector apply is in flight, canvas operations are
disabled (spinner), so an apply cannot land on top of an edit made after it.

A new node's id suffix is the smallest integer ≥ 2 not used by a current
node; deleting a node deletes its incident edges and clears the selection
(no undo stack exists, so no stale reference can hold a freed id).

### 8.3 Inspector (U8)

`schema_form` renders the served schema for the selected element
(`GraphNode` or `GraphEdge`), resolving local `$ref` → `$defs`. Supported:
`string` (with `pattern`), `number`/`integer` (with `minimum`/`maximum`/
`exclusiveMinimum`/`exclusiveMaximum`), `boolean`, `enum`, nullable
`anyOf: [X, {type: 'null'}]`, arrays of strings, nested objects (as a
fieldset). Anything else renders a JSON snippet field (`JSON.parse` in TS;
no YAML — U8 as amended). An untouched field is never written: rendering a
`GateConfig` does not materialize `threshold: 0.8`, and setting `policy` on
a node with no `gate` creates `gate: {policy: …}` and nothing more; a
nullable is written `null` only when the user sets null (SCHEMA_FORM-4). `type` is shown read-only (a type change is delete + add).

Strings render as auto-growing text areas (so `instructions` is usable).
Renaming a node's `id` is an inspector apply whose candidate graph rewrites
every incident edge's `source`/`target` to the new id in the same step — an
edit mechanic, not a legality rule, subject to M2 and M3.

Apply sends the whole candidate graph through `parseGraph({graph})`; `shape_errors`
whose `loc` path points into the edited element are shown on the matching
fields; the working copy is replaced only on success. The form marks nothing
special about loader-owned fields (`instructions`, `tool_files`); `validate`
reports them (E-72 §5). Renaming a gate node's id: see E76-OQ-1.

### 8.4 Layout

`@dagrejs/dagre`, `rankdir: LR`. Auto-layout runs on load only for nodes
without `position`; "Tidy" re-lays all. Edges listed in `back_edges` are
excluded from dagre's ranking input so loops do not distort ranks; before
any validation result exists, all edges are passed and dagre's own
`acyclicer: 'greedy'` pass breaks cycles for ranking (dagre reverses a
feedback arc set internally; it does not throw on cycles). That choice is
layout only and never marks an edge `backward` — curvature waits for
`back_edges`. **Layout input hygiene** (presentation, not legality): the
layout wrapper adds only edges whose endpoints are both among the supplied
node keys — graphlib would otherwise create a phantom node for a dangling
edge (the `dangling_edge` scenario, the commonest broken draft) — and
ignores `move` for an unknown key. `layout()` is also wrapped: on an exception the canvas keeps
existing positions, places unpositioned nodes on a grid, and emits a
`layout-failed` event the view shows as a warning. Layout lives in
`@kroker/ui` (presentation) and returns positions via a `move` event, which
the store writes into the working copy.

### 8.5 YAML pane and round-trip loss

Opening the pane shows `serialize(working copy)`. Text edits are local until
**Apply**. Applying text replaces the working copy. The pane states, in its
header, that the text is canonical: comments, key order and default values
are not preserved across a canvas edit (D2 — inherent in server-side
`to_yaml`). Cosmetics **are** preserved: `to_yaml` includes `position` and
`label` (E-72 §7.2), so applying serialized text never scrambles a layout;
only nodes the applied text leaves without `position` are auto-laid out. Text the user typed is kept verbatim until they leave the pane or
a canvas edit replaces it (with a confirm when the pane is dirty).

### 8.6 Save

Enabled when `capabilities.save` and state is `graph_loaded`. `saveGraph`
→ show sha; if `validation` has errors, a "not runnable" badge with the
issue count (U6). Before E-73/E-77 on http, the button is disabled with
"Saving arrives with E-77; validation with E-73."

## 9. Run mode (RunView)

- Loads `getRun`, `getCatalog`; if `capabilities.run_graph`, `getRunGraph`.
  `no_graph` → empty state "This run predates graph execution" (U7);
  capability false → "Graph view arrives with E-75". The StageDots strip
  renders above the canvas in every case.
- `graph` → canvas with `editable=false`; subscription via `runGraph.start`.
- **Node decoration** from `NodeRunState`: status ring class
  `cmp-graph-node-<status>`; cost (`null` shows "—"); elapsed from
  `started_at`/`ended_at` (a running node re-renders each second client-side);
  `round > 1` shown as `r<round>`.
- **Edge decoration**: for an edge with `max_traversals`, counter
  `traversals/max_traversals` (traversals default 0); an edge in
  `back_edges` renders curved (`cmp-graph-edge-backward`).
- **Pending gate**: for `pending[kind='gate']`, the node shows the
  `gate_decision` component; submit calls
  `decideGate(runId, pending.key, outcome, comment)`; controls go busy until
  the next state no longer lists the key; a `404` (another surface won the
  race, FR-302) shows a toast and waits for the next state. `clarify` and
  `escalation` pendings show a badge linking to the inbox; no controls.
- **Editing a running graph is disabled by design**: RunView has no edit
  path; "Open copy in editor" is the only route from a run to `/graphs`.
- `graph_sha` ≠ `GraphResponse.sha` → error state, no silent refetch.

### 9.1 Stage strip (U4)

`adapters/fleet.ts` `toStageDots(run, canonicalStages)`:

1. If `run.stages` is present (E-75 projection): render it verbatim, in
   `canonicalStages` order, stages absent from it as `skipped`.
2. Otherwise (legacy runs, and all runs until E-75): the active stages are
   `run.activeStages`; for each canonical stage, `done` if its index is below
   the lowest active index, the active mark (`active`/`blocked`/`failed`/`done`
   per `run.status`) if listed, else `pending`. This is today's linear
   behaviour on the correct list. It over-reports `done` for canonical stages
   a legacy run never executes (e.g. `adversary`); accepted and recorded
   (E76-OQ-3).
3. `activeStages = []`: every mark `pending`, whatever `run.status`
   (a queued or just-started run has not reached a stage). A closed run
   always has `[terminal_stage]`, so it never lands here; if one does
   (malformed snapshot), the marks stay `pending` rather than guessing.
   A stage name in `activeStages` that is not in `canonicalStages` is
   ignored for position and reported once to the console as a product
   fault (never silently mapped).

http fills `activeStages` from `RunState.current_stage` / closed
`terminal_stage` (`[name]` or `[]`), never inventing node ids. The mock seeds
`activeStages` names. `constants.ts` `STAGES`, `http.ts` `CANONICAL_STAGES`,
`composables/stageState.ts`'s index API, `mock/index.ts`'s `stageIdx` seeds,
and the six dependent test files (`constants.test.ts`,
`composables.test.ts`, `FleetTable.test.ts`, `adapters/fleet.test.ts`,
`mock/index.test.ts`, `http.test.ts`) are removed or rewritten in the same
change (`constants.test.ts` is rewritten, not deleted: its 14-stage
alignment and index assertions go, its `ARTIFACTS`/`STATUS_KINDS` assertions
stay); `stageIdx` is deleted outright, not
deprecated — the only consumers are the dashboard's own adapters, provider
and tests, all in this change, and `vue-tsc` fails any missed use.
`StageDots.vue` is unchanged.

## 10. Components, clauses, testing

### 10.1 Python (fast tier, no markers)

| test | pins |
|---|---|
| `tests/graph/test_graph_io.py` (extended) | duplicate key at top level, inside `role:`, inside an edge list item → `GraphSchemaError`; anchor, alias, `<<` → `GraphSchemaError`, with the alias case proven to fail in the composer (a `ComposerError` on `__cause__`) and a nested-alias payload failing fast; a duplicate key inside a flow mapping; `!!python/object` → `GraphSchemaError`; existing round-trip/fixpoint/golden tests unchanged. |
| `tests/test_dashboard_graph_wire.py` | `connectable` equals `ports_compatible` over every port pair of `NODE_TYPES` and of an injected fixture registry; `canonical_stages == CANONICAL_STAGES`; schemas embed `RoleConfig`/`GateConfig` `$defs`; `parse_text` ok carries `content_sha`; model failure maps `loc`/`msg`; YAML failure carries `line`; `parse_object`; `serialize == to_yaml`; module-level import purity; NFR-10 order independence of `catalog()` across registry insertion order. **Forcing test:** if `importlib.util.find_spec("sdlc.graph.validate")` is not None, assert `graph_wire` exposes the validate mapping, failing with "sdlc.graph.validate exists: add graph_wire's mapping onto ValidationWire and real validate fixtures (E-76 §5.5)". The module name is fixed through the E-73 handover (§11 item 1), not by a filesystem glob (a glob would turn E-73's own intermediate commits red before anything exists to wire). Python also pins every `default_id` matching `ID_PATTERN`. **Schema coverage:** every property of `RoleConfig` and `GateConfig` in the served schema classifies as a supported construct (the Python mirror of SCHEMA_FORM-3's no-fallback rule, so a pydantic upgrade that emits a new construct fails here first). |
| `tests/test_dashboard_graph_routes.py` | the three routes via `TestClient`: shapes match `response_model`; `413` above `MAX_GRAPH_BYTES`; `422` for a body with both/neither of `yaml`/`graph`. |
| `tests/test_graph_fixtures_fresh.py` | `dump_graph_fixtures.build()` equals the committed JSON, compared **parsed** (no `.gitattributes`; CRLF must not false-fail). Docstring: a pydantic upgrade that changes JSON Schema output turns this red on purpose. |

### 10.2 `@kroker/ui` components (FR-1401 clause doc, FR-1402 profiles, FR-1404 tokens only)

| component | primitives (props → events) | profiles (min) |
|---|---|---|
| `graph_canvas` | `nodes: CanvasNode[]`, `edges: CanvasEdge[]`, `editable`, `connectable(from,to)`, `selectedKey` → `connect`, `move`, `remove`, `select`, `drop-type`, `layout-failed` | `edit-empty`, `edit-pre-code`, `edit-with-issues`, `edit-duplicate-ids`, `run-mid-flight`, `run-looped` (counter `2/3`, curved edge), `run-gate-pending` |
| `node_palette` | `items: {type, kind, stage}[]` → `pick`, `dragstart` | `seed`, `empty` |
| `schema_form` | `schema`, `value`, `errors: {path, msg}[]`, `readonly` → `update` | `gate-config`, `role-config`, `edge`, `with-errors`, `unsupported-fallback` |
| `yaml_pane` | `text`, `errors: ShapeErrorPrimitive[]`, `dirty`, `canonicalNotice` → `update:text`, `apply` | `clean`, `shape-errors`, `dirty` |
| `issue_list` | `items: {key, severity, message, targetLabel}[]` → `focus` | `none`, `mixed` |
| `gate_decision` | `title`, `busy`, `disabled` → `decide {outcome, comment}` | `idle`, `busy`, `revise-needs-comment` |

`CanvasNode = {key, title, subtitle?, ports: CanvasPort[], status?, metrics?: {cost?: string, elapsed?: string, round?: string}, issueCount, position?}`;
`CanvasPort = {name, side: 'in'|'out', kind: 'signal'|'data', label, optional}`;
`CanvasEdge = {key, from: {node, port}, to: {node, port}, label?, backward, counter?: {used, max}, issueCount}`.
None contain a domain type; each is constructible as a literal (FR-1400).

Each new component ships the E-89 artifact set in
`interfaces/ui/src/components/<name>/`: `<Name>.vue`, `<name>.md` (clause
contract), `<name>.profiles.ts`, `<name>.spec.ts` (Vitest), `<name>.pw.ts`
(Playwright), plus an entry in `interfaces/ui/showcase/registry.ts`; the
public ones are exported from `interfaces/ui/src/index.ts`.

Representative clauses (full lists in each `<name>.md`, underscore IDs per
`interfaces/ui/AGENTS.md`):

- **GRAPH_CANVAS-1** one rendered node per supplied node, keyed by `key`
  (duplicate domain ids are the adapter's to disambiguate; the canvas
  renders what it is given).
- **GRAPH_CANVAS-2** an edge with `backward: true` renders on a curved path
  and carries `cmp-graph-edge-backward`.
- **GRAPH_CANVAS-3** an edge with `counter` renders `used/max` as text.
- **GRAPH_CANVAS-4** a node with `status` carries `cmp-graph-node-<status>`;
  an unknown status fails rendering (STAGE_DOTS-1.2 precedent).
- **GRAPH_CANVAS-5** `editable: false` emits no `connect`/`move`/`remove`
  and shows no palette drop target.
- **GRAPH_CANVAS-6** a connection attempt is accepted iff `connectable`
  returns true; the component evaluates no other rule.
- **GATE_DECISION-2** revise is disabled while the comment is blank.
- **SCHEMA_FORM-3** a nullable `anyOf` and a `$ref` enum render as native
  controls, not the fallback; against the recorded `catalog.json`, no
  `RoleConfig` or `GateConfig` property renders the fallback.
- **GRAPH_CANVAS-8** `move` never emits a non-finite coordinate; layout adds
  no edge whose endpoint is not a supplied node key.
- **SCHEMA_FORM-4** an untouched field is not written; a nullable is written
  `null` only by an explicit user action.
- **GRAPH_CANVAS-7** the canvas's colours resolve through tokens: vue-flow's
  default theme stylesheet is not imported, and vue-flow CSS variables are
  set from `--*` tokens under `.cmp-graph-canvas`.

### 10.3 Dashboard tiers

- **Vitest** (`sdlc-dashboard`): `adapters/graph.test.ts` (duplicate node ids
  → unique keys, issues mapped to every duplicate, an edge naming a
  duplicated id attaches to the first occurrence in server order; a node
  whose type is not in the catalog renders read-only handles synthesized
  from the edges naming it, not connectable; an issue whose target resolves
  to no element (deleted since, or a canned mock result) lands in the
  graph-level list, never throws; edge keys from 4-tuple +
  occurrence index; counter join with `max_traversals`; `backward` from
  `back_edges` only; pending gate join); `adapters/fleet.test.ts` (strip by
  name over 18 stages, `run.stages` precedence, the §3 defect case as a
  regression test); `stores/graphEditor.test.ts` (state transitions; a response dispatched at
  an older epoch is discarded for parse, serialize and validate; an id rename
  cascades to edges; M1–M4 each pinned, including M3's non-rewrite; delete by
  canvas key removes one of two duplicate edges; canvas operations disabled
  while an apply is in flight); `stores/runGraph.test.ts` (no fetch after stop, including a fetch in
  flight at stop; chain ends on terminal and on 404; backoff and reset;
  sha-mismatch error; an in-flight gate key survives a stale state and clears
  on disappearance or non-404 failure); `api/http.test.ts` (catalog cached, capability gating);
  `api/mock` (unrecorded text or object → error, never success);
  `adapters/fleet.test.ts` also covers `activeStages = []` for every
  `Run.status`.
- **Playwright app tier** (`interfaces/ui/app.pw.ts`, clauses added to
  `interfaces/ui/app.md`):
  - **CONSOLE-3** the fleet strip renders one mark per served canonical stage.
  - **CONSOLE-4** RunView of the seeded graph run renders its nodes, a loop
    counter and a curved backward edge.
  - **CONSOLE-5** deciding the seeded pending gate from the canvas clears it
    on the next state.
  - **CONSOLE-6** RunView of a legacy run shows the no-graph empty state.
  - **CONSOLE-7** `/graphs`: applying the `pre_code` scenario renders the
    canvas; applying `bad_yaml` shows shape errors with the canvas disabled.
  - **CONSOLE-8** RunView offers no edit affordance; "Open copy" lands on
    `/graphs` in `graph_loaded`.
- vue-flow needs real layout (ResizeObserver), so canvas behaviour clauses
  are Playwright-tier; Vitest covers adapters, stores and pure helpers.
- **Dependencies:** `@vue-flow/core` and `@dagrejs/dagre` are added to
  `interfaces/ui/package.json` **`dependencies`** (runtime imports of
  `graph_canvas` and its layout helper — not `devDependencies`, and not the
  dashboard package, which receives them through `@kroker/ui` and the
  workspace hoist). The root lockfile is updated in the same commit.
- Gate: `python scripts/check_ui.py` unchanged in shape (the new deps arrive
  via its `npm ci` step and the lockfile); `scripts/check_file_size.py` (no file > 1000
  lines — the editor view and stores are split to stay under).

## 11. Boundaries

**FR-1205 traceability**

| clause | discharged by |
|---|---|
| one renderer, two modes | `graph_canvas` with `editable` + run decorations (§10.2) |
| live per-node status | `subscribeGraphState` + node decoration (§9); real data E-75 |
| traversal counters on loop edges | edge counter join (§9), CONSOLE-4 |
| gate approve/reject via FR-301/302 | `gate_decision` → `decideGate` (§9), CONSOLE-5 |
| node palette and inspector | `node_palette`, `schema_form` (§8) |
| editing a running graph disabled | RunView has no edit path; copy-only (§9), CONSOLE-8 |
| validate via FR-1202, never its own copy | server validate (§5.5); TS evaluates only the Python-computed `connectable` table (§8.2, GRAPH_CANVAS-6) |

**Out of scope:** E-73 validate/router internals; E-75 real `graph()`,
`graph_state()`, save/load routes; E-77 store and `graph_sha`; subflows
(OQ-14); auth beyond OQ-11 containment; node display metadata in the
registry.

**Handed to other tracks (filed as `.workspace/tasks/` notes on landing,
and relayed to the E-73 planner now through the orchestrator):**

1. E-73: validate output must carry per-issue `target`, stable `code`,
   `severity`, deterministic order, and `back_edges`; module named
   `sdlc.graph.validate` (the forcing test keys on it).
2. E-75: implement §5.5–§5.8 with `graph_wire` models as `response_model`;
   flip capabilities; `RunState.stages` projection.
3. Inbox: freshness test for `fleet-snapshot.json`.

**Docs on landing** (docs describe `main`): tick E-76 in
`docs/roadmap/pipeline-as-data.md` and ROADMAP FR-1205; refine the
`currentNodes` line (§5.8) and the row's "fixed 15-stage strip" phrase to
the served canonical list (18 stages, U4); ARCHITECTURE component list gains the canvas and
`graph_wire`; E-72 spec §7.2 gains the duplicate-key line.

## 12. Open questions (for the user gate)

- **E76-OQ-1 — gate rename (canvas half of E72-OQ-2).** Renaming a gate
  node's id changes its signal name and CLI argument and resets calibration
  history. Options: (a) inspector warns on gate-id rename; (b) ids immutable
  after first save; (c) nothing until a `gate_name` field exists. Depends on
  E-73's ruling of its half.
- **E76-OQ-2 — drag refusal.** Refusing a type-incompatible drag uses the
  Python-computed `connectable` table (D3). Alternative: allow every drop and
  only highlight, leaving all rejection to validate.
- **E76-OQ-3 — fleet strip for graph runs before E-75.** Linear inference
  over-reports `done` and cannot show `skipped`; exact rendering needs E-75's
  `RunState.stages`.
- **E76-OQ-4 — revise comment.** UI requires a comment; the server accepts an
  empty revise (`channels/contract.py:115`). Enforce server-side, or keep as
  UI affordance?
- **E76-OQ-5 — comment loss.** Canonical YAML drops comments and author
  order after a canvas edit. Accept (current design) or keep an author-text
  side channel?

## 13. Skeptic round 1 — dispositions

| finding | disposition |
|---|---|
| F-01 parse/validate race | **Adopted, redesigned** — D11 (canvas ops never round-trip) + edit epoch on every async response + canvas disabled during an apply (§8.2). |
| F-02 mock echoes object parse | **Adopted** — object parses are recordings too; a miss is an error (§6.3, §7.2). An in-TS JSON Schema validator (ajv) was rejected: a second shape checker that still misses the model validators (`_reject_unknown_role_gate_keys`, `schema_version` int check). |
| F-03 poll leaks | **Adopted** — recursive timeout, abort, terminal/404 end, backoff (§7.3). |
| F-04 fleet crash | **Partly rejected.** No production crash: `types.ts`, `http.ts` and the adapter change in one frontend commit against an unchanged backend field (`current_stage`); `stageIdx` is not kept as a deprecated field (no external consumer; `vue-tsc` catches misses). **Adopted:** the `activeStages = []` rule and tests (§9.1). |
| F-05 schema form coverage | **Adopted** — no-fallback clause against the recorded catalog, Python-side construct coverage test, strings as text areas (§8.3, §10). |
| F-06 dagre on cycles | **Partly rejected.** Dagre does not loop or throw on cycles: its acyclic phase reverses a feedback arc set (`acyclicer`). No TS cycle-breaking DFS is added. **Adopted:** the layout exception fallback (§8.4). Duplicate keys were already the adapter's (§10.3). |
| F-07 gate double submit | **Adopted** — in-flight keys in the store (§7.3). |
| F-08 alias expansion before constructor | **Adopted** — anchors/aliases rejected at compose time (§6.1, D10). |
| F-09 forcing test name | **Adopted, redesigned** in r2 as a file glob; **superseded by N-01** (§13.1). |
| F-10 vendor CSS | **Adopted** — GRAPH_CANVAS-7; hypothesis checked in plan task 1 (§3). |
| F-11 memory | **Adopted minimally** — `shallowRef`, wholesale replace, unchanged-fingerprint skip (§7.3). The deeper claim is speculative. |
| F-12 id reuse | **Rejected as a defect** (no undo stack; deleting a node removes its edges and selection); the suffix rule is now stated (§8.2). |
| F-13 positions lost on YAML apply | **Clarified** — `to_yaml` includes cosmetics (§8.5). |
| F-14 bytes vs chars | **Adopted** — `max_graph_bytes` served; client measures UTF-8 bytes (§5.3). |
| F-15 YAGNI save/load; rename undefined | **Save/load kept** (U1: the mock implements save, so its shape must be defined). **Rename adopted** — id rename cascades to edges (§8.3); the gate-rename *warning* stays E76-OQ-1. |

### 13.1 Skeptic round 2 and advisor Q3

Skeptic r2: all fifteen round-1 findings closed (F-09 reopened as N-01);
no critical findings remain.

| finding | disposition |
|---|---|
| N-01 glob forcing test collides with the purity pin | **Adopted, per advisor** — keyed on `find_spec("sdlc.graph.validate")` only; the name travels in the E-73 handover (§10.1). |
| N-02 duplicate edge on local connect | **Adopted as M1** (edit-mechanics register, §8.2); self-loops left to validate. The real bug behind it — delete by 4-tuple — fixed by delete-by-canvas-key. |
| N-03 rename onto an in-use id merges edge sets | **Adopted as M2/M3** (§8.2), worded as mechanics, never as issues. |
| N-04 no jitter | **Adopted** — ±20 % on every delay (§7.3). |
| N-05 `TextEncoder` under Vitest | **Adopted** — measured in the store; a Node global under jsdom (§5.3). |
| Q3(a) dagre and dangling edges | **Adopted** — layout input hygiene (§8.4); duplicate-id edge attachment rule (§10.3). |
| Q3(b) recordings only hit under conditions | **Adopted** — flow rules, SCHEMA_FORM-4, miss diagnostics, lookup-key confinement (§7.2). |
| Q3(c) five test files, not three | **Corrected** (§9.1); reviewer r1 found a sixth (`constants.test.ts`), see §13.2. |
| Q3(d) non-finite positions; `default_id` restatement; unknown types | **Adopted** — M4 + GRAPH_CANVAS-8; `default_id` served from Python; synthesized read-only handles (§5.2, §8.2, §10.3). |
| Q3(e) U8 YAML vs JSON snippet | **Put to the user; U8 amended to JSON** (§2.1). Mock capability override pinned (§7.2). |

### 13.2 Reviewer round 1 (FIXES-NEEDED, no critical)

| finding | disposition |
|---|---|
| 1 six dependent test files, not five | **Fixed** — `constants.test.ts` added, rewritten not deleted (§9.1). Verified: it imports `STAGES` and asserts length 14. |
| 2 dependency placement unstated | **Fixed** — `interfaces/ui/package.json` `dependencies` (§10.3); §3 anchor reworded. |
| 3 `layout-failed` missing from the events column | **Fixed** (§10.2). |
| 4 Tidy bullet stranded below the register | **Fixed** — moved into the operations list (§8.2). |
| 5 per-component artifact set; ds-bundle vendor CSS | **Fixed** — artifact set stated (§10.2); ds-bundle hypothesis added to plan task 1 (§3). |
| 6 "fixed 15-stage strip" phrase stales | **Fixed** — landing note extended (§11). |
