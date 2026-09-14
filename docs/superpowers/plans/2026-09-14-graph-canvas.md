# E-76 Graph Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship FR-1205's graph canvas — one renderer, run mode (RunView) and edit mode (`/graphs`) — plus the wire contract E-73/E-75/E-77 implement to, the pure `catalog`/`parse`/`serialize` routes, the strict graph YAML loader, and the name-keyed stage strip.

**Architecture:** Legality stays in Python. `sdlc/dashboard/graph_wire.py` projects `sdlc.graph` onto pydantic wire models served by three read-only routes; a Python dump script records their answers as fixtures the dashboard mock replays (a recording, never a simulator). The dashboard's providers, stores and adapters map wire shapes onto display primitives rendered by six new `@kroker/ui` components (`graph_canvas` over `@vue-flow/core` + `@dagrejs/dagre`, `node_palette`, `issue_list`, `yaml_pane`, `schema_form`, `gate_decision`). Canvas operations stay local; only text and inspector applies round-trip through the server parse, guarded by an edit epoch.

**Tech Stack:** Python ≥ 3.11, pydantic v2, PyYAML, FastAPI, pytest · Vue 3.4, Pinia, vue-router, Vite 5, TypeScript 5, Vitest 1.6, Playwright 1.63, `@vue-flow/core` 1.48.2, `@dagrejs/dagre` 3.1.1.

**Spec:** `docs/superpowers/specs/2026-09-14-graph-canvas-design.md` (user-approved at gate 2; commit `7c0f397`). This plan implements the spec, not the planner brief. Read both documents. Where this plan and the spec disagree, the spec wins except for the named deviations below.

## Global Constraints

- **Legality never in TypeScript** (FR-1202, spec D1/D3): TS evaluates only the Python-computed `connectable` table and the edit-mechanics register M1–M4 (spec §8.2). No YAML parser, no sha, no `gate_key` formatting, no back-edge computation in TS.
- **`ui/` never imports `dashboard/`** (`interfaces/AGENTS.md`); display primitives are constructible as literals (FR-1400).
- **Clause IDs use underscores** (`GRAPH_CANVAS-6`), cited on the same line as the test: `// clause: GRAPH_CANVAS-6` (`interfaces/ui/AGENTS.md`). One ID per marker — `check_clauses.py` reads only the first.
- **No hex colour literals** in component stylesheets; colours only through `var(--*)` tokens (FR-1404). Playwright asserts structure and stable classes, never a hex value or pixel size.
- **Every component** ships `<Name>.vue`, `<name>.md`, `<name>.profiles.ts`, `<name>.spec.ts`, `<name>.pw.ts` and a `showcase/registry.ts` entry.
- **File size:** 1000 physical lines per file, no waiver (`scripts/check_file_size.py`). Run it in every task.
- **Node toolchain:** `python scripts/check_ui.py` is the single CI entry; locally you may call `npm run … --workspace …` for fast loops. Playwright locally needs `PLAYWRIGHT_BROWSERS_PATH=D:/own/.pw-browsers`.
- **Python:** `py311` syntax, ruff `line-length = 100`, lint `E,F,I,UP,B`. Never chain two `pytest` runs in one shell call.
- **Out of scope** (spec §11): E-73 validate/router internals, E-75 `graph()`/`graph_state()`/save/load routes, E-77 store, subflows, auth beyond OQ-11. Do **not** decide E76-OQ-1…5.
- **Commits:** subject + body only. **No attribution trailers of any kind** — no `Co-Authored-By:` in any form, no session links, no generated-by footers. `git commit -F <msgfile>` with message files under `.workspace/tmp/` (gitignored); one path per `git add` line. A per-task review gate applies: do not start task N+1 until the reviewer has answered on task N's diff.
- **Branch:** a feature branch cut from `main` at or after `7c0f397`; the orchestrator's exec phase names it.

## Named deviations from the spec (reviewer: judge these explicitly)

1. **`ShapeError.line`/`column` are `number | null`**, not optional: pydantic serializes `None` as `null` (spec §5.1 wrote `line?:`).
2. **`IssueTarget` is one model with optional fields** (`kind` + `id`/`edge`/`node`/`port`), mirroring the pydantic model; the adapter checks the field for its `kind` before use (spec §5.5 wrote a TS union). PROVISIONAL either way — E-73 owns the final shape.
3. **The mock's graph run advances only on `decideGate`, never on a timer** (spec §7.2 said timer + decisions): Playwright stays deterministic.
4. **Mock `validateGraph` with no recorded scenario returns one `mock.unrecorded` warning issue**, not an empty (falsely clean) result.
5. **`Capabilities` is a typed model whose `validate` key is an alias** (`can_validate` field, `serialize_by_alias`): a field named `validate` would shadow `BaseModel.validate`. The wire shape is exactly spec §5.2's.
6. **`subscribeGraphState(runId, cb, onError?)`** gains `onError(consecutiveFailures)`, which drives "connection lost — retrying" (spec §7.3).
7. **`api/errors.ts` `HttpStatusError`** is shared: `http.ts` and the mock throw it (the mock's "no pending item" is a 404), so `runGraph` detects the FR-302 race by status, not by message text.
8. **Clauses beyond spec §10's lists:** GRAPH_CANVAS-9 (decoration changes never replace vue-flow's element arrays — a defect found while prototyping, below), CONSOLE-9 (inspector apply round-trip), and full contracts for the five smaller components.
9. **`AppHeader` gains a GRAPHS tab** — the spec gave `/graphs` no navigation entry.
10. **The mock seeds an eighth run, `feature-graph-demo`, and its inbox gate `architecture#2`**: tests that counted 7 runs / 5 inbox items now count 8 / 6.
11. **Signatures:** `toFleetRow(run, canonicalStages)`, `toStageDots(run, canonicalStages)`; `composables/stageState.ts` exports `stageStates(run, stages)` (the index API is gone).
12. **`scripts/dump_graph_fixtures.py` puts `ROOT/src` on `sys.path`** (runs without an editable install); object recordings carry `base: "pre_code"` (which canned validation applies).
13. **A failed text apply after a graph was loaded also goes `text_broken`**, keeping the last good working copy (spec §8.1's table; U5 — the canvas is disabled until the text parses). Stated because a natural implementation would keep `graph_loaded`.
14. **Primitive-level refinements to spec §10.2's representative tables and §10.1's test layout:**
    (a) the strict-loader tests live in a new `tests/graph/test_graph_io_strict.py`, not appended to `test_graph_io.py` (§10.1 said "extended"): one file per concern, and the E-72 file stays untouched;
    (b) `node_palette` groups by `kind` only and shows each type's `canonical_stage` as a per-item label (§5.2 said "grouped by `kind` and `canonical_stage`") — nine seed types do not need two grouping levels;
    (c) `yaml_pane` drops the `canonicalNotice` prop (the notice is unconditional, YAML_PANE-3), adds `busy` and `maxBytes`, and takes errors as `{path, message, line, column}` with the adapter formatting `loc` into `path`;
    (d) small primitive additions: `IssueItem.focusKey`, `CanvasNode.readonly` (unknown types), `graph_canvas`'s `tidyRequest` prop and exposed `relayout()`, and `node_palette`'s drag payload (`application/x-kroker-node-type`) in place of a `dragstart` emit;
    (e) aligned, not deviated: a non-canonical stage name is reported to the console **once per name** (§9.1), via a module-level set in `stageState.ts`.

## Findings made while prototyping (plan facts)

- **Spec §3 hypothesis resolved:** `@vue-flow/core/dist/style.css` (1.48.2) carries colour literals (`#b1b1b7`, `#555`, `white`), so it is **not imported**; `GraphCanvas.vue` re-declares the structural rules with tokens (GRAPH_CANVAS-7). `@dagrejs/dagre` 3.1.1 ships ESM that Vite 5 and Vitest resolve. The FR-1405 ds-bundle previews of `graph_canvas` inline those rules.
- **Defect found and fixed (GRAPH_CANVAS-9):** passing freshly built `nodes`/`edges` arrays to vue-flow on every decoration change — RunView's 1 s elapsed clock — rendered **0 of 11 edges** and dropped the loop counters. vue-flow now receives element arrays rebuilt only on structural change (keys, positions, ports, endpoints, backward); slot templates read status, metrics, counters and issue counts from key maps. Pinned by an app-tier test driven with Playwright's `page.clock`.
- **Lockfile:** generated with npm 11; `npm ci` on Node 20.20.2 / npm 10.9.9 (CI's `.nvmrc`) installs it cleanly (verified on a fresh copy).

## Provenance of the code in this plan

Every code block below is the literal content of a file that was executed in scratch before this plan was written, generated into this document by script (no retyping):

- **Python** (copy of `src/` + `tests/`, Python 3.14.3, pydantic 2.13.5): `tests/graph/` 117 pass; `test_dashboard_graph_wire.py` 21 pass + the forcing test skipped; `test_dashboard_graph_routes.py` 14 pass with the existing `test_dashboard_api.py` green; `test_graph_fixtures_fresh.py` 3 pass; ruff, ruff format, mypy clean on the new modules. Against the **pre-task** modules: the strict-loader tests give 9 failed / 3 passed, the route tests 14 failed — the counts quoted in Tasks 2 and 4.
- **Frontend** (copy of `interfaces/` + root `package.json`/lockfile, deps installed): both `vue-tsc` typechecks, both builds, `ds:bundle`, dashboard Vitest **153**, ui Vitest **72**, Playwright **48** (showcase + app tier on `VITE_API=mock`), `check_clauses.py`: 61 declared, 0 untested, 0 dangling.
- Not re-run on Python 3.11 (no test deps on this machine's 3.11); no syntax newer than 3.11 is used. The other tasks' "Expected: FAIL" lines are derived from task order (a test importing a module the task creates cannot resolve it), not each observed.
- **R2 (CI drift):** `pyproject.toml` floors `pydantic>=2.13.5`; if CI resolves a pydantic whose `model_json_schema()` output differs, `test_graph_fixtures_fresh.py` goes red **by design**. The remedy is `python scripts/dump_graph_fixtures.py` and a reviewed fixture diff — never loosening the test.

## File Structure

| path | responsibility | task |
|---|---|---|
| `interfaces/ui/package.json`, `package-lock.json` | `@vue-flow/core`, `@dagrejs/dagre` as `@kroker/ui` runtime deps | 1 |
| `interfaces/ui/src/components/graph_canvas/{types,graph_layout,connection}.ts` (+specs) | display primitives, dagre layout + hygiene, the connection fence | 1 |
| `src/sdlc/graph/io.py` | `_StrictLoader`: aliases/anchors at compose time, duplicate/merge keys at construct time | 2 |
| `src/sdlc/dashboard/graph_wire.py` | wire models (FINAL + PROVISIONAL), `catalog`, `parse_text`, `parse_object`, `serialize` | 3 |
| `src/sdlc/dashboard/api.py` | `GET /graphs/catalog`, `POST /graphs/parse`, `POST /graphs/serialize` (256 KiB raw-body cap) | 4 |
| `scripts/dump_graph_fixtures.py`, `interfaces/dashboard/frontend/src/api/__fixtures__/graph/**` | recordings + hand-written PROVISIONAL fixtures | 5 |
| `interfaces/dashboard/frontend/src/api/{poll,errors}.ts` | cancel-safe poll chain; `HttpStatusError` | 6 |
| `…/api/{graph-types,types,http,http-graph}.ts`, `…/api/mock/{graph,index}.ts`, `…/stores/catalog.ts`, `…/composables/stageState.ts`, `…/adapters/fleet.ts`, `…/constants.ts`, `…/components/fleet/FleetTable.vue`, `…/App.vue` | the API contract change and the name-keyed strip (atomic: `vue-tsc` forces it) | 7 |
| `interfaces/ui/src/components/gate_decision/` | approve/revise/reject controls | 8 |
| `interfaces/ui/src/components/{node_palette,issue_list}/` | palette; issue list | 9 |
| `interfaces/ui/src/components/yaml_pane/` | canonical YAML view + byte cap | 10 |
| `interfaces/ui/src/components/schema_form/` | JSON-Schema form (`schema.ts`, `SchemaField.vue`, `SchemaForm.vue`) | 11 |
| `interfaces/ui/src/components/graph_canvas/` (component) | the renderer | 12 |
| `interfaces/dashboard/frontend/src/adapters/graph.ts` | wire → canvas primitives | 13 |
| `…/stores/{graphEdits,graphEditor}.ts` | pure edit operations + M1–M4; the edit state machine | 14 |
| `…/stores/runGraph.ts` | run-state subscription, in-flight gate keys | 15 |
| `…/views/GraphEditorView.vue`, `…/components/graph/GraphInspector.vue`, `…/router.ts`, `ui/…/app_header/AppHeader.vue` | edit mode | 16 |
| `…/views/RunView.vue` | run mode | 17 |
| `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md` | landing docs | 18 |

---
### Task 1: `@kroker/ui` dependencies + pure canvas helpers

**Files:**
- Modify: `interfaces/ui/package.json`, `package-lock.json` (via `npm install`)
- Create: `interfaces/ui/src/components/graph_canvas/types.ts`, `graph_layout.ts`, `connection.ts`
- Test: `interfaces/ui/src/components/graph_canvas/graph_layout.spec.ts`, `connection.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `CanvasStatus`, `CANVAS_STATUSES`, `CanvasPort`, `CanvasNode`, `PortRef`, `CanvasEdge`, `Point` (`types.ts`); `NODE_WIDTH`, `nodeHeight(node)`, `isFinitePoint(p)`, `layoutGraph(nodes, edges, {all?, backwardKeys?}) → {positions, failed}`, `gridPositions(nodes)`, `backwardPath(sx, sy, tx, ty) → [path, labelX, labelY]` (`graph_layout.ts`); `handleId(side, port)`, `toPortRefs(c)`, `acceptConnection(editable, connectable, c)` (`connection.ts`).

- [ ] **Step 1: Install the two runtime dependencies from the repo root**

```bash
npm install @vue-flow/core@1.48.2 @dagrejs/dagre@3.1.1 --workspace @kroker/ui
git status --short
```

Expected: `interfaces/ui/package.json` gains a `dependencies` block (its first) with `"@dagrejs/dagre": "^3.1.1"` and `"@vue-flow/core": "^1.48.2"`, and the **root** `package-lock.json` changes (about +180 lines). Nothing else changes. Do not import `@vue-flow/core/dist/style.css` anywhere — it carries colour literals (see "Findings").
- [ ] **Step 2: Write the failing specs**

`interfaces/ui/src/components/graph_canvas/graph_layout.spec.ts` (create; 67 lines):

```ts
import { describe, it, expect } from 'vitest'
import { backwardPath, gridPositions, isFinitePoint, layoutGraph, nodeHeight } from './graph_layout'
import type { CanvasEdge, CanvasNode } from './types'

const node = (key: string, position?: { x: number; y: number }): CanvasNode => ({
  key, title: key, issueCount: 0, position,
  ports: [{ name: 'in', side: 'in', kind: 'signal', label: 'in', optional: false },
          { name: 'out', side: 'out', kind: 'signal', label: 'out', optional: false }],
})
const edge = (from: string, to: string, key = `${from}>${to}`): CanvasEdge => ({
  key, from: { node: from, port: 'out' }, to: { node: to, port: 'in' }, backward: false, issueCount: 0,
})

describe('layoutGraph', () => {
  it('positions only unpositioned nodes unless asked for all', () => {
    const nodes = [node('a', { x: 5, y: 5 }), node('b')]
    const r = layoutGraph(nodes, [edge('a', 'b')])
    expect(Object.keys(r.positions)).toEqual(['b'])
    expect(Object.keys(layoutGraph(nodes, [edge('a', 'b')], { all: true }).positions).sort()).toEqual(['a', 'b'])
  })

  it('ranks left to right along edges', () => {
    const r = layoutGraph([node('a'), node('b'), node('c')], [edge('a', 'b'), edge('b', 'c')])
    expect(r.failed).toBeNull()
    expect(r.positions.a.x).toBeLessThan(r.positions.b.x)
    expect(r.positions.b.x).toBeLessThan(r.positions.c.x)
  })

  it('lays out a cycle without throwing when no back-edge data exists', () => {
    const r = layoutGraph([node('a'), node('b')], [edge('a', 'b'), edge('b', 'a')])
    expect(r.failed).toBeNull()
    expect(Object.values(r.positions).every(isFinitePoint)).toBe(true)
  })

  it('excludes named backward edges from ranking', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'a', 'loop')]
    const r = layoutGraph(nodes, edges, { backwardKeys: new Set(['loop']) })
    expect(r.positions.a.x).toBeLessThan(r.positions.c.x)
  })

  it('never invents a node for a dangling edge', () => {  // clause: GRAPH_CANVAS-8
    const r = layoutGraph([node('intake')], [edge('intake', 'ghost')])
    expect(r.failed).toBeNull()
    expect(Object.keys(r.positions)).toEqual(['intake'])
  })

  it('emits only finite coordinates', () => {  // clause: GRAPH_CANVAS-8
    const r = layoutGraph([node('a'), node('b', { x: NaN, y: 0 })], [])
    expect(Object.values(r.positions).every(isFinitePoint)).toBe(true)
    expect(Object.keys(r.positions).sort()).toEqual(['a', 'b'])
  })
})

describe('helpers', () => {
  it('sizes a node by its busier port column', () => {
    expect(nodeHeight(node('a'))).toBe(62)
  })
  it('grids nodes when layout fails', () => {
    expect(gridPositions([node('a'), node('b'), node('c'), node('d')]).d).toEqual({ x: 250, y: 140 })
  })
  it('dips a backward path below both endpoints', () => {
    const [path, , labelY] = backwardPath(400, 50, 100, 60)
    expect(path.startsWith('M 400,50 C')).toBe(true)
    expect(labelY).toBeGreaterThan(60)
  })
})
```

`interfaces/ui/src/components/graph_canvas/connection.spec.ts` (create; 29 lines):

```ts
import { describe, it, expect, vi } from 'vitest'
import { acceptConnection, handleId, toPortRefs } from './connection'

const c = { source: 'architect', sourceHandle: handleId('out', 'spec'), target: 'architecture', targetHandle: handleId('in', 'artifact') }

describe('acceptConnection', () => {
  it('accepts exactly what the caller accepts, passing port refs', () => {  // clause: GRAPH_CANVAS-6
    const yes = vi.fn(() => true)
    expect(acceptConnection(true, yes, c)).toBe(true)
    expect(yes).toHaveBeenCalledWith({ node: 'architect', port: 'spec' }, { node: 'architecture', port: 'artifact' })
    expect(acceptConnection(true, () => false, c)).toBe(false)
  })

  it('evaluates no rule of its own: a self-loop and a repeat both defer to the caller', () => {  // clause: GRAPH_CANVAS-6
    const self = { source: 'a', sourceHandle: 'out:x', target: 'a', targetHandle: 'in:x' }
    expect(acceptConnection(true, () => true, self)).toBe(true)
    expect(acceptConnection(true, () => true, c)).toBe(true)
  })

  it('refuses everything when not editable, without asking', () => {  // clause: GRAPH_CANVAS-5
    const ask = vi.fn(() => true)
    expect(acceptConnection(false, ask, c)).toBe(false)
    expect(ask).not.toHaveBeenCalled()
  })

  it('maps handles to port refs', () => {
    expect(toPortRefs(c)).toEqual({ from: { node: 'architect', port: 'spec' }, to: { node: 'architecture', port: 'artifact' } })
  })
})
```
- [ ] **Step 3: Run them to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/graph_canvas
```

Expected: FAIL — both spec files fail to resolve `./graph_layout` / `./connection`.
- [ ] **Step 4: Write the helpers**

`interfaces/ui/src/components/graph_canvas/types.ts` (create; 48 lines):

```ts
// Display primitives for the graph canvas (E-76 spec §10.2). Constructible
// as literals; no domain type and no vue-flow type ever appears here
// (FR-1400). The dashboard's adapters/graph.ts builds these.

export type CanvasStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale'

export const CANVAS_STATUSES: readonly CanvasStatus[] = ['idle', 'running', 'blocked', 'done', 'failed', 'stale']

export interface CanvasPort {
  name: string
  side: 'in' | 'out'
  kind: 'signal' | 'data'
  label: string
  optional: boolean
}

export interface CanvasNode {
  key: string
  title: string
  subtitle?: string
  ports: CanvasPort[]
  status?: CanvasStatus
  metrics?: { cost?: string; elapsed?: string; round?: string }
  issueCount: number
  position?: { x: number; y: number }
  /** A node whose type is not in the catalog: handles render, none connect. */
  readonly?: boolean
}

export interface PortRef {
  node: string
  port: string
}

export interface CanvasEdge {
  key: string
  from: PortRef
  to: PortRef
  label?: string
  backward: boolean
  counter?: { used: number; max: number }
  issueCount: number
}

export interface Point {
  x: number
  y: number
}
```

`interfaces/ui/src/components/graph_canvas/graph_layout.ts` (create; 79 lines):

```ts
// Auto-layout for the graph canvas (E-76 spec §8.4). Presentation only:
// nothing here decides legality or marks an edge backward.
import dagre from '@dagrejs/dagre'
import type { CanvasEdge, CanvasNode, Point } from './types'

export const NODE_WIDTH = 190
const HEADER = 44
const PORT_ROW = 18

export function nodeHeight(node: Pick<CanvasNode, 'ports'>): number {
  const ins = node.ports.filter((p) => p.side === 'in').length
  const outs = node.ports.filter((p) => p.side === 'out').length
  return HEADER + PORT_ROW * Math.max(ins, outs, 1)
}

export function isFinitePoint(p: Point | undefined | null): p is Point {
  return !!p && Number.isFinite(p.x) && Number.isFinite(p.y)
}

export interface LayoutResult {
  positions: Record<string, Point>
  failed: string | null
}

/**
 * Positions for `nodes`. `all` re-lays every node (Tidy); otherwise only nodes
 * without a finite position get one. Edges named in `backwardKeys` are left
 * out of ranking so loops do not distort ranks; before any back-edge data
 * exists, dagre's own acyclic pass (a greedy feedback arc set) breaks cycles
 * for ranking. Input hygiene: an edge whose endpoint is not a supplied node
 * key is never added -- graphlib would invent a phantom node for it
 * (GRAPH_CANVAS-8). On any exception the existing positions are kept and
 * unpositioned nodes go on a grid.
 */
export function layoutGraph(
  nodes: readonly CanvasNode[],
  edges: readonly CanvasEdge[],
  opts: { all?: boolean; backwardKeys?: ReadonlySet<string> } = {},
): LayoutResult {
  const wanted = nodes.filter((n) => opts.all || !isFinitePoint(n.position))
  if (wanted.length === 0) return { positions: {}, failed: null }
  try {
    const g = new dagre.graphlib.Graph({ multigraph: true })
    g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90, acyclicer: 'greedy' })
    g.setDefaultEdgeLabel(() => ({}))
    const keys = new Set(nodes.map((n) => n.key))
    for (const n of nodes) g.setNode(n.key, { width: NODE_WIDTH, height: nodeHeight(n) })
    for (const e of edges) {
      if (!keys.has(e.from.node) || !keys.has(e.to.node)) continue
      if (opts.backwardKeys?.has(e.key)) continue
      g.setEdge(e.from.node, e.to.node, {}, e.key)
    }
    dagre.layout(g)
    const positions: Record<string, Point> = {}
    for (const n of wanted) {
      const laid = g.node(n.key)
      const p = { x: laid.x - NODE_WIDTH / 2, y: laid.y - nodeHeight(n) / 2 }
      if (isFinitePoint(p)) positions[n.key] = p
    }
    return { positions, failed: null }
  } catch (e) {
    return { positions: gridPositions(wanted), failed: String(e) }
  }
}

export function gridPositions(nodes: readonly CanvasNode[]): Record<string, Point> {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)))
  return Object.fromEntries(
    nodes.map((n, i) => [n.key, { x: (i % cols) * (NODE_WIDTH + 60), y: Math.floor(i / cols) * 140 }]),
  )
}

/** A downward arc for a backward edge (GRAPH_CANVAS-2). */
export function backwardPath(sx: number, sy: number, tx: number, ty: number): [string, number, number] {
  const dip = Math.max(80, Math.abs(sx - tx) * 0.25)
  const bottom = Math.max(sy, ty) + dip
  const path = `M ${sx},${sy} C ${sx + 60},${bottom} ${tx - 60},${bottom} ${tx},${ty}`
  return [path, (sx + tx) / 2, bottom - dip * 0.25]
}
```

`interfaces/ui/src/components/graph_canvas/connection.ts` (create; 29 lines):

```ts
// GRAPH_CANVAS-6, the fence: a connection is accepted iff the canvas is
// editable and the CALLER's `connectable` says so. The component evaluates
// no other rule -- multiplicity, duplicates, cycles are validate.py's.
import type { PortRef } from './types'

export interface HandleConnection {
  source: string
  sourceHandle?: string | null
  target: string
  targetHandle?: string | null
}

export const handleId = (side: 'in' | 'out', port: string) => `${side}:${port}`

const portOf = (handle: string | null | undefined) => (handle ?? '').replace(/^(in|out):/, '')

export function toPortRefs(c: HandleConnection): { from: PortRef; to: PortRef } {
  return { from: { node: c.source, port: portOf(c.sourceHandle) }, to: { node: c.target, port: portOf(c.targetHandle) } }
}

export function acceptConnection(
  editable: boolean,
  connectable: (from: PortRef, to: PortRef) => boolean,
  c: HandleConnection,
): boolean {
  if (!editable) return false
  const { from, to } = toPortRefs(c)
  return connectable(from, to)
}
```
- [ ] **Step 5: Run the specs to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/graph_canvas
npm run typecheck --workspace @kroker/ui
```

Expected: PASS — 13 tests (graph_layout 9, connection 4); typecheck clean.
- [ ] **Step 6: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 7: Commit**

Write `.workspace/tmp/e76-t1-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 canvas helpers and vue-flow/dagre deps

Adds @vue-flow/core 1.48.2 and @dagrejs/dagre 3.1.1 as @kroker/ui's
first runtime dependencies, plus the canvas's pure helpers: display
primitives, dagre auto-layout with input hygiene (no phantom node for a
dangling edge, finite coordinates only), a backward-edge arc, and the
GRAPH_CANVAS-6 connection fence. vue-flow's stylesheet is not imported:
it carries colour literals.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/package.json
git add package-lock.json
git add interfaces/ui/src/components/graph_canvas/types.ts
git add interfaces/ui/src/components/graph_canvas/graph_layout.ts
git add interfaces/ui/src/components/graph_canvas/graph_layout.spec.ts
git add interfaces/ui/src/components/graph_canvas/connection.ts
git add interfaces/ui/src/components/graph_canvas/connection.spec.ts
git commit -F .workspace/tmp/e76-t1-msg.txt
```
### Task 2: Strict graph YAML loader — `io.py`

**Files:**
- Modify: `src/sdlc/graph/io.py` (whole file below)
- Modify: `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` §7.2 (one bullet)
- Test: `tests/graph/test_graph_io_strict.py`

**Interfaces:**
- Consumes: `sdlc.graph.model.PipelineGraph`.
- Produces: unchanged public API (`from_yaml`, `to_yaml`, `GraphSchemaError`); `from_yaml` now also raises `GraphSchemaError` for a duplicate key at any level, an anchor, an alias or a `<<` merge key, with the PyYAML mark on `__cause__.problem_mark` (Task 3 reads it for line/column).

- [ ] **Step 1: Write the failing test**

`tests/graph/test_graph_io_strict.py` (create; 79 lines):

```python
"""E-76 D10: graph text rejects duplicate keys, anchors, aliases and merges."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.graph import GraphSchemaError, from_yaml, to_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


@pytest.mark.parametrize(
    "text",
    [
        "schema_version: 1\nnodes: []\nnodes: []\nedges: []\n",
        "schema_version: 1\nnodes:\n- id: a\n  type: intake\n  role:\n    model: x\n    model: y\n"
        "edges: []\n",
        "schema_version: 1\nnodes: []\nedges:\n- source: a\n  source: b\n  source_port: ok\n"
        "  target: c\n  target_port: trigger\n",
        "schema_version: 1\nnodes: []\nedges: [{source: a, source: b}]\n",
    ],
    ids=["top_level", "inside_role", "inside_edge_item", "flow_mapping"],
)
def test_duplicate_key_is_rejected_at_every_level(text):
    with pytest.raises(GraphSchemaError, match="duplicate key") as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, yaml.constructor.ConstructorError)


def test_alias_is_rejected_in_the_composer():
    text = "schema_version: 1\nnodes: &n []\nedges: *n\n"
    with pytest.raises(GraphSchemaError, match="anchors are not allowed") as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, yaml.composer.ComposerError)


def test_bare_alias_is_rejected_in_the_composer():
    # An alias with an unknown anchor still fails as an alias, not a lookup.
    with pytest.raises(GraphSchemaError, match="aliases are not allowed") as info:
        from_yaml("schema_version: 1\nnodes: *missing\nedges: []\n")
    assert isinstance(info.value.__cause__, yaml.composer.ComposerError)


def test_nested_alias_bomb_fails_fast():
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 9) + "]" for i in range(1, 9)]
    with pytest.raises(GraphSchemaError, match="anchors are not allowed"):
        from_yaml("\n".join(lines) + "\n")


def test_merge_key_is_rejected():
    text = "schema_version: 1\nnodes: []\nedges:\n- <<: {source: a}\n  source_port: ok\n"
    with pytest.raises(GraphSchemaError, match="merge keys"):
        from_yaml(text)


def test_python_object_tag_is_still_rejected():
    with pytest.raises(GraphSchemaError) as info:
        from_yaml("!!python/object:os.system {}\n")
    assert isinstance(info.value.__cause__, yaml.YAMLError)


def test_yaml_error_mark_survives_on_the_cause():
    with pytest.raises(GraphSchemaError) as info:
        from_yaml("schema_version: 1\nnodes: []\nnodes: []\nedges: []\n")
    mark = info.value.__cause__.problem_mark
    assert (mark.line, mark.column) == (2, 0)


def test_the_fixture_still_round_trips():
    text = FIXTURE.read_text(encoding="utf-8")
    assert to_yaml(from_yaml(text)) == text


def test_the_strict_loader_leaves_safe_load_untouched():
    assert yaml.safe_load("a: 1\na: 2\n") == {"a": 2}
```
- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/graph/test_graph_io_strict.py -q
```

Expected: FAIL — `9 failed, 3 passed` (duplicate keys, aliases, the bomb, merge keys and the mark test fail against `yaml.safe_load`; `!!python/object`, the fixture round-trip and the untouched-`safe_load` tests already pass).
- [ ] **Step 3: Replace `src/sdlc/graph/io.py`**

`src/sdlc/graph/io.py` (replace; 97 lines):

```python
"""YAML storage shape for `graphs/<sha>.yaml` (E-72, spec §7.2).

Serialize/deserialize only -- writing, reading and lookup of the store are
E-75/E-77. `from_yaml` raises exactly one exception type, GraphSchemaError,
for every way text fails to become a graph: one catch contract for E-75/E-76.

Graph text is stricter than YAML (E-76 spec D10): anchors, aliases and `<<`
merge keys are rejected, and so is a duplicate key in any mapping --
`yaml.safe_load` would keep the last one silently.
"""

from __future__ import annotations

import yaml

from .model import PipelineGraph

_SCHEMA_VERSION = 1
_MERGE_TAG = "tag:yaml.org,2002:merge"


class GraphSchemaError(ValueError):
    """Graph text is not a well-shaped PipelineGraph (bad YAML, not a
    mapping, unsupported schema_version, or a model shape failure).
    Legality of a well-shaped graph is validate.py's (E-73), not this."""


class _StrictLoader(yaml.SafeLoader):
    """MUST stay a yaml.SafeLoader subclass: it inherits only the safe
    constructors, which is what makes yaml.load(..., Loader=_StrictLoader)
    safe. Never register these overrides on yaml.SafeLoader itself -- that
    would change every safe_load in the process."""

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        # Reject at COMPOSE time: by construct time an alias graph exists.
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                None, None, "aliases are not allowed in graph text", event.start_mark
            )
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise yaml.composer.ComposerError(
                None, None, "anchors are not allowed in graph text", event.start_mark
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
        seen: set[object] = set()
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "merge keys (<<) are not allowed in graph text",
                    key_node.start_mark,
                )
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def to_yaml(graph: PipelineGraph) -> str:
    """Deterministic: model field order, normalized node/edge order,
    exclude_defaults. Cosmetics are INCLUDED -- the canvas needs them."""
    return yaml.safe_dump(
        graph.model_dump(mode="json", exclude_defaults=True),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def from_yaml(text: str) -> PipelineGraph:
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 -- a SafeLoader subclass
    except yaml.YAMLError as exc:
        raise GraphSchemaError(f"graph text is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise GraphSchemaError(f"graph document must be a mapping, got {type(data).__name__}")
    version = data.get("schema_version")
    # type() not isinstance(): bool is an int subclass, and `true` is not 1.
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise GraphSchemaError(
            f"unsupported graph schema_version {version!r}; this worker reads {_SCHEMA_VERSION}"
        )
    try:
        return PipelineGraph.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise GraphSchemaError(f"graph does not match the schema: {exc}") from exc
```
- [ ] **Step 4: Record the rule in the E-72 spec (artifact boundary)**

In `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` §7.2, replace:

```markdown
  - `yaml.safe_load`; a `yaml.YAMLError` is re-raised as `GraphSchemaError`
    (chained);
```

with:

```markdown
  - a strict `yaml.SafeLoader` subclass (E-76 spec D10) rejects anchors,
    aliases and `<<` merge keys at compose/construct time and a duplicate key
    in any mapping (`yaml.safe_load` would keep the last one silently); every
    `yaml.YAMLError` is re-raised as `GraphSchemaError` (chained);
```
- [ ] **Step 5: Run the graph suite to verify it passes**

```bash
python -m pytest tests/graph -q
```

Expected: PASS — 117 passed (the existing E-72 tests, including `test_graph_purity.py`, stay green: `io.py`'s module-level imports are unchanged).
- [ ] **Step 6: Gate**

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
python scripts/check_file_size.py
```

Expected: all clean (mypy: no NEW errors in the touched files; the repo baseline is scoped to `src/`).
- [ ] **Step 7: Commit**

Write `.workspace/tmp/e76-t2-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(graph): E-76 strict graph YAML loader

from_yaml now loads through a yaml.SafeLoader subclass that rejects
anchors and aliases at compose time (before an alias graph exists) and a
duplicate key or << merge key in any mapping at construct time. Closes the
E-72 review minor: yaml.safe_load kept the last duplicate `nodes:` block
silently. Every failure still surfaces as GraphSchemaError with the PyYAML
mark on __cause__.
```

Then, one path per `git add`:

```bash
git add src/sdlc/graph/io.py
git add tests/graph/test_graph_io_strict.py
git add docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md
git commit -F .workspace/tmp/e76-t2-msg.txt
```
### Task 3: Graph wire projections — `graph_wire.py`

**Files:**
- Create: `src/sdlc/dashboard/graph_wire.py`
- Test: `tests/test_dashboard_graph_wire.py`

**Interfaces:**
- Consumes: `sdlc.graph` (`NODE_TYPES`, `GraphNode`, `GraphEdge`, `GraphSchemaError`, `NodeTypeSpec`, `PipelineGraph`, `from_yaml`, `ports_compatible`, `to_yaml`); `CANONICAL_STAGES` imported inside `catalog()`.
- Produces: `MAX_GRAPH_BYTES = 262144`; models `ShapeError`, `EdgeRef`, `PortWire`, `ConnectTarget`, `NodeTypeWire`, `Capabilities`, `CatalogWire`, `ParseOk`, `ParseErr`, `SerializeOk` (FINAL) and `IssueTarget`, `Issue`, `ValidationWire`, `SaveOk`, `LoadOk`, `LoadMissing`, `GraphResponse`, `NoGraph`, `NodeRunState`, `EdgeRunState`, `PendingRef`, `GraphState` (PROVISIONAL); functions `default_id(type_) → str`, `catalog(registry=NODE_TYPES) → CatalogWire`, `parse_text(text) → ParseOk | ParseErr`, `parse_object(obj) → ParseOk | ParseErr`, `serialize(obj) → SerializeOk | ParseErr`.

- [ ] **Step 1: Write the failing test**

`tests/test_dashboard_graph_wire.py` (create; 239 lines):

```python
"""E-76 graph wire projections (spec §5.2-§5.4, §6.2, §10.1)."""

from __future__ import annotations

import ast
import importlib.util
import itertools
import re
from pathlib import Path

import pytest

import sdlc.dashboard.graph_wire as graph_wire
from sdlc.benchmarks.heatmap import CANONICAL_STAGES
from sdlc.core.models import GateConfig, RoleConfig
from sdlc.graph import (
    NODE_TYPES,
    NodePort,
    NodeTypeSpec,
    from_yaml,
    ports_compatible,
    to_yaml,
)
from sdlc.graph.model import ID_PATTERN

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


def _fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# --- catalog ------------------------------------------------------------------


def test_catalog_lists_every_registered_type_sorted():
    types = [t.type for t in graph_wire.catalog().node_types]
    assert types == sorted(NODE_TYPES)


def test_connectable_is_exactly_ports_compatible_over_every_pair():
    wire = {t.type: t for t in graph_wire.catalog().node_types}
    for src_key, src in NODE_TYPES.items():
        for out_port in (p for p in src.ports if p.direction == "out"):
            expected = sorted(
                (dst_key, in_port.name)
                for dst_key, dst in NODE_TYPES.items()
                for in_port in dst.ports
                if ports_compatible(out_port, in_port)
            )
            got = sorted((c.type, c.port) for c in wire[src_key].connectable[out_port.name])
            assert got == expected, (src_key, out_port.name)


def test_connectable_follows_an_injected_registry():
    registry = {
        "a": NodeTypeSpec(
            type="a",
            kind="stage",
            role=None,
            canonical_stage=None,
            ports=(NodePort(name="out", direction="out", payload="X"),),
        ),
        "b": NodeTypeSpec(
            type="b",
            kind="stage",
            role=None,
            canonical_stage=None,
            ports=(
                NodePort(name="x", direction="in", payload="X"),
                NodePort(name="y", direction="in", payload="Y"),
            ),
        ),
    }
    (a, b) = graph_wire.catalog(registry).node_types
    assert [(c.type, c.port) for c in a.connectable["out"]] == [("b", "x")]
    assert b.connectable == {}


def test_default_id_matches_the_id_pattern_for_every_type():
    for node_type in graph_wire.catalog().node_types:
        assert re.fullmatch(ID_PATTERN, node_type.default_id), node_type.type
    assert graph_wire.default_id("gate.plan") == "gate_plan"


def test_catalog_serves_the_benchmark_canonical_stages():
    assert graph_wire.catalog().canonical_stages == CANONICAL_STAGES


def test_catalog_capabilities_are_all_false_until_later_epics():
    wire = graph_wire.catalog().model_dump(mode="json")["capabilities"]
    assert wire == {"validate": False, "save": False, "load": False, "run_graph": False}
    assert graph_wire.Capabilities.model_validate({"validate": True}).can_validate is True


def test_catalog_serves_node_and_edge_schemas_with_embedded_defs():
    schemas = graph_wire.catalog().schemas
    assert set(schemas) == {"GraphNode", "GraphEdge"}
    assert {"RoleConfig", "GateConfig"} <= set(schemas["GraphNode"]["$defs"])
    assert graph_wire.catalog().max_graph_bytes == graph_wire.MAX_GRAPH_BYTES == 256 * 1024


def test_catalog_is_order_independent():
    keys = sorted(NODE_TYPES)
    baseline = graph_wire.catalog().model_dump_json()
    for order in itertools.islice(itertools.permutations(keys), 50):
        registry = {k: NODE_TYPES[k] for k in order}
        assert graph_wire.catalog(registry).model_dump_json() == baseline


# --- schema coverage (SCHEMA_FORM-3's Python mirror) ---------------------------

_SCALARS = {"string", "number", "integer", "boolean"}


def _supported(schema: dict, defs: dict) -> bool:
    """The construct set schema_form renders natively (spec §8.3)."""
    if "$ref" in schema:
        return _supported(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        branches = schema["anyOf"]
        nulls = [b for b in branches if b.get("type") == "null"]
        rest = [b for b in branches if b.get("type") != "null"]
        return len(nulls) == 1 and len(rest) == 1 and _supported(rest[0], defs)
    kind = schema.get("type")
    if kind in _SCALARS:
        return True
    if kind == "array":
        return schema.get("items", {}).get("type") == "string"
    if kind == "object":
        return all(_supported(p, defs) for p in schema.get("properties", {}).values())
    return False


@pytest.mark.parametrize("model", [RoleConfig, GateConfig])
def test_every_role_and_gate_property_is_a_supported_construct(model):
    """Red on purpose if a pydantic upgrade or a new field emits a construct
    schema_form cannot render natively. Extend schema_form, never this set."""
    node_schema = graph_wire.catalog().schemas["GraphNode"]
    defs = node_schema["$defs"]
    for name, prop in defs[model.__name__]["properties"].items():
        assert _supported(prop, defs), (model.__name__, name, prop)


def test_every_edge_property_is_a_supported_construct():
    edge_schema = graph_wire.catalog().schemas["GraphEdge"]
    for name, prop in edge_schema["properties"].items():
        assert _supported(prop, edge_schema.get("$defs", {})), name


# --- parse / serialize ------------------------------------------------------------


def test_parse_text_ok_carries_the_graph_and_its_sha():
    result = graph_wire.parse_text(_fixture_text())
    graph = from_yaml(_fixture_text())
    assert isinstance(result, graph_wire.ParseOk)
    assert result.sha == graph.content_sha()
    assert result.graph == graph.model_dump(mode="json", exclude_defaults=True)


def test_parse_text_maps_a_model_failure_to_loc_and_msg():
    text = "schema_version: 1\nnodes:\n- id: Bad\n  type: intake\nedges: []\n"
    result = graph_wire.parse_text(text)
    assert isinstance(result, graph_wire.ParseErr)
    assert [e.loc for e in result.shape_errors] == [["nodes", 0, "id"]]
    assert result.shape_errors[0].line is None


def test_parse_text_carries_a_one_based_line_for_yaml_failures():
    result = graph_wire.parse_text("schema_version: 1\nnodes: []\nnodes: []\nedges: []\n")
    assert isinstance(result, graph_wire.ParseErr)
    (error,) = result.shape_errors
    assert error.loc == [] and "duplicate key" in error.msg
    assert (error.line, error.column) == (3, 1)


def test_parse_text_reports_version_failures_without_a_location():
    result = graph_wire.parse_text("schema_version: 2\nnodes: []\nedges: []\n")
    assert isinstance(result, graph_wire.ParseErr)
    (error,) = result.shape_errors
    assert error.loc == [] and error.line is None and "schema_version" in error.msg


def test_parse_object_round_trips_the_wire_graph():
    wire = graph_wire.parse_text(_fixture_text())
    again = graph_wire.parse_object(wire.graph)
    assert again == wire


def test_parse_object_maps_failures():
    result = graph_wire.parse_object({"schema_version": 1, "nodes": [{"id": "a"}], "edges": []})
    assert isinstance(result, graph_wire.ParseErr)
    assert [e.loc for e in result.shape_errors] == [["nodes", 0, "type"]]


def test_serialize_is_exactly_to_yaml():
    wire = graph_wire.parse_text(_fixture_text())
    result = graph_wire.serialize(wire.graph)
    assert isinstance(result, graph_wire.SerializeOk)
    assert result.yaml == to_yaml(from_yaml(_fixture_text()))


def test_serialize_refuses_a_misshapen_object():
    result = graph_wire.serialize({"schema_version": 1, "nodes": "x", "edges": []})
    assert isinstance(result, graph_wire.ParseErr)


# --- boundaries ---------------------------------------------------------------------

_ALLOWED = {"__future__", "collections", "typing", "pydantic", "sdlc.graph", "sdlc.core.models"}


def test_module_level_imports_are_pinned():
    tree = ast.parse(Path(graph_wire.__file__).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    roots = {m if m.startswith("sdlc") else m.split(".")[0] for m in found}
    assert roots <= _ALLOWED, sorted(roots - _ALLOWED)


def test_there_is_no_validate_stub():
    assert not hasattr(graph_wire, "validate")


def test_validation_wire_is_wired_once_validate_exists():
    """Forcing test (spec §10.1): E-73 names its module sdlc.graph.validate
    (handover, spec §11). The day it lands, this goes red until graph_wire
    maps validate.py's result onto ValidationWire."""
    if importlib.util.find_spec("sdlc.graph.validate") is None:
        pytest.skip("E-73 has not landed sdlc.graph.validate")
    assert hasattr(graph_wire, "validation"), (
        "sdlc.graph.validate exists: add graph_wire's mapping onto ValidationWire "
        "and real validate fixtures (E-76 spec §5.5)"
    )
```
- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_dashboard_graph_wire.py -q
```

Expected: FAIL — collection error, `ModuleNotFoundError: No module named 'sdlc.dashboard.graph_wire'`.
- [ ] **Step 3: Write the module**

`src/sdlc/dashboard/graph_wire.py` (create; 348 lines):

```python
"""Graph wire shapes for the dashboard (E-76, FR-1205).

Spec: docs/superpowers/specs/2026-09-14-graph-canvas-design.md §5-§6.

Pure projections over sdlc.graph: the models here are the HTTP contract the
canvas consumes. E-76's routes (catalog, parse, serialize) use them now;
E-75's routes use the PROVISIONAL ones as `response_model=` later, so a
route cannot drift from the fixtures `scripts/dump_graph_fixtures.py`
records from these same functions.

Nothing here decides legality (FR-1202): `connectable` is Python's
`ports_compatible` served as data, and there is deliberately no validate
stub -- a fake "no issues" is worse than none.

Module-level imports stay within stdlib, pydantic, sdlc.graph and
sdlc.core.models (pinned by tests/test_dashboard_graph_wire.py).
CANONICAL_STAGES is imported inside catalog(): benchmarks sits on the
benchmarks <-> stages import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sdlc.graph import (
    NODE_TYPES,
    GraphEdge,
    GraphNode,
    GraphSchemaError,
    NodeTypeSpec,
    PipelineGraph,
    from_yaml,
    ports_compatible,
    to_yaml,
)

MAX_GRAPH_BYTES = 256 * 1024

_WIRE = ConfigDict(frozen=True, extra="forbid")


# --- shared -----------------------------------------------------------------


class ShapeError(BaseModel):
    model_config = _WIRE

    loc: list[str | int]
    msg: str
    line: int | None = None
    column: int | None = None


class EdgeRef(BaseModel):
    model_config = _WIRE

    source: str
    source_port: str
    target: str
    target_port: str


# --- catalog (FINAL) -----------------------------------------------------------


class PortWire(BaseModel):
    model_config = _WIRE

    name: str
    direction: Literal["in", "out"]
    payload: str | None
    required: bool
    multiplicity: Literal["one", "many"]


class ConnectTarget(BaseModel):
    model_config = _WIRE

    type: str
    port: str


class NodeTypeWire(BaseModel):
    model_config = _WIRE

    type: str
    kind: Literal["stage", "gate"]
    role: str | None
    canonical_stage: str | None
    default_id: str
    ports: list[PortWire]
    connectable: dict[str, list[ConnectTarget]]


class Capabilities(BaseModel):
    """Server-declared graph capabilities (spec D9). E-76 serves all False;
    E-73 flips `validate`, E-75/E-77 the rest. The wire key `validate` is an
    alias: a field of that name would shadow BaseModel.validate."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", serialize_by_alias=True, validate_by_name=True
    )

    can_validate: bool = Field(default=False, alias="validate")
    save: bool = False
    load: bool = False
    run_graph: bool = False


class CatalogWire(BaseModel):
    model_config = _WIRE

    node_types: list[NodeTypeWire]
    canonical_stages: list[str]
    schemas: dict[str, dict[str, Any]]
    capabilities: Capabilities
    max_graph_bytes: int


def default_id(type_: str) -> str:
    """A node id for a fresh node of `type_`: TYPE_PATTERN with its one dot
    turned into '_' is always an ID_PATTERN (pinned by a test)."""
    return type_.replace(".", "_")


def _connectable(
    spec: NodeTypeSpec, registry: Mapping[str, NodeTypeSpec]
) -> dict[str, list[ConnectTarget]]:
    out: dict[str, list[ConnectTarget]] = {}
    for port in spec.ports:
        if port.direction != "out":
            continue
        out[port.name] = [
            ConnectTarget(type=other_key, port=in_port.name)
            for other_key in sorted(registry)
            for in_port in registry[other_key].ports
            if ports_compatible(port, in_port)
        ]
    return out


def catalog(registry: Mapping[str, NodeTypeSpec] = NODE_TYPES) -> CatalogWire:
    from sdlc.benchmarks.heatmap import CANONICAL_STAGES

    node_types = [
        NodeTypeWire(
            type=spec.type,
            kind=spec.kind,
            role=spec.role,
            canonical_stage=spec.canonical_stage,
            default_id=default_id(spec.type),
            ports=[PortWire(**p.model_dump()) for p in spec.ports],
            connectable=_connectable(spec, registry),
        )
        for spec in (registry[key] for key in sorted(registry))
    ]
    return CatalogWire(
        node_types=node_types,
        canonical_stages=list(CANONICAL_STAGES),
        schemas={
            "GraphNode": GraphNode.model_json_schema(),
            "GraphEdge": GraphEdge.model_json_schema(),
        },
        capabilities=Capabilities(),
        max_graph_bytes=MAX_GRAPH_BYTES,
    )


# --- parse / serialize (FINAL) -------------------------------------------------


class ParseOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    graph: dict[str, Any]
    sha: str


class ParseErr(BaseModel):
    model_config = _WIRE

    ok: Literal[False] = False
    shape_errors: list[ShapeError]


class SerializeOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    yaml: str


def _graph_json(graph: PipelineGraph) -> dict[str, Any]:
    return graph.model_dump(mode="json", exclude_defaults=True)


def _validation_errors(exc: ValidationError) -> list[ShapeError]:
    return [ShapeError(loc=list(e["loc"]), msg=e["msg"]) for e in exc.errors()]


def _schema_errors(exc: GraphSchemaError) -> list[ShapeError]:
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        return _validation_errors(cause)
    mark = getattr(cause, "problem_mark", None)
    if mark is not None:
        # PyYAML marks are 0-based; editors count from 1.
        return [ShapeError(loc=[], msg=str(exc), line=mark.line + 1, column=mark.column + 1)]
    return [ShapeError(loc=[], msg=str(exc))]


def parse_text(text: str) -> ParseOk | ParseErr:
    try:
        graph = from_yaml(text)
    except GraphSchemaError as exc:
        return ParseErr(shape_errors=_schema_errors(exc))
    return ParseOk(graph=_graph_json(graph), sha=graph.content_sha())


def parse_object(obj: Any) -> ParseOk | ParseErr:
    try:
        graph = PipelineGraph.model_validate(obj)
    except ValidationError as exc:
        return ParseErr(shape_errors=_validation_errors(exc))
    return ParseOk(graph=_graph_json(graph), sha=graph.content_sha())


def serialize(obj: Any) -> SerializeOk | ParseErr:
    try:
        graph = PipelineGraph.model_validate(obj)
    except ValidationError as exc:
        return ParseErr(shape_errors=_validation_errors(exc))
    return SerializeOk(yaml=to_yaml(graph))


# --- PROVISIONAL: validate (E-73 + E-75) ---------------------------------------


class IssueTarget(BaseModel):
    model_config = _WIRE

    kind: Literal["graph", "node", "edge", "port"]
    id: str | None = None
    edge: EdgeRef | None = None
    node: str | None = None
    port: str | None = None


class Issue(BaseModel):
    model_config = _WIRE

    code: str
    severity: Literal["error", "warning"]
    message: str
    target: IssueTarget


class ValidationWire(BaseModel):
    model_config = _WIRE

    issues: list[Issue]
    back_edges: list[EdgeRef]


# --- PROVISIONAL: save / load (E-75 + E-77) ------------------------------------


class SaveOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    sha: str
    validation: ValidationWire | None


class LoadOk(BaseModel):
    model_config = _WIRE

    ok: Literal[True] = True
    sha: str
    graph: dict[str, Any]


class LoadMissing(BaseModel):
    model_config = _WIRE

    ok: Literal[False] = False
    reason: Literal["not_found"] = "not_found"


# --- PROVISIONAL: run graph and run state (E-75 on E-74) -----------------------


class GraphResponse(BaseModel):
    model_config = _WIRE

    kind: Literal["graph"] = "graph"
    sha: str
    graph: dict[str, Any]
    back_edges: list[EdgeRef]


class NoGraph(BaseModel):
    model_config = _WIRE

    kind: Literal["no_graph"] = "no_graph"
    reason: Literal["legacy_run"] = "legacy_run"


class NodeRunState(BaseModel):
    model_config = _WIRE

    status: Literal["idle", "running", "blocked", "done", "failed", "stale"]
    round: int
    started_at: str | None
    ended_at: str | None
    cost_usd: float | None


class EdgeRunState(BaseModel):
    model_config = _WIRE

    edge: EdgeRef
    traversals: int


class PendingRef(BaseModel):
    model_config = _WIRE

    node: str
    key: str
    kind: Literal["gate", "clarify", "escalation"]


class GraphState(BaseModel):
    model_config = _WIRE

    kind: Literal["state"] = "state"
    graph_sha: str
    nodes: dict[str, NodeRunState]
    edges: list[EdgeRunState]
    current_nodes: list[str]
    pending: list[PendingRef]
    terminal: Literal["done", "failed", "escalated"] | None
```
- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_dashboard_graph_wire.py -q
```

Expected: PASS — 21 passed, 1 skipped (`test_validation_wire_is_wired_once_validate_exists` skips until E-73 lands `sdlc.graph.validate`; that is the forcing test working).
- [ ] **Step 5: Gate**

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
python scripts/check_file_size.py
```

Expected: all clean (mypy: no NEW errors in the touched files; the repo baseline is scoped to `src/`).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t3-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 graph wire projections

sdlc/dashboard/graph_wire.py projects sdlc.graph onto the canvas's HTTP
contract: the node-type catalog with a connectable table computed by
ports_compatible, served JSON schemas and canonical stages, server-declared
capabilities (all false until E-73/E-75/E-77), and shape-only parse and
serialize results. PROVISIONAL validate, save/load and run-state models are
defined for later epics; there is deliberately no validate stub. A forcing
test fails once sdlc.graph.validate exists until the mapping is wired.
```

Then, one path per `git add`:

```bash
git add src/sdlc/dashboard/graph_wire.py
git add tests/test_dashboard_graph_wire.py
git commit -F .workspace/tmp/e76-t3-msg.txt
```
### Task 4: The pure graph routes — `api.py`

**Files:**
- Modify: `src/sdlc/dashboard/api.py` (three edits)
- Test: `tests/test_dashboard_graph_routes.py`

**Interfaces:**
- Consumes: Task 3's `graph_wire`.
- Produces: `GET /graphs/catalog → CatalogWire`; `POST /graphs/parse` with `{yaml: string}` or `{graph: object}` → `ParseOk | ParseErr` (200 for both), `413` above `MAX_GRAPH_BYTES` UTF-8 body bytes, `422` for any other body; `POST /graphs/serialize` with `{graph}` → `SerializeOk | ParseErr`. Mounted under `/api` by `interfaces/dashboard/api/main.py` (unchanged).

- [ ] **Step 1: Write the failing test**

`tests/test_dashboard_graph_routes.py` (create; 102 lines):

```python
"""E-76 pure graph routes: catalog, parse, serialize (spec §5.2-§5.4, §6.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.dashboard import graph_wire
from sdlc.dashboard.api import create_router

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


class _NoPoller:
    """The graph routes must never touch the fleet poller."""

    def __getattr__(self, name):
        raise AssertionError(f"graph route touched the poller: {name}")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(create_router(_NoPoller()))
    return TestClient(app)


def test_catalog_route_serves_the_projection(client):
    r = client.get("/graphs/catalog")
    assert r.status_code == 200
    assert r.json() == graph_wire.catalog().model_dump(mode="json")


def test_parse_route_accepts_yaml_text(client):
    text = FIXTURE.read_text(encoding="utf-8")
    r = client.post("/graphs/parse", json={"yaml": text})
    assert r.status_code == 200
    assert r.json() == graph_wire.parse_text(text).model_dump(mode="json")
    assert r.json()["ok"] is True


def test_parse_route_returns_shape_errors_as_200(client):
    r = client.post("/graphs/parse", json={"yaml": "schema_version: 1\nnodes: []\nnodes: []\n"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["shape_errors"][0]["line"] == 3


def test_parse_route_accepts_a_graph_object(client):
    graph = graph_wire.parse_text(FIXTURE.read_text(encoding="utf-8")).graph
    r = client.post("/graphs/parse", json={"graph": graph})
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.parametrize(
    "body",
    [{}, {"yaml": "x", "graph": {}}, {"yaml": 3}, {"text": "x"}, []],
    ids=["empty", "both", "yaml_not_string", "unknown_key", "not_object"],
)
def test_parse_route_rejects_a_malformed_body_with_422(client, body):
    assert client.post("/graphs/parse", json=body).status_code == 422


def test_parse_route_rejects_non_json_with_422(client):
    r = client.post("/graphs/parse", content=b"yaml: x", headers={"content-type": "text/plain"})
    assert r.status_code == 422


def _raw(body: dict) -> bytes:
    # What the browser sends: JSON.stringify does not \u-escape non-ASCII.
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def test_parse_route_caps_the_body_in_utf8_bytes(client):
    # 'é' is two UTF-8 bytes: under the cap in characters, over it in bytes.
    text = "é" * (graph_wire.MAX_GRAPH_BYTES // 2 + 1)
    assert len(_raw({"yaml": text}).decode("utf-8")) < graph_wire.MAX_GRAPH_BYTES
    r = client.post("/graphs/parse", content=_raw({"yaml": text}))
    assert r.status_code == 413


def test_parse_route_accepts_a_body_exactly_at_the_cap(client):
    overhead = len(_raw({"yaml": ""}))
    text = "a" * (graph_wire.MAX_GRAPH_BYTES - overhead)
    r = client.post("/graphs/parse", content=_raw({"yaml": text}))
    assert r.status_code == 200 and r.json()["ok"] is False


def test_serialize_route_is_to_yaml(client):
    text = FIXTURE.read_text(encoding="utf-8")
    graph = graph_wire.parse_text(text).graph
    r = client.post("/graphs/serialize", json={"graph": graph})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "yaml": text}


def test_serialize_route_rejects_a_yaml_body(client):
    assert client.post("/graphs/serialize", json={"yaml": "x"}).status_code == 422
```
- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_dashboard_graph_routes.py -q
```

Expected: FAIL — `14 failed` (every route answers 404).
- [ ] **Step 3: Edit `src/sdlc/dashboard/api.py`**

(a) Replace the FastAPI import line:

```python
from fastapi import APIRouter, Header, HTTPException
```

with:

```python
from fastapi import APIRouter, Header, HTTPException, Request
```

(b) Replace:

```python
from .channel import DashboardChannel
```

with:

```python
from . import graph_wire
from .channel import DashboardChannel
```

(c) Inside `create_router`, immediately **before** the line `    @router.post("/runs", response_model=StartedRun)`, insert this block (the module already imports `json`):

```python
    async def _graph_body(request: Request) -> dict:
        """The capped JSON body of a graph route (E-76 spec §5.3). Read raw
        so the cap applies before any parsing: /graphs/parse accepts
        arbitrary YAML on an unauthenticated, localhost-bound surface."""
        raw = await request.body()
        if len(raw) > graph_wire.MAX_GRAPH_BYTES:
            raise HTTPException(413, f"graph body exceeds {graph_wire.MAX_GRAPH_BYTES} bytes")
        try:
            body = json.loads(raw)
        except ValueError as e:
            raise HTTPException(422, "body is not JSON") from e
        if not isinstance(body, dict):
            raise HTTPException(422, "body must be a JSON object")
        return body

    @router.get("/graphs/catalog", response_model=graph_wire.CatalogWire)
    async def graph_catalog():
        return graph_wire.catalog()

    @router.post("/graphs/parse", response_model=graph_wire.ParseOk | graph_wire.ParseErr)
    async def graph_parse(request: Request):
        body = await _graph_body(request)
        if set(body) == {"yaml"} and isinstance(body["yaml"], str):
            return graph_wire.parse_text(body["yaml"])
        if set(body) == {"graph"}:
            return graph_wire.parse_object(body["graph"])
        raise HTTPException(422, "body must be exactly one of {yaml: string} or {graph: object}")

    @router.post("/graphs/serialize", response_model=graph_wire.SerializeOk | graph_wire.ParseErr)
    async def graph_serialize(request: Request):
        body = await _graph_body(request)
        if set(body) != {"graph"}:
            raise HTTPException(422, "body must be {graph: object}")
        return graph_wire.serialize(body["graph"])

```
- [ ] **Step 4: Run the route tests and the existing API tests**

```bash
python -m pytest tests/test_dashboard_graph_routes.py -q
```

Expected: PASS — 14 passed. Then, in a separate call:

```bash
python -m pytest tests/test_dashboard_api.py -q
```

Expected: PASS — unchanged.
- [ ] **Step 5: Gate**

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
python scripts/check_file_size.py
```

Expected: all clean (mypy: no NEW errors in the touched files; the repo baseline is scoped to `src/`).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t4-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 pure graph routes

GET /graphs/catalog, POST /graphs/parse and POST /graphs/serialize are
thin wrappers over graph_wire: read-only, no workflow, no store, OQ-11
localhost-bind containment unchanged. The body is read raw and capped at
256 KiB UTF-8 bytes before any parsing, since parse accepts arbitrary YAML
on an unauthenticated surface. A shape failure is a 200 result, not an
error; a malformed body is a 422.
```

Then, one path per `git add`:

```bash
git add src/sdlc/dashboard/api.py
git add tests/test_dashboard_graph_routes.py
git commit -F .workspace/tmp/e76-t4-msg.txt
```
### Task 5: Recordings for the mock — dump script, fixtures, freshness test

**Files:**
- Create: `scripts/dump_graph_fixtures.py`
- Create (generated): `interfaces/dashboard/frontend/src/api/__fixtures__/graph/catalog.json`, `scenarios/{bad_schema_version,bad_yaml,dangling_edge,duplicate_node_id,duplicate_top_level_key,incompatible_ports,pre_code,role_typo}.json`, `objects/{pre_code_architecture_soft,pre_code_intake_renamed_invalid}.json`
- Create (hand-written, PROVISIONAL): `…/__fixtures__/graph/validation.provisional.json`, `…/__fixtures__/graph/run_graphs.provisional.json`
- Test: `tests/test_graph_fixtures_fresh.py`

**Interfaces:**
- Consumes: Task 3 (`graph_wire.catalog/parse_text/parse_object/serialize`), `tests/graph/fixtures/pre_code.graph.yaml`.
- Produces: `build() → dict[relpath, object]`, `OUT`, `SCENARIOS`; fixture files Task 7 imports. The demo run script: run `feature-graph-demo`, scenario `pre_code`, initial state `blocked_r2` with pending key `architecture#2`; `approve → planning`, `revise → revising_r3` (loop edge traversals 2), `reject → rejected` (terminal `failed`).

- [ ] **Step 1: Write the failing test**

`tests/test_graph_fixtures_fresh.py` (create; 50 lines):

```python
"""The dashboard mock's graph recordings equal what the real code produces
(E-76 spec §6.3, §10.1).

Compared PARSED, never as bytes: the repo has no .gitattributes, so a CRLF
checkout must not false-fail. A pydantic upgrade that changes JSON Schema
output turns this red ON PURPOSE -- the served schema really changed.
Regenerate with `python scripts/dump_graph_fixtures.py`; never loosen this.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dump_graph_fixtures", ROOT / "scripts" / "dump_graph_fixtures.py"
)
assert _spec and _spec.loader
dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dump)

PROVISIONAL = {"validation.provisional.json", "run_graphs.provisional.json"}


def test_committed_recordings_equal_a_fresh_build():
    for rel, expected in dump.build().items():
        path = dump.OUT / rel
        assert path.exists(), f"missing {rel}: run python scripts/dump_graph_fixtures.py"
        assert json.loads(path.read_text(encoding="utf-8")) == expected, (
            f"{rel} is stale: run python scripts/dump_graph_fixtures.py"
        )


def test_no_stray_recordings():
    built = set(dump.build())
    on_disk = {p.relative_to(dump.OUT).as_posix() for p in dump.OUT.rglob("*.json")}
    assert on_disk - built == PROVISIONAL


def test_scenarios_cover_both_parse_outcomes():
    built = dump.build()
    outcomes = {
        rel: obj["parse"]["ok"] for rel, obj in built.items() if rel.startswith("scenarios/")
    }
    assert outcomes["scenarios/pre_code.json"] is True
    assert outcomes["scenarios/bad_yaml.json"] is False
    assert outcomes["scenarios/dangling_edge.json"] is True  # legality is validate's
    assert built["objects/pre_code_intake_renamed_invalid.json"]["parse"]["ok"] is False
```
- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_graph_fixtures_fresh.py -q
```

Expected: FAIL — collection error: `scripts/dump_graph_fixtures.py` does not exist.
- [ ] **Step 3: Write the dump script**

`scripts/dump_graph_fixtures.py` (create; 136 lines):

```python
"""Record the graph wire fixtures the dashboard mock replays (E-76 spec §6.3).

    python scripts/dump_graph_fixtures.py

The mock is a recording, not a simulator (spec D4): every catalog, parse and
serialize answer it gives was produced here by the real sdlc.graph code, and
tests/test_graph_fixtures_fresh.py fails when the committed JSON no longer
equals what build() produces. The two *.provisional.json files beside them
are hand-written until E-73/E-74 exist and are not touched by this script.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdlc.dashboard import graph_wire  # noqa: E402

OUT = ROOT / "interfaces/dashboard/frontend/src/api/__fixtures__/graph"
PRE_CODE = ROOT / "tests/graph/fixtures/pre_code.graph.yaml"

_POS = "  position:\n    x: {x}\n    y: 0.0\n"

SCENARIOS: dict[str, str] = {
    "pre_code": PRE_CODE.read_text(encoding="utf-8"),
    "dangling_edge": (
        "schema_version: 1\nnodes:\n- id: intake\n  type: intake\n"
        + _POS.format(x="0.0")
        + "edges:\n- source: intake\n  source_port: ok\n  target: ghost\n  target_port: trigger\n"
    ),
    "duplicate_node_id": (
        "schema_version: 1\nnodes:\n"
        "- id: intake\n  type: intake\n" + _POS.format(x="0.0") + "- id: intake\n  type: intake\n"
        "  position:\n    x: 200.0\n    y: 0.0\n"
        "edges: []\n"
    ),
    "incompatible_ports": (
        "schema_version: 1\nnodes:\n"
        "- id: architect\n  type: architect\n" + _POS.format(x="200.0") + "- id: intake\n"
        "  type: intake\n" + _POS.format(x="0.0") + "edges:\n- source: intake\n  source_port: ok\n"
        "  target: architect\n  target_port: requirements\n"
    ),
    "bad_yaml": "schema_version: 1\nnodes: [\n",
    "bad_schema_version": "schema_version: 2\nnodes: []\nedges: []\n",
    "role_typo": (
        "schema_version: 1\nnodes:\n- id: architect\n  type: architect\n  role:\n    modle: x\n"
        "edges: []\n"
    ),
    "duplicate_top_level_key": "schema_version: 1\nnodes: []\nnodes: []\nedges: []\n",
}


def _node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in graph["nodes"] if n["id"] == node_id)


def _set_gate_policy(graph: dict[str, Any], node_id: str, policy: str) -> dict[str, Any]:
    """What schema_form emits for one touched field (SCHEMA_FORM-4)."""
    out = copy.deepcopy(graph)
    node = _node(out, node_id)
    node["gate"] = {**node.get("gate", {}), "policy": policy}
    return out


def _rename(graph: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """The inspector's id-rename cascade (spec §8.3): the node and every
    incident edge endpoint, in place, no reordering."""
    out = copy.deepcopy(graph)
    _node(out, old)["id"] = new
    for edge in out["edges"]:
        if edge["source"] == old:
            edge["source"] = new
        if edge["target"] == old:
            edge["target"] = new
    return out


def _objects(pre_code: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "pre_code_architecture_soft": _set_gate_policy(pre_code, "architecture", "soft"),
        "pre_code_intake_renamed_invalid": _rename(pre_code, "intake", "Intake"),
    }


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


def build() -> dict[str, Any]:
    """Relative path under OUT -> JSON-ready object."""
    files: dict[str, Any] = {"catalog.json": _dump(graph_wire.catalog())}
    pre_code_graph: dict[str, Any] | None = None
    for name in sorted(SCENARIOS):
        text = SCENARIOS[name]
        parsed = graph_wire.parse_text(text)
        serialized = (
            _dump(graph_wire.serialize(parsed.graph))
            if isinstance(parsed, graph_wire.ParseOk)
            else None
        )
        if name == "pre_code":
            assert isinstance(parsed, graph_wire.ParseOk)
            pre_code_graph = parsed.graph
        files[f"scenarios/{name}.json"] = {
            "name": name,
            "yaml": text,
            "parse": _dump(parsed),
            "serialize": serialized,
        }
    assert pre_code_graph is not None
    for name, graph in sorted(_objects(pre_code_graph).items()):
        files[f"objects/{name}.json"] = {
            "name": name,
            "base": "pre_code",  # the scenario whose canned validation applies
            "graph": graph,
            "parse": _dump(graph_wire.parse_object(graph)),
        }
    return files


def main() -> None:
    for rel, obj in build().items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
```
- [ ] **Step 4: Generate the recordings**

```bash
python scripts/dump_graph_fixtures.py
```

Expected: 11 `wrote …` lines (catalog, eight scenarios, two objects). Spot-check: `scenarios/bad_yaml.json` has `"ok": false` with `"line": 3`; `scenarios/pre_code.json` has `"ok": true` and a 64-hex `sha`.
- [ ] **Step 5: Write the two hand-written PROVISIONAL fixtures**

`interfaces/dashboard/frontend/src/api/__fixtures__/graph/validation.provisional.json` (create; 86 lines):

```json
{
  "_note": "PROVISIONAL until E-73: hand-written, not produced by validate.py. Codes are placeholders E-73 will replace (E-76 spec \u00a75.5, \u00a76.3).",
  "pre_code": {
    "issues": [],
    "back_edges": [
      {
        "source": "architecture",
        "source_port": "revise",
        "target": "architect",
        "target_port": "guidance"
      },
      {
        "source": "plan",
        "source_port": "revise",
        "target": "planner",
        "target_port": "guidance"
      },
      {
        "source": "research",
        "source_port": "revise",
        "target": "researcher",
        "target_port": "guidance"
      }
    ]
  },
  "dangling_edge": {
    "issues": [
      {
        "code": "edge.unknown_endpoint",
        "severity": "error",
        "message": "edge target 'ghost' is not a node",
        "target": {
          "kind": "edge",
          "edge": {
            "source": "intake",
            "source_port": "ok",
            "target": "ghost",
            "target_port": "trigger"
          }
        }
      }
    ],
    "back_edges": []
  },
  "duplicate_node_id": {
    "issues": [
      {
        "code": "node.duplicate_id",
        "severity": "error",
        "message": "node id 'intake' is used by 2 nodes",
        "target": {
          "kind": "node",
          "id": "intake"
        }
      }
    ],
    "back_edges": []
  },
  "incompatible_ports": {
    "issues": [
      {
        "code": "edge.incompatible_ports",
        "severity": "error",
        "message": "intake.ok (signal) cannot feed architect.requirements (ClarifiedRequirements)",
        "target": {
          "kind": "edge",
          "edge": {
            "source": "intake",
            "source_port": "ok",
            "target": "architect",
            "target_port": "requirements"
          }
        }
      },
      {
        "code": "graph.unreachable",
        "severity": "warning",
        "message": "no path reaches every node",
        "target": {
          "kind": "graph"
        }
      }
    ],
    "back_edges": []
  }
}
```

`interfaces/dashboard/frontend/src/api/__fixtures__/graph/run_graphs.provisional.json` (create; 568 lines):

```json
{
  "_note": "PROVISIONAL until E-74/E-75: a hand-written state script, not router output. Transitions fire only on decideGate, never on a timer, so Playwright is deterministic (E-76 spec \u00a77.2).",
  "runs": {
    "feature-graph-demo": {
      "scenario": "pre_code",
      "initial": "blocked_r2",
      "states": {
        "blocked_r2": {
          "state": {
            "kind": "state",
            "graph_sha": "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1",
            "nodes": {
              "intake": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:00Z",
                "ended_at": "2026-09-14T09:00:05Z",
                "cost_usd": null
              },
              "researcher": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:05Z",
                "ended_at": "2026-09-14T09:04:00Z",
                "cost_usd": 0.42
              },
              "research": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:04:00Z",
                "ended_at": "2026-09-14T09:06:00Z",
                "cost_usd": null
              },
              "clarifier": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:06:00Z",
                "ended_at": "2026-09-14T09:10:00Z",
                "cost_usd": 0.31
              },
              "architect": {
                "status": "done",
                "round": 2,
                "started_at": "2026-09-14T09:25:00Z",
                "ended_at": "2026-09-14T09:31:00Z",
                "cost_usd": 1.87
              },
              "architecture": {
                "status": "blocked",
                "round": 2,
                "started_at": "2026-09-14T09:31:00Z",
                "ended_at": null,
                "cost_usd": null
              },
              "planner": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              },
              "plan": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              }
            },
            "edges": [
              {
                "edge": {
                  "source": "intake",
                  "source_port": "ok",
                  "target": "researcher",
                  "target_port": "trigger"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "researcher",
                  "source_port": "brief",
                  "target": "research",
                  "target_port": "artifact"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "research",
                  "source_port": "approve",
                  "target": "clarifier",
                  "target_port": "research"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "architect",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "planner",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "architect",
                  "source_port": "spec",
                  "target": "architecture",
                  "target_port": "artifact"
                },
                "traversals": 2
              },
              {
                "edge": {
                  "source": "architecture",
                  "source_port": "revise",
                  "target": "architect",
                  "target_port": "guidance"
                },
                "traversals": 1
              }
            ],
            "current_nodes": [
              "architecture"
            ],
            "pending": [
              {
                "node": "architecture",
                "key": "architecture#2",
                "kind": "gate"
              }
            ],
            "terminal": null
          },
          "on": {
            "approve": "planning",
            "revise": "revising_r3",
            "reject": "rejected"
          }
        },
        "planning": {
          "state": {
            "kind": "state",
            "graph_sha": "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1",
            "nodes": {
              "intake": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:00Z",
                "ended_at": "2026-09-14T09:00:05Z",
                "cost_usd": null
              },
              "researcher": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:05Z",
                "ended_at": "2026-09-14T09:04:00Z",
                "cost_usd": 0.42
              },
              "research": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:04:00Z",
                "ended_at": "2026-09-14T09:06:00Z",
                "cost_usd": null
              },
              "clarifier": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:06:00Z",
                "ended_at": "2026-09-14T09:10:00Z",
                "cost_usd": 0.31
              },
              "architect": {
                "status": "done",
                "round": 2,
                "started_at": "2026-09-14T09:25:00Z",
                "ended_at": "2026-09-14T09:31:00Z",
                "cost_usd": 1.87
              },
              "architecture": {
                "status": "done",
                "round": 2,
                "started_at": "2026-09-14T09:31:00Z",
                "ended_at": "2026-09-14T09:40:00Z",
                "cost_usd": null
              },
              "planner": {
                "status": "running",
                "round": 1,
                "started_at": "2026-09-14T09:40:00Z",
                "ended_at": null,
                "cost_usd": null
              },
              "plan": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              }
            },
            "edges": [
              {
                "edge": {
                  "source": "intake",
                  "source_port": "ok",
                  "target": "researcher",
                  "target_port": "trigger"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "researcher",
                  "source_port": "brief",
                  "target": "research",
                  "target_port": "artifact"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "research",
                  "source_port": "approve",
                  "target": "clarifier",
                  "target_port": "research"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "architect",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "planner",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "architect",
                  "source_port": "spec",
                  "target": "architecture",
                  "target_port": "artifact"
                },
                "traversals": 2
              },
              {
                "edge": {
                  "source": "architecture",
                  "source_port": "revise",
                  "target": "architect",
                  "target_port": "guidance"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "architecture",
                  "source_port": "approve",
                  "target": "planner",
                  "target_port": "spec"
                },
                "traversals": 1
              }
            ],
            "current_nodes": [
              "planner"
            ],
            "pending": [],
            "terminal": null
          },
          "on": {}
        },
        "revising_r3": {
          "state": {
            "kind": "state",
            "graph_sha": "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1",
            "nodes": {
              "intake": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:00Z",
                "ended_at": "2026-09-14T09:00:05Z",
                "cost_usd": null
              },
              "researcher": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:05Z",
                "ended_at": "2026-09-14T09:04:00Z",
                "cost_usd": 0.42
              },
              "research": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:04:00Z",
                "ended_at": "2026-09-14T09:06:00Z",
                "cost_usd": null
              },
              "clarifier": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:06:00Z",
                "ended_at": "2026-09-14T09:10:00Z",
                "cost_usd": 0.31
              },
              "architect": {
                "status": "running",
                "round": 3,
                "started_at": "2026-09-14T09:40:00Z",
                "ended_at": null,
                "cost_usd": null
              },
              "architecture": {
                "status": "idle",
                "round": 2,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              },
              "planner": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              },
              "plan": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              }
            },
            "edges": [
              {
                "edge": {
                  "source": "intake",
                  "source_port": "ok",
                  "target": "researcher",
                  "target_port": "trigger"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "researcher",
                  "source_port": "brief",
                  "target": "research",
                  "target_port": "artifact"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "research",
                  "source_port": "approve",
                  "target": "clarifier",
                  "target_port": "research"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "architect",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "planner",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "architect",
                  "source_port": "spec",
                  "target": "architecture",
                  "target_port": "artifact"
                },
                "traversals": 2
              },
              {
                "edge": {
                  "source": "architecture",
                  "source_port": "revise",
                  "target": "architect",
                  "target_port": "guidance"
                },
                "traversals": 2
              }
            ],
            "current_nodes": [
              "architect"
            ],
            "pending": [],
            "terminal": null
          },
          "on": {}
        },
        "rejected": {
          "state": {
            "kind": "state",
            "graph_sha": "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1",
            "nodes": {
              "intake": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:00Z",
                "ended_at": "2026-09-14T09:00:05Z",
                "cost_usd": null
              },
              "researcher": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:00:05Z",
                "ended_at": "2026-09-14T09:04:00Z",
                "cost_usd": 0.42
              },
              "research": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:04:00Z",
                "ended_at": "2026-09-14T09:06:00Z",
                "cost_usd": null
              },
              "clarifier": {
                "status": "done",
                "round": 1,
                "started_at": "2026-09-14T09:06:00Z",
                "ended_at": "2026-09-14T09:10:00Z",
                "cost_usd": 0.31
              },
              "architect": {
                "status": "done",
                "round": 2,
                "started_at": "2026-09-14T09:25:00Z",
                "ended_at": "2026-09-14T09:31:00Z",
                "cost_usd": 1.87
              },
              "architecture": {
                "status": "failed",
                "round": 2,
                "started_at": "2026-09-14T09:31:00Z",
                "ended_at": "2026-09-14T09:40:00Z",
                "cost_usd": null
              },
              "planner": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              },
              "plan": {
                "status": "idle",
                "round": 1,
                "started_at": null,
                "ended_at": null,
                "cost_usd": null
              }
            },
            "edges": [
              {
                "edge": {
                  "source": "intake",
                  "source_port": "ok",
                  "target": "researcher",
                  "target_port": "trigger"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "researcher",
                  "source_port": "brief",
                  "target": "research",
                  "target_port": "artifact"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "research",
                  "source_port": "approve",
                  "target": "clarifier",
                  "target_port": "research"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "architect",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "clarifier",
                  "source_port": "requirements",
                  "target": "planner",
                  "target_port": "requirements"
                },
                "traversals": 1
              },
              {
                "edge": {
                  "source": "architect",
                  "source_port": "spec",
                  "target": "architecture",
                  "target_port": "artifact"
                },
                "traversals": 2
              },
              {
                "edge": {
                  "source": "architecture",
                  "source_port": "revise",
                  "target": "architect",
                  "target_port": "guidance"
                },
                "traversals": 1
              }
            ],
            "current_nodes": [],
            "pending": [],
            "terminal": "failed"
          },
          "on": {}
        }
      }
    }
  }
}
```

**Note:** `run_graphs.provisional.json` embeds the `pre_code` sha (`9bc61539…`). If Step 4 printed a different `sha` for `scenarios/pre_code.json` (it will not unless the E-72 fixture changed), replace every `graph_sha` value with the generated one.
- [ ] **Step 6: Run the freshness test to verify it passes**

```bash
python -m pytest tests/test_graph_fixtures_fresh.py -q
```

Expected: PASS — 3 passed.
- [ ] **Step 7: Gate**

```bash
ruff check src tests scripts
ruff format --check src tests scripts
mypy
python scripts/check_file_size.py
```

Expected: all clean (mypy: no NEW errors in the touched files; the repo baseline is scoped to `src/`).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t5-msg.txt` with exactly this content (no trailers of any kind):

```text
test(dashboard): E-76 graph recordings for the mock provider

scripts/dump_graph_fixtures.py records the real catalog, parse and
serialize answers for eight text scenarios and two inspector object edits;
tests/test_graph_fixtures_fresh.py fails when the committed JSON drifts from
a fresh build (compared parsed, so a CRLF checkout cannot false-fail).
validation.provisional.json and run_graphs.provisional.json are
hand-written and marked PROVISIONAL until E-73/E-74 produce the real thing.
```

Then, one path per `git add`:

```bash
git add scripts/dump_graph_fixtures.py
git add tests/test_graph_fixtures_fresh.py
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/catalog.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/bad_schema_version.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/bad_yaml.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/dangling_edge.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/duplicate_node_id.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/duplicate_top_level_key.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/incompatible_ports.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/pre_code.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/scenarios/role_typo.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/objects/pre_code_architecture_soft.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/objects/pre_code_intake_renamed_invalid.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/validation.provisional.json
git add interfaces/dashboard/frontend/src/api/__fixtures__/graph/run_graphs.provisional.json
git commit -F .workspace/tmp/e76-t5-msg.txt
```
### Task 6: Poll chain + `HttpStatusError`

**Files:**
- Create: `interfaces/dashboard/frontend/src/api/poll.ts`, `interfaces/dashboard/frontend/src/api/errors.ts`
- Test: `interfaces/dashboard/frontend/src/api/poll.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `PollStep<T>`, `PollOptions`, `jittered(ms, jitter, random)`, `startPoll(fetchOnce(signal), onValue, onFailures, opts) → stop()` (recursive `setTimeout`, abort on stop, `final`/`stop` end the chain, backoff ×2 capped 30 s, ±20 % jitter, report after 3 failures, reset on success); `HttpStatusError(status, message)`, `isNotFound(e)`.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/api/poll.test.ts` (create; 91 lines):

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { jittered, startPoll, type PollStep } from './poll'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

const noJitter = { jitter: 0, random: () => 0.5 }
const flush = async () => { await vi.advanceTimersByTimeAsync(0) }

describe('jittered', () => {
  it('spreads a delay by ±jitter', () => {
    expect(jittered(2000, 0.2, () => 0)).toBe(1600)
    expect(jittered(2000, 0.2, () => 1)).toBe(2400)
  })
})

describe('startPoll', () => {
  it('fetches immediately, then every base interval', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1 }))
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    await flush()
    expect(fetchOnce).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetchOnce).toHaveBeenCalledTimes(2)
    expect(onValue).toHaveBeenCalledTimes(2)
  })

  it('never fetches or delivers after stop, even with a fetch in flight', async () => {
    let resolve!: (s: PollStep<number>) => void
    let seenSignal: AbortSignal | null = null
    const fetchOnce = vi.fn((signal: AbortSignal) => {
      seenSignal = signal
      return new Promise<PollStep<number>>((r) => { resolve = r })
    })
    const onValue = vi.fn()
    const stop = startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    stop()
    expect(seenSignal!.aborted).toBe(true)
    resolve({ kind: 'value', value: 1 })
    await vi.advanceTimersByTimeAsync(10000)
    expect(onValue).not.toHaveBeenCalled()
    expect(fetchOnce).toHaveBeenCalledTimes(1)
  })

  it('ends the chain on a final value and on stop', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1, final: true }))
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchOnce).toHaveBeenCalledTimes(1)
    expect(onValue).toHaveBeenCalledTimes(1)

    const stopper = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'stop' }))
    startPoll(stopper, onValue, vi.fn(), noJitter)
    await vi.advanceTimersByTimeAsync(10000)
    expect(stopper).toHaveBeenCalledTimes(1)
  })

  it('backs off on failure, reports after three, and resets on success', async () => {
    let fail = true
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => {
      if (fail) throw new Error('down')
      return { kind: 'value', value: 1 }
    })
    const onFailures = vi.fn()
    startPoll(fetchOnce, vi.fn(), onFailures, noJitter)
    await flush()                                   // fail 1 -> wait 4s
    await vi.advanceTimersByTimeAsync(4000)         // fail 2 -> wait 8s
    expect(onFailures).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(8000)         // fail 3 -> report, wait 16s
    expect(onFailures).toHaveBeenLastCalledWith(3)
    fail = false
    await vi.advanceTimersByTimeAsync(16000)        // success -> reset
    expect(onFailures).toHaveBeenLastCalledWith(0)
    const calls = fetchOnce.mock.calls.length
    await vi.advanceTimersByTimeAsync(2000)         // back to the base interval
    expect(fetchOnce.mock.calls.length).toBe(calls + 1)
  })

  it('caps the backoff', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => { throw new Error('down') })
    startPoll(fetchOnce, vi.fn(), vi.fn(), { ...noJitter, capMs: 5000 })
    await flush()
    await vi.advanceTimersByTimeAsync(4000)
    await vi.advanceTimersByTimeAsync(5000)
    const calls = fetchOnce.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchOnce.mock.calls.length).toBe(calls + 1)
  })
})
```
- [ ] **Step 2: Run it to verify it fails**

```bash
npm run test --workspace sdlc-dashboard -- src/api/poll.test.ts
```

Expected: FAIL — cannot resolve `./poll`.
- [ ] **Step 3: Write the modules**

`interfaces/dashboard/frontend/src/api/poll.ts` (create; 75 lines):

```ts
// A cancel-safe poll chain (E-76 spec §7.3). A recursive setTimeout, never
// setInterval: nothing fires after stop(), including a fetch in flight at
// stop (aborted), and a slow response can never stack a second request.

export type PollStep<T> =
  | { kind: 'value'; value: T; final?: boolean }
  | { kind: 'stop' }

export interface PollOptions {
  baseMs?: number
  capMs?: number
  jitter?: number
  random?: () => number
  failuresBeforeReport?: number
}

export function jittered(ms: number, jitter: number, random: () => number): number {
  return Math.round(ms * (1 - jitter + random() * 2 * jitter))
}

export function startPoll<T>(
  fetchOnce: (signal: AbortSignal) => Promise<PollStep<T>>,
  onValue: (value: T) => void,
  onFailures: (consecutive: number) => void,
  opts: PollOptions = {},
): () => void {
  const baseMs = opts.baseMs ?? 2000
  const capMs = opts.capMs ?? 30000
  const jitter = opts.jitter ?? 0.2
  const random = opts.random ?? Math.random
  const report = opts.failuresBeforeReport ?? 3

  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let controller: AbortController | null = null
  let failures = 0
  let delay = baseMs

  const schedule = (ms: number) => {
    if (cancelled) return
    timer = setTimeout(tick, jittered(ms, jitter, random))
  }

  async function tick() {
    if (cancelled) return
    controller = new AbortController()
    let step: PollStep<T>
    try {
      step = await fetchOnce(controller.signal)
    } catch {
      if (cancelled) return
      failures += 1
      delay = Math.min(delay * 2, capMs)
      if (failures >= report) onFailures(failures)
      schedule(delay)
      return
    }
    if (cancelled) return
    if (failures > 0) onFailures(0)
    failures = 0
    delay = baseMs
    if (step.kind === 'stop') return
    onValue(step.value)
    if (step.final) return
    schedule(baseMs)
  }

  void tick()

  return () => {
    cancelled = true
    if (timer) clearTimeout(timer)
    controller?.abort()
  }
}
```

`interfaces/dashboard/frontend/src/api/errors.ts` (create; 11 lines):

```ts
// An HTTP failure that keeps its status, so callers branch on the code, not
// on message text. A 404 from /decide is FR-302 working as designed: another
// surface decided first (E-76 spec §7.3).
export class HttpStatusError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
    this.name = 'HttpStatusError'
  }
}

export const isNotFound = (e: unknown): boolean => e instanceof HttpStatusError && e.status === 404
```
- [ ] **Step 4: Run it to verify it passes**

```bash
npm run test --workspace sdlc-dashboard -- src/api/poll.test.ts
```

Expected: PASS — 6 tests.
- [ ] **Step 5: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t6-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 cancel-safe poll chain

startPoll is a recursive setTimeout chain -- never setInterval -- that
aborts an in-flight fetch on stop, ends on a final value or a stop step,
backs off on failure with jitter, and reports sustained failure. It carries
run mode's graph-state subscription (spec §7.3). HttpStatusError keeps the
status so callers branch on the code, not on message text.
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/api/poll.ts
git add interfaces/dashboard/frontend/src/api/poll.test.ts
git add interfaces/dashboard/frontend/src/api/errors.ts
git commit -F .workspace/tmp/e76-t6-msg.txt
```
### Task 7: The API contract change and the name-keyed stage strip (atomic)

This task is one commit because `vue-tsc` fails between any split of it: `Run.stageIdx` → `Run.activeStages` and the new `DashboardApi` graph methods change every provider, adapter and dependent test at once. Work through the steps in order.

**Files:**
- Create: `interfaces/dashboard/frontend/src/api/graph-types.ts`, `interfaces/dashboard/frontend/src/api/http-graph.ts`, `interfaces/dashboard/frontend/src/api/mock/graph.ts`, `interfaces/dashboard/frontend/src/stores/catalog.ts`
- Replace: `interfaces/dashboard/frontend/src/api/types.ts`, `interfaces/dashboard/frontend/src/api/http.ts`, `interfaces/dashboard/frontend/src/api/mock/index.ts`, `interfaces/dashboard/frontend/src/composables/stageState.ts`, `interfaces/dashboard/frontend/src/constants.ts`, `interfaces/dashboard/frontend/src/adapters/fleet.ts`, `interfaces/dashboard/frontend/src/components/fleet/FleetTable.vue`, `interfaces/dashboard/frontend/src/App.vue`
- Tests (create): `interfaces/dashboard/frontend/src/api/http-graph.test.ts`, `interfaces/dashboard/frontend/src/api/mock/graph.test.ts`
- Tests (replace): `interfaces/dashboard/frontend/src/constants.test.ts`, `interfaces/dashboard/frontend/src/composables/composables.test.ts`, `interfaces/dashboard/frontend/src/components/fleet/FleetTable.test.ts`, `interfaces/dashboard/frontend/src/adapters/fleet.test.ts`, `interfaces/dashboard/frontend/src/api/mock/index.test.ts`, `interfaces/dashboard/frontend/src/api/http.test.ts`, `interfaces/dashboard/frontend/src/api/client.test.ts`
- Modify: `interfaces/ui/app.md` (CONSOLE-3), `interfaces/ui/app.pw.ts` (append)

**Interfaces:**
- Consumes: Task 5 fixtures; Task 6 `startPoll`, `HttpStatusError`, `isNotFound`.
- Produces: `Run.activeStages: string[]` (no `stageIdx`); `DashboardApi` gains `getCatalog`, `parseGraph({yaml}|{graph})`, `serializeGraph`, `validateGraph`, `saveGraph`, `loadGraph`, `getRunGraph`, `subscribeGraphState(runId, cb, onError?)`; wire types in `api/graph-types.ts` (`GraphWire`, `NodeWire`, `EdgeWire`, `EdgeRef`, `ShapeError`, `PortWire`, `NodeTypeWire`, `Capability`, `CatalogWire`, `JsonSchema`, `ParseWire`, `SerializeWire`, `IssueTarget`, `Issue`, `ValidationWire`, `SaveWire`, `LoadWire`, `GraphResponse`, `NodeRunStatus`, `NodeRunState`, `PendingRef`, `GraphStateResponse`, `CapabilityUnavailable`, `edgeRefOf`, `sameEdge`); `createHttpGraphApi(baseUrl)`; `createMockGraph() → MockGraph` (with `onDecision(runId, key, outcome)`, `graphRunIds()`); `useCatalogStore()` → `{catalog, error, load, canonicalStages, nodeTypes, typeOf, can, connectable(sourceType, sourcePort, targetType, targetPort)}`; `stageStates(run, canonicalStages)`; `toStageDots(run, canonicalStages)`; `toFleetRow(run, canonicalStages)`.

- [ ] **Step 1: Write the new failing tests**

`interfaces/dashboard/frontend/src/api/http-graph.test.ts` (create; 86 lines):

```ts
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { createHttpGraphApi } from './http-graph'
import { CapabilityUnavailable } from './graph-types'
import catalogJson from './__fixtures__/graph/catalog.json'
import preCode from './__fixtures__/graph/scenarios/pre_code.json'

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('http graph provider', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(catalogJson)
      if (path === '/api/graphs/parse') return ok(preCode.parse)
      return new Response('nope', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('fetches the catalog once per session', async () => {
    const api = createHttpGraphApi()
    await api.getCatalog()
    await api.getCatalog()
    expect(fetchMock.mock.calls.filter(([p]) => p === '/api/graphs/catalog')).toHaveLength(1)
  })

  it('does not cache a failed catalog fetch', async () => {
    fetchMock.mockImplementationOnce(async () => new Response('down', { status: 502 }))
    const api = createHttpGraphApi()
    await expect(api.getCatalog()).rejects.toThrow('502')
    expect((await api.getCatalog()).canonical_stages).toHaveLength(18)
  })

  it('posts parse input verbatim to the shipped route', async () => {
    const api = createHttpGraphApi()
    await api.parseGraph({ yaml: preCode.yaml })
    const [path, init] = fetchMock.mock.calls.find(([p]) => p === '/api/graphs/parse')!
    expect(path).toBe('/api/graphs/parse')
    expect(JSON.parse(init.body)).toEqual({ yaml: preCode.yaml })
  })

  it.each([
    ['validateGraph', 'validate'],
    ['saveGraph', 'save'],
    ['loadGraph', 'load'],
    ['getRunGraph', 'run_graph'],
  ] as const)('%s refuses without calling the route while %s is not declared', async (method, cap) => {
    const api = createHttpGraphApi()
    const arg = method === 'loadGraph' || method === 'getRunGraph' ? 'x' : ({ schema_version: 1, nodes: [], edges: [] } as never)
    await expect((api[method] as (a: unknown) => Promise<unknown>)(arg)).rejects.toEqual(new CapabilityUnavailable(cap))
    expect(fetchMock.mock.calls.map(([p]) => p)).toEqual(['/api/graphs/catalog'])
  })

  it('never polls run state while run_graph is not declared', async () => {
    vi.useFakeTimers()
    const api = createHttpGraphApi()
    const cb = vi.fn()
    api.subscribeGraphState('r1', cb)
    await vi.advanceTimersByTimeAsync(10000)
    expect(cb).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls.map(([p]) => p)).toEqual(['/api/graphs/catalog'])
  })

  it('polls run state when declared and ends the chain on a terminal state', async () => {
    vi.useFakeTimers()
    const catalog = { ...catalogJson, capabilities: { ...catalogJson.capabilities, run_graph: true } }
    let polls = 0
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(catalog)
      polls += 1
      return ok({ kind: 'state', graph_sha: 's', nodes: {}, edges: [], current_nodes: [], pending: [], terminal: polls >= 2 ? 'done' : null })
    })
    const api = createHttpGraphApi()
    const cb = vi.fn()
    api.subscribeGraphState('r 1', cb)
    await vi.advanceTimersByTimeAsync(60000)
    expect(polls).toBe(2)
    expect(cb).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.some(([p]) => p === '/api/runs/r%201/graph_state')).toBe(true)
  })
})
```

`interfaces/dashboard/frontend/src/api/mock/graph.test.ts` (create; 132 lines):

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import * as graphModule from './graph'
import { createMockGraph } from './graph'
import { createMockApi } from './index'
import catalogJson from '../__fixtures__/graph/catalog.json'
import preCode from '../__fixtures__/graph/scenarios/pre_code.json'
import badYaml from '../__fixtures__/graph/scenarios/bad_yaml.json'
import soft from '../__fixtures__/graph/objects/pre_code_architecture_soft.json'
import type { GraphStateResponse, GraphWire } from '../graph-types'

afterEach(() => { vi.restoreAllMocks() })

const tick = () => new Promise((r) => setTimeout(r, 0))

describe('mock graph: a recording, never a simulator', () => {
  it('overrides the recorded all-false capabilities so every flow is exercisable', async () => {
    expect(catalogJson.capabilities).toEqual({ validate: false, save: false, load: false, run_graph: false })
    const catalog = await createMockGraph().getCatalog()
    expect(catalog.capabilities).toEqual({ validate: true, save: true, load: true, run_graph: true })
    expect(catalog.canonical_stages).toEqual(catalogJson.canonical_stages)
  })

  it('answers recorded text with the recorded parse', async () => {
    const g = createMockGraph()
    expect(await g.parseGraph({ yaml: preCode.yaml })).toEqual(preCode.parse)
    expect(await g.parseGraph({ yaml: badYaml.yaml })).toEqual(badYaml.parse)
  })

  it('answers unrecorded text as a shape error, never success', async () => {
    const r = await createMockGraph().parseGraph({ yaml: 'schema_version: 1\nnodes: []\nedges: []\n' })
    expect(r.ok).toBe(false)
  })

  it('answers a recorded graph object, independent of key order', async () => {
    const g = createMockGraph()
    const reverseKeys = (v: unknown): unknown =>
      Array.isArray(v) ? v.map(reverseKeys)
        : v !== null && typeof v === 'object'
          ? Object.fromEntries(Object.keys(v).reverse().map((k) => [k, reverseKeys((v as Record<string, unknown>)[k])]))
          : v
    expect(await g.parseGraph({ graph: soft.graph as GraphWire })).toEqual(soft.parse)
    expect(await g.parseGraph({ graph: reverseKeys(soft.graph) as GraphWire })).toEqual(soft.parse)
  })

  it('answers an unrecorded graph object as a shape error and names the nearest recording', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const graph = { ...(preCode.parse as { graph: GraphWire }).graph, edges: [] }
    const r = await createMockGraph().parseGraph({ graph })
    expect(r.ok).toBe(false)
    expect(warn.mock.calls[0][0]).toMatch(/nearest recording: \w+/)
  })

  it('exports nothing that computes the lookup key', () => {
    expect(Object.keys(graphModule).sort()).toEqual(['createMockGraph'])
  })

  it('serializes a recorded graph verbatim and anything else as visibly non-canonical JSON', async () => {
    const g = createMockGraph()
    const recorded = (preCode.parse as { graph: GraphWire }).graph
    expect(await g.serializeGraph(recorded)).toEqual(preCode.serialize)
    const other = { schema_version: 1 as const, nodes: [], edges: [] }
    expect(await g.serializeGraph(other)).toEqual({ ok: true, yaml: JSON.stringify(other, null, 2) })
  })

  it('validates against the scenario of the last recorded parse, else reports unrecorded', async () => {
    const g = createMockGraph()
    const before = await g.validateGraph({ schema_version: 1, nodes: [], edges: [] })
    expect(before.issues[0].code).toBe('mock.unrecorded')
    await g.parseGraph({ yaml: preCode.yaml })
    expect((await g.validateGraph({ schema_version: 1, nodes: [], edges: [] })).back_edges).toHaveLength(3)
  })

  it('saves under the recorded sha and loads it back', async () => {
    const g = createMockGraph()
    const graph = (preCode.parse as { graph: GraphWire; sha: string })
    const saved = await g.saveGraph(graph.graph)
    expect(saved).toMatchObject({ ok: true, sha: graph.sha })
    expect(await g.loadGraph(graph.sha)).toEqual({ ok: true, sha: graph.sha, graph: graph.graph })
    expect(await g.loadGraph('nope')).toEqual({ ok: false, reason: 'not_found' })
    const other = await g.saveGraph({ schema_version: 1, nodes: [], edges: [] })
    expect(other).toMatchObject({ ok: true, sha: 'mock-sha-1' })
  })
})

describe('mock graph runs', () => {
  it('returns no_graph for a legacy run', async () => {
    expect(await createMockGraph().getRunGraph('feature-add-sso')).toEqual({ kind: 'no_graph', reason: 'legacy_run' })
  })

  it('serves the demo run graph with the recorded sha and back edges', async () => {
    const r = await createMockGraph().getRunGraph('feature-graph-demo')
    expect(r.kind).toBe('graph')
    if (r.kind === 'graph') {
      expect(r.sha).toBe((preCode.parse as { sha: string }).sha)
      expect(r.back_edges).toHaveLength(3)
    }
  })

  it('delivers the scripted state and advances only on a decision for the pending key', async () => {
    const api = createMockApi({ simulateLive: false })
    const seen: GraphStateResponse[] = []
    const stop = api.subscribeGraphState('feature-graph-demo', (s) => seen.push(s))
    await tick()
    const first = seen.at(-1)!
    expect(first.kind === 'state' && first.pending.map((p) => p.key)).toEqual(['architecture#2'])
    await api.decideGate('feature-graph-demo', 'architecture#2', 'approve', '')
    const next = seen.at(-1)!
    expect(next.kind === 'state' && next.current_nodes).toEqual(['planner'])
    stop()
    await expect(api.decideGate('feature-graph-demo', 'architecture#2', 'approve', '')).rejects.toThrow()
  })

  it('revise bumps the loop edge traversal count', async () => {
    const api = createMockApi({ simulateLive: false })
    const seen: GraphStateResponse[] = []
    api.subscribeGraphState('feature-graph-demo', (s) => seen.push(s))
    await tick()
    await api.decideGate('feature-graph-demo', 'architecture#2', 'revise', 'again')
    const s = seen.at(-1)!
    const loop = s.kind === 'state' ? s.edges.find((e) => e.edge.source === 'architecture' && e.edge.source_port === 'revise') : undefined
    expect(loop?.traversals).toBe(2)
  })

  it('delivers nothing after unsubscribe', async () => {
    const g = createMockGraph()
    const cb = vi.fn()
    const stop = g.subscribeGraphState('feature-graph-demo', cb)
    stop()
    await tick()
    expect(cb).not.toHaveBeenCalled()
  })
})
```
- [ ] **Step 2: Replace the dependent tests**

`interfaces/dashboard/frontend/src/constants.test.ts` (replace; 17 lines):

```ts
import { describe, it, expect } from 'vitest'
import { ARTIFACTS, STATUS_KINDS } from './constants'

// The stage list moved to the server (E-76 spec U4): the strip reads
// catalog.canonical_stages, so no TS stage list is asserted here any more.
describe('constants', () => {
  it('has 14 artifacts', () => {
    expect(ARTIFACTS).toHaveLength(14)
  })

  it('exposes the status kinds list', () => {
    expect(STATUS_KINDS).toContain('running')
    expect(STATUS_KINDS).toContain('blocked')
    expect(STATUS_KINDS).toContain('failed')
    expect(STATUS_KINDS).toContain('done')
  })
})
```

`interfaces/dashboard/frontend/src/composables/composables.test.ts` (replace; 79 lines):

```ts
import { describe, it, expect, vi } from 'vitest'
import { money, budgetPct, budgetColor } from './format'
import { statusMetaOf } from './status'
import { stageStates } from './stageState'
import type { Run } from '../api/types'

const run = (over: Partial<Run>): Run => ({
  id: 'x',
  title: 't',
  mode: 'brownfield',
  repo: 'r',
  activeStages: ['clarify'],
  status: 'running',
  blocker: '',
  cost: 1,
  budget: 10,
  age: '1m',
  decisions: [],
  ...over,
})

describe('format', () => {
  it('formats USD', () => {
    expect(money(3.1)).toBe('$3.10')
    expect(money(0)).toBe('$0.00')
  })
  it('caps budget pct at 100', () => {
    expect(budgetPct(5, 10)).toBe(50)
    expect(budgetPct(20, 10)).toBe(100)
  })
  it('colors budget by threshold', () => {
    expect(budgetColor(50)).toBe('#4fae7f')
    expect(budgetColor(70)).toBe('#e0b050')
    expect(budgetColor(90)).toBe('#e06c55')
  })
})

describe('statusMetaOf', () => {
  it('maps each status to color/label/anim', () => {
    expect(statusMetaOf(run({ status: 'running' })).label).toBe('running')
    expect(statusMetaOf(run({ status: 'blocked' })).label).toBe('awaiting human')
    expect(statusMetaOf(run({ status: 'failed' })).anim).toBe('none')
    expect(statusMetaOf(run({ status: 'done' })).color).toBe('var(--status-done)')
  })
})

const STRIP = ['intake', 'research', 'clarify', 'architecture', 'planning']

describe('stageStates', () => {
  it('marks stages before the lowest active stage done and later ones pending', () => {
    expect(stageStates(run({ activeStages: ['clarify'] }), STRIP)).toEqual(
      ['done', 'done', 'active', 'pending', 'pending'],
    )
  })
  it('marks the active stage blocked, failed or done from the run status', () => {
    expect(stageStates(run({ status: 'blocked' }), STRIP)[2]).toBe('blocked')
    expect(stageStates(run({ status: 'failed' }), STRIP)[2]).toBe('failed')
    expect(stageStates(run({ status: 'done' }), STRIP)[2]).toBe('done')
  })
  it('marks every active stage of a fanned-out run', () => {
    expect(stageStates(run({ activeStages: ['research', 'architecture'] }), STRIP)).toEqual(
      ['done', 'active', 'pending', 'active', 'pending'],
    )
  })
  it.each(['running', 'blocked', 'failed', 'done'] as const)(
    'renders every mark pending when no stage is active (status %s)',
    (status) => {
      expect(stageStates(run({ activeStages: [], status }), STRIP)).toEqual(STRIP.map(() => 'pending'))
    },
  )
  it('ignores a stage name that is not canonical and reports it once', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(stageStates(run({ activeStages: ['bogus'] }), STRIP)).toEqual(STRIP.map(() => 'pending'))
    stageStates(run({ activeStages: ['bogus'] }), STRIP)
    expect(err).toHaveBeenCalledTimes(1)
    expect(err).toHaveBeenCalledWith(expect.stringContaining('bogus'))
    err.mockRestore()
  })
})
```

`interfaces/dashboard/frontend/src/components/fleet/FleetTable.test.ts` (replace; 61 lines):

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FleetTable from './FleetTable.vue'
import { useFleetStore } from '../../stores/fleet'
import { useCatalogStore } from '../../stores/catalog'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'
import type { Run } from '../../api/types'

const RouterLinkStub = {
  props: ['to'],
  template: '<a data-testid="row-link"><slot /></a>',
}

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'feature-x', title: 'A feature', mode: 'brownfield', repo: 'r', activeStages: ['clarify'],
  status: 'blocked', blocker: 'clarify gate', cost: 3.12, budget: 40, age: '2h',
  decisions: [], ...over,
})

beforeEach(() => {
  setActivePinia(createPinia())
  useCatalogStore().catalog = catalogJson as unknown as CatalogWire
})

describe('FleetTable', () => {
  it('renders a header and one row per run', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'r1' }), mkRun({ id: 'r2', status: 'done' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(2)
    expect(w.text()).toContain('RUN')
    expect(w.text()).toContain('STATUS')
  })

  it('renders one stage dot per served canonical stage', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun()]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="stage-dot"]')).toHaveLength(18)
  })

  it('formats cost and age', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ cost: 3.1, age: '2h 14m' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.text()).toContain('$3.10')
    expect(w.text()).toContain('2h 14m')
  })

  it('renders status pip with stable class and no inline style', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ status: 'blocked' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    const pip = w.find('.cmp-status-pip')
    expect(pip.exists()).toBe(true)
    expect(pip.classes()).toContain('cmp-status-pip-blocked')
    expect(pip.attributes('style')).toBeUndefined()
  })
})
```

`interfaces/dashboard/frontend/src/adapters/fleet.test.ts` (replace; 84 lines):

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { toFleetRow, toStageDots } from './fleet'
import type { Run } from '../api/types'
import catalogJson from '../api/__fixtures__/graph/catalog.json'

const CANONICAL: string[] = catalogJson.canonical_stages

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'run-1',
  title: 'Test run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['requirements'],
  status: 'running',
  blocker: null,
  cost: null,
  budget: 50,
  age: '10m',
  decisions: [],
  ...over,
})

describe('fleet adapter', () => {
  it('adapts a run into FleetRowProps preserving null cost', () => {
    const run = mkRun({ cost: null })
    const row = toFleetRow(run, CANONICAL)
    expect(row.id).toBe('run-1')
    expect(row.title).toBe('Test run')
    expect(row.mode).toBe('brownfield')
    expect(row.cost).toBeNull()
    expect(row.href).toBe('/runs/run-1')
    expect(row.status.kind).toBe('running')
    expect(row.status.pulsing).toBe(true)
  })

  it('renders one dot per served canonical stage, keyed by name', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'running' }), CANONICAL)
    expect(dots.map((d) => d.stage)).toEqual(CANONICAL)
    expect(dots).toHaveLength(18)
    expect(dots.find((d) => d.stage === 'research')!.state).toBe('done')
    expect(dots.find((d) => d.stage === 'clarify')!.state).toBe('active')
    expect(dots.find((d) => d.stage === 'architecture')!.state).toBe('pending')
  })

  it('regression: a run at clarify never lights architecture (the 14/18 index defect)', () => {
    const dots = toStageDots(mkRun({ activeStages: ['clarify'], status: 'blocked' }), CANONICAL)
    expect(dots.filter((d) => d.state === 'blocked').map((d) => d.stage)).toEqual(['clarify'])
  })

  it('renders nothing before the catalog loads', () => {
    expect(toStageDots(mkRun(), [])).toEqual([])
  })

  it('satisfies the ownership rule: ui never imports from dashboard or api/types', () => {
    function getFiles(dir: string): string[] {
      const entries = readdirSync(dir)
      const files: string[] = []
      for (const e of entries) {
        const full = join(dir, e)
        if (statSync(full).isDirectory()) {
          files.push(...getFiles(full))
        } else if (full.endsWith('.ts') || full.endsWith('.vue')) {
          files.push(full)
        }
      }
      return files
    }

    const uiSrc = join(__dirname, '../../../../ui/src')
    const files = getFiles(uiSrc)
    const violations: string[] = []

    for (const f of files) {
      const content = readFileSync(f, 'utf8')
      if (content.includes("from '../../dashboard") || content.includes('api/types')) {
        violations.push(f)
      }
    }

    expect(violations).toEqual([])
  })
})
```

`interfaces/dashboard/frontend/src/api/mock/index.test.ts` (replace; 102 lines):

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createMockApi, tickCosts } from './index'
import type { Run } from '../types'

const mk = (over: Partial<Run>): Run => ({
  id: 'x', title: 't', mode: 'brownfield', repo: 'r', activeStages: ['architecture'], status: 'running',
  blocker: '', cost: 1, budget: 10, age: '1m', decisions: [],
  ...over,
})

afterEach(() => { vi.restoreAllMocks() })

describe('tickCosts', () => {
  it('bumps running runs and leaves others untouched', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [mk({ id: 'a', status: 'running', cost: 1 }), mk({ id: 'b', status: 'done', cost: 5 })]
    const out = tickCosts(runs)
    expect(out[0].cost).toBeCloseTo(1.05, 5)
    expect(out[1].cost).toBe(5)
  })
})

describe('mock api decision flows', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  it('seeds 8 runs and 6 inbox items, including the graph demo run', async () => {
    expect(await api.listRuns()).toHaveLength(8)
    expect(await api.listInbox()).toHaveLength(6)
  })

  it('answers a clarify question and logs a decision', async () => {
    await api.answerClarify('feature-add-sso', 'q1', 'Use OIDC.')
    const inbox = await api.listInbox()
    expect(inbox.find((i) => i.id === 'q1')).toBeUndefined()
    const run = await api.getRun('feature-add-sso')
    expect(run?.decisions.some((d) => d.outcome === 'approve' && d.gate.includes('clarify Q1'))).toBe(true)
  })

  it('advances a run to architecture when the last clarify is answered', async () => {
    await api.answerClarify('feature-add-sso', 'q1', 'OIDC')
    await api.answerClarify('feature-add-sso', 'q2', 'Keep password behind a flag')
    const run = await api.getRun('feature-add-sso')
    expect(run?.activeStages).toEqual(['architecture'])
    expect(run?.status).toBe('running')
  })

  it('throws when the key is not pending on that run', async () => {
    // q1 belongs to feature-add-sso; scoping to another run must fail loudly,
    // not silently succeed (the wrong-run POST is F1's whole finding).
    await expect(
      api.answerClarify('feature-usage-metering', 'q1', 'x'),
    ).rejects.toThrow('no pending item q1 on feature-usage-metering')
  })

  it('approving a gate advances the stage', async () => {
    await api.decideGate('feature-usage-metering', 'g2', 'approve', '')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('running')
    expect(run?.activeStages).toEqual(['planning'])
  })

  it('rejecting a gate fails the branch', async () => {
    await api.decideGate('feature-usage-metering', 'g2', 'reject', 'wrong layering')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('failed')
  })

  it('override approve moves run to deploy', async () => {
    await api.overrideMerge('feature-billing-webhooks', 'g1', true, 'retry branches covered indirectly')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.activeStages).toEqual(['deploy'])
    expect(run?.status).toBe('running')
  })

  it('override send-back drops run to code', async () => {
    await api.overrideMerge('feature-billing-webhooks', 'g1', false, '')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.activeStages).toEqual(['code'])
  })

  it('escalation retry resumes the task', async () => {
    await api.resolveEscalation('fix-rate-limit-retry', 'e1', true, 'inject a clock')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('repair attempt 4')
  })

  it('escalation quarantine keeps the wave going', async () => {
    await api.resolveEscalation('fix-rate-limit-retry', 'e1', false, '')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('quarantined')
    expect(run?.status).toBe('running')
  })

  it('startRun slugs the title and prepends the run', async () => {
    const r = await api.startRun({ title: 'Add SSO to customer portal', description: '', repo: '', mode: 'brownfield' })
    expect(r.id).toBe('feature-add-sso-to-customer')
    expect((await api.listRuns())[0].id).toBe(r.id)
  })
})
```

`interfaces/dashboard/frontend/src/api/http.test.ts` (replace; 94 lines):

```ts
import { describe, it, expect } from 'vitest'
import snapshot from './__fixtures__/fleet-snapshot.json'
import { mapSnapshot } from './http'

const NOW = new Date('2026-08-18T11:00:00Z')

describe('mapSnapshot', () => {
  it('maps a live run onto the view model', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const sso = runs.find((r) => r.id === 'feature-add-sso')!
    expect(sso.title).toBe('Add SSO to customer portal')
    expect(sso.mode).toBe('brownfield')
    expect(sso.repo).toBe('git@github.com:acme/portal')
    expect(sso.cost).toBe(3.12)
    expect(sso.budget).toBe(40)
  })

  it('maps an awaiting status to blocked', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.status).toBe('blocked')
  })

  it('maps a running status to running', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.status).toBe('running')
  })

  it('keeps an unpriced run null rather than zero', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-unpriced')!.cost).toBeNull()
  })

  it('carries current_stage as a stage name, never an index', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.activeStages).toEqual(['architecture'])
  })

  it('formats age from started_at', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-add-sso')!.age).toBe('2h 00m')
  })

  it('renders a closed run as done', () => {
    const { runs } = mapSnapshot(snapshot as never, NOW)
    const closed = runs.find((r) => r.id === 'feature-dark-mode')!
    expect(closed.status).toBe('done')
    expect(closed.title).toBe('Dark mode for settings pages')
  })

  it('renders a rolled-back closed run as failed, not done', () => {
    // deployed: is the only success prefix; rolled-back: must not render
    // green (E-10 review F2).
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'fix-payment-retry')!.status).toBe('failed')
    expect(runs.find((r) => r.id === 'feature-dark-mode')!.status).toBe('done')
  })

  it('renders a merged-not-deployed closed run as done, not failed', () => {
    // Success family per tidyup.py: merged-not-deployed passed the absolute
    // merge gate; deploy was disabled/unapproved. It must not render red.
    const { runs } = mapSnapshot(snapshot as never, NOW)
    expect(runs.find((r) => r.id === 'feature-flag-cleanup')!.status).toBe('done')
    expect(runs.find((r) => r.id === 'fix-payment-retry')!.status).toBe('failed')
    expect(runs.find((r) => r.id === 'feature-dark-mode')!.status).toBe('done')
  })

  it('maps each pending variant to its inbox item type', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.type)).toEqual([
      'clarify', 'gate', 'override', 'escalation',
    ])
  })

  it('carries the merge gate check table onto the override item', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    const override = inbox.find((i) => i.type === 'override')!
    expect(override.checks).toEqual([
      { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
      { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 - target 0.80' },
    ])
  })

  it('uses the pending key as the inbox item id', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox.map((i) => i.id)).toEqual([
      'Q1', 'architecture#1', 'merge#1', 'task:T07#1',
    ])
  })

  it('computes inbox age from opened_at', () => {
    const { inbox } = mapSnapshot(snapshot as never, NOW)
    expect(inbox[0].age).toBe('2h 00m')
  })
})
```

`interfaces/dashboard/frontend/src/api/client.test.ts` (replace; 66 lines):

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { selectApi } from './client'
import snapshot from './__fixtures__/fleet-snapshot.json'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('selectApi', () => {
  it('mock provider seeds 8 runs', async () => {
    const api = selectApi('mock', { simulateLive: false })
    expect(await api.listRuns()).toHaveLength(8)
  })

  it('http provider fetches and maps the fleet snapshot', async () => {
    const api = selectApi('http')
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify(snapshot), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const runs = await api.listRuns()
    expect(runs.find((r) => r.id === 'feature-add-sso')?.title).toBe('Add SSO to customer portal')
    expect(fetchMock).toHaveBeenCalledWith('/api/inbox', expect.anything())
  })

  it('http startRun falls back to a locally-built run when the fresh snapshot does not contain it', async () => {
    const api = selectApi('http')
    const fetchMock = vi.fn(
      async (_path: string, init?: RequestInit) =>
        init?.method === 'POST'
          ? new Response(JSON.stringify({ run_id: 'feature-x' }), { status: 200 })
          : new Response(JSON.stringify(snapshot), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const run = await api.startRun({
      title: 'Feature X', description: '', repo: '', mode: 'brownfield',
    })
    expect(run.id).toBe('feature-x')
    expect(run.status).toBe('running')
  })

  it('defaults to the http provider when VITE_API is unset', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API', '')
    // Env is read at module init, so the default is only observable through
    // a fresh import. Behavioral distinction, not object identity: with no
    // fetch stub the http provider has no backend and rejects, where the
    // mock provider would resolve seeded runs.
    const { api } = await import('./client')
    await expect(api.listRuns()).rejects.toThrow()
  })

  it('selects the mock provider when VITE_API is mock', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API', 'mock')
    const { api } = await import('./client')
    try {
      expect(await api.listRuns()).toHaveLength(8)
    } finally {
      // The module-level api constructs the mock with simulateLive, whose
      // interval would otherwise outlive the test.
      ;(api as unknown as { dispose?: () => void }).dispose?.()
    }
  })
})
```
- [ ] **Step 3: Append the CONSOLE-3 clause and its app-tier test**

In `interfaces/ui/app.md`, insert before `## Failure modes`:

```markdown
### CONSOLE-3
The fleet strip renders one mark per canonical stage the provider's catalog
serves (18 today), keyed by name. [FR-1205, E-76 U4]
```

Append to `interfaces/ui/app.pw.ts`:

```ts
test('the fleet strip renders one mark per served canonical stage', async ({ page }) => {  // clause: CONSOLE-3
  const firstRow = page.locator('[data-testid="fleet-row"]').first()
  await expect(firstRow.locator('[data-testid="stage-dot"]')).toHaveCount(18)
  await expect(firstRow.locator('[data-testid="stage-dot"]').nth(4)).toHaveAttribute('title', /^research · /)
})
```
- [ ] **Step 4: Run the dashboard tests to verify they fail**

```bash
npm run test --workspace sdlc-dashboard
```

Expected: FAIL — `http-graph.test.ts` and `mock/graph.test.ts` cannot resolve their modules; the rewritten tests fail on `activeStages`/`stageStates`/`toStageDots(run, stages)` (undefined or wrong arity) and on the 8-run / 6-item mock seed.
- [ ] **Step 5: Write the new modules**

`interfaces/dashboard/frontend/src/api/graph-types.ts` (create; 169 lines):

```ts
// Graph wire shapes (E-76 spec §5). A STRUCTURAL mirror of the pydantic
// models in src/sdlc/dashboard/graph_wire.py, pinned by the recorded
// fixtures in __fixtures__/graph/ (tests/test_graph_fixtures_fresh.py).
// `role` and `gate` stay opaque: the canvas never learns RoleConfig fields.
// FINAL = shipped by E-76; PROVISIONAL = E-73/E-75/E-77 implement.

export interface NodeWire {
  id: string
  type: string
  role?: Record<string, unknown>
  gate?: Record<string, unknown>
  position?: { x: number; y: number }
  label?: string
}

export interface EdgeWire {
  source: string
  source_port: string
  target: string
  target_port: string
  max_traversals?: number
  label?: string
}

export interface GraphWire {
  schema_version: 1
  nodes: NodeWire[]
  edges: EdgeWire[]
}

export interface EdgeRef {
  source: string
  source_port: string
  target: string
  target_port: string
}

export interface ShapeError {
  loc: (string | number)[]
  msg: string
  line: number | null
  column: number | null
}

// --- catalog (FINAL) ---------------------------------------------------------

export interface PortWire {
  name: string
  direction: 'in' | 'out'
  payload: string | null
  required: boolean
  multiplicity: 'one' | 'many'
}

export interface NodeTypeWire {
  type: string
  kind: 'stage' | 'gate'
  role: string | null
  canonical_stage: string | null
  default_id: string
  ports: PortWire[]
  connectable: Record<string, { type: string; port: string }[]>
}

export type Capability = 'validate' | 'save' | 'load' | 'run_graph'

export interface CatalogWire {
  node_types: NodeTypeWire[]
  canonical_stages: string[]
  schemas: { GraphNode: JsonSchema; GraphEdge: JsonSchema }
  capabilities: Record<Capability, boolean>
  max_graph_bytes: number
}

// The JSON Schema subset pydantic emits; schema_form narrows further.
export type JsonSchema = Record<string, unknown>

// --- parse / serialize (FINAL) ----------------------------------------------------

export type ParseWire =
  | { ok: true; graph: GraphWire; sha: string }
  | { ok: false; shape_errors: ShapeError[] }

export type SerializeWire = { ok: true; yaml: string } | { ok: false; shape_errors: ShapeError[] }

// --- validate (PROVISIONAL, E-73 + E-75) ---------------------------------------------

export interface IssueTarget {
  kind: 'graph' | 'node' | 'edge' | 'port'
  id?: string | null
  edge?: EdgeRef | null
  node?: string | null
  port?: string | null
}

export interface Issue {
  code: string
  severity: 'error' | 'warning'
  message: string
  target: IssueTarget
}

export interface ValidationWire {
  issues: Issue[]
  back_edges: EdgeRef[]
}

// --- save / load (PROVISIONAL, E-75 + E-77) --------------------------------------------

export type SaveWire =
  | { ok: true; sha: string; validation: ValidationWire | null }
  | { ok: false; shape_errors: ShapeError[] }

export type LoadWire =
  | { ok: true; sha: string; graph: GraphWire }
  | { ok: false; reason: 'not_found' }

// --- run graph and run state (PROVISIONAL, E-75 on E-74) --------------------------------

export type GraphResponse =
  | { kind: 'graph'; sha: string; graph: GraphWire; back_edges: EdgeRef[] }
  | { kind: 'no_graph'; reason: 'legacy_run' }

export type NodeRunStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale'

export interface NodeRunState {
  status: NodeRunStatus
  round: number
  started_at: string | null
  ended_at: string | null
  cost_usd: number | null
}

export interface PendingRef {
  node: string
  key: string
  kind: 'gate' | 'clarify' | 'escalation'
}

export type GraphStateResponse =
  | { kind: 'no_graph'; reason: 'legacy_run' }
  | {
      kind: 'state'
      graph_sha: string
      nodes: Record<string, NodeRunState>
      edges: { edge: EdgeRef; traversals: number }[]
      current_nodes: string[]
      pending: PendingRef[]
      terminal: null | 'done' | 'failed' | 'escalated'
    }

export class CapabilityUnavailable extends Error {
  constructor(readonly capability: Capability) {
    super(`graph capability "${capability}" is not available on this server`)
  }
}

export function edgeRefOf(e: EdgeRef): EdgeRef {
  return { source: e.source, source_port: e.source_port, target: e.target, target_port: e.target_port }
}

export function sameEdge(a: EdgeRef, b: EdgeRef): boolean {
  return (
    a.source === b.source &&
    a.source_port === b.source_port &&
    a.target === b.target &&
    a.target_port === b.target_port
  )
}
```

`interfaces/dashboard/frontend/src/api/http-graph.ts` (create; 85 lines):

```ts
// The http provider's graph surface (E-76 spec §7.2). The three FINAL
// routes are real; the PROVISIONAL ones are wired to their spec paths but
// gated by the server-declared capabilities (D9) instead of probing 404s.
import type { DashboardApi } from './types'
import {
  CapabilityUnavailable,
  type Capability,
  type CatalogWire,
  type GraphStateResponse,
} from './graph-types'
import { startPoll, type PollStep } from './poll'
import { HttpStatusError, isNotFound } from './errors'

type GraphApi = Pick<
  DashboardApi,
  | 'getCatalog' | 'parseGraph' | 'serializeGraph' | 'validateGraph' | 'saveGraph'
  | 'loadGraph' | 'getRunGraph' | 'subscribeGraphState'
>

export function createHttpGraphApi(baseUrl = '/api'): GraphApi {
  const call = async (path: string, init?: RequestInit) => {
    const r = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
    if (!r.ok) throw new HttpStatusError(r.status, `${init?.method ?? 'GET'} ${path}: ${r.status}`)
    return r.json()
  }
  const post = (path: string, body: unknown) =>
    call(path, { method: 'POST', body: JSON.stringify(body) })

  let catalog: Promise<CatalogWire> | null = null
  const getCatalog = () => {
    catalog ??= call('/graphs/catalog').catch((e) => {
      catalog = null // a failed fetch is retried, never cached
      throw e
    })
    return catalog
  }
  const need = async (cap: Capability) => {
    if (!(await getCatalog()).capabilities[cap]) throw new CapabilityUnavailable(cap)
  }
  const run = (runId: string) => `/runs/${encodeURIComponent(runId)}`

  return {
    getCatalog,
    parseGraph: (input) => post('/graphs/parse', input),
    serializeGraph: (graph) => post('/graphs/serialize', { graph }),
    async validateGraph(graph) {
      await need('validate')
      return post('/graphs/validate', { graph })
    },
    async saveGraph(graph) {
      await need('save')
      return post('/graphs', { graph })
    },
    async loadGraph(sha) {
      await need('load')
      return call(`/graphs/${encodeURIComponent(sha)}`)
    },
    async getRunGraph(runId) {
      await need('run_graph')
      return call(`${run(runId)}/graph`)
    },
    subscribeGraphState(runId, cb, onError) {
      const fetchOnce = async (signal: AbortSignal): Promise<PollStep<GraphStateResponse>> => {
        try {
          await need('run_graph')
        } catch (e) {
          if (e instanceof CapabilityUnavailable) return { kind: 'stop' }
          throw e
        }
        try {
          const state: GraphStateResponse = await call(`${run(runId)}/graph_state`, { signal })
          const final = state.kind === 'no_graph' || state.terminal !== null
          return { kind: 'value', value: state, final }
        } catch (e) {
          if (isNotFound(e)) return { kind: 'stop' }
          throw e
        }
      }
      return startPoll(fetchOnce, cb, (n) => onError?.(n))
    },
  }
}
```

`interfaces/dashboard/frontend/src/api/mock/graph.ts` (create; 169 lines):

```ts
// The mock's graph surface (E-76 spec D4, §7.2): a RECORDING, not a
// simulator. Catalog, parse and serialize answers were produced by the real
// Python (scripts/dump_graph_fixtures.py); validation and run state are
// hand-written PROVISIONAL fixtures. Anything unrecorded is answered as
// unrecorded -- never as success -- so Playwright cannot pass on behaviour
// nothing real produced.
import type { DashboardApi, GateOutcome } from '../types'
import type {
  CatalogWire, GraphResponse, GraphStateResponse, GraphWire, ParseWire, ValidationWire,
} from '../graph-types'
import catalogJson from '../__fixtures__/graph/catalog.json'
import validationJson from '../__fixtures__/graph/validation.provisional.json'
import runGraphsJson from '../__fixtures__/graph/run_graphs.provisional.json'

interface Scenario { name: string; yaml: string; parse: ParseWire; serialize: { ok: true; yaml: string } | null }
interface ObjectRecording { name: string; base: string; graph: GraphWire; parse: ParseWire }
interface ScriptState { state: GraphStateResponse; on: Partial<Record<GateOutcome, string>> }
interface RunScript { scenario: string; initial: string; states: Record<string, ScriptState> }

const scenarioModules = import.meta.glob('../__fixtures__/graph/scenarios/*.json', { eager: true, import: 'default' })
const objectModules = import.meta.glob('../__fixtures__/graph/objects/*.json', { eager: true, import: 'default' })
const SCENARIOS = Object.values(scenarioModules) as Scenario[]
const OBJECTS = Object.values(objectModules) as ObjectRecording[]
const VALIDATION = validationJson as unknown as Record<string, ValidationWire>
const RUN_SCRIPTS = (runGraphsJson as unknown as { runs: Record<string, RunScript> }).runs

// A LOOKUP KEY ONLY: object keys sorted, arrays untouched. Never a sha, never
// a canonical form, never exported (pinned by mock/graph.test.ts).
function lookupKey(value: unknown): string {
  const norm = (v: unknown): unknown =>
    Array.isArray(v)
      ? v.map(norm)
      : v !== null && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, norm((v as Record<string, unknown>)[k])]))
        : v
  return JSON.stringify(norm(value))
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

const UNRECORDED_VALIDATION: ValidationWire = {
  issues: [{ code: 'mock.unrecorded', severity: 'warning', message: 'mock: no recorded validation for this graph', target: { kind: 'graph' } }],
  back_edges: [],
}

type GraphApi = Pick<
  DashboardApi,
  | 'getCatalog' | 'parseGraph' | 'serializeGraph' | 'validateGraph' | 'saveGraph'
  | 'loadGraph' | 'getRunGraph' | 'subscribeGraphState'
>

export interface MockGraph extends GraphApi {
  /** Advance a scripted graph run after mock decideGate succeeded. */
  onDecision(runId: string, key: string, outcome: GateOutcome): void
  /** The seeded run ids that execute a graph. */
  graphRunIds(): string[]
}

export function createMockGraph(): MockGraph {
  const byText = new Map(SCENARIOS.map((s) => [s.yaml, s]))
  const byGraph = new Map<string, { parse: ParseWire; base: string }>()
  for (const s of SCENARIOS) if (s.parse.ok) byGraph.set(lookupKey(s.parse.graph), { parse: s.parse, base: s.name })
  for (const o of OBJECTS) byGraph.set(lookupKey(o.graph), { parse: o.parse, base: o.base })
  const serialized = new Map<string, string>()
  for (const s of SCENARIOS) if (s.parse.ok && s.serialize) serialized.set(lookupKey(s.parse.graph), s.serialize.yaml)

  let scenario: string | null = null
  let savedSeq = 0
  const saved = new Map<string, GraphWire>()
  const runState = new Map<string, string>(Object.entries(RUN_SCRIPTS).map(([id, s]) => [id, s.initial]))
  const listeners = new Map<string, Set<(s: GraphStateResponse) => void>>()

  const catalog: CatalogWire = {
    ...(catalogJson as unknown as CatalogWire),
    // The recording carries Python's all-false; the mock exercises every flow.
    capabilities: { validate: true, save: true, load: true, run_graph: true },
  }

  const nearest = (key: string) => {
    let best = ''
    let bestLen = -1
    for (const k of byGraph.keys()) {
      let i = 0
      while (i < k.length && k[i] === key[i]) i++
      if (i > bestLen) { bestLen = i; best = byGraph.get(k)!.base }
    }
    return best
  }

  const stateOf = (runId: string): GraphStateResponse => {
    const script = RUN_SCRIPTS[runId]
    if (!script) return { kind: 'no_graph', reason: 'legacy_run' }
    return clone(script.states[runState.get(runId)!].state)
  }

  return {
    async getCatalog() { return clone(catalog) },

    async parseGraph(input) {
      if ('yaml' in input) {
        const hit = byText.get(input.yaml)
        if (!hit) return { ok: false, shape_errors: [{ loc: [], msg: 'mock: unrecorded input', line: null, column: null }] }
        scenario = hit.name
        return clone(hit.parse)
      }
      const key = lookupKey(input.graph)
      const hit = byGraph.get(key)
      if (!hit) {
        console.warn(`mock parseGraph: unrecorded graph (nearest recording: ${nearest(key)})`, key)
        return { ok: false, shape_errors: [{ loc: [], msg: 'mock: unrecorded graph', line: null, column: null }] }
      }
      scenario = hit.base
      return clone(hit.parse)
    },

    async serializeGraph(graph) {
      const yaml = serialized.get(lookupKey(graph)) ?? JSON.stringify(graph, null, 2)
      return { ok: true, yaml }
    },

    async validateGraph() {
      const hit = scenario ? VALIDATION[scenario] : undefined
      return clone(hit ?? UNRECORDED_VALIDATION)
    },

    async saveGraph(graph) {
      const hit = byGraph.get(lookupKey(graph))
      const sha = hit && hit.parse.ok ? hit.parse.sha : `mock-sha-${++savedSeq}`
      saved.set(sha, clone(graph))
      return { ok: true, sha, validation: clone(scenario ? VALIDATION[scenario] ?? UNRECORDED_VALIDATION : UNRECORDED_VALIDATION) }
    },

    async loadGraph(sha) {
      const graph = saved.get(sha)
      return graph ? { ok: true, sha, graph: clone(graph) } : { ok: false, reason: 'not_found' }
    },

    async getRunGraph(runId): Promise<GraphResponse> {
      const script = RUN_SCRIPTS[runId]
      if (!script) return { kind: 'no_graph', reason: 'legacy_run' }
      const recorded = SCENARIOS.find((s) => s.name === script.scenario)!.parse
      if (!recorded.ok) throw new Error(`mock: scenario ${script.scenario} does not parse`)
      return { kind: 'graph', sha: recorded.sha, graph: clone(recorded.graph), back_edges: clone(VALIDATION[script.scenario].back_edges) }
    },

    subscribeGraphState(runId, cb) {
      // Deliver now and on every scripted transition; no timer, so a
      // Playwright flow is deterministic.
      const set = listeners.get(runId) ?? new Set()
      listeners.set(runId, set)
      set.add(cb)
      queueMicrotask(() => { if (set.has(cb)) cb(stateOf(runId)) })
      return () => { set.delete(cb) }
    },

    onDecision(runId, key, outcome) {
      const script = RUN_SCRIPTS[runId]
      if (!script) return
      const current = script.states[runState.get(runId)!]
      const pending = current.state.kind === 'state' && current.state.pending.some((p) => p.key === key)
      const next = current.on[outcome]
      if (!pending || !next) return
      runState.set(runId, next)
      for (const listener of listeners.get(runId) ?? []) listener(stateOf(runId))
    },

    graphRunIds() { return Object.keys(RUN_SCRIPTS) },
  }
}
```

`interfaces/dashboard/frontend/src/stores/catalog.ts` (create; 37 lines):

```ts
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { api } from '../api/client'
import type { Capability, CatalogWire, NodeTypeWire } from '../api/graph-types'

// The node-type catalog, canonical stages and capabilities, served by
// GET /graphs/catalog (E-76 spec §5.2, §7.3). Loaded once per session.
export const useCatalogStore = defineStore('catalog', () => {
  const catalog = shallowRef<CatalogWire | null>(null)
  const error = ref<string | null>(null)
  let inflight: Promise<void> | null = null

  function load(): Promise<void> {
    // Promise.resolve() first: a provider that throws synchronously still
    // lands in the error branch, never as an unhandled rejection at mount.
    inflight ??= Promise.resolve().then(() => api.getCatalog()).then(
      (c) => { catalog.value = c; error.value = null },
      (e: unknown) => { inflight = null; error.value = String(e) },
    )
    return inflight
  }

  const canonicalStages = computed<readonly string[]>(() => catalog.value?.canonical_stages ?? [])
  const nodeTypes = computed<readonly NodeTypeWire[]>(() => catalog.value?.node_types ?? [])
  const typeOf = (type: string): NodeTypeWire | undefined =>
    catalog.value?.node_types.find((t) => t.type === type)
  const can = (cap: Capability): boolean => catalog.value?.capabilities[cap] ?? false

  // The ONLY check TS runs while dragging (spec §8.2, GRAPH_CANVAS-6): a
  // membership test over Python's ports_compatible, served as data.
  function connectable(sourceType: string, sourcePort: string, targetType: string, targetPort: string): boolean {
    const targets = typeOf(sourceType)?.connectable[sourcePort] ?? []
    return targets.some((t) => t.type === targetType && t.port === targetPort)
  }

  return { catalog, error, load, canonicalStages, nodeTypes, typeOf, can, connectable }
})
```
- [ ] **Step 6: Replace the changed modules**

`interfaces/dashboard/frontend/src/api/types.ts` (replace; 127 lines):

```ts
import type {
  CatalogWire, GraphResponse, GraphStateResponse, GraphWire, LoadWire, ParseWire, SaveWire,
  SerializeWire, ValidationWire,
} from './graph-types'

export type Status = 'running' | 'blocked' | 'failed' | 'done'
export type GateOutcome = 'approve' | 'revise' | 'reject'
export type ProjectMode = 'brownfield' | 'greenfield'

export interface Decision {
  ts: string
  gate: string
  outcome: GateOutcome
  comment: string
  decider: string
}

export interface Run {
  id: string
  title: string
  mode: ProjectMode
  repo: string
  // Canonical stage NAMES (E-76 spec §5.8): a graph can fan out, so more
  // than one may be active. Never an index -- see adapters/fleet.ts.
  activeStages: string[]
  status: Status
  blocker: string
  cost: number | null
  budget: number | null
  age: string
  decisions: Decision[]
}

export interface ClarifyItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'clarify'
  title: string
  body: string
  suggestion: string
}

export interface GateItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'gate'
  gate: string
  title: string
  body: string
}

export interface CheckRow {
  name: string
  kind: 'ABSOLUTE' | 'ADVISORY'
  ok: boolean
  detail: string
}

export interface OverrideItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'override'
  gate: 'merge'
  title: string
  body: string
  verdict: string
  checks: CheckRow[]
}

export interface EscalationItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'escalation'
  title: string
  body: string
  analysis: string
}

export type InboxItem =
  | ClarifyItem
  | GateItem
  | OverrideItem
  | EscalationItem

export interface StartRunInput {
  title: string
  description: string
  repo: string
  mode: ProjectMode
}

export interface FleetState {
  runs: Run[]
  inbox: InboxItem[]
  errors: { runId: string; error: string }[]
}

export interface DashboardApi {
  listRuns(): Promise<Run[]>
  getRun(id: string): Promise<Run | undefined>
  listInbox(): Promise<InboxItem[]>
  answerClarify(runId: string, key: string, answer: string): Promise<void>
  decideGate(runId: string, key: string, outcome: GateOutcome, comment: string): Promise<void>
  overrideMerge(runId: string, key: string, approve: boolean, justification: string): Promise<void>
  resolveEscalation(runId: string, key: string, retry: boolean, guidance: string): Promise<void>
  startRun(input: StartRunInput): Promise<Run>
  subscribe(cb: (s: FleetState) => void): () => void

  // Graph surface (E-76 spec §7.1). A method whose capability is false in
  // getCatalog() throws CapabilityUnavailable; views gate on capabilities.
  getCatalog(): Promise<CatalogWire>
  parseGraph(input: { yaml: string } | { graph: GraphWire }): Promise<ParseWire>
  serializeGraph(graph: GraphWire): Promise<SerializeWire>
  validateGraph(graph: GraphWire): Promise<ValidationWire>
  saveGraph(graph: GraphWire): Promise<SaveWire>
  loadGraph(sha: string): Promise<LoadWire>
  getRunGraph(runId: string): Promise<GraphResponse>
  subscribeGraphState(runId: string, cb: (s: GraphStateResponse) => void, onError?: (failures: number) => void): () => void
}
```

`interfaces/dashboard/frontend/src/api/http.ts` (replace; 216 lines):

```ts
import type {
  ClarifyItem, DashboardApi, Decision, EscalationItem, FleetState, GateItem,
  GateOutcome, InboxItem, OverrideItem, Run, StartRunInput, Status,
} from './types'
import { createHttpGraphApi } from './http-graph'
import { HttpStatusError } from './errors'

// Stage NAMES only (E-76 spec §9.1): the strip's canonical list is served by
// GET /graphs/catalog, never copied here, and no node id is ever invented.
function stagesOf(name: string | null | undefined): string[] {
  return name ? [name] : []
}

function age(fromIso: string | null | undefined, now: Date): string {
  if (!fromIso) return ''
  const ms = now.getTime() - new Date(fromIso).getTime()
  const mins = Math.max(0, Math.floor(ms / 60000))
  const d = Math.floor(mins / 1440)
  if (d > 0) return `${d}d ${Math.floor((mins % 1440) / 60)}h`
  const h = Math.floor(mins / 60)
  return `${h}h ${String(mins % 60).padStart(2, '0')}m`
}

function hhmm(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

function liveStatus(status: string): Status {
  return status.startsWith('awaiting:') ? 'blocked' : 'running'
}

function closedStatus(outcome: string): Status {
  // Success family per tidyup.py: deployed = merged AND shipped;
  // merged-not-deployed = merged, deploy disabled/unapproved. Failure has
  // many prefixes (deploy-broken:, deploy-rejected:, rolled-back:, plus
  // gate rejections), so testing for success keeps a rolled-back run from
  // rendering green.
  const done = outcome.startsWith('deployed:')
    || outcome.startsWith('merged-not-deployed:')
  return done ? 'done' : 'failed'
}

function blocker(status: string, pendingCount: number): string {
  if (!status.startsWith('awaiting:')) return ''
  const gate = status.slice('awaiting:'.length)
  return pendingCount > 1 ? `${gate} gate — ${pendingCount} items` : `${gate} gate`
}

function decisions(raw: any[]): Decision[] {
  return (raw ?? []).map((d) => ({
    ts: hhmm(d.decided_at),
    gate: `${d.gate} r${d.round}`,
    outcome: d.outcome as GateOutcome,
    comment: d.comments ?? '',
    decider: d.reviewer ?? d.decided_by,
  }))
}

function mapRun(s: any, pendingCount: number, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    activeStages: stagesOf(s.current_stage),
    status: liveStatus(s.status),
    blocker: blocker(s.status, pendingCount),
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: decisions(s.decisions),
  }
}

function mapClosed(s: any, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    activeStages: stagesOf(s.terminal_stage),
    status: closedStatus(s.outcome),
    blocker: '',
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: [],
  }
}

function mapPending(runId: string, p: any, now: Date): InboxItem {
  const base = { id: p.key, runId, round: p.round ?? 1, age: age(p.opened_at, now) }
  if (p.kind === 'clarify') {
    return {
      ...base, type: 'clarify', title: p.question, body: p.why_it_matters,
      suggestion: p.suggested_answer ?? '',
    } as ClarifyItem
  }
  if (p.kind === 'merge_gate') {
    return {
      ...base, type: 'override', gate: 'merge',
      title: `Merge gate — round ${p.round}`,
      body: 'Merging requires an audited human override (FR-106).',
      verdict: p.verdict ?? '',
      checks: (p.checks ?? []).map((c: any) => ({
        // CheckClass is lowercase on the wire ("absolute"); CheckRow.kind is
        // uppercase. Normalize here, not by widening the TS union.
        name: c.name, ok: c.passed, detail: c.detail,
        kind: String(c.classification).toUpperCase(),
      })),
    } as OverrideItem
  }
  if (p.kind === 'task_escalation') {
    return {
      ...base, type: 'escalation',
      title: `${p.task_id} — resolver exhausted (${p.attempts})`,
      body: `Task ${p.task_id} could not be closed by the fix loop.`,
      analysis: p.analysis ?? '',
    } as EscalationItem
  }
  return {
    ...base, type: 'gate', gate: p.gate,
    title: `${p.gate} (round ${p.round})`, body: p.spec_summary ?? '',
  } as GateItem
}

export function mapSnapshot(snap: any, now: Date = new Date()): FleetState {
  const pendingByRun = new Map<string, any[]>()
  for (const r of snap.inbox ?? []) pendingByRun.set(r.run_id, r.pending)

  const runs = [
    ...(snap.runs ?? []).map((s: any) =>
      mapRun(s, (pendingByRun.get(s.run_id) ?? []).length, now)),
    ...(snap.closed ?? []).map((s: any) => mapClosed(s, now)),
  ]
  const inbox: InboxItem[] = []
  for (const r of snap.inbox ?? []) {
    for (const p of r.pending) inbox.push(mapPending(r.run_id, p, now))
  }
  const errors = (snap.errors ?? []).map((e: any) => ({
    runId: e.run_id, error: e.error,
  }))
  return { runs, inbox, errors }
}

export function createHttpApi(baseUrl = '/api'): DashboardApi {
  const json = async (path: string, init?: RequestInit) => {
    const r = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
    if (!r.ok) throw new HttpStatusError(r.status, `${init?.method ?? 'GET'} ${path}: ${r.status}`)
    return r.status === 204 ? null : r.json()
  }

  const snapshot = async (): Promise<FleetState> =>
    mapSnapshot(await json('/inbox'))

  // Write verbs are run-scoped: two runs can both be awaiting the same key,
  // so looking the key up across the fleet could POST to the wrong run. Not
  // found is the backend's 404, never a silent return.
  const decide = (runId: string, key: string, body: Record<string, unknown>) =>
    json(`/runs/${encodeURIComponent(runId)}/decide`, {
      method: 'POST', body: JSON.stringify({ key, ...body }),
    })

  return {
    ...createHttpGraphApi(baseUrl),
    async listRuns() { return (await snapshot()).runs },
    async getRun(id) { return (await snapshot()).runs.find((r) => r.id === id) },
    async listInbox() { return (await snapshot()).inbox },

    async answerClarify(runId, key, answer) {
      await json(`/runs/${encodeURIComponent(runId)}/answer`, {
        method: 'POST', body: JSON.stringify({ key, text: answer }),
      })
    },
    decideGate: (runId, key, outcome, comment) =>
      decide(runId, key, { outcome, text: comment }),
    overrideMerge: (runId, key, approve, justification) =>
      decide(runId, key, {
        outcome: approve ? 'approve' : 'revise', text: justification,
      }),
    resolveEscalation: (runId, key, retry, guidance) =>
      decide(runId, key, {
        outcome: retry ? 'approve' : 'reject', text: guidance,
      }),

    async startRun(input: StartRunInput) {
      const { run_id } = await json('/runs', {
        method: 'POST',
        body: JSON.stringify({
          title: input.title, description: input.description,
          mode: input.mode, repo: input.repo,
        }),
      })
      const run = (await snapshot()).runs.find((r) => r.id === run_id)
      if (run) return run
      const nowIso = new Date().toISOString()
      return {
        id: run_id, title: input.title, mode: input.mode, repo: input.repo,
        activeStages: [], status: 'running' as const, blocker: '',
        cost: null, budget: null, age: age(nowIso, new Date(nowIso)),
        decisions: [],
      }
    },

    subscribe(cb) {
      const es = new EventSource(`${baseUrl}/events`)
      es.onmessage = (e) => cb(mapSnapshot(JSON.parse(e.data)))
      return () => es.close()
    },
  }
}
```

`interfaces/dashboard/frontend/src/api/mock/index.ts` (replace; 398 lines):

```ts
import type {
  DashboardApi,
  FleetState,
  GateOutcome,
  Run,
  InboxItem,
  ClarifyItem,
  GateItem,
  OverrideItem,
  EscalationItem,
  StartRunInput,
} from '../types'
import { createMockGraph } from './graph'
import { HttpStatusError } from '../errors'
import catalogJson from '../__fixtures__/graph/catalog.json'

// Stage NAMES, advanced along the served canonical list (E-76 spec §9.1).
const CANONICAL: string[] = (catalogJson as { canonical_stages: string[] }).canonical_stages
const nextStage = (stages: string[]): string[] => {
  const i = Math.max(...stages.map((s) => CANONICAL.indexOf(s)))
  return [CANONICAL[Math.min(i + 1, CANONICAL.length - 1)]]
}

export function tickCosts(runs: Run[]): Run[] {
  return runs.map((r) =>
    r.status === 'running'
      ? { ...r, cost: +((r.cost ?? 0) + 0.02 + Math.random() * 0.06).toFixed(2) }
      : r,
  )
}

function seedRuns(): Run[] {
  return [
    {
      // Executes a graph (mock/graph.ts + run_graphs.provisional.json): the
      // only seeded run whose RunView renders a canvas.
      id: 'feature-graph-demo',
      title: 'Graph-executed pre-code pipeline',
      mode: 'greenfield',
      repo: 'git@github.com:acme/graph-demo',
      activeStages: ['architecture'],
      status: 'blocked',
      blocker: 'architecture gate — round 2',
      cost: 2.6,
      budget: 20,
      age: '40m',
      decisions: [
        { ts: '09:25', gate: 'architecture r1', outcome: 'revise', comment: 'split the auth service', decider: 'human · sam' },
      ],
    },
    {
      id: 'feature-add-sso',
      title: 'Add SSO to customer portal',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      activeStages: ['clarify'],
      status: 'blocked',
      blocker: 'clarify gate — 2 questions',
      cost: 3.12,
      budget: 40,
      age: '2h 14m',
      decisions: [
        { ts: '09:12', gate: 'clarify r1 (partial)', outcome: 'approve', comment: '4 questions auto-answered, confidence ≥ 0.95', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'feature-billing-webhooks',
      title: 'Outbound webhooks for billing events',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      activeStages: ['quality_gate'],
      status: 'blocked',
      blocker: 'merge gate — advisory: coverage',
      cost: 18.4,
      budget: 60,
      age: '9h 03m',
      decisions: [
        { ts: '02:20', gate: 'architecture r1', outcome: 'approve', comment: 'delta grounded in CodebaseMap', decider: 'human · mika' },
        { ts: '03:05', gate: 'plan r1', outcome: 'approve', comment: '7 tasks / 3 waves, DAG valid', decider: 'policy (soft)' },
        { ts: '08:44', gate: 'task T-04 repair', outcome: 'approve', comment: 'review fix loop 1/2 green', decider: 'policy' },
      ],
    },
    {
      id: 'feature-onboarding-v2',
      title: 'Self-serve onboarding flow (new service)',
      mode: 'greenfield',
      repo: 'git@github.com:acme/onboard',
      activeStages: ['code'],
      status: 'running',
      blocker: '',
      cost: 9.75,
      budget: 50,
      age: '4h 41m',
      decisions: [
        { ts: '11:02', gate: 'clarify r1', outcome: 'approve', comment: 'all suggestions accepted', decider: 'human · sam' },
        { ts: '11:38', gate: 'architecture r1', outcome: 'revise', comment: 'split auth from profile service', decider: 'human · sam' },
        { ts: '12:19', gate: 'architecture r2', outcome: 'approve', comment: '', decider: 'human · sam' },
        { ts: '12:31', gate: 'plan r1', outcome: 'approve', comment: 'confidence 0.97', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'fix-rate-limit-retry',
      title: 'Fix: retry budget exhausted under burst load',
      mode: 'brownfield',
      repo: 'git@github.com:acme/gateway',
      activeStages: ['qa'],
      status: 'blocked',
      blocker: 'escalation — T-07 resolver 3/3',
      cost: 6.2,
      budget: 30,
      age: '6h 27m',
      decisions: [{ ts: '13:15', gate: 'plan r1', outcome: 'approve', comment: '', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-usage-metering',
      title: 'Usage metering for billing tiers',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      activeStages: ['architecture'],
      status: 'blocked',
      blocker: 'architecture gate — round 1',
      cost: 2.05,
      budget: 45,
      age: '1h 02m',
      decisions: [{ ts: '14:30', gate: 'clarify r1', outcome: 'approve', comment: 'auto, confidence 0.96', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-audit-export',
      title: 'Audit-trail export (events.jsonl + report)',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      activeStages: ['deploy'],
      status: 'running',
      blocker: '',
      cost: 14.02,
      budget: 40,
      age: '11h 50m',
      decisions: [
        { ts: '05:12', gate: 'merge r1', outcome: 'approve', comment: 'all checks green', decider: 'policy (soft)' },
        { ts: '06:01', gate: 'deploy r1', outcome: 'approve', comment: 'PR #482 merged, staging deploy', decider: 'human · mika' },
      ],
    },
    {
      id: 'feature-dark-mode',
      title: 'Dark mode for settings pages',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      activeStages: ['retro'],
      status: 'done',
      blocker: '',
      cost: 7.88,
      budget: 30,
      age: '1d 3h',
      decisions: [
        { ts: 'yday', gate: 'merge r1', outcome: 'approve', comment: '', decider: 'policy (soft)' },
        { ts: 'yday', gate: 'deploy r1', outcome: 'approve', comment: '', decider: 'human · sam' },
      ],
    },
  ]
}

function seedInbox(): InboxItem[] {
  return [
    {
      id: 'architecture#2',
      type: 'gate',
      gate: 'architecture',
      runId: 'feature-graph-demo',
      round: 2,
      age: '9m',
      title: 'Architecture (round 2) — graph demo',
      body: 'Revised after round 1: auth split into its own service.',
    },
    {
      id: 'q1',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q1 — Which identity protocol should SSO support?',
      body: 'The repo has no auth-provider abstraction. Requirements mention "enterprise SSO" but not a protocol; the CodebaseMap shows session middleware in portal/auth/session.py.',
      suggestion: 'OIDC (Authorization Code + PKCE). It fits the existing session middleware; defer SAML to a follow-up run if an enterprise customer requires it.',
    },
    {
      id: 'q2',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q2 — Should password login remain enabled after SSO ships?',
      body: 'US-1 is silent on migration. Disabling password auth immediately would lock out users whose IdP mapping fails on first login.',
      suggestion: 'Keep password auth behind a feature flag for 2 releases, then retire it once SSO adoption is > 95%.',
    },
    {
      id: 'g2',
      type: 'gate',
      gate: 'architecture',
      runId: 'feature-usage-metering',
      round: 1,
      age: '54m',
      title: 'Architecture (delta) — usage metering',
      body: 'Adds MeteringService (event ingest + hourly rollup), modifies billing-worker to emit usage events, adds 3 contracts (UsageEvent, MeterReading, TierQuota). No removals. Grounded in CodebaseMap @ a41c9e.',
    },
    {
      id: 'g1',
      type: 'override',
      gate: 'merge',
      runId: 'feature-billing-webhooks',
      round: 1,
      age: '1h 12m',
      title: 'Merge gate — advisory check needs a decision',
      body: 'All absolute checks pass. One advisory check fails; merging requires an audited human override (FR-106).',
      verdict: 'MergeVerdict 0.91 — approve. Uncovered lines are retry/backoff branches exercised indirectly by the integration suite; direct unit coverage would need an injected clock.',
      checks: [
        { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
        { name: 'security (critical)', kind: 'ABSOLUTE', ok: true, detail: '0 critical findings' },
        { name: 'build / integration', kind: 'ABSOLUTE', ok: true, detail: 'green · 4m12s' },
        { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 — target 0.80' },
        { name: 'criterion→test traceability', kind: 'ADVISORY', ok: true, detail: '9/9 criteria mapped' },
        { name: 'review severity', kind: 'ADVISORY', ok: true, detail: 'max severity: medium' },
      ],
    },
    {
      id: 'e1',
      type: 'escalation',
      runId: 'fix-rate-limit-retry',
      round: 1,
      age: '2h 05m',
      title: 'T-07 "retry budget accounting" — resolver exhausted (3/3)',
      body: 'QA fix loop hit MAX_REPAIR_ATTEMPTS. The task branch stays parked on its worktree; wave 3 is holding.',
      analysis: 'test_retry_budget flakes on wall-clock timing. A reliable fix needs an injected clock in RateLimiter, but rate_limiter/core.py is outside the task’s declared file scope. Recommend widening scope or quarantining.',
    },
  ]
}

export interface MockOptions {
  simulateLive?: boolean
}

export function createMockApi(opts: MockOptions = {}): DashboardApi & { dispose(): void } {
  const simulateLive = opts.simulateLive ?? true
  let runs: Run[] = seedRuns()
  let inbox: InboxItem[] = seedInbox()
  const graph = createMockGraph()

  const delay = () => new Promise<void>((r) => setTimeout(r, 120 + Math.random() * 180))

  const now = () => {
    const d = new Date()
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  }
  const patchRun = (id: string, patch: Partial<Run> | ((r: Run) => Partial<Run>)) => {
    runs = runs.map((r) => (r.id === id ? { ...r, ...(typeof patch === 'function' ? patch(r) : patch) } : r))
  }
  const addDecision = (runId: string, d: { ts?: string; gate: string; outcome: GateOutcome; comment?: string; decider?: string }) =>
    patchRun(runId, (r) => ({
      decisions: [...r.decisions, { ts: now(), decider: 'human · you', comment: '', ...d }],
    }))
  const removeItem = (id: string) => {
    inbox = inbox.filter((i) => i.id !== id)
  }
  const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

  const api: DashboardApi & { dispose(): void } = {
    getCatalog: graph.getCatalog,
    parseGraph: graph.parseGraph,
    serializeGraph: graph.serializeGraph,
    validateGraph: graph.validateGraph,
    saveGraph: graph.saveGraph,
    loadGraph: graph.loadGraph,
    getRunGraph: graph.getRunGraph,
    subscribeGraphState: graph.subscribeGraphState,

    async listRuns() {
      await delay()
      return clone(runs)
    },
    async getRun(id: string) {
      await delay()
      const r = runs.find((x) => x.id === id)
      return r ? clone(r) : undefined
    },
    async listInbox() {
      await delay()
      return clone(inbox)
    },

    async answerClarify(runId: string, key: string, answer: string) {
      await delay()
      const it = inbox.find((i) => i.id === key && i.runId === runId) as ClarifyItem | undefined
      if (!it) throw new HttpStatusError(404, `no pending item ${key} on ${runId}`)
      removeItem(key)
      addDecision(it.runId, {
        gate: `clarify Q${it.id.slice(1)} r${it.round}`,
        outcome: 'approve',
        comment: answer.length > 60 ? answer.slice(0, 57) + '…' : answer,
      })
      const left = inbox.some((i) => i.runId === it.runId && i.type === 'clarify')
      if (!left) {
        patchRun(it.runId, { status: 'running', activeStages: ['architecture'], blocker: '' })
      }
    },

    async decideGate(runId: string, key: string, outcome: GateOutcome, comment: string) {
      await delay()
      const it = inbox.find((i) => i.id === key && i.runId === runId && i.type === 'gate') as GateItem | undefined
      if (!it) throw new HttpStatusError(404, `no pending item ${key} on ${runId}`)
      removeItem(key)
      addDecision(it.runId, { gate: `${it.gate} r${it.round}`, outcome, comment })
      if (outcome === 'approve') {
        patchRun(it.runId, (r) => ({ status: 'running', activeStages: nextStage(r.activeStages), blocker: '' }))
      } else if (outcome === 'revise') {
        patchRun(it.runId, { status: 'running', blocker: `revising — round ${it.round + 1}` })
      } else {
        patchRun(it.runId, { status: 'failed', blocker: `rejected at ${it.gate}` })
      }
      graph.onDecision(runId, key, outcome)
    },

    async overrideMerge(runId: string, key: string, approve: boolean, justification: string) {
      await delay()
      const it = inbox.find((i) => i.id === key && i.runId === runId && i.type === 'override') as OverrideItem | undefined
      if (!it) throw new HttpStatusError(404, `no pending item ${key} on ${runId}`)
      removeItem(key)
      if (approve) {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'approve', comment: `ADVISORY OVERRIDE: ${justification}`, decider: 'human · you (override)' })
        patchRun(it.runId, { status: 'running', activeStages: ['deploy'], blocker: '' })
      } else {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'revise', comment: justification || 'raise diff coverage to 0.80' })
        patchRun(it.runId, { status: 'running', activeStages: ['code'], blocker: 'revising — coverage' })
      }
    },

    async resolveEscalation(runId: string, key: string, retry: boolean, guidance: string) {
      await delay()
      const it = inbox.find((i) => i.id === key && i.runId === runId && i.type === 'escalation') as EscalationItem | undefined
      if (!it) throw new HttpStatusError(404, `no pending item ${key} on ${runId}`)
      removeItem(key)
      if (retry) {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'approve', comment: `retry w/ guidance: ${guidance || '(none)'}` })
        patchRun(it.runId, { status: 'running', blocker: 'repair attempt 4 (guided)' })
      } else {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'reject', comment: guidance ? `quarantined: ${guidance}` : 'quarantined' })
        patchRun(it.runId, { status: 'running', blocker: 'T-07 quarantined' })
      }
    },

    async startRun(input: StartRunInput) {
      await delay()
      const t = input.title.trim()
      const id = 'feature-' + t
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .split('-')
        .slice(0, 4)
        .join('-')
      const run: Run = {
        id,
        title: t,
        mode: input.mode,
        repo: input.repo || 'git@github.com:acme/portal',
        activeStages: ['requirements'],
        status: 'running',
        blocker: '',
        cost: 0.04,
        budget: 40,
        age: 'just now',
        decisions: [],
      }
      runs = [run, ...runs]
      return clone(run)
    },

    subscribe(cb: (s: FleetState) => void) {
      // The mock already faked liveness with this timer; a push-shaped
      // contract is simply more honest about what it was doing.
      const t = setInterval(() => {
        runs = tickCosts(runs)
        cb({ runs: clone(runs), inbox: clone(inbox), errors: [] })
      }, 4000)
      return () => clearInterval(t)
    },

    dispose() {
      if (timer) clearInterval(timer)
    },
  }

  let timer: ReturnType<typeof setInterval> | null = null
  if (simulateLive && typeof window !== 'undefined') {
    timer = setInterval(() => {
      runs = tickCosts(runs)
    }, 4000)
  }

  return api
}
```

`interfaces/dashboard/frontend/src/composables/stageState.ts` (replace; 40 lines):

```ts
import type { Run } from '../api/types'
import type { DotState } from '@kroker/ui/components/stage_dots/StageDots.vue'

export type StageState = DotState

// The strip keyed by NAME over the served canonical list (E-76 spec §9.1).
// No index ever crosses the API: the old stageIdx computed in one stage list
// and rendered in another (a live run at clarify lit `architecture`).
// Names already reported: a product fault is logged once per name (§9.1),
// not on every recomputation of the strip.
const reported = new Set<string>()

export function stageStates(
  run: Pick<Run, 'activeStages' | 'status'>,
  canonicalStages: readonly string[],
): StageState[] {
  const positions: number[] = []
  for (const name of run.activeStages) {
    const i = canonicalStages.indexOf(name)
    if (i < 0) {
      // A product fault, never silently mapped (spec §9.1 rule 3).
      if (!reported.has(name)) {
        reported.add(name)
        console.error(`stage strip: "${name}" is not a canonical stage`)
      }
      continue
    }
    positions.push(i)
  }
  if (positions.length === 0) return canonicalStages.map(() => 'pending')
  const lowest = Math.min(...positions)
  const activeMark: StageState =
    run.status === 'blocked' ? 'blocked'
      : run.status === 'failed' ? 'failed'
        : run.status === 'done' ? 'done'
          : 'active'
  return canonicalStages.map((_, i) =>
    positions.includes(i) ? activeMark : i < lowest ? 'done' : 'pending',
  )
}
```

`interfaces/dashboard/frontend/src/constants.ts` (replace; 28 lines):

```ts
export const ARTIFACTS = [
  'IdeaBrief',
  'Constitution',
  'CodebaseMap',
  'Requirements',
  'Clarifications',
  'Architecture',
  'TaskPlan',
  'CodeArtifact',
  'ReviewReport',
  'AnalysisReport',
  'TestReport',
  'GateReport',
  'DeployReport',
  'RunSummary',
] as const

export const STATUS_KINDS = [
  'running',
  'blocked',
  'failed',
  'done',
  'quarantined',
  'pending',
  'skipped',
] as const

export type StatusKind = (typeof STATUS_KINDS)[number]
```

`interfaces/dashboard/frontend/src/adapters/fleet.ts` (replace; 35 lines):

```ts
import type { Run } from '../api/types'
import type { FleetRowProps } from '@kroker/ui/components/fleet_row/FleetRow.vue'
import type { StageDot } from '@kroker/ui/components/stage_dots/StageDots.vue'
import { statusMetaOf } from '../composables/status'
import { stageStates } from '../composables/stageState'

// canonicalStages comes from the catalog store (GET /graphs/catalog), never a
// TS copy (E-76 spec U4). Empty until the catalog loads: StageDots renders no
// marks for an unresolved list (STAGE_DOTS-1.1).
export function toStageDots(
  run: Pick<Run, 'activeStages' | 'status'>,
  canonicalStages: readonly string[],
): StageDot[] {
  const states = stageStates(run, canonicalStages)
  return canonicalStages.map((stage, i) => ({ stage, state: states[i] }))
}

export function toFleetRow(run: Run, canonicalStages: readonly string[]): FleetRowProps {
  const meta = statusMetaOf(run)
  return {
    id: run.id,
    title: run.title,
    mode: run.mode,
    dots: toStageDots(run, canonicalStages),
    status: {
      kind: run.status,
      label: meta.label,
      pulsing: run.status === 'running' || run.status === 'blocked',
    },
    blocker: run.blocker,
    cost: run.cost,
    age: run.age,
    href: `/runs/${run.id}`,
  }
}
```

`interfaces/dashboard/frontend/src/components/fleet/FleetTable.vue` (replace; 15 lines):

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../stores/fleet'
import { useCatalogStore } from '../../stores/catalog'
import FleetTable from '@kroker/ui/components/fleet_table/FleetTable.vue'
import { toFleetRow } from '../../adapters/fleet'

const fleet = useFleetStore()
const catalog = useCatalogStore()
const rows = computed(() => fleet.runs.map((r) => toFleetRow(r, catalog.canonicalStages)))
</script>

<template>
  <FleetTable :rows="rows" />
</template>
```

`interfaces/dashboard/frontend/src/App.vue` (replace; 50 lines):

```vue
<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useFleetStore } from './stores/fleet'
import { useInboxStore } from './stores/inbox'
import { useCatalogStore } from './stores/catalog'
import AppHeader from './components/AppHeader.vue'
import Toasts from './components/Toasts.vue'
import StartRunModal from './components/StartRunModal.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
const catalog = useCatalogStore()
let pollId: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([catalog.load(), fleet.refresh(), inbox.refresh()])
  pollId = setInterval(() => {
    if (document.visibilityState === 'visible') {
      fleet.refresh()
      inbox.refresh()
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollId) clearInterval(pollId)
})
</script>

<template>
  <div class="console">
    <AppHeader />
    <RouterView />
    <Toasts />
    <StartRunModal />
  </div>
</template>

<style scoped>
.console {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ground-1);
  color: var(--ink-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  overflow: hidden;
}
</style>
```
- [ ] **Step 7: Run the dashboard tests and typechecks to verify they pass**

```bash
npm run test --workspace sdlc-dashboard
npm run typecheck --workspace sdlc-dashboard
grep -rn "stageIdx" interfaces/dashboard/frontend/src
```

Expected: PASS — 16 test files, 98 tests (http-graph 9, mock/graph 14, poll 6 and the rewritten suites); typecheck clean; `grep` finds only the explanatory comment in `composables/stageState.ts`.
- [ ] **Step 8: Run the CONSOLE-3 app-tier test**

```bash
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- app.pw.ts
```

Expected: PASS — CONSOLE-1, CONSOLE-2, CONSOLE-3.
- [ ] **Step 9: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 10: Commit**

Write `.workspace/tmp/e76-t7-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 graph API contract and name-keyed stage strip

DashboardApi gains the graph surface: getCatalog, parse/serialize over
the shipped routes, and validate/save/load/run-graph/run-state wired to
their PROVISIONAL paths but gated by server-declared capabilities. The mock
replays the Python recordings -- unrecorded input is an error, never
success -- and seeds feature-graph-demo, a decision-driven graph run.

Run.stageIdx becomes Run.activeStages: stage NAMES matched over the
canonical list the catalog serves. This removes both TS stage lists and
fixes the existing defect where http.ts indexed an 18-stage list that the
fleet row rendered against a 14-stage one (a run at clarify lit
architecture).
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/api/graph-types.ts
git add interfaces/dashboard/frontend/src/api/http-graph.ts
git add interfaces/dashboard/frontend/src/api/mock/graph.ts
git add interfaces/dashboard/frontend/src/stores/catalog.ts
git add interfaces/dashboard/frontend/src/api/types.ts
git add interfaces/dashboard/frontend/src/api/http.ts
git add interfaces/dashboard/frontend/src/api/mock/index.ts
git add interfaces/dashboard/frontend/src/composables/stageState.ts
git add interfaces/dashboard/frontend/src/constants.ts
git add interfaces/dashboard/frontend/src/adapters/fleet.ts
git add interfaces/dashboard/frontend/src/components/fleet/FleetTable.vue
git add interfaces/dashboard/frontend/src/App.vue
git add interfaces/dashboard/frontend/src/api/http-graph.test.ts
git add interfaces/dashboard/frontend/src/api/mock/graph.test.ts
git add interfaces/dashboard/frontend/src/constants.test.ts
git add interfaces/dashboard/frontend/src/composables/composables.test.ts
git add interfaces/dashboard/frontend/src/components/fleet/FleetTable.test.ts
git add interfaces/dashboard/frontend/src/adapters/fleet.test.ts
git add interfaces/dashboard/frontend/src/api/mock/index.test.ts
git add interfaces/dashboard/frontend/src/api/http.test.ts
git add interfaces/dashboard/frontend/src/api/client.test.ts
git add interfaces/ui/app.md
git add interfaces/ui/app.pw.ts
git commit -F .workspace/tmp/e76-t7-msg.txt
```
### Task 8: `gate_decision` component

**Files:**
- Create: `interfaces/ui/src/components/gate_decision/GateDecision.vue`, `interfaces/ui/src/components/gate_decision/gate_decision.md`, `interfaces/ui/src/components/gate_decision/gate_decision.profiles.ts`
- Test: `interfaces/ui/src/components/gate_decision/gate_decision.spec.ts`, `interfaces/ui/src/components/gate_decision/gate_decision.pw.ts`
- Modify: `interfaces/ui/showcase/registry.ts`

**Interfaces:**
- Consumes: `defineProfiles` (`interfaces/ui/src/profile.ts`).
- Produces: `GateDecision.vue` — props `title`, `busy?`, `disabled?`; emits `decide({outcome: 'approve'|'revise'|'reject', comment})`; exports type `GateDecisionOutcome`.

- [ ] **Step 1: Write the clause contract and profiles**

`interfaces/ui/src/components/gate_decision/gate_decision.md` (create; 25 lines):

```markdown
# Gate Decision Component

Renders the approve / revise / reject controls for one pending human gate,
with a comment. The caller owns which gate is pending, the decision key, the
API call, and the busy state while a decision is in flight; the component
owns the controls and the revise-needs-a-comment affordance.

## Requirements

### GATE_DECISION-1
A Gate Decision emits `decide` with `{ outcome, comment }` for the pressed
outcome, the comment trimmed. [FR-1205]

### GATE_DECISION-2
Revise is disabled while the comment is blank; approve and reject are not.
This is a UI affordance, not a server guard (E76-OQ-4). [FR-1205]

### GATE_DECISION-3
While `busy` or `disabled`, every control is disabled and no `decide` is
emitted: a decision in flight cannot be submitted twice. [FR-1205]

## Failure modes

A blank revise emits nothing. Busy state is caller-owned; the component
never clears it.
```

`interfaces/ui/src/components/gate_decision/gate_decision.profiles.ts` (create; 13 lines):

```ts
import { defineProfiles } from '../../profile'
import GateDecision from './GateDecision.vue'

export default defineProfiles({
  component: 'gate_decision',
  group: 'Graph',
  target: GateDecision,
  profiles: [
    { name: 'idle', summary: 'A pending gate awaiting a decision.', props: { title: 'architecture · round 2' } },
    { name: 'busy', summary: 'A decision in flight: every control disabled.', props: { title: 'architecture · round 2', busy: true } },
    { name: 'revise-needs-comment', summary: 'Revise stays disabled until a comment is typed.', props: { title: 'plan · round 1' } },
  ],
})
```
- [ ] **Step 2: Write the failing tests**

`interfaces/ui/src/components/gate_decision/gate_decision.spec.ts` (create; 39 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GateDecision from './GateDecision.vue'

describe('GateDecision', () => {
  it('emits the pressed outcome with the trimmed comment', async () => {  // clause: GATE_DECISION-1
    const w = mount(GateDecision, { props: { title: 'arch' } })
    await w.find('[data-testid="gate-comment"]').setValue('  looks good ')
    await w.find('[data-testid="gate-approve"]').trigger('click')
    await w.find('[data-testid="gate-reject"]').trigger('click')
    expect(w.emitted('decide')).toEqual([
      [{ outcome: 'approve', comment: 'looks good' }],
      [{ outcome: 'reject', comment: 'looks good' }],
    ])
  })

  it('disables revise until the comment is non-blank', async () => {  // clause: GATE_DECISION-2
    const w = mount(GateDecision, { props: { title: 'arch' } })
    const revise = w.find('[data-testid="gate-revise"]')
    expect(revise.attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="gate-approve"]').attributes('disabled')).toBeUndefined()
    await w.find('[data-testid="gate-comment"]').setValue('   ')
    expect(revise.attributes('disabled')).toBeDefined()
    await w.find('[data-testid="gate-comment"]').setValue('split auth')
    expect(revise.attributes('disabled')).toBeUndefined()
    await revise.trigger('click')
    expect(w.emitted('decide')).toEqual([[{ outcome: 'revise', comment: 'split auth' }]])
  })

  it('emits nothing while busy', async () => {  // clause: GATE_DECISION-3
    const w = mount(GateDecision, { props: { title: 'arch', busy: true } })
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(w.find(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    await w.find('[data-testid="gate-approve"]').trigger('click')
    await w.find('[data-testid="gate-reject"]').trigger('click')
    expect(w.emitted('decide')).toBeUndefined()
  })
})
```

`interfaces/ui/src/components/gate_decision/gate_decision.pw.ts` (create; 19 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-gate_decision-${profile}`

test('revise enables only once a comment is typed', async ({ page }) => {  // clause: GATE_DECISION-2
  await page.goto('/')
  const revise = page.locator(`${at('revise-needs-comment')} [data-testid="gate-revise"]`)
  await expect(revise).toBeDisabled()
  await expect(page.locator(`${at('revise-needs-comment')} [data-testid="gate-approve"]`)).toBeEnabled()
  await page.locator(`${at('revise-needs-comment')} [data-testid="gate-comment"]`).fill('tighten the plan')
  await expect(revise).toBeEnabled()
})

test('busy disables every control', async ({ page }) => {  // clause: GATE_DECISION-3
  await page.goto('/')
  for (const id of ['gate-approve', 'gate-revise', 'gate-reject', 'gate-comment']) {
    await expect(page.locator(`${at('busy')} [data-testid="${id}"]`)).toBeDisabled()
  }
})
```
- [ ] **Step 3: Register the profiles in the showcase**

In `interfaces/ui/showcase/registry.ts`, add the import(s) after the last existing profile import:

```ts
import gateDecision from '../src/components/gate_decision/gate_decision.profiles'
```

and append `gateDecision` to the end of the `REGISTRY` array (keep existing order).
- [ ] **Step 4: Run the unit tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/gate_decision
```

Expected: FAIL — the spec files cannot resolve the component module(s) (the profiles also import them, so the showcase build fails until Step 5).
- [ ] **Step 5: Write the implementation**

`interfaces/ui/src/components/gate_decision/GateDecision.vue` (create; 54 lines):

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'

export type GateDecisionOutcome = 'approve' | 'revise' | 'reject'

const props = withDefaults(defineProps<{ title: string; busy?: boolean; disabled?: boolean }>(), {
  busy: false,
  disabled: false,
})
const emit = defineEmits<{ (e: 'decide', v: { outcome: GateDecisionOutcome; comment: string }): void }>()

const comment = ref('')
const locked = computed(() => props.busy || props.disabled)
// GATE_DECISION-2: a revise must say what to change. A UI affordance only --
// the server accepts an empty revise (E-76 spec E76-OQ-4).
const reviseBlocked = computed(() => locked.value || comment.value.trim() === '')

function decide(outcome: GateDecisionOutcome) {
  if (locked.value || (outcome === 'revise' && reviseBlocked.value)) return
  emit('decide', { outcome, comment: comment.value.trim() })
}
</script>

<template>
  <div class="cmp-gate-decision" :class="{ 'is-busy': busy }" data-testid="gate-decision" @mousedown.stop @keydown.stop>
    <div class="title">{{ title }}</div>
    <textarea
      v-model="comment"
      class="comment"
      data-testid="gate-comment"
      rows="2"
      placeholder="comment (required to revise)"
      :disabled="locked"
    />
    <div class="actions">
      <button data-testid="gate-approve" class="btn approve" :disabled="locked" @click="decide('approve')">approve</button>
      <button data-testid="gate-revise" class="btn revise" :disabled="reviseBlocked" @click="decide('revise')">revise</button>
      <button data-testid="gate-reject" class="btn reject" :disabled="locked" @click="decide('reject')">reject</button>
    </div>
  </div>
</template>

<style scoped>
.cmp-gate-decision { display: flex; flex-direction: column; gap: 6px; padding: 8px; border-top: 1px solid var(--line); background: var(--ground-4); }
.cmp-gate-decision.is-busy { opacity: 0.6; }
.title { color: var(--ink-primary); font-size: 12px; font-weight: 600; }
.comment { resize: vertical; background: var(--ground-2); color: var(--ink-secondary); border: 1px solid var(--line); border-radius: 4px; font-family: var(--font-sans); font-size: 12px; padding: 4px 6px; }
.actions { display: flex; gap: 6px; }
.btn { flex: 1; border: 1px solid var(--line-strong); border-radius: 4px; background: var(--ground-3); color: var(--ink-secondary); font-family: var(--font-mono); font-size: 11px; padding: 3px 0; cursor: pointer; }
.btn:disabled { cursor: not-allowed; color: var(--ink-whisper); }
.approve:not(:disabled) { border-color: var(--status-done); }
.revise:not(:disabled) { border-color: var(--status-blocked); }
.reject:not(:disabled) { border-color: var(--status-failed); }
</style>
```
- [ ] **Step 6: Run the unit and browser tests to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/gate_decision
npm run typecheck --workspace @kroker/ui
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- src/components/gate_decision
```

Expected: PASS — Vitest 3 tests; Playwright 2 tests; typecheck clean.
- [ ] **Step 7: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t8-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 gate_decision component

Approve / revise / reject with a comment for one pending gate. Revise
stays disabled while the comment is blank (a UI affordance only -- the
server accepts an empty revise, E76-OQ-4), and busy disables everything so
a decision in flight cannot be submitted twice.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/src/components/gate_decision/GateDecision.vue
git add interfaces/ui/src/components/gate_decision/gate_decision.md
git add interfaces/ui/src/components/gate_decision/gate_decision.profiles.ts
git add interfaces/ui/src/components/gate_decision/gate_decision.spec.ts
git add interfaces/ui/src/components/gate_decision/gate_decision.pw.ts
git add interfaces/ui/showcase/registry.ts
git commit -F .workspace/tmp/e76-t8-msg.txt
```
### Task 9: `node_palette` and `issue_list` components

**Files:**
- Create: `interfaces/ui/src/components/node_palette/NodePalette.vue`, `interfaces/ui/src/components/issue_list/IssueList.vue`, `interfaces/ui/src/components/node_palette/node_palette.md`, `interfaces/ui/src/components/node_palette/node_palette.profiles.ts`, `interfaces/ui/src/components/issue_list/issue_list.md`, `interfaces/ui/src/components/issue_list/issue_list.profiles.ts`
- Test: `interfaces/ui/src/components/node_palette/node_palette.spec.ts`, `interfaces/ui/src/components/node_palette/node_palette.pw.ts`, `interfaces/ui/src/components/issue_list/issue_list.spec.ts`, `interfaces/ui/src/components/issue_list/issue_list.pw.ts`
- Modify: `interfaces/ui/showcase/registry.ts`

**Interfaces:**
- Consumes: `defineProfiles` (`interfaces/ui/src/profile.ts`).
- Produces: `NodePalette.vue` — props `items: PaletteItem[] {type, kind, stage}`, `disabled?`; emits `pick(type)`; drag payload `application/x-kroker-node-type`. `IssueList.vue` — props `items: IssueItem[] {key, severity, message, targetLabel, focusKey}`; emits `focus(key)`.

- [ ] **Step 1: Write the clause contract and profiles**

`interfaces/ui/src/components/node_palette/node_palette.md` (create; 21 lines):

```markdown
# Node Palette Component

Lists the node types a draft graph may add, grouped by kind. The caller owns
the type catalog (served by the backend) and what adding a node means; the
component owns the list, its grouping, and the drag payload.

## Requirements

### NODE_PALETTE-1
A Node Palette renders one item per supplied type, grouped stages first then
gates, supplied order kept within a group; an empty list renders an empty
state, not an error. [FR-1205]

### NODE_PALETTE-2
Clicking an item emits `pick` with its type; dragging it carries the type as
`application/x-kroker-node-type`, the payload `graph_canvas` accepts on drop.
While `disabled`, neither happens. [FR-1205]

## Failure modes

A type with no canonical stage shows `unknown`, never a guessed stage.
```

`interfaces/ui/src/components/node_palette/node_palette.profiles.ts` (create; 28 lines):

```ts
import { defineProfiles } from '../../profile'
import NodePalette from './NodePalette.vue'

export default defineProfiles({
  component: 'node_palette',
  group: 'Graph',
  target: NodePalette,
  profiles: [
    {
      name: 'seed',
      summary: 'The seed catalog: six stages, three gates.',
      props: {
        items: [
          { type: 'architect', kind: 'stage', stage: 'architecture' },
          { type: 'clarify', kind: 'stage', stage: 'clarify' },
          { type: 'context', kind: 'stage', stage: 'context' },
          { type: 'gate.architecture', kind: 'gate', stage: 'architecture' },
          { type: 'gate.plan', kind: 'gate', stage: 'planning' },
          { type: 'gate.research', kind: 'gate', stage: 'research' },
          { type: 'intake', kind: 'stage', stage: 'intake' },
          { type: 'plan', kind: 'stage', stage: 'planning' },
          { type: 'research', kind: 'stage', stage: 'research' },
        ],
      },
    },
    { name: 'empty', summary: 'No catalog yet: an empty state.', props: { items: [] } },
  ],
})
```

`interfaces/ui/src/components/issue_list/issue_list.md` (create; 21 lines):

```markdown
# Issue List Component

Lists validation issues for a draft graph. The caller owns where issues come
from (the backend validator, never TypeScript), their order, and how an issue
maps onto a canvas element; the component owns the list and focus requests.

## Requirements

### ISSUE_LIST-1
An Issue List renders one row per supplied issue, in supplied order, each
carrying its severity as a stable class `cmp-issue-<severity>`; an empty list
renders "no issues". [FR-1205]

### ISSUE_LIST-2
An issue with a `focusKey` offers its target as a control that emits
`focus` with that key; a graph-level issue (`focusKey: null`) offers none.
[FR-1205]

## Failure modes

Severity and wording are the validator's; the component never reclassifies.
```

`interfaces/ui/src/components/issue_list/issue_list.profiles.ts` (create; 22 lines):

```ts
import { defineProfiles } from '../../profile'
import IssueList from './IssueList.vue'

export default defineProfiles({
  component: 'issue_list',
  group: 'Graph',
  target: IssueList,
  profiles: [
    { name: 'none', summary: 'A clean draft.', props: { items: [] } },
    {
      name: 'mixed',
      summary: 'An edge error, a node error and a graph-level warning.',
      props: {
        items: [
          { key: 'i0', severity: 'error', message: 'intake.ok (signal) cannot feed architect.requirements', targetLabel: 'intake.ok → architect.requirements', focusKey: 'e0' },
          { key: 'i1', severity: 'error', message: "node id 'intake' is used by 2 nodes", targetLabel: 'intake', focusKey: 'intake' },
          { key: 'i2', severity: 'warning', message: 'no path reaches every node', targetLabel: 'graph', focusKey: null },
        ],
      },
    },
  ],
})
```
- [ ] **Step 2: Write the failing tests**

`interfaces/ui/src/components/node_palette/node_palette.spec.ts` (create; 39 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NodePalette from './NodePalette.vue'

const items = [
  { type: 'gate.plan', kind: 'gate' as const, stage: 'planning' },
  { type: 'architect', kind: 'stage' as const, stage: 'architecture' },
  { type: 'mystery', kind: 'stage' as const, stage: null },
]

describe('NodePalette', () => {
  it('groups stages before gates, keeping supplied order', () => {  // clause: NODE_PALETTE-1
    const w = mount(NodePalette, { props: { items } })
    expect(w.findAll('[data-testid="palette-item"]').map((b) => b.attributes('data-type'))).toEqual(['architect', 'mystery', 'gate.plan'])
    expect(w.text()).toContain('unknown')
  })

  it('renders an empty state for no items', () => {  // clause: NODE_PALETTE-1
    const w = mount(NodePalette, { props: { items: [] } })
    expect(w.find('[data-testid="palette-empty"]').exists()).toBe(true)
  })

  it('emits pick with the type, unless disabled', async () => {  // clause: NODE_PALETTE-2
    const w = mount(NodePalette, { props: { items } })
    await w.find('[data-type="architect"]').trigger('click')
    expect(w.emitted('pick')).toEqual([['architect']])
    const off = mount(NodePalette, { props: { items, disabled: true } })
    await off.find('[data-type="architect"]').trigger('click')
    expect(off.emitted('pick')).toBeUndefined()
  })

  it('carries the type as the drag payload', async () => {  // clause: NODE_PALETTE-2
    const w = mount(NodePalette, { props: { items } })
    const data: Record<string, string> = {}
    const dataTransfer = { setData: (k: string, v: string) => { data[k] = v } }
    await w.find('[data-type="gate.plan"]').trigger('dragstart', { dataTransfer })
    expect(data).toEqual({ 'application/x-kroker-node-type': 'gate.plan' })
  })
})
```

`interfaces/ui/src/components/node_palette/node_palette.pw.ts` (create; 17 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-node_palette-${profile}`

test('stages render before gates, one item per type', async ({ page }) => {  // clause: NODE_PALETTE-1
  await page.goto('/')
  const items = page.locator(`${at('seed')} [data-testid="palette-item"]`)
  await expect(items).toHaveCount(9)
  await expect(items.nth(0)).toHaveAttribute('data-type', 'architect')
  await expect(items.nth(8)).toHaveAttribute('data-type', 'gate.research')
  await expect(page.locator(`${at('empty')} [data-testid="palette-empty"]`)).toBeVisible()
})

test('items are draggable buttons', async ({ page }) => {  // clause: NODE_PALETTE-2
  await page.goto('/')
  await expect(page.locator(`${at('seed')} [data-type="gate.plan"]`)).toHaveAttribute('draggable', 'true')
})
```

`interfaces/ui/src/components/issue_list/issue_list.spec.ts` (create; 27 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import IssueList from './IssueList.vue'

const items = [
  { key: 'a', severity: 'error' as const, message: 'bad edge', targetLabel: 'x → y', focusKey: 'e1' },
  { key: 'b', severity: 'warning' as const, message: 'unreachable', targetLabel: 'graph', focusKey: null },
]

describe('IssueList', () => {
  it('renders rows in order with severity classes', () => {  // clause: ISSUE_LIST-1
    const w = mount(IssueList, { props: { items } })
    const rows = w.findAll('[data-testid="issue"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].classes()).toContain('cmp-issue-error')
    expect(rows[1].classes()).toContain('cmp-issue-warning')
    expect(mount(IssueList, { props: { items: [] } }).find('[data-testid="issues-none"]').exists()).toBe(true)
  })

  it('emits focus for an element issue and offers no control for a graph issue', async () => {  // clause: ISSUE_LIST-2
    const w = mount(IssueList, { props: { items } })
    const rows = w.findAll('[data-testid="issue"]')
    await rows[0].find('button').trigger('click')
    expect(w.emitted('focus')).toEqual([['e1']])
    expect(rows[1].find('button').exists()).toBe(false)
  })
})
```

`interfaces/ui/src/components/issue_list/issue_list.pw.ts` (create; 19 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-issue_list-${profile}`

test('issues render in order with severity classes', async ({ page }) => {  // clause: ISSUE_LIST-1
  await page.goto('/')
  const rows = page.locator(`${at('mixed')} [data-testid="issue"]`)
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toHaveClass(/cmp-issue-error/)
  await expect(rows.nth(2)).toHaveClass(/cmp-issue-warning/)
  await expect(page.locator(`${at('none')} [data-testid="issues-none"]`)).toBeVisible()
})

test('a graph-level issue offers no focus control', async ({ page }) => {  // clause: ISSUE_LIST-2
  await page.goto('/')
  const rows = page.locator(`${at('mixed')} [data-testid="issue"]`)
  await expect(rows.nth(0).locator('button')).toHaveCount(1)
  await expect(rows.nth(2).locator('button')).toHaveCount(0)
})
```
- [ ] **Step 3: Register the profiles in the showcase**

In `interfaces/ui/showcase/registry.ts`, add the import(s) after the last existing profile import:

```ts
import nodePalette from '../src/components/node_palette/node_palette.profiles'
import issueList from '../src/components/issue_list/issue_list.profiles'
```

and append `nodePalette, issueList` to the end of the `REGISTRY` array (keep existing order).
- [ ] **Step 4: Run the unit tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/node_palette src/components/issue_list
```

Expected: FAIL — the spec files cannot resolve the component module(s) (the profiles also import them, so the showcase build fails until Step 5).
- [ ] **Step 5: Write the implementation**

`interfaces/ui/src/components/node_palette/NodePalette.vue` (create; 64 lines):

```vue
<script setup lang="ts">
import { computed } from 'vue'

export interface PaletteItem {
  type: string
  kind: 'stage' | 'gate'
  stage: string | null
}

const props = withDefaults(defineProps<{ items: PaletteItem[]; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ (e: 'pick', type: string): void }>()

// Supplied order within each kind (the catalog serves types sorted).
const groups = computed(() =>
  (['stage', 'gate'] as const)
    .map((kind) => ({ kind, items: props.items.filter((i) => i.kind === kind) }))
    .filter((g) => g.items.length > 0),
)

function onDragStart(ev: DragEvent, type: string) {
  if (props.disabled) {
    ev.preventDefault()
    return
  }
  ev.dataTransfer?.setData('application/x-kroker-node-type', type)
}

function onPick(type: string) {
  if (!props.disabled) emit('pick', type)
}
</script>

<template>
  <aside class="cmp-node-palette" data-testid="node-palette">
    <p v-if="groups.length === 0" class="empty" data-testid="palette-empty">no node types</p>
    <section v-for="g in groups" :key="g.kind">
      <h4 class="group">{{ g.kind === 'stage' ? 'STAGES' : 'GATES' }}</h4>
      <button
        v-for="item in g.items"
        :key="item.type"
        class="item"
        data-testid="palette-item"
        :data-type="item.type"
        :disabled="disabled"
        draggable="true"
        @dragstart="onDragStart($event, item.type)"
        @click="onPick(item.type)"
      >
        <span class="type">{{ item.type }}</span>
        <span class="stage">{{ item.stage ?? 'unknown' }}</span>
      </button>
    </section>
  </aside>
</template>

<style scoped>
.cmp-node-palette { display: flex; flex-direction: column; gap: 10px; padding: 10px; width: 180px; background: var(--ground-2); border-right: 1px solid var(--line); overflow: auto; }
.empty { color: var(--ink-subtle); font-size: 12px; }
.group { margin: 0 0 4px; color: var(--ink-faint); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; }
.item { display: flex; flex-direction: column; align-items: flex-start; width: 100%; margin-bottom: 4px; padding: 4px 6px; background: var(--ground-3); border: 1px solid var(--line); border-radius: 4px; color: var(--ink-secondary); cursor: grab; }
.item:disabled { cursor: not-allowed; color: var(--ink-whisper); }
.type { font-family: var(--font-mono); font-size: 12px; }
.stage { color: var(--ink-subtle); font-size: 10px; }
</style>
```

`interfaces/ui/src/components/issue_list/IssueList.vue` (create; 43 lines):

```vue
<script setup lang="ts">
export interface IssueItem {
  key: string
  severity: 'error' | 'warning'
  message: string
  targetLabel: string
  /** Canvas key to focus; null for a graph-level issue. */
  focusKey: string | null
}

defineProps<{ items: IssueItem[] }>()
const emit = defineEmits<{ (e: 'focus', key: string): void }>()
</script>

<template>
  <div class="cmp-issue-list" data-testid="issue-list">
    <p v-if="items.length === 0" class="none" data-testid="issues-none">no issues</p>
    <ul v-else>
      <li
        v-for="item in items"
        :key="item.key"
        class="issue"
        :class="`cmp-issue-${item.severity}`"
        data-testid="issue"
      >
        <button v-if="item.focusKey" class="target" @click="emit('focus', item.focusKey)">{{ item.targetLabel }}</button>
        <span v-else class="target graph">{{ item.targetLabel }}</span>
        <span class="message">{{ item.message }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cmp-issue-list { padding: 8px 10px; background: var(--ground-2); border-top: 1px solid var(--line); font-size: 12px; overflow: auto; }
.none { margin: 0; color: var(--ink-subtle); }
ul { margin: 0; padding: 0; list-style: none; }
.issue { display: flex; gap: 8px; padding: 2px 0; color: var(--ink-secondary); }
.target { background: none; border: none; padding: 0; color: var(--link); font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.target.graph { color: var(--ink-faint); cursor: default; }
.cmp-issue-error .message { color: var(--status-failed); }
.cmp-issue-warning .message { color: var(--status-blocked); }
</style>
```
- [ ] **Step 6: Run the unit and browser tests to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/node_palette src/components/issue_list
npm run typecheck --workspace @kroker/ui
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- src/components/node_palette src/components/issue_list
```

Expected: PASS — Vitest 6 tests; Playwright 4 tests; typecheck clean.
- [ ] **Step 7: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t9-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 node_palette and issue_list components

The palette lists node types grouped stages-then-gates and carries the
type as the drag payload graph_canvas accepts; the issue list renders
validator issues in supplied order with severity classes and focus
requests. Neither classifies or orders anything itself.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/src/components/node_palette/NodePalette.vue
git add interfaces/ui/src/components/issue_list/IssueList.vue
git add interfaces/ui/src/components/node_palette/node_palette.md
git add interfaces/ui/src/components/node_palette/node_palette.profiles.ts
git add interfaces/ui/src/components/issue_list/issue_list.md
git add interfaces/ui/src/components/issue_list/issue_list.profiles.ts
git add interfaces/ui/src/components/node_palette/node_palette.spec.ts
git add interfaces/ui/src/components/node_palette/node_palette.pw.ts
git add interfaces/ui/src/components/issue_list/issue_list.spec.ts
git add interfaces/ui/src/components/issue_list/issue_list.pw.ts
git add interfaces/ui/showcase/registry.ts
git commit -F .workspace/tmp/e76-t9-msg.txt
```
### Task 10: `yaml_pane` component

**Files:**
- Create: `interfaces/ui/src/components/yaml_pane/YamlPane.vue`, `interfaces/ui/src/components/yaml_pane/yaml_pane.md`, `interfaces/ui/src/components/yaml_pane/yaml_pane.profiles.ts`
- Test: `interfaces/ui/src/components/yaml_pane/yaml_pane.spec.ts`, `interfaces/ui/src/components/yaml_pane/yaml_pane.pw.ts`
- Modify: `interfaces/ui/showcase/registry.ts`

**Interfaces:**
- Consumes: `defineProfiles` (`interfaces/ui/src/profile.ts`).
- Produces: `YamlPane.vue` — props `text`, `errors?: YamlPaneError[] {path, message, line, column}`, `dirty?`, `busy?`, `maxBytes?`; emits `update:text(text)`, `apply()`.

- [ ] **Step 1: Write the clause contract and profiles**

`interfaces/ui/src/components/yaml_pane/yaml_pane.md` (create; 30 lines):

```markdown
# YAML Pane Component

A text view of a draft graph's YAML with its shape errors. The caller owns
the text's origin (server `serialize`), what applying it means (server
`parse`), the errors, and the dirty state; the component owns the editor, the
canonical-form notice, the byte-cap refusal, and the error list.

## Requirements

### YAML_PANE-1
A YAML Pane emits `update:text` on every edit and `apply` only when the text
is dirty, not busy, and within `maxBytes` UTF-8 bytes. [FR-1205]

### YAML_PANE-2
Each supplied error renders as a row showing its line (and column) when
present, its document path when present, and its message; no errors, no
list. [FR-1205]

### YAML_PANE-3
The pane states that its text is canonical: comments, key order and default
values are not kept across canvas edits (E-76 spec §8.5). [FR-1205]

### YAML_PANE-4
Text above `maxBytes` UTF-8 bytes shows its size against the cap and cannot
be applied; the size counts bytes, not characters. [FR-1205]

## Failure modes

The component never parses YAML: a text that fails the shape parse is the
caller's `errors`, returned by the server.
```

`interfaces/ui/src/components/yaml_pane/yaml_pane.profiles.ts` (create; 27 lines):

```ts
import { defineProfiles } from '../../profile'
import YamlPane from './YamlPane.vue'

const TEXT = 'schema_version: 1\nnodes:\n- id: intake\n  type: intake\nedges: []\n'

export default defineProfiles({
  component: 'yaml_pane',
  group: 'Graph',
  target: YamlPane,
  profiles: [
    { name: 'clean', summary: 'Canonical text, nothing to apply.', props: { text: TEXT } },
    {
      name: 'shape-errors',
      summary: 'Text that failed the shape parse, with a YAML error and a model error.',
      props: {
        text: 'schema_version: 1\nnodes: [\n',
        dirty: true,
        errors: [
          { path: '', message: "graph text is not valid YAML: expected the node content, but found '<stream end>'", line: 3, column: 1 },
          { path: 'nodes[0].id', message: "String should match pattern '^[a-z][a-z0-9_]*$'", line: null, column: null },
        ],
      },
    },
    { name: 'dirty', summary: 'Edited text ready to apply.', props: { text: TEXT, dirty: true } },
    { name: 'too-large', summary: 'Text over the byte cap cannot be applied.', props: { text: TEXT, dirty: true, maxBytes: 16 } },
  ],
})
```
- [ ] **Step 2: Write the failing tests**

`interfaces/ui/src/components/yaml_pane/yaml_pane.spec.ts` (create; 47 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import YamlPane from './YamlPane.vue'

describe('YamlPane', () => {
  it('emits update:text on edit and apply only when dirty and not busy', async () => {  // clause: YAML_PANE-1
    const w = mount(YamlPane, { props: { text: 'a' } })
    await w.find('[data-testid="yaml-text"]').setValue('b')
    expect(w.emitted('update:text')).toEqual([['b']])
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ dirty: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
    await w.setProps({ busy: true })
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toHaveLength(1)
  })

  it('renders error rows with line, path and message', () => {  // clause: YAML_PANE-2
    const w = mount(YamlPane, {
      props: {
        text: 'x',
        errors: [
          { path: '', message: 'bad yaml', line: 3, column: 1 },
          { path: 'nodes[0].id', message: 'bad id', line: null, column: null },
        ],
      },
    })
    const rows = w.findAll('[data-testid="yaml-error"]')
    expect(rows.map((r) => r.text())).toEqual(['line 3:1bad yaml', 'nodes[0].idbad id'])
    expect(mount(YamlPane, { props: { text: 'x' } }).find('[data-testid="yaml-errors"]').exists()).toBe(false)
  })

  it('states that the text is canonical', () => {  // clause: YAML_PANE-3
    expect(mount(YamlPane, { props: { text: '' } }).text()).toContain('comments, key order and default values are not kept')
  })

  it('counts UTF-8 bytes against the cap', async () => {  // clause: YAML_PANE-4
    const w = mount(YamlPane, { props: { text: 'éé', dirty: true, maxBytes: 3 } })
    expect(w.find('[data-testid="yaml-too-large"]').text()).toContain('4 bytes exceeds 3')
    await w.find('[data-testid="yaml-apply"]').trigger('click')
    expect(w.emitted('apply')).toBeUndefined()
    await w.setProps({ maxBytes: 4 })
    expect(w.find('[data-testid="yaml-too-large"]').exists()).toBe(false)
  })
})
```

`interfaces/ui/src/components/yaml_pane/yaml_pane.pw.ts` (create; 18 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-yaml_pane-${profile}`

test('shape errors render with their locations', async ({ page }) => {  // clause: YAML_PANE-2
  await page.goto('/')
  const rows = page.locator(`${at('shape-errors')} [data-testid="yaml-error"]`)
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('line 3:1')
  await expect(rows.nth(1)).toContainText('nodes[0].id')
})

test('over-cap text cannot be applied', async ({ page }) => {  // clause: YAML_PANE-4
  await page.goto('/')
  await expect(page.locator(`${at('too-large')} [data-testid="yaml-too-large"]`)).toBeVisible()
  await expect(page.locator(`${at('too-large')} [data-testid="yaml-apply"]`)).toBeDisabled()
  await expect(page.locator(`${at('dirty')} [data-testid="yaml-apply"]`)).toBeEnabled()
})
```
- [ ] **Step 3: Register the profiles in the showcase**

In `interfaces/ui/showcase/registry.ts`, add the import(s) after the last existing profile import:

```ts
import yamlPane from '../src/components/yaml_pane/yaml_pane.profiles'
```

and append `yamlPane` to the end of the `REGISTRY` array (keep existing order).
- [ ] **Step 4: Run the unit tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/yaml_pane
```

Expected: FAIL — the spec files cannot resolve the component module(s) (the profiles also import them, so the showcase build fails until Step 5).
- [ ] **Step 5: Write the implementation**

`interfaces/ui/src/components/yaml_pane/YamlPane.vue` (create; 79 lines):

```vue
<script setup lang="ts">
import { computed } from 'vue'

export interface YamlPaneError {
  /** A readable path into the document, e.g. "nodes[3].id"; '' for the whole text. */
  path: string
  message: string
  line: number | null
  column: number | null
}

const props = withDefaults(
  defineProps<{
    text: string
    errors?: YamlPaneError[]
    dirty?: boolean
    busy?: boolean
    /** Refuse to apply above this many UTF-8 bytes (the server's cap). */
    maxBytes?: number | null
  }>(),
  { errors: () => [], dirty: false, busy: false, maxBytes: null },
)

const emit = defineEmits<{
  (e: 'update:text', text: string): void
  (e: 'apply'): void
}>()

const bytes = computed(() => new TextEncoder().encode(props.text).length)
const tooLarge = computed(() => props.maxBytes !== null && bytes.value > props.maxBytes)
const applyDisabled = computed(() => props.busy || !props.dirty || tooLarge.value)

function onInput(ev: Event) {
  emit('update:text', (ev.target as HTMLTextAreaElement).value)
}
function onApply() {
  if (!applyDisabled.value) emit('apply')
}
const where = (e: YamlPaneError) =>
  [e.line !== null ? `line ${e.line}${e.column !== null ? `:${e.column}` : ''}` : '', e.path].filter(Boolean).join(' · ')
</script>

<template>
  <section class="cmp-yaml-pane" data-testid="yaml-pane">
    <header class="bar">
      <span class="notice">canonical YAML — comments, key order and default values are not kept across canvas edits</span>
      <span v-if="tooLarge" class="too-large" data-testid="yaml-too-large">{{ bytes }} bytes exceeds {{ maxBytes }}</span>
      <button class="apply" data-testid="yaml-apply" :disabled="applyDisabled" @click="onApply">apply</button>
    </header>
    <textarea
      class="text"
      data-testid="yaml-text"
      spellcheck="false"
      :value="text"
      :readonly="busy"
      @input="onInput"
    />
    <ul v-if="errors.length" class="errors" data-testid="yaml-errors">
      <li v-for="(e, i) in errors" :key="i" class="error" data-testid="yaml-error">
        <span v-if="where(e)" class="where">{{ where(e) }}</span>
        <span class="message">{{ e.message }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cmp-yaml-pane { display: flex; flex-direction: column; height: 100%; background: var(--ground-2); }
.bar { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-bottom: 1px solid var(--line); }
.notice { flex: 1; color: var(--ink-subtle); font-size: 11px; }
.too-large { color: var(--status-failed); font-family: var(--font-mono); font-size: 11px; }
.apply { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 4px; padding: 3px 12px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.apply:disabled { background: var(--ground-4); color: var(--ink-whisper); cursor: not-allowed; }
.text { flex: 1; min-height: 240px; resize: none; border: none; padding: 10px; background: var(--ground-1); color: var(--ink-secondary); font-family: var(--font-mono); font-size: 12px; line-height: 1.5; outline: none; }
.errors { margin: 0; padding: 6px 10px; list-style: none; border-top: 1px solid var(--line); max-height: 30%; overflow: auto; }
.error { display: flex; gap: 8px; padding: 2px 0; font-size: 12px; }
.where { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; white-space: nowrap; }
.message { color: var(--status-failed); white-space: pre-wrap; }
</style>
```
- [ ] **Step 6: Run the unit and browser tests to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/yaml_pane
npm run typecheck --workspace @kroker/ui
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- src/components/yaml_pane
```

Expected: PASS — Vitest 4 tests; Playwright 2 tests; typecheck clean.
- [ ] **Step 7: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t10-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 yaml_pane component

The canonical-YAML view of a draft: edits emit update:text, apply is
allowed only when dirty, idle and within the UTF-8 byte cap, shape errors
render with line, path and message, and the header states that comments,
key order and defaults are not kept across canvas edits. It never parses.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/src/components/yaml_pane/YamlPane.vue
git add interfaces/ui/src/components/yaml_pane/yaml_pane.md
git add interfaces/ui/src/components/yaml_pane/yaml_pane.profiles.ts
git add interfaces/ui/src/components/yaml_pane/yaml_pane.spec.ts
git add interfaces/ui/src/components/yaml_pane/yaml_pane.pw.ts
git add interfaces/ui/showcase/registry.ts
git commit -F .workspace/tmp/e76-t10-msg.txt
```
### Task 11: `schema_form` component

**Files:**
- Create: `interfaces/ui/src/components/schema_form/schema.ts`, `interfaces/ui/src/components/schema_form/SchemaField.vue`, `interfaces/ui/src/components/schema_form/SchemaForm.vue`, `interfaces/ui/src/components/schema_form/schema_form.md`, `interfaces/ui/src/components/schema_form/schema_form.profiles.ts`
- Test: `interfaces/ui/src/components/schema_form/schema.spec.ts`, `interfaces/ui/src/components/schema_form/schema_form.spec.ts`, `interfaces/ui/src/components/schema_form/schema_form.pw.ts`
- Modify: `interfaces/ui/showcase/registry.ts`

**Interfaces:**
- Consumes: `defineProfiles` (`interfaces/ui/src/profile.ts`).
- Produces: `schema.ts` — `Schema`, `Field`, `resolveRef`, `classify(schema, defs)`, `fullySupported(field)`, `Path`, `getPath`, `setPath(value, path, next, base)`. `SchemaForm.vue` — props `schema`, `value`, `errors?: SchemaFormError[] {path, msg}`, `readonly?`, `readonlyPaths?`; emits `update(value)`.

- [ ] **Step 1: Write the clause contract and profiles**

`interfaces/ui/src/components/schema_form/schema_form.md` (create; 42 lines):

```markdown
# Schema Form Component

A generic form over a JSON Schema document. The caller owns the schema
(served by the backend from pydantic `model_json_schema()`), the value, the
errors, and what applying an edit means; the component owns rendering each
schema construct as a control and the touched-fields-only value it emits.
No Kroker field name appears in the component (E-76 spec U8).

## Requirements

### SCHEMA_FORM-1
A Schema Form renders one control per property of the root object schema, in
schema order, recursing into nested objects as fieldsets. [FR-1205]

### SCHEMA_FORM-2
`string`, `number`/`integer`, `boolean`, string `enum`, arrays of strings,
nested objects, the nullable `anyOf: [X, {type: null}]` pattern and local
`$ref` into `$defs` render as native controls; any other construct renders a
JSON snippet field, parsed with `JSON.parse`, whose invalid text stays local
and emits nothing. [FR-1205]

### SCHEMA_FORM-3
A nullable `anyOf` and a `$ref` enum render as native controls, not the
fallback; against the backend's recorded catalog, no `RoleConfig` or
`GateConfig` property renders the fallback (pinned in the dashboard tier, the
only tier that may import the recording). [FR-1205]

### SCHEMA_FORM-4
An untouched field is never written: rendering does not materialize a
default; setting one field under an absent object creates that object with
that field only; clearing a field removes its key, and an object emptied that
way is removed unless the supplied value already held it. [FR-1205]

### SCHEMA_FORM-5
Each supplied error renders beside the control at its dot path; an error at
path `''` renders at the top of the form. `readonly` and `readonlyPaths`
suppress edits. [FR-1205]

## Failure modes

The form never validates a value: bounds and patterns in the schema are
hints; shape errors come back from the server as `errors`.
```

`interfaces/ui/src/components/schema_form/schema_form.profiles.ts` (create; 43 lines):

```ts
import { defineProfiles } from '../../profile'
import SchemaForm from './SchemaForm.vue'

// A generic JSON Schema fixture in the shapes pydantic emits. Deliberately
// NOT a Kroker model: the recorded GraphNode schema is exercised in the
// dashboard tier (SCHEMA_FORM-3), which may import backend recordings.
const defs = {
  Level: { enum: ['low', 'medium', 'high'], title: 'Level', type: 'string' },
  Settings: {
    type: 'object',
    properties: {
      level: { $ref: '#/$defs/Level', default: 'low' },
      ratio: { type: 'number', minimum: 0, maximum: 1, default: 0.5, title: 'Ratio' },
      retries: { anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }], default: null },
      enabled: { type: 'boolean', default: false },
      tags: { type: 'array', items: { type: 'string' } },
    },
  },
}

const schema = {
  $defs: defs,
  type: 'object',
  required: ['id'],
  properties: {
    id: { type: 'string', pattern: '^[a-z][a-z0-9_]*$' },
    kind: { type: 'string' },
    settings: { anyOf: [{ $ref: '#/$defs/Settings' }, { type: 'null' }], default: null },
    note: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null },
  },
}

export default defineProfiles({
  component: 'schema_form',
  group: 'Graph',
  target: SchemaForm,
  profiles: [
    { name: 'object-with-defs', summary: 'A nested nullable $ref object with enum, bounds and arrays.', props: { schema, value: { id: 'alpha', kind: 'demo', settings: { level: 'high' } }, readonlyPaths: ['kind'] } },
    { name: 'absent-object', summary: 'A nullable object not yet set: placeholders show defaults, nothing is written.', props: { schema, value: { id: 'beta', kind: 'demo' } } },
    { name: 'with-errors', summary: 'Server shape errors beside their fields and at the top.', props: { schema, value: { id: 'Bad', kind: 'demo' }, errors: [{ path: 'id', msg: "String should match pattern '^[a-z][a-z0-9_]*$'" }, { path: '', msg: 'the graph changed — apply again' }] } },
    { name: 'unsupported-fallback', summary: 'A construct outside the subset renders a JSON snippet.', props: { schema: { type: 'object', properties: { matrix: { type: 'array', items: { type: 'array', items: { type: 'integer' } } } } }, value: { matrix: [[1, 2]] } } },
  ],
})
```
- [ ] **Step 2: Write the failing tests**

`interfaces/ui/src/components/schema_form/schema.spec.ts` (create; 84 lines):

```ts
import { describe, it, expect } from 'vitest'
import { classify, fullySupported, getPath, resolveRef, setPath, type Schema } from './schema'

// Shapes pydantic v2 emits (verified against GraphNode.model_json_schema()).
const defs: Record<string, Schema> = {
  Policy: { enum: ['hard', 'soft', 'off'], type: 'string', title: 'Policy' },
  Cfg: {
    type: 'object',
    properties: {
      policy: { $ref: '#/$defs/Policy', default: 'hard' },
      threshold: { type: 'number', minimum: 0, maximum: 1, default: 0.8 },
      remind: { anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }], default: null },
      kind: { enum: ['a', 'b'], type: 'string', default: 'a' },
      flag: { type: 'boolean' },
      args: { type: 'array', items: { type: 'string' } },
      harness: { anyOf: [{ $ref: '#/$defs/Policy' }, { type: 'null' }], default: null },
    },
  },
}

describe('classify', () => {
  it('resolves a $ref enum with its sibling default', () => {
    expect(classify({ $ref: '#/$defs/Policy', default: 'hard' }, defs)).toMatchObject({ kind: 'enum', values: ['hard', 'soft', 'off'], default: 'hard', nullable: false })
  })

  it('reads the nullable anyOf pattern, including a nullable $ref', () => {
    expect(classify({ anyOf: [{ type: 'integer', exclusiveMinimum: 0 }, { type: 'null' }] }, defs)).toMatchObject({ kind: 'integer', nullable: true, exclusiveMinimum: 0 })
    expect(classify({ anyOf: [{ $ref: '#/$defs/Policy' }, { type: 'null' }] }, defs)).toMatchObject({ kind: 'enum', nullable: true })
  })

  it('classifies a nested object and every supported leaf', () => {
    const f = classify({ anyOf: [{ $ref: '#/$defs/Cfg' }, { type: 'null' }] }, defs)
    expect(f.kind).toBe('object')
    expect(fullySupported(f)).toBe(true)
    if (f.kind === 'object') {
      expect(f.properties.map((p) => [p.name, p.field.kind])).toEqual([
        ['policy', 'enum'], ['threshold', 'number'], ['remind', 'integer'], ['kind', 'enum'],
        ['flag', 'boolean'], ['args', 'string-array'], ['harness', 'enum'],
      ])
    }
  })

  it('marks anything else unsupported', () => {
    expect(classify({ type: 'array', items: { type: 'integer' } }, defs).kind).toBe('unsupported')
    expect(classify({ anyOf: [{ type: 'string' }, { type: 'integer' }] }, defs).kind).toBe('unsupported')
    expect(classify({ $ref: '#/$defs/Missing' }, defs).kind).toBe('unsupported')
    expect(fullySupported(classify({ type: 'object', properties: { x: { oneOf: [] } } }, defs))).toBe(false)
  })

  it('does not loop on a recursive $ref', () => {
    const loop = { Node: { type: 'object', properties: { next: { $ref: '#/$defs/Node' } } } }
    expect(() => classify({ $ref: '#/$defs/Node' }, loop)).not.toThrow()
  })

  it('keeps sibling keys over the referenced schema', () => {
    expect(resolveRef({ $ref: '#/$defs/Policy', default: 'soft' }, defs)).toMatchObject({ enum: ['hard', 'soft', 'off'], default: 'soft' })
  })
})

describe('setPath', () => {
  it('writes only the touched path', () => {
    const base = { id: 'plan', gate: {} }
    expect(setPath(base, ['gate', 'policy'], 'soft', base)).toEqual({ id: 'plan', gate: { policy: 'soft' } })
    expect(setPath({ id: 'x' }, ['gate', 'policy'], 'soft', { id: 'x' })).toEqual({ id: 'x', gate: { policy: 'soft' } })
  })

  it('removes a cleared key and an object the user created, but keeps an authored empty object', () => {
    const created = setPath({ id: 'x' }, ['role', 'model'], 'm', { id: 'x' })
    expect(setPath(created, ['role', 'model'], undefined, { id: 'x' })).toEqual({ id: 'x' })
    const authored = { id: 'plan', gate: { policy: 'soft' } }
    expect(setPath(authored, ['gate', 'policy'], undefined, { id: 'plan', gate: {} })).toEqual({ id: 'plan', gate: {} })
  })

  it('never mutates its input', () => {
    const v = { id: 'x', gate: { policy: 'hard' } }
    setPath(v, ['gate', 'policy'], 'soft', v)
    expect(v.gate.policy).toBe('hard')
  })

  it('reads nested paths', () => {
    expect(getPath({ a: { b: [1, 2] } }, ['a', 'b', 1])).toBe(2)
    expect(getPath({ a: 1 }, ['a', 'b'])).toBeUndefined()
  })
})
```

`interfaces/ui/src/components/schema_form/schema_form.spec.ts` (create; 55 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from './SchemaForm.vue'
import profiles from './schema_form.profiles'

const byName = (name: string) => profiles.profiles.find((p) => p.name === name)!.props as Record<string, unknown>
const lastUpdate = (w: ReturnType<typeof mount>) => { const all = w.emitted('update')!; return all[all.length - 1] }
const kinds = (w: ReturnType<typeof mount>) =>
  Object.fromEntries(w.findAll('[data-testid="schema-field"]').map((f) => [f.attributes('data-path'), f.attributes('data-kind')]))

describe('SchemaForm', () => {
  it('renders one control per property, recursing into objects', () => {  // clause: SCHEMA_FORM-1
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(Object.keys(kinds(w))).toEqual(['id', 'kind', 'settings.level', 'settings.ratio', 'settings.retries', 'settings.enabled', 'settings.tags', 'note'])
    expect(w.find('fieldset[data-path="settings"]').exists()).toBe(true)
  })

  it('renders every supported construct natively and the rest as a JSON snippet', async () => {  // clause: SCHEMA_FORM-2
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(kinds(w)).toMatchObject({ id: 'string', 'settings.level': 'enum', 'settings.ratio': 'number', 'settings.retries': 'integer', 'settings.enabled': 'boolean', 'settings.tags': 'string-array', note: 'string' })
    const fb = mount(SchemaForm, { props: byName('unsupported-fallback') as never })
    const snippet = fb.find('[data-testid="schema-fallback"]')
    expect(snippet.exists()).toBe(true)
    await snippet.setValue('{not json')
    await snippet.trigger('blur')
    expect(fb.emitted('update')).toBeUndefined()
    await snippet.setValue('[[3]]')
    await snippet.trigger('blur')
    expect(fb.emitted('update')).toEqual([[{ matrix: [[3]] }]])
  })

  it('renders a nullable anyOf and a $ref enum natively', () => {  // clause: SCHEMA_FORM-3
    const w = mount(SchemaForm, { props: byName('object-with-defs') as never })
    expect(w.find('[data-path="settings.retries"]').attributes('data-kind')).toBe('integer')
    expect(w.find('[data-path="settings.level"] select').exists()).toBe(true)
  })

  it('writes only touched fields and prunes an object it created', async () => {  // clause: SCHEMA_FORM-4
    const w = mount(SchemaForm, { props: byName('absent-object') as never })
    expect(w.emitted('update')).toBeUndefined()
    await w.find('[data-path="settings.level"] select').setValue('high')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo', settings: { level: 'high' } }])
    await w.find('[data-path="settings.level"] select').setValue('')
    expect(lastUpdate(w)).toEqual([{ id: 'beta', kind: 'demo' }])
  })

  it('shows errors by path and at the top, and honours read-only paths', async () => {  // clause: SCHEMA_FORM-5
    const w = mount(SchemaForm, { props: byName('with-errors') as never })
    expect(w.find('[data-testid="form-error"]').text()).toContain('apply again')
    expect(w.find('[data-path="id"] [data-testid="field-error"]').text()).toContain('pattern')
    const ro = mount(SchemaForm, { props: byName('object-with-defs') as never })
    await ro.find('[data-path="kind"] textarea').setValue('changed')
    expect(ro.emitted('update')).toBeUndefined()
  })
})
```

`interfaces/ui/src/components/schema_form/schema_form.pw.ts` (create; 19 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-schema_form-${profile}`

test('supported constructs render native controls; others a JSON snippet', async ({ page }) => {  // clause: SCHEMA_FORM-2
  await page.goto('/')
  const form = page.locator(at('object-with-defs'))
  await expect(form.locator('[data-path="settings.level"] select')).toHaveCount(1)
  await expect(form.locator('[data-path="settings.ratio"] input[type="number"]')).toHaveCount(1)
  await expect(form.locator('[data-path="settings.enabled"] input[type="checkbox"]')).toHaveCount(1)
  await expect(form.locator('[data-testid="schema-fallback"]')).toHaveCount(0)
  await expect(page.locator(`${at('unsupported-fallback')} [data-testid="schema-fallback"]`)).toHaveCount(1)
})

test('errors render beside their field and at the top', async ({ page }) => {  // clause: SCHEMA_FORM-5
  await page.goto('/')
  await expect(page.locator(`${at('with-errors')} [data-testid="form-error"]`)).toContainText('apply again')
  await expect(page.locator(`${at('with-errors')} [data-path="id"] [data-testid="field-error"]`)).toBeVisible()
})
```
- [ ] **Step 3: Register the profiles in the showcase**

In `interfaces/ui/showcase/registry.ts`, add the import(s) after the last existing profile import:

```ts
import schemaForm from '../src/components/schema_form/schema_form.profiles'
```

and append `schemaForm` to the end of the `REGISTRY` array (keep existing order).
- [ ] **Step 4: Run the unit tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/schema_form
```

Expected: FAIL — the spec files cannot resolve the component module(s) (the profiles also import them, so the showcase build fails until Step 5).
- [ ] **Step 5: Write the implementation**

`interfaces/ui/src/components/schema_form/schema.ts` (create; 138 lines):

```ts
// The JSON Schema subset schema_form renders natively (E-76 spec §8.3):
// string, number/integer (with bounds), boolean, enum, a nullable
// anyOf [X, {type: null}], arrays of strings, nested objects, and local
// $ref -> $defs. Anything else is `unsupported` and renders a JSON snippet.
// This module knows JSON Schema, never a Kroker model: no field name of
// RoleConfig or GateConfig appears in TypeScript.

export type Schema = Record<string, unknown>

export type Field =
  | { kind: 'string'; nullable: boolean; pattern?: string; default?: unknown; title?: string }
  | { kind: 'number' | 'integer'; nullable: boolean; minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number; default?: unknown; title?: string }
  | { kind: 'boolean'; nullable: boolean; default?: unknown; title?: string }
  | { kind: 'enum'; nullable: boolean; values: string[]; default?: unknown; title?: string }
  | { kind: 'string-array'; nullable: boolean; default?: unknown; title?: string }
  | { kind: 'object'; nullable: boolean; properties: { name: string; field: Field; required: boolean }[]; title?: string }
  | { kind: 'unsupported'; nullable: boolean; schema: Schema; title?: string }

const isObj = (v: unknown): v is Schema => v !== null && typeof v === 'object' && !Array.isArray(v)

export function resolveRef(schema: Schema, defs: Record<string, Schema>): Schema {
  const ref = schema.$ref
  if (typeof ref !== 'string') return schema
  const match = /^#\/\$defs\/(.+)$/.exec(ref)
  const target = match ? defs[match[1]] : undefined
  if (!target) return { __unresolved: ref }
  // Sibling keys next to a $ref (pydantic puts `default` there) win.
  const { $ref: _ref, ...siblings } = schema
  return { ...resolveRef(target, defs), ...siblings }
}

export function classify(input: Schema, defs: Record<string, Schema>, seen: string[] = []): Field {
  const meta = { default: input.default, title: typeof input.title === 'string' ? input.title : undefined }
  if (typeof input.$ref === 'string') {
    if (seen.includes(input.$ref)) return { kind: 'unsupported', nullable: false, schema: input, ...meta }
    const resolved = resolveRef(input, defs)
    return classify(resolved, defs, [...seen, input.$ref as string])
  }
  if (Array.isArray(input.anyOf)) {
    const branches = input.anyOf.filter(isObj)
    const nulls = branches.filter((b) => b.type === 'null')
    const rest = branches.filter((b) => b.type !== 'null')
    if (branches.length === input.anyOf.length && nulls.length === 1 && rest.length === 1) {
      const inner = classify(rest[0], defs, seen)
      if (inner.kind !== 'unsupported') return { ...inner, nullable: true, ...defined(meta) } as Field
    }
    return { kind: 'unsupported', nullable: false, schema: input, ...meta }
  }
  if (Array.isArray(input.enum) && input.enum.every((v) => typeof v === 'string')) {
    return { kind: 'enum', nullable: false, values: input.enum as string[], ...meta }
  }
  switch (input.type) {
    case 'string':
      return { kind: 'string', nullable: false, pattern: typeof input.pattern === 'string' ? input.pattern : undefined, ...meta }
    case 'number':
    case 'integer':
      return {
        kind: input.type, nullable: false, ...meta,
        ...pickNumbers(input, ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum']),
      }
    case 'boolean':
      return { kind: 'boolean', nullable: false, ...meta }
    case 'array':
      return isObj(input.items) && input.items.type === 'string'
        ? { kind: 'string-array', nullable: false, ...meta }
        : { kind: 'unsupported', nullable: false, schema: input, ...meta }
    case 'object': {
      const props = isObj(input.properties) ? input.properties : {}
      const required = Array.isArray(input.required) ? (input.required as string[]) : []
      return {
        kind: 'object', nullable: false, title: meta.title,
        properties: Object.entries(props).filter(([, s]) => isObj(s)).map(([name, s]) => ({
          name, field: classify(s as Schema, defs, seen), required: required.includes(name),
        })),
      }
    }
    default:
      return { kind: 'unsupported', nullable: false, schema: input, ...meta }
  }
}

function defined(meta: { default: unknown; title?: string }) {
  return Object.fromEntries(Object.entries(meta).filter(([, v]) => v !== undefined))
}

function pickNumbers(s: Schema, keys: string[]): Record<string, number> {
  return Object.fromEntries(keys.filter((k) => typeof s[k] === 'number').map((k) => [k, s[k] as number]))
}

/** True when no leaf anywhere under `field` renders the JSON fallback. */
export function fullySupported(field: Field): boolean {
  if (field.kind === 'unsupported') return false
  if (field.kind === 'object') return field.properties.every((p) => fullySupported(p.field))
  return true
}

// --- values: only touched paths are ever written (SCHEMA_FORM-4) -------------------

export type Path = (string | number)[]

export function getPath(value: unknown, path: Path): unknown {
  let cur: unknown = value
  for (const key of path) {
    if (cur === null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string | number, unknown>)[key]
  }
  return cur
}

/**
 * A copy of `value` with `path` set to `next`. `undefined` REMOVES the key.
 * An object emptied by a removal is removed too, unless `base` already held
 * that object (so an authored `gate: {}` survives, and a role the user
 * created and then cleared returns to absent, not `role: {}`).
 */
export function setPath(value: Record<string, unknown>, path: Path, next: unknown, base: unknown): Record<string, unknown> {
  const root = JSON.parse(JSON.stringify(value)) as Record<string, unknown>
  let cur: Record<string | number, unknown> = root
  for (const key of path.slice(0, -1)) {
    if (cur[key] === null || typeof cur[key] !== 'object') cur[key] = {}
    cur = cur[key] as Record<string | number, unknown>
  }
  const last = path[path.length - 1]
  if (next === undefined) delete cur[last]
  else cur[last] = next
  if (next === undefined) {
    for (let depth = path.length - 1; depth > 0; depth--) {
      const objPath = path.slice(0, depth)
      const obj = getPath(root, objPath)
      if (obj && typeof obj === 'object' && Object.keys(obj).length === 0 && getPath(base, objPath) === undefined) {
        delete (getPath(root, objPath.slice(0, -1)) as Record<string | number, unknown>)[objPath[objPath.length - 1]]
      } else {
        break
      }
    }
  }
  return root
}
```

`interfaces/ui/src/components/schema_form/SchemaField.vue` (create; 131 lines):

```vue
<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Field, Path } from './schema'

const props = defineProps<{
  name: string
  field: Field
  path: Path
  value: unknown
  errors: Record<string, string>
  readonlyPaths: string[]
  readonly: boolean
}>()
const emit = defineEmits<{ (e: 'set', path: Path, value: unknown): void }>()

const key = (p: Path) => p.join('.')
const isReadonly = () => props.readonly || props.readonlyPaths.includes(key(props.path))
const placeholder = () =>
  'default' in props.field && props.field.default !== undefined && props.field.default !== null
    ? String(props.field.default)
    : ''

function onText(ev: Event) {
  const v = (ev.target as HTMLInputElement | HTMLTextAreaElement).value
  emit('set', props.path, v === '' ? undefined : v)
}
function onNumber(ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const n = Number(raw)
  emit('set', props.path, raw === '' || !Number.isFinite(n) ? undefined : n)
}
function onBool(ev: Event) {
  emit('set', props.path, (ev.target as HTMLInputElement).checked)
}
function onEnum(ev: Event) {
  const v = (ev.target as HTMLSelectElement).value
  emit('set', props.path, v === '' ? undefined : v)
}
function onLines(ev: Event) {
  const lines = (ev.target as HTMLTextAreaElement).value.split('\n').filter((l) => l !== '')
  emit('set', props.path, lines.length ? lines : undefined)
}

// JSON snippet fallback (U8 as amended): parsed on blur; bad JSON stays local.
const snippet = ref(props.value === undefined ? '' : JSON.stringify(props.value, null, 2))
const snippetError = ref<string | null>(null)
watch(() => props.value, (v) => { snippet.value = v === undefined ? '' : JSON.stringify(v, null, 2) })
function onSnippetBlur() {
  if (snippet.value.trim() === '') { snippetError.value = null; emit('set', props.path, undefined); return }
  try {
    const parsed = JSON.parse(snippet.value)
    snippetError.value = null
    emit('set', props.path, parsed)
  } catch (e) {
    snippetError.value = `not JSON: ${(e as Error).message}`
  }
}
const str = (v: unknown) => (v === undefined || v === null ? '' : String(v))
</script>

<template>
  <fieldset v-if="field.kind === 'object'" class="group" :data-path="key(path)">
    <legend>{{ name }}</legend>
    <SchemaField
      v-for="p in field.properties"
      :key="p.name"
      :name="p.name"
      :field="p.field"
      :path="[...path, p.name]"
      :value="value && typeof value === 'object' ? (value as Record<string, unknown>)[p.name] : undefined"
      :errors="errors"
      :readonly-paths="readonlyPaths"
      :readonly="readonly"
      @set="(p2, v) => emit('set', p2, v)"
    />
    <p v-if="errors[key(path)]" class="err" data-testid="field-error">{{ errors[key(path)] }}</p>
  </fieldset>

  <label v-else class="row" :data-path="key(path)" data-testid="schema-field" :data-kind="field.kind">
    <span class="name">{{ name }}</span>
    <textarea
      v-if="field.kind === 'string'"
      class="input" rows="1" :value="str(value)" :placeholder="placeholder()" :readonly="isReadonly()"
      @input="onText"
    />
    <input
      v-else-if="field.kind === 'number' || field.kind === 'integer'"
      class="input" type="number" :step="field.kind === 'integer' ? 1 : 'any'"
      :min="field.minimum ?? field.exclusiveMinimum" :max="field.maximum ?? field.exclusiveMaximum"
      :value="str(value)" :placeholder="placeholder()" :readonly="isReadonly()"
      @change="onNumber"
    />
    <input
      v-else-if="field.kind === 'boolean'"
      type="checkbox" :checked="value === true" :disabled="isReadonly()"
      @change="onBool"
    />
    <select
      v-else-if="field.kind === 'enum'"
      class="input" :value="str(value)" :disabled="isReadonly()"
      @change="onEnum"
    >
      <option value="">{{ placeholder() ? `(default: ${placeholder()})` : '(unset)' }}</option>
      <option v-for="v in field.values" :key="v" :value="v">{{ v }}</option>
    </select>
    <textarea
      v-else-if="field.kind === 'string-array'"
      class="input" rows="2" placeholder="one per line"
      :value="Array.isArray(value) ? value.join('\n') : ''" :readonly="isReadonly()"
      @change="onLines"
    />
    <template v-else>
      <textarea
        v-model="snippet" class="input snippet" rows="3" data-testid="schema-fallback" :readonly="isReadonly()"
        @blur="onSnippetBlur"
      />
      <span v-if="snippetError" class="err">{{ snippetError }}</span>
    </template>
    <span v-if="errors[key(path)]" class="err" data-testid="field-error">{{ errors[key(path)] }}</span>
  </label>
</template>

<style scoped>
.group { margin: 6px 0; padding: 6px 8px; border: 1px solid var(--line); border-radius: 4px; }
legend { padding: 0 4px; color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; }
.row { display: grid; grid-template-columns: 110px 1fr; gap: 4px 8px; align-items: center; padding: 2px 0; }
.name { color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; overflow: hidden; text-overflow: ellipsis; }
.input { width: 100%; box-sizing: border-box; background: var(--ground-2); color: var(--ink-secondary); border: 1px solid var(--line); border-radius: 4px; font-family: var(--font-mono); font-size: 12px; padding: 2px 4px; field-sizing: content; resize: vertical; }
.snippet { min-height: 48px; }
.err { grid-column: 2; color: var(--status-failed); font-size: 11px; }
</style>
```

`interfaces/ui/src/components/schema_form/SchemaForm.vue` (create; 65 lines):

```vue
<script setup lang="ts">
// A generic form over a served JSON Schema (E-76 spec §8.3, U8). The caller
// owns the schema (pydantic model_json_schema() from the backend), the value
// and what applying it means; the form knows JSON Schema, not Kroker models.
import { computed, ref, watch } from 'vue'
import SchemaField from './SchemaField.vue'
import { classify, setPath, type Path, type Schema } from './schema'

export interface SchemaFormError {
  /** Dot path inside the value, e.g. "gate.policy"; '' for the whole value. */
  path: string
  msg: string
}

const props = withDefaults(
  defineProps<{
    schema: Schema
    value: Record<string, unknown>
    errors?: SchemaFormError[]
    readonly?: boolean
    readonlyPaths?: string[]
  }>(),
  { errors: () => [], readonly: false, readonlyPaths: () => [] },
)
const emit = defineEmits<{ (e: 'update', value: Record<string, unknown>): void }>()

const defs = computed(() => (props.schema.$defs ?? {}) as Record<string, Schema>)
const root = computed(() => classify(props.schema, defs.value))
const properties = computed(() => (root.value.kind === 'object' ? root.value.properties : []))
const errorMap = computed(() => Object.fromEntries(props.errors.map((e) => [e.path, e.msg])))
const formError = computed(() => errorMap.value[''] ?? null)

// `base` is the value as supplied; the draft accumulates touched paths only.
const draft = ref<Record<string, unknown>>(JSON.parse(JSON.stringify(props.value)))
watch(() => props.value, (v) => { draft.value = JSON.parse(JSON.stringify(v)) })

function onSet(path: Path, next: unknown) {
  if (props.readonly || props.readonlyPaths.includes(path.join('.'))) return
  draft.value = setPath(draft.value, path, next, props.value)
  emit('update', draft.value)
}
</script>

<template>
  <form class="cmp-schema-form" data-testid="schema-form" @submit.prevent>
    <p v-if="formError" class="err" data-testid="form-error">{{ formError }}</p>
    <SchemaField
      v-for="p in properties"
      :key="p.name"
      :name="p.name"
      :field="p.field"
      :path="[p.name]"
      :value="draft[p.name]"
      :errors="errorMap"
      :readonly-paths="readonlyPaths"
      :readonly="readonly"
      @set="onSet"
    />
  </form>
</template>

<style scoped>
.cmp-schema-form { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; font-size: 12px; }
.err { margin: 0 0 6px; color: var(--status-failed); }
</style>
```
- [ ] **Step 6: Run the unit and browser tests to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/schema_form
npm run typecheck --workspace @kroker/ui
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- src/components/schema_form
```

Expected: PASS — Vitest 15 tests (schema 10, form 5); Playwright 2 tests; typecheck clean.
- [ ] **Step 7: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t11-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 schema_form component

A generic form over a served JSON Schema: string, number/integer with
bounds, boolean, enum, arrays of strings, nested objects, the nullable
anyOf pattern and local $ref render natively; anything else is a JSON
snippet (U8 as amended). Only touched fields are ever written, and an
object the user created and then emptied is removed rather than left as
{}. No Kroker field name appears in the component.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/src/components/schema_form/schema.ts
git add interfaces/ui/src/components/schema_form/SchemaField.vue
git add interfaces/ui/src/components/schema_form/SchemaForm.vue
git add interfaces/ui/src/components/schema_form/schema_form.md
git add interfaces/ui/src/components/schema_form/schema_form.profiles.ts
git add interfaces/ui/src/components/schema_form/schema.spec.ts
git add interfaces/ui/src/components/schema_form/schema_form.spec.ts
git add interfaces/ui/src/components/schema_form/schema_form.pw.ts
git add interfaces/ui/showcase/registry.ts
git commit -F .workspace/tmp/e76-t11-msg.txt
```
### Task 12: `graph_canvas` component

**Files:**
- Create: `interfaces/ui/src/components/graph_canvas/GraphCanvas.vue`, `interfaces/ui/src/components/graph_canvas/graph_canvas.md`, `interfaces/ui/src/components/graph_canvas/graph_canvas.profiles.ts`
- Test: `interfaces/ui/src/components/graph_canvas/graph_canvas.spec.ts`, `interfaces/ui/src/components/graph_canvas/graph_canvas.pw.ts`
- Modify: `interfaces/ui/showcase/registry.ts`

**Interfaces:**
- Consumes: `defineProfiles` (`interfaces/ui/src/profile.ts`); Task 1 helpers.
- Produces: `GraphCanvas.vue` — props `nodes: CanvasNode[]`, `edges: CanvasEdge[]`, `editable?`, `connectable?(from, to)`, `selectedKey?`, `tidyRequest?`; emits `connect({from, to})`, `move({key, x, y})`, `remove({kind, key})`, `select(key|null)`, `drop-type({type, x, y})`, `layout-failed(message)`; slot `node-extra` with `{nodeKey}`; exposes `relayout(all)`.

- [ ] **Step 1: Write the clause contract and profiles**

`interfaces/ui/src/components/graph_canvas/graph_canvas.md` (create; 51 lines — GRAPH_CANVAS-9 is added in Task 17 with its test):

```markdown
# Graph Canvas Component

Renders a pipeline graph as nodes with typed ports and directed edges, in one
of two modes: editable (a draft) or read-only with run decorations (a run).
The caller owns the graph, its keys, legality, layout persistence and every
consequence of an edit; the component owns rendering, auto-layout of
unpositioned nodes, and turning gestures into events. It decides no legality
(FR-1202): the single connection rule it runs is the caller's `connectable`.

## Requirements

### GRAPH_CANVAS-1
A Graph Canvas renders exactly one node per supplied node, keyed by its
`key`, with its issue count when non-zero; duplicate domain ids are the
caller's to disambiguate into distinct keys. [FR-1205]

### GRAPH_CANVAS-2
An edge with `backward: true` renders on a curved path below its endpoints
and carries `cmp-graph-edge-backward`. [FR-1205]

### GRAPH_CANVAS-3
An edge with a `counter` renders `used/max` as its label text. [FR-1205]

### GRAPH_CANVAS-4
A node with a `status` carries `cmp-graph-node-<status>`; an unknown status
fails rendering rather than falling back (STAGE_DOTS-1.2 precedent).
[FR-1205]

### GRAPH_CANVAS-5
With `editable: false` no node is draggable, no handle is connectable, and
no `connect`, `move`, `remove` or `drop-type` is emitted. [FR-1205]

### GRAPH_CANVAS-6
A connection attempt is accepted iff `editable` and the caller's
`connectable(from, to)` returns true; the component evaluates no other rule
(no multiplicity, duplicate, self-loop or cycle check). [FR-1202, FR-1205]

### GRAPH_CANVAS-7
The canvas's colours resolve through design tokens: vue-flow's stylesheet
(`@vue-flow/core/dist/style.css`, which carries colour literals) is not
imported; the structural rules the canvas needs are re-declared with `--*`
tokens under `.cmp-graph-canvas`. [FR-1404]

### GRAPH_CANVAS-8
`move` never emits a non-finite coordinate or an unknown key, and auto-layout
never adds an edge whose endpoint is not a supplied node key. [FR-1205]

## Failure modes

Layout throws: existing positions are kept, unpositioned nodes go on a grid,
and `layout-failed` is emitted. An edge naming a missing node is not drawn.
```

`interfaces/ui/src/components/graph_canvas/graph_canvas.profiles.ts` (create; 73 lines):

```ts
import { defineProfiles } from '../../profile'
import GraphCanvas from './GraphCanvas.vue'
import type { CanvasEdge, CanvasNode, CanvasPort, CanvasStatus } from './types'

const port = (name: string, side: 'in' | 'out', kind: 'signal' | 'data' = 'data', optional = false): CanvasPort =>
  ({ name, side, kind, label: name, optional })

const node = (key: string, x: number, ports: CanvasPort[], extra: Partial<CanvasNode> = {}): CanvasNode =>
  ({ key, title: key, ports, issueCount: 0, position: { x, y: 0 }, ...extra })

const edge = (from: string, fromPort: string, to: string, toPort: string, extra: Partial<CanvasEdge> = {}): CanvasEdge =>
  ({ key: `${from}.${fromPort}>${to}.${toPort}`, from: { node: from, port: fromPort }, to: { node: to, port: toPort }, backward: false, issueCount: 0, ...extra })

const pipeline = (status?: Record<string, CanvasStatus>): CanvasNode[] => [
  node('intake', 0, [port('ok', 'out', 'signal')], { subtitle: 'intake', status: status?.intake }),
  node('architect', 260, [port('requirements', 'in'), port('guidance', 'in', 'data', true), port('spec', 'out')], { subtitle: 'architect', status: status?.architect }),
  node('architecture', 520, [port('artifact', 'in'), port('approve', 'out'), port('revise', 'out'), port('reject', 'out', 'signal')], { subtitle: 'gate.architecture', status: status?.architecture }),
  node('planner', 780, [port('spec', 'in'), port('plan', 'out')], { subtitle: 'plan', status: status?.planner }),
]

const wires = (used?: number): CanvasEdge[] => [
  edge('intake', 'ok', 'architect', 'requirements'),
  edge('architect', 'spec', 'architecture', 'artifact'),
  edge('architecture', 'approve', 'planner', 'spec'),
  edge('architecture', 'revise', 'architect', 'guidance', { backward: true, counter: used === undefined ? undefined : { used, max: 3 } }),
]

export default defineProfiles({
  component: 'graph_canvas',
  group: 'Graph',
  target: GraphCanvas,
  profiles: [
    { name: 'edit-empty', summary: 'An empty draft: no nodes, no edges.', props: { nodes: [], edges: [], editable: true } },
    { name: 'edit-pre-code', summary: 'A loaded draft in edit mode, loop edge curved.', props: { nodes: pipeline(), edges: wires(), editable: true } },
    {
      name: 'edit-with-issues',
      summary: 'Validation issues decorate a node and an edge.',
      props: {
        nodes: pipeline().map((n) => (n.key === 'planner' ? { ...n, issueCount: 2 } : n)),
        edges: wires().map((e, i) => (i === 0 ? { ...e, issueCount: 1 } : e)),
        editable: true,
      },
    },
    {
      name: 'edit-duplicate-ids',
      summary: 'Two nodes share a domain id; the adapter gave them distinct keys.',
      props: {
        nodes: [node('intake', 0, [port('ok', 'out', 'signal')], { issueCount: 1 }), node('intake~2', 260, [port('ok', 'out', 'signal')], { title: 'intake', issueCount: 1 })],
        edges: [],
        editable: true,
      },
    },
    {
      name: 'run-mid-flight',
      summary: 'Run mode: status rings and metrics, nothing editable.',
      props: {
        nodes: pipeline({ intake: 'done', architect: 'running', architecture: 'idle', planner: 'idle' })
          .map((n) => (n.key === 'architect' ? { ...n, metrics: { cost: '$1.87', elapsed: '6m 02s', round: 'r1' } } : n)),
        edges: wires(0),
      },
    },
    {
      name: 'run-looped',
      summary: 'A revise loop taken twice: the counter reads 2/3 on a curved edge.',
      props: { nodes: pipeline({ intake: 'done', architect: 'running', architecture: 'done', planner: 'idle' }), edges: wires(2) },
    },
    {
      name: 'run-gate-pending',
      summary: 'A gate node held for a human decision.',
      props: { nodes: pipeline({ intake: 'done', architect: 'done', architecture: 'blocked', planner: 'idle' }), edges: wires(1) },
    },
  ],
})
```
- [ ] **Step 2: Write the failing tests**

`interfaces/ui/src/components/graph_canvas/graph_canvas.spec.ts` (create; 43 lines):

```ts
import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import GraphCanvas from './GraphCanvas.vue'
import type { CanvasNode } from './types'

// vue-flow needs real layout, so rendering clauses are Playwright-tier
// (graph_canvas.pw.ts). jsdom covers the fail-fast contract and events that
// do not depend on measured geometry.
beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

const node = (key: string, extra: Partial<CanvasNode> = {}): CanvasNode => ({
  key, title: key, ports: [], issueCount: 0, position: { x: 0, y: 0 }, ...extra,
})

describe('GraphCanvas', () => {
  it('fails rendering on an unknown status', () => {  // clause: GRAPH_CANVAS-4
    expect(() => mount(GraphCanvas, { props: { nodes: [node('a', { status: 'sideways' as never })], edges: [] } })).toThrow(/sideways/)
  })

  it('emits no remove in run mode and removes the selection in edit mode', async () => {  // clause: GRAPH_CANVAS-5
    const ro = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], selectedKey: 'a' } })
    await ro.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(ro.emitted('remove')).toBeUndefined()
    const rw = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], selectedKey: 'a', editable: true } })
    await rw.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(rw.emitted('remove')).toEqual([[{ kind: 'node', key: 'a' }]])
  })

  it('lays out an unpositioned node and emits its finite position only when editable', () => {  // clause: GRAPH_CANVAS-8
    const rw = mount(GraphCanvas, { props: { nodes: [node('a', { position: undefined })], edges: [], editable: true } })
    const moves = rw.emitted('move') as [{ key: string; x: number; y: number }][]
    expect(moves).toHaveLength(1)
    expect(Number.isFinite(moves[0][0].x) && Number.isFinite(moves[0][0].y)).toBe(true)
    const ro = mount(GraphCanvas, { props: { nodes: [node('a', { position: undefined })], edges: [] } })
    expect(ro.emitted('move')).toBeUndefined()
  })
})
```

`interfaces/ui/src/components/graph_canvas/graph_canvas.pw.ts` (create; 54 lines):

```ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-graph_canvas-${profile}`

test.beforeEach(async ({ page }) => {
  await page.goto('/')
})

test('renders one node per supplied node, keyed by key', async ({ page }) => {  // clause: GRAPH_CANVAS-1
  await expect(page.locator(`${at('edit-pre-code')} [data-testid="graph-node"]`)).toHaveCount(4)
  const dup = page.locator(`${at('edit-duplicate-ids')} [data-testid="graph-node"]`)
  await expect(dup).toHaveCount(2)
  await expect(dup.nth(0)).toHaveAttribute('data-key', 'intake')
  await expect(dup.nth(1)).toHaveAttribute('data-key', 'intake~2')
})

test('a backward edge renders curved with its stable class', async ({ page }) => {  // clause: GRAPH_CANVAS-2
  const backward = page.locator(`${at('run-looped')} .cmp-graph-edge-backward`)
  await expect(backward).toHaveCount(1)
  const d = await backward.locator('path').first().getAttribute('d')
  expect(d).toMatch(/^M [-\d.]+,[-\d.]+ C /)
  await expect(page.locator(`${at('run-looped')} .cmp-graph-edge:not(.cmp-graph-edge-backward)`)).toHaveCount(3)
})

test('an edge with a counter renders used/max as text', async ({ page }) => {  // clause: GRAPH_CANVAS-3
  await expect(page.locator(`${at('run-looped')} .vue-flow__edge-text`, { hasText: '2/3' })).toHaveCount(1)
})

test('a node status carries its stable class', async ({ page }) => {  // clause: GRAPH_CANVAS-4
  await expect(page.locator(`${at('run-mid-flight')} .cmp-graph-node-running`)).toHaveCount(1)
  await expect(page.locator(`${at('run-mid-flight')} .cmp-graph-node-done`)).toHaveCount(1)
  await expect(page.locator(`${at('run-gate-pending')} .cmp-graph-node-blocked`)).toHaveCount(1)
  await expect(page.locator(`${at('run-mid-flight')} [data-testid="node-metrics"]`)).toContainText('$1.87')
})

test('run mode offers no connectable handle and no draggable node', async ({ page }) => {  // clause: GRAPH_CANVAS-5
  await expect(page.locator(`${at('run-mid-flight')} .vue-flow__handle.connectable`)).toHaveCount(0)
  await expect(page.locator(`${at('run-mid-flight')} .vue-flow__node.draggable`)).toHaveCount(0)
  await expect(page.locator(`${at('edit-pre-code')} .vue-flow__node.draggable`)).toHaveCount(4)
})

test('issue counts decorate nodes', async ({ page }) => {  // clause: GRAPH_CANVAS-1
  await expect(page.locator(`${at('edit-with-issues')} [data-testid="node-issues"]`)).toHaveText(['2'])
})

test('canvas colours resolve through tokens', async ({ page }) => {  // clause: GRAPH_CANVAS-7
  const stroke = await page.locator(`${at('edit-pre-code')} .vue-flow__edge-path`).first()
    .evaluate((el) => getComputedStyle(el).stroke)
  const token = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--line-strong').trim())
  expect(token).not.toBe('')
  expect(stroke).not.toBe('')
  const linked = await page.evaluate(() => [...document.styleSheets].some((s) => (s.href ?? '').includes('vue-flow')))
  expect(linked).toBe(false)
})
```
- [ ] **Step 3: Register the profiles in the showcase**

In `interfaces/ui/showcase/registry.ts`, add the import(s) after the last existing profile import:

```ts
import graphCanvas from '../src/components/graph_canvas/graph_canvas.profiles'
```

and append `graphCanvas` to the end of the `REGISTRY` array (keep existing order).
- [ ] **Step 4: Run the unit tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/graph_canvas
```

Expected: FAIL — the spec files cannot resolve the component module(s) (the profiles also import them, so the showcase build fails until Step 5).
- [ ] **Step 5: Write the implementation**

`interfaces/ui/src/components/graph_canvas/GraphCanvas.vue` (create; 310 lines):

```vue
<script setup lang="ts">
// One renderer, two modes (E-76 spec §8-§10, FR-1205). Renders display
// primitives only; decides no legality. The single connection rule it runs
// is the caller's `connectable` (GRAPH_CANVAS-6).
import { computed, ref, shallowRef, watch } from 'vue'
import { VueFlow, Handle, Position, BaseEdge, getBezierPath } from '@vue-flow/core'
import type { Connection, Edge, Node, NodeDragEvent } from '@vue-flow/core'
import { CANVAS_STATUSES, type CanvasEdge, type CanvasNode, type Point, type PortRef } from './types'
import { backwardPath, isFinitePoint, layoutGraph, NODE_WIDTH } from './graph_layout'
import { acceptConnection, handleId, toPortRefs } from './connection'

const props = withDefaults(
  defineProps<{
    nodes: CanvasNode[]
    edges: CanvasEdge[]
    editable?: boolean
    connectable?: (from: PortRef, to: PortRef) => boolean
    selectedKey?: string | null
    tidyRequest?: number
  }>(),
  { editable: false, connectable: () => false, selectedKey: null, tidyRequest: 0 },
)

const emit = defineEmits<{
  (e: 'connect', v: { from: PortRef; to: PortRef }): void
  (e: 'move', v: { key: string } & Point): void
  (e: 'remove', v: { kind: 'node' | 'edge'; key: string }): void
  (e: 'select', key: string | null): void
  (e: 'drop-type', v: { type: string } & Point): void
  (e: 'layout-failed', message: string): void
}>()

const laid = ref<Record<string, Point>>({})
const backwardKeys = computed(() => new Set(props.edges.filter((e) => e.backward).map((e) => e.key)))

function relayout(all: boolean) {
  const result = layoutGraph(props.nodes, props.edges, { all, backwardKeys: backwardKeys.value })
  if (result.failed) emit('layout-failed', result.failed)
  laid.value = all ? result.positions : { ...laid.value, ...result.positions }
  if (props.editable) {
    // Positions the layout chose become cosmetic data (spec §8.4).
    for (const [key, p] of Object.entries(result.positions)) emitMove(key, p)
  }
}

function emitMove(key: string, p: Point) {
  // GRAPH_CANVAS-8: never a non-finite coordinate, never an unknown key.
  if (!isFinitePoint(p) || !props.nodes.some((n) => n.key === key)) return
  emit('move', { key, x: p.x, y: p.y })
}

watch(
  () => props.nodes.filter((n) => !isFinitePoint(n.position) && !laid.value[n.key]).map((n) => n.key).join('|'),
  (missing) => { if (missing) relayout(false) },
  { immediate: true },
)
watch(() => props.tidyRequest, (v, old) => { if (v !== old) relayout(true) })

// Decorations (status, metrics, counters, issue counts) are read by the slot
// templates from these maps. vue-flow's own element arrays below change ONLY
// when structure changes: replacing them on every run-state tick drops the
// measured handle bounds and the edges with them (verified 2026-09-14,
// @vue-flow/core 1.48.2).
// GRAPH_CANVAS-4: an unknown status is a product fault, not a default.
// Checked synchronously at setup (so mounting fails) and on every update.
function assertStatuses(nodes: readonly CanvasNode[]) {
  for (const n of nodes) {
    if (n.status !== undefined && !CANVAS_STATUSES.includes(n.status)) {
      throw new Error(`GraphCanvas: unknown status "${n.status}" for node "${n.key}"`)
    }
  }
}
assertStatuses(props.nodes)
watch(() => props.nodes, assertStatuses)
const nodeByKey = computed(() => new Map(props.nodes.map((n) => [n.key, n])))
const edgeByKey = computed(() => new Map(props.edges.map((e) => [e.key, e])))

const flowNodes = shallowRef<Node[]>([])
const flowEdges = shallowRef<Edge[]>([])

const positionOf = (n: CanvasNode): Point => (isFinitePoint(n.position) ? n.position : laid.value[n.key] ?? { x: 0, y: 0 })

watch(
  () => JSON.stringify([props.editable, props.nodes.map((n) => [n.key, positionOf(n), n.ports, n.readonly ?? false])]),
  () => {
    flowNodes.value = props.nodes.map((n) => ({
      id: n.key,
      type: 'kroker',
      position: positionOf(n),
      data: { key: n.key },
      draggable: props.editable,
    }))
  },
  { immediate: true },
)
watch(
  () => JSON.stringify(props.edges.map((e) => [e.key, e.from, e.to, e.backward])),
  () => {
    flowEdges.value = props.edges.map((e) => ({
      id: e.key,
      type: e.backward ? 'backward' : 'forward',
      source: e.from.node,
      sourceHandle: handleId('out', e.from.port),
      target: e.to.node,
      targetHandle: handleId('in', e.to.port),
      data: { key: e.key },
    }))
  },
  { immediate: true },
)

const edgeText = (key: string): string | undefined => {
  const e = edgeByKey.value.get(key)
  if (!e) return undefined
  return e.counter ? `${e.counter.used}/${e.counter.max}` : e.label
}

const accepts = (c: Connection) => acceptConnection(props.editable, props.connectable, c)

function onConnect(c: Connection) {
  if (accepts(c)) emit('connect', toPortRefs(c))
}

function onDragStop(ev: NodeDragEvent) {
  if (!props.editable) return
  for (const n of ev.nodes) emitMove(n.id, n.position)
}

function onKey(ev: KeyboardEvent) {
  if (!props.editable || !props.selectedKey) return
  if (ev.key !== 'Delete' && ev.key !== 'Backspace') return
  const kind = props.nodes.some((n) => n.key === props.selectedKey) ? 'node' : 'edge'
  emit('remove', { kind, key: props.selectedKey })
}

const root = ref<HTMLElement | null>(null)
function onDrop(ev: DragEvent) {
  if (!props.editable) return
  const type = ev.dataTransfer?.getData('application/x-kroker-node-type')
  if (!type || !root.value) return
  const box = root.value.getBoundingClientRect()
  const p = { x: ev.clientX - box.left - NODE_WIDTH / 2, y: ev.clientY - box.top - 20 }
  if (isFinitePoint(p)) emit('drop-type', { type, ...p })
}

const inPorts = (n: CanvasNode) => n.ports.filter((p) => p.side === 'in')
const outPorts = (n: CanvasNode) => n.ports.filter((p) => p.side === 'out')

defineExpose({ relayout })
</script>

<template>
  <div
    ref="root"
    class="cmp-graph-canvas"
    :class="{ 'is-editable': editable }"
    tabindex="0"
    data-testid="graph-canvas"
    @keydown="onKey"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :nodes-draggable="editable"
      :nodes-connectable="editable"
      :elements-selectable="true"
      :delete-key-code="null"
      :is-valid-connection="accepts"
      :fit-view-on-init="true"
      :min-zoom="0.2"
      @connect="onConnect"
      @node-drag-stop="onDragStop"
      @node-click="(e) => emit('select', e.node.id)"
      @edge-click="(e) => emit('select', e.edge.id)"
      @pane-click="emit('select', null)"
    >
      <template #node-kroker="{ id }">
        <div
          v-if="nodeByKey.get(id)"
          class="cmp-graph-node"
          :class="[nodeByKey.get(id)!.status ? `cmp-graph-node-${nodeByKey.get(id)!.status}` : '', { 'is-readonly': nodeByKey.get(id)!.readonly, 'is-selected': id === selectedKey }]"
          data-testid="graph-node"
          :data-key="id"
        >
          <div class="head">
            <span class="title">{{ nodeByKey.get(id)!.title }}</span>
            <span v-if="nodeByKey.get(id)!.issueCount > 0" class="issues" data-testid="node-issues">{{ nodeByKey.get(id)!.issueCount }}</span>
          </div>
          <div v-if="nodeByKey.get(id)!.subtitle" class="subtitle">{{ nodeByKey.get(id)!.subtitle }}</div>
          <div v-if="nodeByKey.get(id)!.metrics" class="metrics" data-testid="node-metrics">
            <span v-if="nodeByKey.get(id)!.metrics!.round">{{ nodeByKey.get(id)!.metrics!.round }}</span>
            <span v-if="nodeByKey.get(id)!.metrics!.elapsed">{{ nodeByKey.get(id)!.metrics!.elapsed }}</span>
            <span v-if="nodeByKey.get(id)!.metrics!.cost">{{ nodeByKey.get(id)!.metrics!.cost }}</span>
          </div>
          <div class="ports">
            <div class="col">
              <div v-for="p in inPorts(nodeByKey.get(id)!)" :key="p.name" class="port in" :class="{ optional: p.optional, signal: p.kind === 'signal' }">
                <Handle :id="handleId('in', p.name)" type="target" :position="Position.Left" :connectable="editable && !nodeByKey.get(id)!.readonly" />
                {{ p.label }}
              </div>
            </div>
            <div class="col out">
              <div v-for="p in outPorts(nodeByKey.get(id)!)" :key="p.name" class="port out" :class="{ signal: p.kind === 'signal' }">
                {{ p.label }}
                <Handle :id="handleId('out', p.name)" type="source" :position="Position.Right" :connectable="editable && !nodeByKey.get(id)!.readonly" />
              </div>
            </div>
          </div>
          <slot name="node-extra" :node-key="id" />
        </div>
      </template>

      <template #edge-forward="edge">
        <g
          class="cmp-graph-edge"
          :class="{ 'has-issues': (edgeByKey.get(edge.id)?.issueCount ?? 0) > 0, 'is-selected': edge.id === selectedKey }"
          data-testid="graph-edge"
          :data-key="edge.id"
        >
          <BaseEdge
            :id="edge.id"
            :path="getBezierPath(edge)[0]"
            :label-x="getBezierPath(edge)[1]"
            :label-y="getBezierPath(edge)[2]"
            :label="edgeText(edge.id)"
          />
        </g>
      </template>

      <template #edge-backward="edge">
        <g
          class="cmp-graph-edge cmp-graph-edge-backward"
          :class="{ 'has-issues': (edgeByKey.get(edge.id)?.issueCount ?? 0) > 0, 'is-selected': edge.id === selectedKey }"
          data-testid="graph-edge"
          :data-key="edge.id"
        >
          <BaseEdge
            :id="edge.id"
            :path="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[0]"
            :label-x="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[1]"
            :label-y="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[2]"
            :label="edgeText(edge.id)"
          />
        </g>
      </template>
    </VueFlow>
  </div>
</template>

<style>
/* vue-flow's structural rules, re-declared with tokens (GRAPH_CANVAS-7).
   @vue-flow/core/dist/style.css is NOT imported: it carries colour literals
   (#b1b1b7, #555, white), verified 2026-09-14 against 1.48.2. */
.cmp-graph-canvas .vue-flow { position: relative; width: 100%; height: 100%; overflow: hidden; z-index: 0; direction: ltr; }
.cmp-graph-canvas .vue-flow__container { position: absolute; height: 100%; width: 100%; left: 0; top: 0; }
.cmp-graph-canvas .vue-flow__pane { z-index: 1; }
.cmp-graph-canvas .vue-flow__pane.draggable { cursor: grab; }
.cmp-graph-canvas .vue-flow__transformationpane { transform-origin: 0 0; z-index: 2; pointer-events: none; }
.cmp-graph-canvas .vue-flow__viewport { z-index: 4; overflow: clip; }
.cmp-graph-canvas .vue-flow__edge-labels { position: absolute; width: 100%; height: 100%; pointer-events: none; user-select: none; }
.cmp-graph-canvas .vue-flow__edges { pointer-events: none; overflow: visible; }
.cmp-graph-canvas .vue-flow__edge-path,
.cmp-graph-canvas .vue-flow__connection-path { stroke: var(--line-strong); stroke-width: 1.5; fill: none; }
.cmp-graph-canvas .vue-flow__edge { pointer-events: visibleStroke; cursor: pointer; }
.cmp-graph-canvas .cmp-graph-edge.is-selected .vue-flow__edge-path { stroke: var(--accent); }
.cmp-graph-canvas .cmp-graph-edge.has-issues .vue-flow__edge-path { stroke: var(--status-failed); }
.cmp-graph-canvas .vue-flow__edge-textbg { fill: var(--ground-3); }
.cmp-graph-canvas .vue-flow__edge-text { fill: var(--ink-tertiary); font-family: var(--font-mono); font-size: 11px; }
.cmp-graph-canvas .vue-flow__connection { pointer-events: none; }
.cmp-graph-canvas .vue-flow__connectionline { z-index: 1001; }
.cmp-graph-canvas .vue-flow__nodes { pointer-events: none; transform-origin: 0 0; }
.cmp-graph-canvas .vue-flow__node { position: absolute; user-select: none; pointer-events: all; transform-origin: 0 0; box-sizing: border-box; cursor: default; }
.cmp-graph-canvas .vue-flow__node.draggable { cursor: grab; }
.cmp-graph-canvas .vue-flow__handle { position: absolute; pointer-events: none; min-width: 7px; min-height: 7px; background: var(--line-strong); border-radius: 50%; }
.cmp-graph-canvas .vue-flow__handle.connectable { pointer-events: all; cursor: crosshair; }
.cmp-graph-canvas .vue-flow__handle-left { top: 50%; left: 0; transform: translate(-50%, -50%); }
.cmp-graph-canvas .vue-flow__handle-right { top: 50%; right: 0; transform: translate(50%, -50%); }
.cmp-graph-canvas .vue-flow__panel { position: absolute; z-index: 5; margin: 15px; }
</style>

<style scoped>
.cmp-graph-canvas { position: relative; width: 100%; height: 100%; min-height: 360px; background: var(--ground-1); outline: none; }
.cmp-graph-node {
  width: 190px; background: var(--ground-3); border: 1px solid var(--line); border-radius: 6px;
  color: var(--ink-secondary); font-family: var(--font-sans); font-size: 12px;
}
.cmp-graph-node.is-readonly { border-style: dashed; }
.cmp-graph-node.is-selected { border-color: var(--accent); }
.head { display: flex; justify-content: space-between; padding: 6px 8px 2px; color: var(--ink-primary); font-weight: 600; }
.issues { background: var(--status-failed); color: var(--ground-0); border-radius: 8px; padding: 0 6px; font-size: 11px; }
.subtitle { padding: 0 8px; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 11px; }
.metrics { display: flex; gap: 8px; padding: 2px 8px; color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; }
.ports { display: flex; justify-content: space-between; padding: 4px 0 6px; }
.col { display: flex; flex-direction: column; }
.col.out { align-items: flex-end; }
.port { position: relative; height: 18px; line-height: 18px; padding: 0 10px; font-family: var(--font-mono); font-size: 11px; color: var(--ink-tertiary); }
.port.optional { color: var(--ink-subtle); }
.port.signal { font-style: italic; }
.cmp-graph-node-idle { border-color: var(--line); }
.cmp-graph-node-running { box-shadow: 0 0 0 2px var(--status-running); }
.cmp-graph-node-blocked { box-shadow: 0 0 0 2px var(--status-blocked); }
.cmp-graph-node-done { box-shadow: 0 0 0 2px var(--status-done); }
.cmp-graph-node-failed { box-shadow: 0 0 0 2px var(--status-failed); }
.cmp-graph-node-stale { box-shadow: 0 0 0 2px var(--status-skipped); }
.cmp-graph-node-running,
.cmp-graph-node-blocked { animation: fc-pulse 1.6s infinite; }
@keyframes fc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
</style>
```
- [ ] **Step 6: Run the unit and browser tests to verify they pass**

```bash
npm run test --workspace @kroker/ui -- src/components/graph_canvas
npm run typecheck --workspace @kroker/ui
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- src/components/graph_canvas
```

Expected: PASS — Vitest 16 tests (graph_canvas 3 + Task 1's helpers 13); Playwright 7 tests; typecheck clean.
- [ ] **Step 7: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 8: Commit**

Write `.workspace/tmp/e76-t12-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(ui): E-76 graph_canvas component

One renderer, two modes over vue-flow. Nodes render typed ports and run
decorations (status rings, metrics), edges render counters and a curved arc
when backward, and editable mode turns gestures into connect/move/remove/
select/drop-type events. vue-flow receives element arrays rebuilt only on
structural change; decorations are read from key maps, because replacing
the arrays on every run-state tick dropped every edge. Its clause,
GRAPH_CANVAS-9, lands with the RunView regression test in Task 17. The
structural vue-flow CSS is re-declared with tokens.
```

Then, one path per `git add`:

```bash
git add interfaces/ui/src/components/graph_canvas/GraphCanvas.vue
git add interfaces/ui/src/components/graph_canvas/graph_canvas.md
git add interfaces/ui/src/components/graph_canvas/graph_canvas.profiles.ts
git add interfaces/ui/src/components/graph_canvas/graph_canvas.spec.ts
git add interfaces/ui/src/components/graph_canvas/graph_canvas.pw.ts
git add interfaces/ui/showcase/registry.ts
git commit -F .workspace/tmp/e76-t12-msg.txt
```
### Task 13: Wire graph → canvas primitives — `adapters/graph.ts`

**Files:**
- Create: `interfaces/dashboard/frontend/src/adapters/graph.ts`
- Test: `interfaces/dashboard/frontend/src/adapters/graph.test.ts`

**Interfaces:**
- Consumes: Task 7 wire types and fixtures; Task 1 `CanvasNode`/`CanvasEdge`/`CanvasPort`; Task 9 `IssueItem`.
- Produces: `CanvasModel {nodes, edges, issues, nodeIndex, edgeIndex, pendingByNode}`, `CanvasOptions {typeOf, issues?, backEdges?, state?, now?}`, `nodeKeys(graph)` (duplicates `id~2`…), `edgeKeys(graph)` (4-tuple + `#n`), `formatElapsed(ms)`, `toCanvas(graph, opts)`, `locWithin(loc, 'nodes'|'edges', index) → string | null`, `locLabel(loc)`.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/adapters/graph.test.ts` (create; 113 lines):

```ts
import { describe, it, expect } from 'vitest'
import { edgeKeys, formatElapsed, locLabel, locWithin, nodeKeys, toCanvas } from './graph'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import preCode from '../api/__fixtures__/graph/scenarios/pre_code.json'
import runGraphs from '../api/__fixtures__/graph/run_graphs.provisional.json'
import validation from '../api/__fixtures__/graph/validation.provisional.json'
import type { CatalogWire, GraphStateResponse, GraphWire, Issue } from '../api/graph-types'

const catalog = catalogJson as unknown as CatalogWire
const typeOf = (t: string) => catalog.node_types.find((n) => n.type === t)
const PRE = (preCode.parse as { graph: GraphWire }).graph
const e = (source: string, source_port: string, target: string, target_port: string, extra = {}) => ({ source, source_port, target, target_port, ...extra })

const DUP: GraphWire = {
  schema_version: 1,
  nodes: [{ id: 'intake', type: 'intake' }, { id: 'intake', type: 'intake' }, { id: 'ghost_type', type: 'mystery.kind' }],
  edges: [e('intake', 'ok', 'ghost_type', 'x'), e('intake', 'ok', 'ghost_type', 'x', { label: 'twin' }), e('ghost_type', 'y', 'intake', 'trigger')],
}

describe('keys', () => {
  it('disambiguates duplicate node ids in server order', () => {
    expect(nodeKeys(DUP)).toEqual(['intake', 'intake~2', 'ghost_type'])
  })
  it('keys edges by 4-tuple plus occurrence', () => {
    expect(edgeKeys(DUP)).toEqual(['intake.ok>ghost_type.x', 'intake.ok>ghost_type.x#2', 'ghost_type.y>intake.trigger'])
  })
})

describe('toCanvas (edit mode)', () => {
  it('maps catalog ports with signal/data kind and optional in-ports', () => {
    const { nodes } = toCanvas(PRE, { typeOf })
    const architect = nodes.find((n) => n.key === 'architect')!
    expect(architect.subtitle).toBe('architect')
    expect(architect.ports.find((p) => p.name === 'guidance')).toMatchObject({ side: 'in', kind: 'data', optional: true })
    expect(nodes.find((n) => n.key === 'intake')!.ports).toEqual([{ name: 'ok', side: 'out', kind: 'signal', label: 'ok', optional: false }])
    expect(nodes.find((n) => n.key === 'plan')!.title).toBe('Plan gate')
  })

  it('maps an issue onto every duplicate and attaches edges to the first occurrence', () => {
    const issues: Issue[] = [{ code: 'node.duplicate_id', severity: 'error', message: 'dup', target: { kind: 'node', id: 'intake' } }]
    const m = toCanvas(DUP, { typeOf, issues })
    expect(m.nodes.filter((n) => n.issueCount === 1).map((n) => n.key)).toEqual(['intake', 'intake~2'])
    expect(m.edges[2].to.node).toBe('intake')
    expect(m.issues[0]).toMatchObject({ focusKey: 'intake', targetLabel: 'intake' })
  })

  it('renders an unknown type read-only with handles synthesized from its edges', () => {
    const ghost = toCanvas(DUP, { typeOf }).nodes.find((n) => n.key === 'ghost_type')!
    expect(ghost.readonly).toBe(true)
    expect(ghost.ports.map((p) => `${p.side}:${p.name}`)).toEqual(['in:x', 'out:y'])
  })

  it('marks backward only the edges the server named', () => {
    const backEdges = (validation as unknown as Record<string, { back_edges: never[] }>).pre_code.back_edges
    const m = toCanvas(PRE, { typeOf, backEdges })
    expect(m.edges.filter((x) => x.backward).map((x) => x.from.port)).toEqual(['revise', 'revise', 'revise'])
    expect(toCanvas(PRE, { typeOf }).edges.some((x) => x.backward)).toBe(false)
  })

  it('routes an unresolvable issue target to the graph level, never throws', () => {
    const issues: Issue[] = [
      { code: 'x', severity: 'warning', message: 'gone', target: { kind: 'node', id: 'deleted_node' } },
      { code: 'y', severity: 'error', message: 'whole', target: { kind: 'graph' } },
      { code: 'z', severity: 'error', message: 'edge', target: { kind: 'edge', edge: e('intake', 'ok', 'ghost_type', 'x') } },
    ]
    const m = toCanvas(DUP, { typeOf, issues })
    expect(m.issues.map((i) => i.focusKey)).toEqual([null, null, 'intake.ok>ghost_type.x'])
    expect(m.edges.filter((x) => x.issueCount === 1)).toHaveLength(2)
  })

  it('shows no run decoration without state', () => {
    const m = toCanvas(PRE, { typeOf })
    expect(m.nodes.every((n) => n.status === undefined && n.metrics === undefined)).toBe(true)
    expect(m.edges.every((x) => x.counter === undefined)).toBe(true)
  })
})

describe('toCanvas (run mode)', () => {
  const script = (runGraphs as unknown as { runs: Record<string, { states: Record<string, { state: GraphStateResponse }> }> }).runs['feature-graph-demo']
  const state = script.states.blocked_r2.state

  it('joins traversals with the pinned max_traversals, defaulting to 0', () => {
    const m = toCanvas(PRE, { typeOf, state })
    const loop = m.edges.find((x) => x.key === 'architecture.revise>architect.guidance')!
    expect(loop.counter).toEqual({ used: 1, max: 2 })
    expect(m.edges.find((x) => x.key === 'plan.revise>planner.guidance')!.counter).toEqual({ used: 0, max: 2 })
    expect(m.edges.find((x) => x.key === 'architect.spec>architecture.artifact')!.counter).toBeUndefined()
  })

  it('decorates status, cost, elapsed and round', () => {
    const m = toCanvas(PRE, { typeOf, state, now: new Date('2026-09-14T09:35:30Z') })
    const architect = m.nodes.find((n) => n.key === 'architect')!
    expect(architect.status).toBe('done')
    expect(architect.metrics).toEqual({ cost: '$1.87', elapsed: '6m 00s', round: 'r2' })
    const gate = m.nodes.find((n) => n.key === 'architecture')!
    expect(gate.metrics).toEqual({ cost: '—', elapsed: '4m 30s', round: 'r2' })
    expect(m.pendingByNode.architecture).toEqual([{ node: 'architecture', key: 'architecture#2', kind: 'gate' }])
  })
})

describe('helpers', () => {
  it('formats elapsed time', () => {
    expect(formatElapsed(362_000)).toBe('6m 02s')
    expect(formatElapsed(3_780_000)).toBe('1h 03m')
    expect(formatElapsed(-5)).toBe('0m 00s')
  })
  it('maps shape-error locs into an element and into a document label', () => {
    expect(locWithin(['nodes', 3, 'role', 'model'], 'nodes', 3)).toBe('role.model')
    expect(locWithin(['nodes', 2, 'id'], 'nodes', 3)).toBeNull()
    expect(locWithin(['nodes', 3], 'nodes', 3)).toBe('')
    expect(locLabel(['nodes', 3, 'id'])).toBe('nodes[3].id')
  })
})
```
- [ ] **Step 2: Run it to verify it fails**

```bash
npm run test --workspace sdlc-dashboard -- src/adapters/graph.test.ts
```

Expected: FAIL — cannot resolve `./graph`.
- [ ] **Step 3: Write the adapter**

`interfaces/dashboard/frontend/src/adapters/graph.ts` (create; 188 lines):

```ts
// Wire graph -> canvas primitives (E-76 spec §10.3). The ONLY place wire
// shapes meet @kroker/ui's display types. Decides no legality: issues and
// back edges arrive from the server and are only mapped onto elements.
import type { CanvasEdge, CanvasNode, CanvasPort } from '@kroker/ui/components/graph_canvas/types'
import type { IssueItem } from '@kroker/ui/components/issue_list/IssueList.vue'
import type {
  EdgeRef, EdgeWire, GraphStateResponse, GraphWire, Issue, NodeTypeWire, PendingRef,
} from '../api/graph-types'
import { sameEdge } from '../api/graph-types'

export interface CanvasModel {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
  issues: IssueItem[]
  /** canvas key -> index into graph.nodes / graph.edges */
  nodeIndex: Record<string, number>
  edgeIndex: Record<string, number>
  /** node id -> pending refs on that node (run mode) */
  pendingByNode: Record<string, PendingRef[]>
}

export interface CanvasOptions {
  typeOf: (type: string) => NodeTypeWire | undefined
  issues?: Issue[]
  backEdges?: EdgeRef[]
  state?: GraphStateResponse | null
  now?: Date
}

const edgeLabel = (e: EdgeRef) => `${e.source}.${e.source_port} → ${e.target}.${e.target_port}`

/** Keys unique on the canvas: duplicate domain ids get `~2`, `~3`… in server order. */
export function nodeKeys(graph: GraphWire): string[] {
  const seen = new Map<string, number>()
  return graph.nodes.map((n) => {
    const count = (seen.get(n.id) ?? 0) + 1
    seen.set(n.id, count)
    return count === 1 ? n.id : `${n.id}~${count}`
  })
}

/** Edge keys: the 4-tuple, plus `#n` for the nth duplicate. Delete by key, never by tuple. */
export function edgeKeys(graph: GraphWire): string[] {
  const seen = new Map<string, number>()
  return graph.edges.map((e) => {
    const base = `${e.source}.${e.source_port}>${e.target}.${e.target_port}`
    const count = (seen.get(base) ?? 0) + 1
    seen.set(base, count)
    return count === 1 ? base : `${base}#${count}`
  })
}

function portsFor(nodeId: string, type: NodeTypeWire | undefined, edges: EdgeWire[]): { ports: CanvasPort[]; readonly: boolean } {
  if (type) {
    return {
      readonly: false,
      ports: type.ports.map((p) => ({
        name: p.name,
        side: p.direction,
        kind: p.payload === null ? 'signal' : 'data',
        label: p.name,
        optional: p.direction === 'in' && !p.required,
      })),
    }
  }
  // A type the catalog does not know: read-only handles synthesized from the
  // edges that name this node, so those edges still have endpoints.
  const ins = [...new Set(edges.filter((e) => e.target === nodeId).map((e) => e.target_port))]
  const outs = [...new Set(edges.filter((e) => e.source === nodeId).map((e) => e.source_port))]
  return {
    readonly: true,
    ports: [
      ...ins.map((name) => ({ name, side: 'in' as const, kind: 'data' as const, label: name, optional: false })),
      ...outs.map((name) => ({ name, side: 'out' as const, kind: 'data' as const, label: name, optional: false })),
    ],
  }
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m ${String(sec).padStart(2, '0')}s`
}

export function toCanvas(graph: GraphWire, opts: CanvasOptions): CanvasModel {
  const nKeys = nodeKeys(graph)
  const eKeys = edgeKeys(graph)
  const state = opts.state && opts.state.kind === 'state' ? opts.state : null
  const now = opts.now ?? new Date()

  const nodeKeysById = new Map<string, string[]>()
  graph.nodes.forEach((n, i) => nodeKeysById.set(n.id, [...(nodeKeysById.get(n.id) ?? []), nKeys[i]]))
  const nodeIssueCount = new Map<string, number>()
  const edgeIssueCount = new Map<string, number>()
  const bump = (map: Map<string, number>, key: string) => map.set(key, (map.get(key) ?? 0) + 1)

  const issues: IssueItem[] = (opts.issues ?? []).map((issue, i) => {
    const t = issue.target
    let keys: string[] = []
    let label = 'graph'
    if (t.kind === 'node' && t.id) {
      keys = nodeKeysById.get(t.id) ?? []
      label = t.id
      keys.forEach((k) => bump(nodeIssueCount, k))
    } else if (t.kind === 'port' && t.node) {
      keys = nodeKeysById.get(t.node) ?? []
      label = `${t.node}.${t.port ?? ''}`
      keys.forEach((k) => bump(nodeIssueCount, k))
    } else if (t.kind === 'edge' && t.edge) {
      const ref = t.edge
      keys = graph.edges.map((e, j) => (sameEdge(e, ref) ? eKeys[j] : null)).filter((k): k is string => k !== null)
      label = edgeLabel(ref)
      keys.forEach((k) => bump(edgeIssueCount, k))
    }
    // A target that resolves to nothing (deleted since, or a canned mock
    // result) is a graph-level row, never a throw.
    return { key: `issue-${i}`, severity: issue.severity, message: issue.message, targetLabel: keys.length ? label : `${label} (not on canvas)`, focusKey: keys[0] ?? null }
  })

  const nodes: CanvasNode[] = graph.nodes.map((n, i) => {
    const { ports, readonly } = portsFor(n.id, opts.typeOf(n.type), graph.edges)
    const run = state?.nodes[n.id]
    const node: CanvasNode = {
      key: nKeys[i],
      title: n.label ?? n.id,
      subtitle: n.type,
      ports,
      issueCount: nodeIssueCount.get(nKeys[i]) ?? 0,
      position: n.position,
      readonly,
    }
    if (run) {
      node.status = run.status
      const elapsed = run.started_at
        ? formatElapsed((run.ended_at ? new Date(run.ended_at) : now).getTime() - new Date(run.started_at).getTime())
        : undefined
      node.metrics = {
        cost: run.cost_usd === null ? '—' : `$${run.cost_usd.toFixed(2)}`,
        elapsed,
        round: run.round > 1 ? `r${run.round}` : undefined,
      }
    }
    return node
  })

  const backEdges = opts.backEdges ?? []
  const edges: CanvasEdge[] = graph.edges.map((e, i) => {
    const edge: CanvasEdge = {
      key: eKeys[i],
      // An edge naming a duplicated id attaches to the first occurrence.
      from: { node: e.source, port: e.source_port },
      to: { node: e.target, port: e.target_port },
      label: e.label,
      backward: backEdges.some((b) => sameEdge(b, e)),
      issueCount: edgeIssueCount.get(eKeys[i]) ?? 0,
    }
    if (state && e.max_traversals !== undefined) {
      const used = state.edges.find((s) => sameEdge(s.edge, e))?.traversals ?? 0
      edge.counter = { used, max: e.max_traversals }
    }
    return edge
  })

  const pendingByNode: Record<string, PendingRef[]> = {}
  for (const p of state?.pending ?? []) (pendingByNode[p.node] ??= []).push(p)

  return {
    nodes,
    edges,
    issues,
    nodeIndex: Object.fromEntries(nKeys.map((k, i) => [k, i])),
    edgeIndex: Object.fromEntries(eKeys.map((k, i) => [k, i])),
    pendingByNode,
  }
}

/** "nodes.3.role.model" style paths from a shape error loc, relative to one element. */
export function locWithin(loc: (string | number)[], collection: 'nodes' | 'edges', index: number): string | null {
  if (loc[0] !== collection || loc[1] !== index) return null
  return loc.slice(2).join('.')
}

/** A readable document path for the YAML pane: nodes[3].id */
export function locLabel(loc: (string | number)[]): string {
  return loc.map((p, i) => (typeof p === 'number' ? `[${p}]` : i === 0 ? p : `.${p}`)).join('')
}
```
- [ ] **Step 4: Run it to verify it passes**

```bash
npm run test --workspace sdlc-dashboard -- src/adapters/graph.test.ts
npm run typecheck --workspace sdlc-dashboard
```

Expected: PASS — 12 tests; typecheck clean.
- [ ] **Step 5: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t13-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 graph adapter

toCanvas maps a wire graph plus catalog, issues, back edges and run
state onto canvas primitives: duplicate ids get distinct keys and every
duplicate carries the issue, edges key by 4-tuple plus occurrence, an
unknown type renders read-only handles from its edges, an issue whose
target resolves to nothing becomes graph-level, counters join traversals
with the pinned max_traversals, and backward comes only from the server.
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/adapters/graph.ts
git add interfaces/dashboard/frontend/src/adapters/graph.test.ts
git commit -F .workspace/tmp/e76-t13-msg.txt
```
### Task 14: Edit mode's store — pure edits + state machine

**Files:**
- Create: `interfaces/dashboard/frontend/src/stores/graphEdits.ts`, `interfaces/dashboard/frontend/src/stores/graphEditor.ts`
- Test: `interfaces/dashboard/frontend/src/stores/graphEdits.test.ts`, `interfaces/dashboard/frontend/src/stores/graphEditor.test.ts`

**Interfaces:**
- Consumes: Task 7 `api`, `useCatalogStore`, wire types; Task 13 `nodeKeys`, `edgeKeys`, `locWithin`.
- Produces: `graphEdits.ts` — `EditResult`, `freshId`, `addNode`, `moveNode` (M4), `idOfKey`, `connect` (M1), `removeElement` (by canvas key), `nodeEditCandidate` (rename cascade, M2, M3), `edgeEditCandidate`, `withoutEmptyLabel`. `graphEditor.ts` — `useGraphEditorStore()` with state `state: 'empty'|'text_broken'|'graph_loaded'`, `working`, `sha`, `savedSha`, `epoch`, `applying`, `selection`, `notice`, `yamlText`, `yamlDirty`, `yamlErrors`, `validation`, `inspectorErrors: FieldError[]`, `tidyRequest`, `canvasLocked`, `errorCount`, `runnable`, `selectedNode`, `selectedEdge`; actions `loadText`, `applyText`, `setYamlText`, `openYaml`, `loadGraph`, `newGraph`, `loadSha`, `openRunCopy`, `addNode`, `connect`, `move`, `remove`, `select`, `tidy`, `applyInspector`, `save`.

- [ ] **Step 1: Write the failing tests**

`interfaces/dashboard/frontend/src/stores/graphEdits.test.ts` (create; 117 lines):

```ts
import { describe, it, expect, vi } from 'vitest'
import {
  addNode, connect, edgeEditCandidate, freshId, idOfKey, moveNode, nodeEditCandidate, removeElement, withoutEmptyLabel,
} from './graphEdits'
import type { GraphWire } from '../api/graph-types'

const e = (source: string, source_port: string, target: string, target_port: string) => ({ source, source_port, target, target_port })
const G = (): GraphWire => ({
  schema_version: 1,
  nodes: [{ id: 'intake', type: 'intake' }, { id: 'architect', type: 'architect' }, { id: 'arch2', type: 'architect' }],
  edges: [e('intake', 'ok', 'architect', 'requirements'), e('architect', 'spec', 'arch2', 'requirements')],
})

describe('add', () => {
  it('uses default_id then the smallest free suffix', () => {
    const g = G()
    expect(freshId(g, 'plan')).toBe('plan')
    expect(freshId(g, 'intake')).toBe('intake_2')
    g.nodes.push({ id: 'intake_2', type: 'intake' })
    expect(freshId(g, 'intake')).toBe('intake_3')
  })
  it('adds a positioned node and selects it, never mutating the input', () => {
    const g = G()
    const r = addNode(g, 'gate.plan', 'gate_plan', 10, 20)
    expect(r.ok && r.graph.nodes.at(-1)).toEqual({ id: 'gate_plan', type: 'gate.plan', position: { x: 10, y: 20 } })
    expect(r.ok && r.select).toBe('gate_plan')
    expect(g.nodes).toHaveLength(3)
  })
})

describe('M4 non-finite positions', () => {
  it('keeps the previous value for a non-finite move', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const g = G()
    g.nodes[0].position = { x: 1, y: 2 }
    const r = moveNode(g, 'intake', NaN, 5)
    expect(r.ok && r.graph.nodes[0].position).toEqual({ x: 1, y: 2 })
    expect(warn).toHaveBeenCalled()
    expect(addNode(g, 'plan', 'plan', Infinity, 0).ok && (addNode(g, 'plan', 'plan', Infinity, 0) as { graph: GraphWire }).graph.nodes.at(-1)!.position).toBeUndefined()
    warn.mockRestore()
  })
  it('ignores a move for an unknown key', () => {
    const g = G()
    expect(moveNode(g, 'ghost', 1, 1)).toEqual({ ok: true, graph: g })
  })
})

describe('M1 connect', () => {
  it('adds a new edge by domain id and selects it', () => {
    const r = connect(G(), 'arch2', 'spec', 'architect', 'guidance')
    expect(r.ok && r.graph.edges.at(-1)).toEqual(e('arch2', 'spec', 'architect', 'guidance'))
    expect(r.ok && r.select).toBe('arch2.spec>architect.guidance')
  })
  it('selects the existing edge instead of adding a duplicate tuple', () => {
    const g = G()
    const r = connect(g, 'intake', 'ok', 'architect', 'requirements')
    expect(r.ok && r.graph).toBe(g)
    expect(r.ok && r.select).toBe('intake.ok>architect.requirements')
  })
  it('does not guard a self-loop: topology is validate’s', () => {
    const r = connect(G(), 'architect', 'spec', 'architect', 'guidance')
    expect(r.ok && r.graph.edges).toHaveLength(3)
  })
  it('resolves a duplicate canvas key to its domain id', () => {
    const g: GraphWire = { schema_version: 1, nodes: [{ id: 'a', type: 'intake' }, { id: 'a', type: 'intake' }], edges: [] }
    expect(idOfKey(g, 'a~2')).toBe('a')
  })
})

describe('remove', () => {
  it('removes one of two duplicate edges by key', () => {
    const g = G()
    g.edges.push(e('intake', 'ok', 'architect', 'requirements'))
    const r = removeElement(g, 'edge', 'intake.ok>architect.requirements#2')
    expect(r.ok && r.graph.edges.filter((x) => x.source === 'intake')).toHaveLength(1)
  })
  it('removes a node and its incident edges', () => {
    const r = removeElement(G(), 'node', 'architect')
    expect(r.ok && r.graph.nodes.map((n) => n.id)).toEqual(['intake', 'arch2'])
    expect(r.ok && r.graph.edges).toEqual([])
  })
  it('keeps edges when another node still carries the removed id', () => {
    const g = G()
    g.nodes.push({ id: 'architect', type: 'architect' })
    const r = removeElement(g, 'node', 'architect~2')
    expect(r.ok && r.graph.edges).toHaveLength(2)
  })
})

describe('inspector candidates', () => {
  it('cascades a rename to every incident edge in place', () => {
    const r = nodeEditCandidate(G(), 'architect', { id: 'designer', type: 'architect' })
    expect(r.ok && r.graph.edges).toEqual([e('intake', 'ok', 'designer', 'requirements'), e('designer', 'spec', 'arch2', 'requirements')])
    expect(r.ok && r.select).toBe('designer')
  })
  it('M2: refuses a rename onto an id another node uses, worded as a mechanic', () => {
    const r = nodeEditCandidate(G(), 'arch2', { id: 'architect', type: 'architect' })
    expect(r).toEqual({ ok: false, field: 'id', message: "'architect' is already used by another node, so renaming would merge their edges" })
  })
  it('M3: renames a duplicated id without rewriting edges, with a notice', () => {
    const g = G()
    g.nodes.push({ id: 'architect', type: 'architect' })
    const r = nodeEditCandidate(g, 'architect~2', { id: 'reviewer', type: 'architect' })
    expect(r.ok && r.graph.edges).toEqual(g.edges)
    expect(r.ok && r.notice).toBe("edges stay with 'architect': the id was ambiguous")
  })
  it('renaming to its own id is a plain edit', () => {
    const r = nodeEditCandidate(G(), 'intake', { id: 'intake', type: 'intake', label: 'Start' })
    expect(r.ok && r.graph.nodes[0]).toEqual({ id: 'intake', type: 'intake', label: 'Start' })
  })
  it('edits an edge by key and drops an emptied label', () => {
    const r = edgeEditCandidate(G(), 'intake.ok>architect.requirements', { ...e('intake', 'ok', 'architect', 'requirements'), max_traversals: 2 })
    expect(r.ok && r.graph.edges[0].max_traversals).toBe(2)
    expect(withoutEmptyLabel({ id: 'a', label: '' })).toEqual({ id: 'a' })
    expect(withoutEmptyLabel({ id: 'a', label: 'x' })).toEqual({ id: 'a', label: 'x' })
  })
})
```

`interfaces/dashboard/frontend/src/stores/graphEditor.test.ts` (create; 216 lines):

```ts
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import preCode from '../api/__fixtures__/graph/scenarios/pre_code.json'
import badYaml from '../api/__fixtures__/graph/scenarios/bad_yaml.json'
import soft from '../api/__fixtures__/graph/objects/pre_code_architecture_soft.json'
import renamedInvalid from '../api/__fixtures__/graph/objects/pre_code_intake_renamed_invalid.json'
import type { CatalogWire, GraphWire, ParseWire, ValidationWire } from '../api/graph-types'

type Deferred<T> = { promise: Promise<T>; resolve: (v: T) => void }
const deferred = <T>(): Deferred<T> => {
  let resolve!: (v: T) => void
  return { promise: new Promise<T>((r) => { resolve = r }), resolve }
}

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  parseGraph: vi.fn(),
  serializeGraph: vi.fn(),
  validateGraph: vi.fn(),
  saveGraph: vi.fn(),
  loadGraph: vi.fn(),
  getRunGraph: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

import { useGraphEditorStore } from './graphEditor'
import { useCatalogStore } from './catalog'

const PRE = preCode.parse as { ok: true; graph: GraphWire; sha: string }
const withCaps = (caps: Partial<CatalogWire['capabilities']>) =>
  ({ ...(catalogJson as unknown as CatalogWire), capabilities: { validate: false, save: false, load: false, run_graph: false, ...caps } })

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  useCatalogStore().catalog = withCaps({ validate: true, save: true })
  api.serializeGraph.mockResolvedValue({ ok: true, yaml: preCode.yaml })
  api.validateGraph.mockResolvedValue({ issues: [], back_edges: [] })
})
afterEach(() => { vi.useRealTimers() })

async function loaded() {
  const s = useGraphEditorStore()
  api.parseGraph.mockResolvedValueOnce(PRE)
  await s.loadText(preCode.yaml)
  return s
}

describe('states', () => {
  it('starts empty, loads recorded text into graph_loaded with its sha', async () => {
    const s = useGraphEditorStore()
    expect(s.state).toBe('empty')
    await loaded()
    expect(s.state).toBe('graph_loaded')
    expect(s.sha).toBe(PRE.sha)
    expect(s.yamlDirty).toBe(false)
  })

  it('shape-broken text goes text_broken with its errors and locks the canvas', async () => {
    const s = useGraphEditorStore()
    api.parseGraph.mockResolvedValueOnce(badYaml.parse)
    await s.loadText(badYaml.yaml)
    expect(s.state).toBe('text_broken')
    expect(s.yamlErrors[0].line).toBe(3)
    expect(s.canvasLocked).toBe(true)
    s.addNode('intake', 0, 0)
    expect(s.working).toBeNull()
  })

  it('a failed apply after a load goes text_broken too, keeping the last good copy', async () => {
    const s = await loaded()
    const good = s.working
    api.parseGraph.mockResolvedValueOnce(badYaml.parse)
    await s.loadText(badYaml.yaml)
    expect(s.state).toBe('text_broken')
    expect(s.canvasLocked).toBe(true)
    expect(s.working).toBe(good)
    api.parseGraph.mockResolvedValueOnce(PRE)
    await s.loadText(preCode.yaml)
    expect(s.state).toBe('graph_loaded')
  })

  it('refuses over-cap text without calling the server', async () => {
    const s = useGraphEditorStore()
    useCatalogStore().catalog = { ...withCaps({}), max_graph_bytes: 10 }
    await s.loadText('schema_version: 1\n')
    expect(api.parseGraph).not.toHaveBeenCalled()
    expect(s.yamlErrors[0].msg).toContain('exceeds 10 bytes')
  })
})

describe('D11 canvas operations never round-trip', () => {
  it('adds, connects, moves and removes locally, bumping the epoch each time', async () => {
    const s = await loaded()
    api.parseGraph.mockClear()
    const e0 = s.epoch
    s.addNode('gate.plan', 5, 5)
    expect(s.working!.nodes.at(-1)!.id).toBe('gate_plan')
    s.connect('planner', 'plan', 'gate_plan', 'artifact')
    s.move('gate_plan', 50, 60)
    s.remove('node', 'gate_plan')
    expect(s.epoch).toBe(e0 + 4)
    expect(api.parseGraph).not.toHaveBeenCalled()
    expect(s.working!.nodes.some((n) => n.id === 'gate_plan')).toBe(false)
  })
})

describe('epoch discards stale responses', () => {
  it('discards a validation dispatched before a later edit', async () => {
    vi.useFakeTimers()
    const s = await loaded()
    const pending = deferred<ValidationWire>()
    api.validateGraph.mockReturnValueOnce(pending.promise)
    await vi.advanceTimersByTimeAsync(400)
    s.move('intake', 1, 1)
    pending.resolve({ issues: [{ code: 'x', severity: 'error', message: 'stale', target: { kind: 'graph' } }], back_edges: [] })
    await vi.advanceTimersByTimeAsync(0)
    expect(s.validation).toBeNull()
  })

  it('discards a serialize dispatched before a later edit', async () => {
    const s = await loaded()
    const pending = deferred<{ ok: true; yaml: string }>()
    api.serializeGraph.mockReturnValueOnce(pending.promise)
    const opening = s.openYaml()
    s.move('intake', 2, 2)
    pending.resolve({ ok: true, yaml: 'STALE' })
    await opening
    expect(s.yamlText).not.toBe('STALE')
  })

  it('locks canvas operations while an inspector apply is in flight', async () => {
    const s = await loaded()
    s.select('architecture')
    const pending = deferred<ParseWire>()
    api.parseGraph.mockReturnValueOnce(pending.promise)
    const applying = s.applyInspector({ ...s.selectedNode!.node, gate: { policy: 'soft' } })
    expect(s.canvasLocked).toBe(true)
    const before = s.working
    s.move('intake', 9, 9)
    expect(s.working).toBe(before)
    pending.resolve(soft.parse as ParseWire)
    await applying
    expect(s.canvasLocked).toBe(false)
  })
})

describe('inspector apply', () => {
  it('commits the parsed graph on success', async () => {
    const s = await loaded()
    s.select('architecture')
    api.parseGraph.mockResolvedValueOnce(soft.parse)
    await s.applyInspector({ ...s.selectedNode!.node, gate: { policy: 'soft' } })
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: soft.graph })
    expect(s.working!.nodes.find((n) => n.id === 'architecture')!.gate).toEqual({ policy: 'soft' })
  })

  it('maps shape errors inside the element onto its fields and counts the rest', async () => {
    const s = await loaded()
    s.select('intake')
    api.parseGraph.mockResolvedValueOnce(renamedInvalid.parse)
    await s.applyInspector({ ...s.selectedNode!.node, id: 'Intake' })
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: renamedInvalid.graph })
    expect(s.inspectorErrors).toEqual([
      { path: 'id', msg: "String should match pattern '^[a-z][a-z0-9_]*$'" },
      { path: '', msg: '1 shape error(s) elsewhere in the graph' },
    ])
    expect(s.working!.nodes.some((n) => n.id === 'intake')).toBe(true)
  })

  it('M2 refuses a rename onto an in-use id without calling the server', async () => {
    const s = await loaded()
    s.select('planner')
    api.parseGraph.mockClear()
    await s.applyInspector({ ...s.selectedNode!.node, id: 'architect' })
    expect(api.parseGraph).not.toHaveBeenCalled()
    expect(s.inspectorErrors[0]).toEqual({ path: 'id', msg: "'architect' is already used by another node, so renaming would merge their edges" })
  })
})

describe('save', () => {
  it('records the sha and the validation it returned', async () => {
    const s = await loaded()
    api.saveGraph.mockResolvedValueOnce({ ok: true, sha: PRE.sha, validation: { issues: [], back_edges: [] } })
    await s.save()
    expect(s.savedSha).toBe(PRE.sha)
    expect(s.runnable).toBe(true)
  })

  it('counts error issues for the not-runnable badge, ignoring warnings (U6)', async () => {
    const s = await loaded()
    api.saveGraph.mockResolvedValueOnce({
      ok: true,
      sha: PRE.sha,
      validation: {
        issues: [
          { code: 'a', severity: 'error', message: 'x', target: { kind: 'graph' } },
          { code: 'b', severity: 'error', message: 'y', target: { kind: 'graph' } },
          { code: 'c', severity: 'warning', message: 'z', target: { kind: 'graph' } },
        ],
        back_edges: [],
      },
    })
    await s.save()
    expect(s.errorCount).toBe(2)
    expect(s.runnable).toBe(false)
  })

  it('does nothing when the server does not declare save', async () => {
    const s = await loaded()
    useCatalogStore().catalog = withCaps({})
    await s.save()
    expect(api.saveGraph).not.toHaveBeenCalled()
  })
})
```
- [ ] **Step 2: Run them to verify they fail**

```bash
npm run test --workspace sdlc-dashboard -- src/stores/graphEdits.test.ts src/stores/graphEditor.test.ts
```

Expected: FAIL — cannot resolve `./graphEdits` / `./graphEditor`.
- [ ] **Step 3: Write the pure edits**

`interfaces/dashboard/frontend/src/stores/graphEdits.ts` (create; 130 lines):

```ts
// Pure edit operations on a working copy (E-76 spec §8.2-§8.3). Each returns
// a NEW graph; none decides legality. The edit-mechanics register (M1-M4) is
// the complete set of guards: each protects the editor's own addressing or
// reversibility, removes no expressiveness (text apply still reaches every
// graph), and reports nothing as a validation result.
import type { EdgeWire, GraphWire, NodeWire } from '../api/graph-types'
import { edgeKeys, nodeKeys } from '../adapters/graph'

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

export type EditResult =
  | { ok: true; graph: GraphWire; select?: string | null; notice?: string }
  | { ok: false; field: string; message: string }

/** A fresh id: the catalog's Python-computed default_id, then _2, _3... (smallest free). */
export function freshId(graph: GraphWire, defaultId: string): string {
  const used = new Set(graph.nodes.map((n) => n.id))
  if (!used.has(defaultId)) return defaultId
  let n = 2
  while (used.has(`${defaultId}_${n}`)) n++
  return `${defaultId}_${n}`
}

// M4: a non-finite coordinate serializes as JSON null and fails NodePosition.
const finite = (x: number, y: number) => Number.isFinite(x) && Number.isFinite(y)

export function addNode(graph: GraphWire, type: string, defaultId: string, x: number, y: number): EditResult {
  const g = clone(graph)
  const id = freshId(g, defaultId)
  const node: NodeWire = { id, type }
  if (finite(x, y)) node.position = { x, y }
  g.nodes.push(node)
  return { ok: true, graph: g, select: id }
}

export function moveNode(graph: GraphWire, key: string, x: number, y: number): EditResult {
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0 || !finite(x, y)) {
    if (!finite(x, y)) console.warn(`graph editor: dropped non-finite position for ${key}`)
    return { ok: true, graph }  // M4 / unknown key: keep the previous value
  }
  const g = clone(graph)
  g.nodes[index].position = { x, y }
  return { ok: true, graph: g }
}

/** Canvas key -> domain id (a duplicate key `id~2` names domain id `id`). */
export function idOfKey(graph: GraphWire, key: string): string | null {
  const index = nodeKeys(graph).indexOf(key)
  return index < 0 ? null : graph.nodes[index].id
}

export function connect(graph: GraphWire, fromKey: string, fromPort: string, toKey: string, toPort: string): EditResult {
  const source = idOfKey(graph, fromKey)
  const target = idOfKey(graph, toKey)
  if (source === null || target === null) return { ok: true, graph }
  const edge: EdgeWire = { source, source_port: fromPort, target, target_port: toPort }
  // M1: the 4-tuple IS edge identity; a second bare copy is unaddressable on
  // the canvas, so connecting onto an existing tuple selects it instead.
  const existing = graph.edges.findIndex(
    (e) => e.source === source && e.source_port === fromPort && e.target === target && e.target_port === toPort,
  )
  if (existing >= 0) return { ok: true, graph, select: edgeKeys(graph)[existing] }
  const g = clone(graph)
  g.edges.push(edge)
  return { ok: true, graph: g, select: edgeKeys(g)[g.edges.length - 1] }
}

export function removeElement(graph: GraphWire, kind: 'node' | 'edge', key: string): EditResult {
  const g = clone(graph)
  if (kind === 'edge') {
    // By canvas key (4-tuple + occurrence), never by tuple: deleting one of
    // two duplicate edges deletes one.
    const index = edgeKeys(graph).indexOf(key)
    if (index >= 0) g.edges.splice(index, 1)
    return { ok: true, graph: g, select: null }
  }
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0) return { ok: true, graph }
  const [removed] = g.nodes.splice(index, 1)
  // Incident edges go with the node -- unless another node still carries the
  // id, in which case those edges cannot be attributed to the deleted copy.
  if (!g.nodes.some((n) => n.id === removed.id)) {
    g.edges = g.edges.filter((e) => e.source !== removed.id && e.target !== removed.id)
  }
  return { ok: true, graph: g, select: null }
}

/**
 * The inspector's candidate graph for a node edit (spec §8.3). A rename
 * rewrites every incident edge endpoint in place, no reordering -- except:
 * M2 refuses a rename onto an id another node uses (the cascade would merge
 * edge sets irreversibly); M3 renames a node whose own id is duplicated
 * WITHOUT touching edges (they cannot be attributed to one copy).
 */
export function nodeEditCandidate(graph: GraphWire, key: string, next: NodeWire): EditResult {
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0) return { ok: false, field: '', message: 'the node is no longer on the canvas' }
  const old = graph.nodes[index]
  const g = clone(graph)
  g.nodes[index] = clone(next)
  if (next.id === old.id) return { ok: true, graph: g }
  const others = graph.nodes.filter((_, i) => i !== index)
  if (others.some((n) => n.id === next.id)) {
    return { ok: false, field: 'id', message: `'${next.id}' is already used by another node, so renaming would merge their edges` }
  }
  if (others.some((n) => n.id === old.id)) {
    return { ok: true, graph: g, select: next.id, notice: `edges stay with '${old.id}': the id was ambiguous` }
  }
  for (const e of g.edges) {
    if (e.source === old.id) e.source = next.id
    if (e.target === old.id) e.target = next.id
  }
  return { ok: true, graph: g, select: next.id }
}

export function edgeEditCandidate(graph: GraphWire, key: string, next: EdgeWire): EditResult {
  const index = edgeKeys(graph).indexOf(key)
  if (index < 0) return { ok: false, field: '', message: 'the edge is no longer on the canvas' }
  const g = clone(graph)
  g.edges[index] = clone(next)
  return { ok: true, graph: g }
}

/** Clearing a label removes the field; never writes ''. */
export function withoutEmptyLabel<T extends { label?: string }>(element: T): T {
  if (element.label !== '') return element
  const { label: _label, ...rest } = element
  return rest as T
}
```
- [ ] **Step 4: Write the store**

`interfaces/dashboard/frontend/src/stores/graphEditor.ts` (create; 259 lines):

```ts
// The edit-mode state machine (E-76 spec §8). Canvas operations mutate the
// working copy locally and never round-trip (D11); only text and inspector
// APPLY go through the server parse. Every async response carries the epoch
// it was dispatched at and is discarded if the working copy moved since.
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { api } from '../api/client'
import type { EdgeWire, GraphWire, NodeWire, ShapeError, ValidationWire } from '../api/graph-types'
import { useCatalogStore } from './catalog'
import {
  addNode as addNodeOp, connect as connectOp, edgeEditCandidate, moveNode, nodeEditCandidate, removeElement,
  withoutEmptyLabel, type EditResult,
} from './graphEdits'
import { edgeKeys, locWithin, nodeKeys } from '../adapters/graph'

export type EditorState = 'empty' | 'text_broken' | 'graph_loaded'
export interface FieldError { path: string; msg: string }

const VALIDATE_DEBOUNCE_MS = 400

export const useGraphEditorStore = defineStore('graphEditor', () => {
  const catalog = useCatalogStore()

  const state = ref<EditorState>('empty')
  const working = shallowRef<GraphWire | null>(null)
  const sha = ref<string | null>(null)          // sha of the working copy, when known
  const savedSha = ref<string | null>(null)
  const epoch = ref(0)
  const applying = ref(false)
  const selection = ref<string | null>(null)
  const notice = ref<string | null>(null)

  const yamlText = ref('')
  const yamlDirty = ref(false)
  const yamlErrors = ref<ShapeError[]>([])
  const validation = shallowRef<ValidationWire | null>(null)
  const inspectorErrors = ref<FieldError[]>([])
  const tidyRequest = ref(0)

  let validateTimer: ReturnType<typeof setTimeout> | null = null

  const canvasLocked = computed(() => applying.value || state.value !== 'graph_loaded')
  const errorCount = computed(() => validation.value?.issues.filter((i) => i.severity === 'error').length ?? 0)
  const runnable = computed(() => validation.value !== null && errorCount.value === 0)

  function commit(graph: GraphWire, opts: { sha?: string | null } = {}) {
    working.value = graph
    sha.value = opts.sha ?? null
    epoch.value += 1
    state.value = 'graph_loaded'
    scheduleValidate()
  }

  function scheduleValidate() {
    if (!catalog.can('validate') || !working.value) return
    if (validateTimer) clearTimeout(validateTimer)
    validateTimer = setTimeout(async () => {
      const at = epoch.value
      const graph = working.value
      if (!graph) return
      try {
        const result = await api.validateGraph(graph)
        if (at === epoch.value) validation.value = result   // stale results are discarded
      } catch (e) {
        if (at === epoch.value) notice.value = `validation failed: ${String(e)}`
      }
    }, VALIDATE_DEBOUNCE_MS)
  }

  function applyEdit(result: EditResult) {
    if (!result.ok || !working.value) return
    if (result.graph !== working.value) commit(result.graph)
    if (result.select !== undefined) selection.value = result.select
    if (result.notice) notice.value = result.notice
  }

  // --- loading -------------------------------------------------------------------

  const tooLarge = (body: unknown) =>
    catalog.catalog !== null && new TextEncoder().encode(JSON.stringify(body)).length > catalog.catalog.max_graph_bytes

  async function applyText() {
    if (applying.value) return
    const body = { yaml: yamlText.value }
    if (tooLarge(body)) {
      yamlErrors.value = [{ loc: [], msg: `graph text exceeds ${catalog.catalog?.max_graph_bytes} bytes`, line: null, column: null }]
      return
    }
    applying.value = true
    const at = epoch.value
    try {
      const result = await api.parseGraph(body)
      if (at !== epoch.value) return
      if (result.ok) {
        yamlErrors.value = []
        yamlDirty.value = false
        validation.value = null
        commit(result.graph, { sha: result.sha })
      } else {
        // U5: the canvas stays disabled until the text parses, even when a
        // graph was loaded before; the last good working copy is kept, and a
        // successful apply replaces it.
        yamlErrors.value = result.shape_errors
        state.value = 'text_broken'
      }
    } finally {
      applying.value = false
    }
  }

  function loadText(text: string) {
    yamlText.value = text
    yamlDirty.value = true
    return applyText()
  }

  function setYamlText(text: string) {
    yamlText.value = text
    yamlDirty.value = true
  }

  async function openYaml() {
    if (!working.value || yamlDirty.value) return
    const at = epoch.value
    const result = await api.serializeGraph(working.value)
    if (at !== epoch.value) return
    if (result.ok) {
      yamlText.value = result.yaml
      yamlErrors.value = []
    } else {
      yamlErrors.value = result.shape_errors
    }
  }

  function loadGraph(graph: GraphWire, graphSha: string | null) {
    validation.value = null
    selection.value = null
    yamlDirty.value = false
    commit(graph, { sha: graphSha })
    void openYaml()
  }

  function newGraph() {
    loadGraph({ schema_version: 1, nodes: [], edges: [] }, null)
  }

  async function loadSha(graphSha: string) {
    const result = await api.loadGraph(graphSha)
    if (result.ok) loadGraph(result.graph, result.sha)
    else notice.value = `no saved graph ${graphSha}`
  }

  async function openRunCopy(runId: string) {
    const result = await api.getRunGraph(runId)
    if (result.kind === 'graph') loadGraph(result.graph, null)   // a copy: no sha association
    else notice.value = 'this run predates graph execution'
  }

  // --- canvas operations (D11: local, never a round trip) ----------------------------

  function addNode(type: string, x: number, y: number) {
    const spec = catalog.typeOf(type)
    if (canvasLocked.value || !working.value || !spec) return
    applyEdit(addNodeOp(working.value, type, spec.default_id, x, y))
  }
  function connect(fromKey: string, fromPort: string, toKey: string, toPort: string) {
    if (canvasLocked.value || !working.value) return
    applyEdit(connectOp(working.value, fromKey, fromPort, toKey, toPort))
  }
  function move(key: string, x: number, y: number) {
    if (canvasLocked.value || !working.value) return
    applyEdit(moveNode(working.value, key, x, y))
  }
  function remove(kind: 'node' | 'edge', key: string) {
    if (canvasLocked.value || !working.value) return
    applyEdit(removeElement(working.value, kind, key))
  }
  function select(key: string | null) {
    selection.value = key
    inspectorErrors.value = []
  }
  function tidy() {
    if (!canvasLocked.value) tidyRequest.value += 1
  }

  // --- inspector apply (the only canvas-side round trip) ------------------------------

  const selectedNode = computed<{ index: number; node: NodeWire } | null>(() => {
    if (!working.value || !selection.value) return null
    const index = nodeKeys(working.value).indexOf(selection.value)
    return index < 0 ? null : { index, node: working.value.nodes[index] }
  })
  const selectedEdge = computed<{ index: number; edge: EdgeWire } | null>(() => {
    if (!working.value || !selection.value) return null
    const index = edgeKeys(working.value).indexOf(selection.value)
    return index < 0 ? null : { index, edge: working.value.edges[index] }
  })

  async function applyInspector(next: NodeWire | EdgeWire) {
    if (!working.value || !selection.value || applying.value) return
    const isNode = selectedNode.value !== null
    const index = isNode ? selectedNode.value!.index : selectedEdge.value?.index
    if (index === undefined) return
    const candidate = isNode
      ? nodeEditCandidate(working.value, selection.value, withoutEmptyLabel(next as NodeWire))
      : edgeEditCandidate(working.value, selection.value, withoutEmptyLabel(next as EdgeWire))
    if (!candidate.ok) {
      inspectorErrors.value = [{ path: candidate.field, msg: candidate.message }]
      return
    }
    applying.value = true
    const at = epoch.value
    try {
      const result = await api.parseGraph({ graph: candidate.graph })
      if (at !== epoch.value) {
        inspectorErrors.value = [{ path: '', msg: 'the graph changed — apply again' }]
        return
      }
      if (result.ok) {
        inspectorErrors.value = []
        commit(result.graph, { sha: result.sha })
        if (candidate.select !== undefined) selection.value = candidate.select
        if (candidate.notice) notice.value = candidate.notice
      } else {
        const collection = isNode ? 'nodes' : 'edges'
        const mine = result.shape_errors
          .map((err) => ({ path: locWithin(err.loc, collection, index), msg: err.msg }))
          .filter((err): err is FieldError => err.path !== null)
        const elsewhere = result.shape_errors.length - mine.length
        inspectorErrors.value = elsewhere > 0 ? [...mine, { path: '', msg: `${elsewhere} shape error(s) elsewhere in the graph` }] : mine
      }
    } finally {
      applying.value = false
    }
  }

  // --- save ------------------------------------------------------------------------

  async function save() {
    if (!working.value || !catalog.can('save') || applying.value) return
    const at = epoch.value
    const result = await api.saveGraph(working.value)
    if (at !== epoch.value) return
    if (result.ok) {
      savedSha.value = result.sha
      sha.value = result.sha
      if (result.validation) validation.value = result.validation
    } else {
      notice.value = `save refused: ${result.shape_errors.length} shape error(s)`
    }
  }

  return {
    state, working, sha, savedSha, epoch, applying, selection, notice, yamlText, yamlDirty, yamlErrors,
    validation, inspectorErrors, tidyRequest, canvasLocked, errorCount, runnable, selectedNode, selectedEdge,
    loadText, applyText, setYamlText, openYaml, loadGraph, newGraph, loadSha, openRunCopy,
    addNode, connect, move, remove, select, tidy, applyInspector, save,
  }
})
```
- [ ] **Step 5: Run them to verify they pass**

```bash
npm run test --workspace sdlc-dashboard -- src/stores/graphEdits.test.ts src/stores/graphEditor.test.ts
npm run typecheck --workspace sdlc-dashboard
```

Expected: PASS — graphEdits 16, graphEditor 14; typecheck clean.
- [ ] **Step 6: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 7: Commit**

Write `.workspace/tmp/e76-t14-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 graph editor store

Canvas operations -- add, connect, move, delete -- mutate the working
copy locally and never round-trip (D11); only text and inspector applies go
through the server parse. Every async response carries the epoch it was
dispatched at and is discarded if the copy moved since, and canvas
operations lock while an apply is in flight. The edit-mechanics register is
exactly M1-M4: connect onto an existing tuple selects it, a rename onto an
in-use id is refused, a duplicated id renames without touching edges, and
non-finite positions are dropped. A failed text apply goes text_broken
even after a load (U5).
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/stores/graphEdits.ts
git add interfaces/dashboard/frontend/src/stores/graphEdits.test.ts
git add interfaces/dashboard/frontend/src/stores/graphEditor.ts
git add interfaces/dashboard/frontend/src/stores/graphEditor.test.ts
git commit -F .workspace/tmp/e76-t14-msg.txt
```
### Task 15: Run mode's store — `runGraph.ts`

**Files:**
- Create: `interfaces/dashboard/frontend/src/stores/runGraph.ts`
- Test: `interfaces/dashboard/frontend/src/stores/runGraph.test.ts`

**Interfaces:**
- Consumes: Task 7 `api`, `useCatalogStore`; Task 6 `isNotFound`; existing `useUiStore().toast`.
- Produces: `useRunGraphStore()` — `runId`, `graph: GraphResponse | null`, `state: GraphStateResponse | null`, `error`, `connectionLost`, `inFlight: Set<string>`; `start(runId)`, `stop()`, `decide(key, outcome, comment)`.

- [ ] **Step 1: Write the failing test**

`interfaces/dashboard/frontend/src/stores/runGraph.test.ts` (create; 141 lines):

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import { HttpStatusError } from '../api/errors'
import type { CatalogWire, GraphStateResponse } from '../api/graph-types'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  getRunGraph: vi.fn(),
  subscribeGraphState: vi.fn(),
  decideGate: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

import { useRunGraphStore } from './runGraph'
import { useCatalogStore } from './catalog'
import { useUiStore } from './ui'

const GRAPH = { kind: 'graph' as const, sha: 'sha-1', graph: { schema_version: 1 as const, nodes: [], edges: [] }, back_edges: [] }
const state = (over: Partial<Extract<GraphStateResponse, { kind: 'state' }>> = {}): GraphStateResponse => ({
  kind: 'state', graph_sha: 'sha-1', nodes: {}, edges: [], current_nodes: [], terminal: null,
  pending: [{ node: 'architecture', key: 'architecture#2', kind: 'gate' }], ...over,
})

let deliver: (s: GraphStateResponse) => void
let onErr: (n: number) => void
const unsubscribe = vi.fn()

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  const catalog = useCatalogStore()
  catalog.catalog = { ...(catalogJson as unknown as CatalogWire), capabilities: { validate: false, save: false, load: false, run_graph: true } }
  api.getCatalog.mockResolvedValue(catalog.catalog)
  api.getRunGraph.mockResolvedValue(GRAPH)
  api.subscribeGraphState.mockImplementation((_id, cb, err) => { deliver = cb; onErr = err; return unsubscribe })
  vi.spyOn(useUiStore(), 'toast').mockImplementation(() => {})
})

describe('lifecycle', () => {
  it('subscribes after loading the graph and unsubscribes on stop', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    expect(api.subscribeGraphState).toHaveBeenCalledWith('r1', expect.any(Function), expect.any(Function))
    s.stop()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('never subscribes for a run superseded while its graph was loading', async () => {
    let resolveGraph!: (v: unknown) => void
    api.getRunGraph.mockReturnValueOnce(new Promise((r) => { resolveGraph = r }))
    const s = useRunGraphStore()
    const first = s.start('r1')
    await Promise.resolve()
    s.stop()
    resolveGraph(GRAPH)
    await first
    expect(api.subscribeGraphState).not.toHaveBeenCalled()
  })

  it('does not subscribe for a legacy run or without the run_graph capability', async () => {
    api.getRunGraph.mockResolvedValueOnce({ kind: 'no_graph', reason: 'legacy_run' })
    const s = useRunGraphStore()
    await s.start('legacy')
    expect(s.graph).toEqual({ kind: 'no_graph', reason: 'legacy_run' })
    useCatalogStore().catalog = { ...useCatalogStore().catalog!, capabilities: { validate: false, save: false, load: false, run_graph: false } }
    await s.start('r2')
    expect(api.getRunGraph).toHaveBeenCalledTimes(1)
    expect(api.subscribeGraphState).not.toHaveBeenCalled()
  })

  it('surfaces a sha mismatch as an error and stops, without refetching', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    deliver(state({ graph_sha: 'other' }))
    expect(s.error).toContain('other')
    expect(unsubscribe).toHaveBeenCalled()
    expect(api.getRunGraph).toHaveBeenCalledTimes(1)
  })

  it('reports connection loss from the provider failure count', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    onErr(3)
    expect(s.connectionLost).toBe(true)
    onErr(0)
    expect(s.connectionLost).toBe(false)
  })

  it('skips a state identical to the last one', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    const a = state()
    deliver(a)
    deliver(JSON.parse(JSON.stringify(a)))
    expect(s.state).toBe(a)
  })
})

describe('gate decisions in flight', () => {
  it('keeps a key busy through a stale state and clears it once the key disappears', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    deliver(state())
    api.decideGate.mockResolvedValueOnce(undefined)
    await s.decide('architecture#2', 'approve', '')
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'architecture#2', 'approve', '')
    deliver(state({ current_nodes: ['architecture'] }))   // stale: still pending
    expect(s.inFlight.has('architecture#2')).toBe(true)
    deliver(state({ pending: [] }))
    expect(s.inFlight.has('architecture#2')).toBe(false)
  })

  it('ignores a second submit for a key already in flight', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    api.decideGate.mockReturnValueOnce(new Promise(() => {}))
    void s.decide('architecture#2', 'approve', '')
    await s.decide('architecture#2', 'reject', '')
    expect(api.decideGate).toHaveBeenCalledTimes(1)
  })

  it('re-enables after a non-404 failure', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    api.decideGate.mockRejectedValueOnce(new HttpStatusError(502, 'down'))
    await s.decide('architecture#2', 'approve', '')
    expect(s.inFlight.has('architecture#2')).toBe(false)
  })

  it('after a 404 stays busy until the next state, then clears even if still listed', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    api.decideGate.mockRejectedValueOnce(new HttpStatusError(404, 'gone'))
    await s.decide('architecture#2', 'approve', '')
    expect(s.inFlight.has('architecture#2')).toBe(true)
    deliver(state())
    expect(s.inFlight.has('architecture#2')).toBe(false)
    expect(useUiStore().toast).toHaveBeenCalledWith('this gate was already decided elsewhere', expect.any(String))
  })
})
```
- [ ] **Step 2: Run it to verify it fails**

```bash
npm run test --workspace sdlc-dashboard -- src/stores/runGraph.test.ts
```

Expected: FAIL — cannot resolve `./runGraph`.
- [ ] **Step 3: Write the store**

`interfaces/dashboard/frontend/src/stores/runGraph.ts` (create; 104 lines):

```ts
// Run mode's live state (E-76 spec §7.3, §9). One subscription per RunView;
// the view calls stop() on unmount and on run change. Gate decisions in flight
// are tracked HERE by key, never in component state, so a stale poll cannot
// re-enable the controls.
import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { api } from '../api/client'
import { isNotFound } from '../api/errors'
import type { GateOutcome } from '../api/types'
import type { GraphResponse, GraphStateResponse } from '../api/graph-types'
import { useCatalogStore } from './catalog'
import { useUiStore } from './ui'

export const useRunGraphStore = defineStore('runGraph', () => {
  const catalog = useCatalogStore()
  const ui = useUiStore()

  const runId = ref<string | null>(null)
  const graph = shallowRef<GraphResponse | null>(null)
  const state = shallowRef<GraphStateResponse | null>(null)
  const error = ref<string | null>(null)
  const connectionLost = ref(false)
  const inFlight = ref<Set<string>>(new Set())
  // A key whose decide 404'd stays busy for exactly one more state.
  const lostRace = new Set<string>()

  let unsubscribe: (() => void) | null = null
  let lastFingerprint = ''
  let generation = 0

  function stop() {
    unsubscribe?.()
    unsubscribe = null
    generation += 1
  }

  function receive(next: GraphStateResponse) {
    const fingerprint = JSON.stringify(next)
    if (fingerprint === lastFingerprint) return
    lastFingerprint = fingerprint
    const g = graph.value
    if (next.kind === 'state' && g?.kind === 'graph' && next.graph_sha !== g.sha) {
      // The pin broke (FR-1203): surface it, never refetch silently.
      error.value = `run state is for graph ${next.graph_sha}, but the run pins ${g.sha}`
      stop()
      return
    }
    state.value = next
    const listed = new Set(next.kind === 'state' ? next.pending.map((p) => p.key) : [])
    for (const key of [...inFlight.value]) {
      if (!listed.has(key) || lostRace.has(key)) {
        inFlight.value.delete(key)
        lostRace.delete(key)
      }
    }
    inFlight.value = new Set(inFlight.value)
  }

  async function start(id: string) {
    stop()
    const mine = generation
    runId.value = id
    graph.value = null
    state.value = null
    error.value = null
    connectionLost.value = false
    inFlight.value = new Set()
    lastFingerprint = ''
    await catalog.load()
    if (mine !== generation) return
    if (!catalog.can('run_graph')) return
    try {
      const response = await api.getRunGraph(id)
      if (mine !== generation) return
      graph.value = response
      if (response.kind === 'no_graph') return
      unsubscribe = api.subscribeGraphState(id, receive, (failures) => { connectionLost.value = failures >= 3 })
    } catch (e) {
      if (mine === generation) error.value = String(e)
    }
  }

  async function decide(key: string, outcome: GateOutcome, comment: string) {
    const id = runId.value
    if (!id || inFlight.value.has(key)) return
    inFlight.value = new Set(inFlight.value).add(key)
    try {
      await api.decideGate(id, key, outcome, comment)
    } catch (e) {
      if (isNotFound(e)) {
        // FR-302: another surface decided first. Busy until the next state.
        ui.toast('this gate was already decided elsewhere', 'var(--status-blocked)')
        lostRace.add(key)
      } else {
        ui.toast(`decision failed: ${String(e)}`, 'var(--status-failed)')
        const next = new Set(inFlight.value)
        next.delete(key)
        inFlight.value = next
      }
    }
  }

  return { runId, graph, state, error, connectionLost, inFlight, start, stop, decide }
})
```
- [ ] **Step 4: Run it to verify it passes**

```bash
npm run test --workspace sdlc-dashboard -- src/stores/runGraph.test.ts
npm run typecheck --workspace sdlc-dashboard
```

Expected: PASS — 10 tests; typecheck clean.
- [ ] **Step 5: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t15-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 run graph store

start() loads the pinned graph and subscribes to run state only when the
server declares run_graph and the run has a graph; a start superseded
mid-load never subscribes. A graph_sha that differs from the pin is an
error that stops the subscription, never a silent refetch. Gate decisions
in flight are tracked by key in the store: a stale state cannot re-enable
the controls, and a 404 (another surface decided first, FR-302) toasts and
clears on the next state.
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/stores/runGraph.ts
git add interfaces/dashboard/frontend/src/stores/runGraph.test.ts
git commit -F .workspace/tmp/e76-t15-msg.txt
```
### Task 16: Edit mode — `/graphs`, the inspector, the GRAPHS tab

**Files:**
- Create: `interfaces/dashboard/frontend/src/views/GraphEditorView.vue`, `interfaces/dashboard/frontend/src/components/graph/GraphInspector.vue`
- Replace: `interfaces/dashboard/frontend/src/router.ts`, `interfaces/ui/src/components/app_header/AppHeader.vue`, `interfaces/ui/src/components/app_header/app_header.spec.ts`
- Test: `interfaces/dashboard/frontend/src/components/graph/schemaCoverage.test.ts`; `interfaces/ui/app.md` (CONSOLE-7, CONSOLE-9) + `interfaces/ui/app.pw.ts` (append)

**Interfaces:**
- Consumes: Tasks 7, 9, 10, 11, 12, 13, 14.
- Produces: route `/graphs` (name `graphs`) accepting `?from=run:<id>` (a copy) and `?sha=<sha>` (when `load` is declared); `AppHeader` `activeTab` accepts `'graphs'` and renders a GRAPHS tab (`data-testid="graphs-tab"`).

- [ ] **Step 1: Write the failing and guard tests**

`interfaces/dashboard/frontend/src/components/graph/schemaCoverage.test.ts` (create/replace; 30 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from '@kroker/ui/components/schema_form/SchemaForm.vue'
import { classify, fullySupported } from '@kroker/ui/components/schema_form/schema'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'

// SCHEMA_FORM-3 against the backend's RECORDED schema: the dashboard is the
// tier allowed to import recordings (the ui package never names a Kroker
// model). Python mirrors this in tests/test_dashboard_graph_wire.py.
const catalog = catalogJson as unknown as CatalogWire

describe('schema_form over the recorded GraphNode / GraphEdge schemas', () => {
  it.each(['GraphNode', 'GraphEdge'] as const)('classifies every %s property as supported', (name) => {  // clause: SCHEMA_FORM-3
    const schema = catalog.schemas[name] as Record<string, unknown>
    const field = classify(schema, (schema.$defs ?? {}) as Record<string, Record<string, unknown>>)
    expect(fullySupported(field)).toBe(true)
  })

  it('renders no fallback for a node carrying a role and a gate', () => {  // clause: SCHEMA_FORM-3
    const w = mount(SchemaForm, {
      props: {
        schema: catalog.schemas.GraphNode,
        value: { id: 'architect', type: 'architect', role: { kind: 'proposer', model: 'm' }, gate: { policy: 'soft' } },
      },
    })
    expect(w.findAll('[data-testid="schema-field"]').length).toBeGreaterThan(15)
    expect(w.find('[data-testid="schema-fallback"]').exists()).toBe(false)
  })
})
```

`interfaces/ui/src/components/app_header/app_header.spec.ts` (create/replace; 53 lines):

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

describe('AppHeader', () => {
  it('renders brand, tabs, and supplied stats', () => {  // clause: APP_HEADER-1
    const w = mount(AppHeader, {
      props: {
        activeCount: 7,
        maxCount: 50,
        totalCost: '$19.80',
        inboxCount: 2,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.text()).toContain('SDLC·FACTORY')
    expect(w.text()).toContain('FLEET')
    expect(w.text()).toContain('INBOX')
    expect(w.text()).toContain('GRAPHS')
    expect(w.text()).toContain('runs 7/50')
    expect(w.text()).toContain('spend today $19.80')
  })

  it('omits inbox badge when count is zero, never rendering 0', () => {  // clause: APP_HEADER-1.1
    const w = mount(AppHeader, {
      props: { inboxCount: 0 },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.find('[data-testid="inbox-count"]').exists()).toBe(false)
  })

  it('applies tab-active stable class to active tab', () => {  // clause: APP_HEADER-2
    const w = mount(AppHeader, {
      props: { activeTab: 'inbox' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    const tabs = w.findAll('.tab')
    expect(tabs[1].classes()).toContain('tab-active')
  })

  it('emits start-run when start button is clicked', async () => {
    const w = mount(AppHeader, {
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(w.emitted('start-run')).toHaveLength(1)
  })
})
```

`schemaCoverage.test.ts` passes on arrival — it pins Task 11's `schema_form` against the **recorded** GraphNode/GraphEdge schemas (SCHEMA_FORM-3), which only the dashboard tier may import. `app_header.spec.ts` gains the GRAPHS assertion and fails until Step 4.
- [ ] **Step 2: Append CONSOLE-7 and CONSOLE-9**

In `interfaces/ui/app.md`, insert before `## Failure modes`:

```markdown
### CONSOLE-7
The graph editor renders the canvas after applying well-shaped recorded text,
and keeps the canvas disabled while showing shape errors after applying text
that does not parse. [FR-1205, E-76 U5]

### CONSOLE-9
In the graph editor, editing one inspector field of a recorded graph and
applying it round-trips through the provider's parse and commits: the
working copy gains the parse's sha and the inspector shows no error. [FR-1205,
E-76 U8]
```

Append to `interfaces/ui/app.pw.ts`:

```ts
test('the editor renders recorded text and holds shape errors with the canvas disabled', async ({ page }) => {  // clause: CONSOLE-7
  await page.goto('/#/graphs?from=run:feature-graph-demo')
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await page.locator('[data-testid="tab-yaml"]').click()
  const text = page.locator('[data-testid="yaml-text"]')
  await expect(text).toHaveValue(/^schema_version: 1/)
  // Re-applying the served canonical text is a recorded parse: canvas back.
  await text.fill(await text.inputValue())
  await page.locator('[data-testid="yaml-apply"]').click()
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(8)
  // Text that does not parse: errors with a line, canvas disabled.
  await page.locator('[data-testid="tab-yaml"]').click()
  await text.fill('schema_version: 1\nnodes: [\n')
  await page.locator('[data-testid="yaml-apply"]').click()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'text_broken')
  await expect(page.locator('[data-testid="yaml-error"]').first()).toContainText('line 3')
  await page.locator('[data-testid="tab-canvas"]').click()
  await expect(page.locator('[data-testid="canvas-disabled"]')).toBeVisible()
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('an inspector edit applies through the parse and commits', async ({ page }) => {  // clause: CONSOLE-9
  // Recorded flow (E-76 spec §7.2): a fully positioned graph, no drag before
  // apply, one touched field -- exactly objects/pre_code_architecture_soft.
  await page.goto('/#/graphs?from=run:feature-graph-demo')
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(0)
  await page.locator('[data-testid="graph-node"][data-key="architecture"] .title').click()
  const inspector = page.locator('[data-testid="graph-inspector"]')
  await inspector.locator('[data-path="gate.policy"] select').selectOption('soft')
  await inspector.locator('[data-testid="inspector-apply"]').click()
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(1)
  await expect(inspector.locator('[data-testid="field-error"]')).toHaveCount(0)
  await expect(inspector.locator('[data-testid="inspector-apply"]')).toBeDisabled()
})
```
- [ ] **Step 3: Run the tests to verify they fail**

```bash
npm run test --workspace @kroker/ui -- src/components/app_header
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- app.pw.ts
```

Expected: FAIL — `app_header.spec.ts` misses `GRAPHS`; CONSOLE-7 and CONSOLE-9 time out (no `/graphs` route).
- [ ] **Step 4: Write the view, the inspector, the route and the tab**

`interfaces/dashboard/frontend/src/components/graph/GraphInspector.vue` (create/replace; 67 lines):

```vue
<script setup lang="ts">
// The inspector (E-76 spec §8.3): a schema_form over the SERVED GraphNode /
// GraphEdge schema. Nothing here names a RoleConfig or GateConfig field.
import { computed, ref, watch } from 'vue'
import SchemaForm from '@kroker/ui/components/schema_form/SchemaForm.vue'
import { useCatalogStore } from '../../stores/catalog'
import { useGraphEditorStore } from '../../stores/graphEditor'
import type { EdgeWire, NodeWire } from '../../api/graph-types'

const catalog = useCatalogStore()
const editor = useGraphEditorStore()

const target = computed(() =>
  editor.selectedNode
    ? { kind: 'node' as const, value: editor.selectedNode.node as unknown as Record<string, unknown> }
    : editor.selectedEdge
      ? { kind: 'edge' as const, value: editor.selectedEdge.edge as unknown as Record<string, unknown> }
      : null,
)
const schema = computed(() => {
  if (!catalog.catalog || !target.value) return null
  return target.value.kind === 'node' ? catalog.catalog.schemas.GraphNode : catalog.catalog.schemas.GraphEdge
})

const draft = ref<Record<string, unknown> | null>(null)
const dirty = ref(false)
watch(target, (t) => { draft.value = t ? { ...t.value } : null; dirty.value = false }, { immediate: true })

function onUpdate(v: Record<string, unknown>) {
  draft.value = v
  dirty.value = true
}
async function apply() {
  if (!draft.value) return
  await editor.applyInspector(draft.value as unknown as NodeWire | EdgeWire)
  if (editor.inspectorErrors.length === 0) dirty.value = false
}
</script>

<template>
  <aside class="inspector" data-testid="graph-inspector">
    <p v-if="!target" class="hint">select a node or an edge</p>
    <template v-else-if="schema && draft">
      <header class="bar">
        <span class="what">{{ target.kind }}</span>
        <button class="apply" data-testid="inspector-apply" :disabled="!dirty || editor.applying" @click="apply">apply</button>
      </header>
      <SchemaForm
        :schema="schema"
        :value="target.value"
        :errors="editor.inspectorErrors"
        :readonly-paths="target.kind === 'node' ? ['type'] : []"
        :readonly="editor.applying"
        @update="onUpdate"
      />
    </template>
  </aside>
</template>

<style scoped>
.inspector { width: 320px; overflow: auto; background: var(--ground-2); border-left: 1px solid var(--line); }
.hint { padding: 12px; color: var(--ink-subtle); font-size: 12px; }
.bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-bottom: 1px solid var(--line); }
.what { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; }
.apply { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 4px; padding: 3px 12px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.apply:disabled { background: var(--ground-4); color: var(--ink-whisper); cursor: not-allowed; }
</style>
```

`interfaces/dashboard/frontend/src/views/GraphEditorView.vue` (create/replace; 139 lines):

```vue
<script setup lang="ts">
// Edit mode at /graphs (E-76 spec §8). `?from=run:<id>` opens a run's graph
// as a COPY; `?sha=<sha>` loads a saved graph (when the server declares load).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import NodePalette from '@kroker/ui/components/node_palette/NodePalette.vue'
import IssueList from '@kroker/ui/components/issue_list/IssueList.vue'
import YamlPane from '@kroker/ui/components/yaml_pane/YamlPane.vue'
import type { PortRef } from '@kroker/ui/components/graph_canvas/types'
import GraphInspector from '../components/graph/GraphInspector.vue'
import { useCatalogStore } from '../stores/catalog'
import { useGraphEditorStore } from '../stores/graphEditor'
import { locLabel, nodeKeys, toCanvas } from '../adapters/graph'

const route = useRoute()
const catalog = useCatalogStore()
const editor = useGraphEditorStore()
const tab = ref<'canvas' | 'yaml'>('canvas')

onMounted(async () => {
  await catalog.load()
  const from = route.query.from
  const sha = route.query.sha
  if (typeof from === 'string' && from.startsWith('run:') && catalog.can('run_graph')) await editor.openRunCopy(from.slice(4))
  else if (typeof sha === 'string' && catalog.can('load')) await editor.loadSha(sha)
})

// U5: text that fails the shape parse lives in the YAML pane.
watch(() => editor.state, (s) => { if (s === 'text_broken') tab.value = 'yaml' })
watch(tab, (t) => { if (t === 'yaml') void editor.openYaml() })

const model = computed(() =>
  editor.working
    ? toCanvas(editor.working, {
        typeOf: catalog.typeOf,
        issues: editor.validation?.issues,
        backEdges: editor.validation?.back_edges,
      })
    : null,
)
const paletteItems = computed(() => catalog.nodeTypes.map((t) => ({ type: t.type, kind: t.kind, stage: t.canonical_stage })))
const yamlErrors = computed(() =>
  editor.yamlErrors.map((e) => ({ path: locLabel(e.loc), message: e.msg, line: e.line, column: e.column })),
)

function typeOfKey(key: string): string | undefined {
  const g = editor.working
  if (!g) return undefined
  const i = nodeKeys(g).indexOf(key)
  return i < 0 ? undefined : g.nodes[i].type
}
// GRAPH_CANVAS-6: the only drag-time rule, Python's table served as data.
function connectable(from: PortRef, to: PortRef): boolean {
  const s = typeOfKey(from.node)
  const t = typeOfKey(to.node)
  return !!s && !!t && catalog.connectable(s, from.port, t, to.port)
}

const saveHint = computed(() =>
  catalog.can('save') ? '' : `Saving arrives with E-77${catalog.can('validate') ? '' : '; validation with E-73'}.`,
)
</script>

<template>
  <main data-testid="graph-editor-view" data-screen-label="Graph editor" class="view">
    <NodePalette :items="paletteItems" :disabled="editor.canvasLocked" @pick="(t) => editor.addNode(t, 40, 40)" />
    <section class="center">
      <header class="toolbar">
        <div class="tabs">
          <button class="tab" :class="{ on: tab === 'canvas' }" data-testid="tab-canvas" @click="tab = 'canvas'">canvas</button>
          <button class="tab" :class="{ on: tab === 'yaml' }" data-testid="tab-yaml" @click="tab = 'yaml'">yaml</button>
        </div>
        <button class="btn" data-testid="editor-new" @click="editor.newGraph()">new</button>
        <button class="btn" data-testid="editor-tidy" :disabled="editor.canvasLocked" @click="editor.tidy()">tidy</button>
        <span class="state" data-testid="editor-state" :data-state="editor.state">{{ editor.state }}</span>
        <span v-if="editor.sha" class="sha" data-testid="editor-sha">{{ editor.sha.slice(0, 12) }}</span>
        <span v-if="editor.validation && !editor.runnable" class="badge" data-testid="not-runnable">not runnable · {{ editor.errorCount }}</span>
        <span v-if="editor.notice" class="notice" data-testid="editor-notice">{{ editor.notice }}</span>
        <span class="spacer" />
        <span v-if="saveHint" class="hint">{{ saveHint }}</span>
        <button class="btn save" data-testid="editor-save" :disabled="!catalog.can('save') || editor.state !== 'graph_loaded'" @click="editor.save()">save</button>
      </header>

      <div v-show="tab === 'canvas'" class="canvas-wrap">
        <p v-if="editor.state === 'text_broken'" class="banner" data-testid="canvas-disabled">
          the text does not parse — fix it in the yaml tab
        </p>
        <p v-else-if="editor.state === 'empty'" class="banner">paste YAML in the yaml tab, or start a new graph</p>
        <GraphCanvas
          v-if="model && editor.state === 'graph_loaded'"
          :nodes="model.nodes"
          :edges="model.edges"
          :editable="!editor.canvasLocked"
          :connectable="connectable"
          :selected-key="editor.selection"
          :tidy-request="editor.tidyRequest"
          @connect="(c) => editor.connect(c.from.node, c.from.port, c.to.node, c.to.port)"
          @move="(m) => editor.move(m.key, m.x, m.y)"
          @remove="(r) => editor.remove(r.kind, r.key)"
          @select="editor.select"
          @drop-type="(d) => editor.addNode(d.type, d.x, d.y)"
          @layout-failed="(msg) => (editor.notice = `layout failed: ${msg}`)"
        />
      </div>
      <YamlPane
        v-if="tab === 'yaml'"
        class="yaml"
        :text="editor.yamlText"
        :errors="yamlErrors"
        :dirty="editor.yamlDirty"
        :busy="editor.applying"
        :max-bytes="catalog.catalog?.max_graph_bytes ?? null"
        @update:text="editor.setYamlText"
        @apply="editor.applyText()"
      />
      <IssueList v-if="model && model.issues.length" :items="model.issues" @focus="editor.select" />
    </section>
    <GraphInspector />
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; min-height: 0; }
.center { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--line); background: var(--ground-0); font-size: 12px; }
.tabs { display: flex; gap: 2px; }
.tab, .btn { background: var(--ground-3); color: var(--ink-tertiary); border: 1px solid var(--line); border-radius: 4px; padding: 2px 10px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.tab.on { border-color: var(--accent); color: var(--ink-primary); }
.btn:disabled { color: var(--ink-whisper); cursor: not-allowed; }
.state, .sha { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; }
.badge { color: var(--status-failed); font-family: var(--font-mono); font-size: 11px; }
.notice { color: var(--status-blocked); font-size: 11px; }
.hint { color: var(--ink-subtle); font-size: 11px; }
.spacer { flex: 1; }
.canvas-wrap { flex: 1; position: relative; min-height: 0; }
.banner { margin: 0; padding: 8px 12px; color: var(--ink-muted); font-size: 12px; }
.yaml { flex: 1; min-height: 0; }
</style>
```

`interfaces/dashboard/frontend/src/router.ts` (create/replace; 15 lines):

```ts
import { createRouter, createWebHashHistory } from 'vue-router'
import FleetView from './views/FleetView.vue'
import InboxView from './views/InboxView.vue'
import RunView from './views/RunView.vue'
import GraphEditorView from './views/GraphEditorView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'fleet', component: FleetView },
    { path: '/inbox', name: 'inbox', component: InboxView },
    { path: '/runs/:id', name: 'run', component: RunView, props: true },
    { path: '/graphs', name: 'graphs', component: GraphEditorView },
  ],
})
```

`interfaces/ui/src/components/app_header/AppHeader.vue` (create/replace; 161 lines):

```vue
<script setup lang="ts">
export interface AppHeaderProps {
  activeCount?: number
  maxCount?: number
  totalCost?: string
  inboxCount?: number
  activeTab?: 'fleet' | 'inbox' | 'graphs' | string
}

withDefaults(defineProps<AppHeaderProps>(), {
  activeCount: 0,
  maxCount: 50,
  totalCost: '$0.00',
  inboxCount: 0,
  activeTab: 'fleet',
})

const emit = defineEmits<{
  (e: 'start-run'): void
}>()
</script>

<template>
  <header class="cmp-app-header hdr">
    <div class="brand">
      <span class="mark">SDLC·FACTORY</span>
      <span class="sub">temporal · ai-sdlc queue</span>
    </div>
    <nav class="tabs">
      <RouterLink
        to="/"
        class="tab"
        :class="{ 'tab-active': activeTab === 'fleet' }"
        active-class="tab-active"
      >
        FLEET
      </RouterLink>
      <RouterLink
        to="/inbox"
        class="tab"
        :class="{ 'tab-active': activeTab === 'inbox' }"
        active-class="tab-active"
      >
        INBOX
        <span v-if="inboxCount > 0" data-testid="inbox-count" class="badge">{{ inboxCount }}</span>
      </RouterLink>
      <RouterLink
        to="/graphs"
        class="tab"
        :class="{ 'tab-active': activeTab === 'graphs' }"
        active-class="tab-active"
        data-testid="graphs-tab"
      >
        GRAPHS
      </RouterLink>
    </nav>
    <div class="spacer" />
    <div class="stats">
      <span>runs <b>{{ activeCount }}</b>/{{ maxCount }}</span>
      <span>spend today <b>{{ totalCost }}</b></span>
      <button data-testid="start-btn" class="start" @click="emit('start-run')">+ START RUN</button>
    </div>
  </header>
</template>

<style scoped>
.hdr {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: var(--ground-0);
  border-bottom: 1px solid var(--line);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.mark {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.08em;
  color: var(--ink-primary);
}
.sub {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-whisper);
}
.tabs {
  display: flex;
  gap: 4px;
  height: 100%;
}
.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 100%;
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--ink-faint);
  border-bottom: 2px solid transparent;
  text-decoration: none;
  cursor: pointer;
}
.tab:hover {
  color: var(--ink-primary);
}
.tab-active {
  color: var(--ink-primary);
  border-bottom-color: var(--status-blocked);
}
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--status-blocked);
  color: var(--accent-ink);
  border-radius: 9px;
  font-size: 10.5px;
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.stats {
  display: flex;
  align-items: center;
  gap: 18px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
}
.stats b {
  color: var(--ink-secondary);
}
.start {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 14px;
  background: var(--status-blocked);
  color: var(--accent-ink);
  border: none;
  border-radius: 4px;
}
.start:hover {
  background: var(--accent-hover);
}
</style>
```
- [ ] **Step 5: Run the tests to verify they pass**

```bash
npm run test --workspace sdlc-dashboard -- src/components/graph
npm run test --workspace @kroker/ui -- src/components/app_header
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- app.pw.ts
```

Expected: PASS — schemaCoverage 3, app_header green, app tier CONSOLE-1/2/3/7/9.
- [ ] **Step 6: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 7: Commit**

Write `.workspace/tmp/e76-t16-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 graph editor at /graphs

Edit mode: palette, canvas, YAML pane, issue list and a schema-driven
inspector over the served GraphNode/GraphEdge schemas. Text that fails the
shape parse holds the canvas disabled; ?from=run:<id> opens a run's graph
as a copy with no sha association. Save and validate stay disabled, with
the owning epic named, until the server declares them. The header gains a
GRAPHS tab.
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/components/graph/GraphInspector.vue
git add interfaces/dashboard/frontend/src/components/graph/schemaCoverage.test.ts
git add interfaces/dashboard/frontend/src/views/GraphEditorView.vue
git add interfaces/dashboard/frontend/src/router.ts
git add interfaces/ui/src/components/app_header/AppHeader.vue
git add interfaces/ui/src/components/app_header/app_header.spec.ts
git add interfaces/ui/app.md
git add interfaces/ui/app.pw.ts
git commit -F .workspace/tmp/e76-t16-msg.txt
```
### Task 17: Run mode — RunView

**Files:**
- Replace: `interfaces/dashboard/frontend/src/views/RunView.vue`
- Modify: `interfaces/ui/src/components/graph_canvas/graph_canvas.md` (GRAPH_CANVAS-9)
- Test: `interfaces/ui/app.md` (CONSOLE-4, CONSOLE-5, CONSOLE-6, CONSOLE-8) + `interfaces/ui/app.pw.ts` (append, including the GRAPH_CANVAS-9 regression)

**Interfaces:**
- Consumes: Tasks 7, 8, 12, 13, 15; `useFleetStore().getOrLoad`; `StageDots`.
- Produces: RunView's canvas (read-only) with `GateDecision` in the `node-extra` slot for a pending gate, an inbox link for other pendings, the stage strip, "open copy in editor" (`data-testid="open-copy"`), and empty/unavailable/error/connection-lost states.

- [ ] **Step 1: Append the clauses and app-tier tests**

In `interfaces/ui/src/components/graph_canvas/graph_canvas.md`, insert before `## Failure modes`:

```markdown
### GRAPH_CANVAS-9
Decoration changes -- status, metrics, counters, issue counts -- never
replace the renderer's element lists; only a structural change (keys,
positions, ports, endpoints, backward) does, so edges persist across
run-state updates. [FR-1205]
```

In `interfaces/ui/app.md`, insert before `## Failure modes`:

```markdown
### CONSOLE-4
The run view of a graph-executed run renders one canvas node per graph node,
a loop-edge counter as `used/max`, and its backward edge curved. [FR-1205]

### CONSOLE-5
Deciding a pending gate from the run view's canvas clears that gate's
controls once the provider's next run state no longer lists it. [FR-1205,
FR-301/302]

### CONSOLE-6
The run view of a run that predates graph execution shows the no-graph empty
state and still renders the stage strip. [FR-1205, E-76 U7]

### CONSOLE-8
The run view offers no edit affordance; its "open copy in editor" link lands
on the graph editor holding the run's graph. [FR-1205]
```

Append to `interfaces/ui/app.pw.ts`:

```ts
test('a graph run renders its nodes, a loop counter and a curved backward edge', async ({ page }) => {  // clause: CONSOLE-4
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-node"]')).toHaveCount(8)
  await expect(canvas.locator('.vue-flow__edge-text', { hasText: '1/2' })).toHaveCount(1)
  await expect(canvas.locator('.cmp-graph-edge-backward')).toHaveCount(3)
  await expect(canvas.locator('.cmp-graph-node-blocked')).toHaveCount(1)
})

test('run-state re-renders never drop the canvas edges', async ({ page }) => {  // clause: GRAPH_CANVAS-9
  // Regression (2026-09-14): RunView's elapsed clock re-renders every second;
  // replacing vue-flow's element arrays on each tick dropped every edge.
  await page.clock.install()
  await page.goto('/#/runs/feature-graph-demo')
  const canvas = page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  // Fire RunView's 1 s clock deterministically -- no sleep, no flake budget.
  await page.clock.runFor(5000)
  await expect(canvas.locator('[data-testid="graph-edge"]')).toHaveCount(11)
  await expect(canvas.locator('.vue-flow__edge-text', { hasText: '1/2' })).toHaveCount(1)
})

test('deciding the pending gate from the canvas clears it', async ({ page }) => {  // clause: CONSOLE-5
  await page.goto('/#/runs/feature-graph-demo')
  const gate = page.locator('[data-testid="run-view"] [data-testid="gate-decision"]')
  await expect(gate).toHaveCount(1)
  await gate.locator('[data-testid="gate-approve"]').click()
  await expect(gate).toHaveCount(0)
  await expect(page.locator('[data-testid="run-view"] .cmp-graph-node-running')).toHaveCount(1)
})

test('a legacy run shows the no-graph empty state and the strip', async ({ page }) => {  // clause: CONSOLE-6
  await page.goto('/#/runs/feature-add-sso')
  await expect(page.locator('[data-testid="run-graph-empty"]')).toBeVisible()
  await expect(page.locator('[data-testid="run-view"] [data-testid="stage-dot"]')).toHaveCount(18)
  await expect(page.locator('[data-testid="run-view"] [data-testid="graph-canvas"]')).toHaveCount(0)
})

test('the run view offers no edit affordance and opens a copy in the editor', async ({ page }) => {  // clause: CONSOLE-8
  await page.goto('/#/runs/feature-graph-demo')
  const view = page.locator('[data-testid="run-view"]')
  await expect(view.locator('.vue-flow__node.draggable')).toHaveCount(0)
  await expect(view.locator('.vue-flow__handle.connectable')).toHaveCount(0)
  await expect(view.locator('[data-testid="node-palette"]')).toHaveCount(0)
  await view.locator('[data-testid="open-copy"]').click()
  await expect(page.locator('[data-testid="graph-editor-view"]')).toBeVisible()
  await expect(page.locator('[data-testid="editor-state"]')).toHaveAttribute('data-state', 'graph_loaded')
  await expect(page.locator('[data-testid="graph-editor-view"] [data-testid="graph-node"]')).toHaveCount(8)
  await expect(page.locator('[data-testid="editor-sha"]')).toHaveCount(0)
})
```
- [ ] **Step 2: Run them to verify they fail**

```bash
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- app.pw.ts
```

Expected: FAIL — CONSOLE-4/5/6/8 and the GRAPH_CANVAS-9 test time out on the placeholder RunView.
- [ ] **Step 3: Replace RunView**

`interfaces/dashboard/frontend/src/views/RunView.vue` (replace; 98 lines):

```vue
<script setup lang="ts">
// Run mode (E-76 spec §9). Read-only by design: there is no edit path from a
// run; "open copy in editor" is the only way to /graphs (FR-1205).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import GateDecision from '@kroker/ui/components/gate_decision/GateDecision.vue'
import StageDots from '@kroker/ui/components/stage_dots/StageDots.vue'
import { useCatalogStore } from '../stores/catalog'
import { useFleetStore } from '../stores/fleet'
import { useRunGraphStore } from '../stores/runGraph'
import { toCanvas } from '../adapters/graph'
import { toStageDots } from '../adapters/fleet'

const props = defineProps<{ id: string }>()
const catalog = useCatalogStore()
const fleet = useFleetStore()
const runGraph = useRunGraphStore()

const now = ref(new Date())
let clock: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void catalog.load()
  void runGraph.start(props.id)
  clock = setInterval(() => { now.value = new Date() }, 1000)
})
watch(() => props.id, (id) => { void runGraph.start(id) })
onBeforeUnmount(() => {
  runGraph.stop()
  if (clock) clearInterval(clock)
})

const run = computed(() => fleet.getOrLoad(props.id))
const dots = computed(() => (run.value ? toStageDots(run.value, catalog.canonicalStages) : []))
const graph = computed(() => (runGraph.graph?.kind === 'graph' ? runGraph.graph : null))
const model = computed(() =>
  graph.value
    ? toCanvas(graph.value.graph, { typeOf: catalog.typeOf, backEdges: graph.value.back_edges, state: runGraph.state, now: now.value })
    : null,
)
const gateOf = (nodeKey: string) => model.value?.pendingByNode[nodeKey]?.find((p) => p.kind === 'gate')
const otherPending = (nodeKey: string) => model.value?.pendingByNode[nodeKey]?.filter((p) => p.kind !== 'gate') ?? []
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <header class="head">
      <h1 class="title">{{ run?.title ?? id }}</h1>
      <StageDots :dots="dots" />
      <span class="spacer" />
      <RouterLink
        v-if="graph"
        :to="{ path: '/graphs', query: { from: `run:${id}` } }"
        class="copy"
        data-testid="open-copy"
      >open copy in editor</RouterLink>
    </header>

    <p v-if="runGraph.error" class="banner error" data-testid="run-graph-error">{{ runGraph.error }}</p>
    <p v-else-if="!catalog.can('run_graph')" class="banner" data-testid="run-graph-unavailable">Graph view arrives with E-75.</p>
    <p v-else-if="runGraph.graph?.kind === 'no_graph'" class="banner" data-testid="run-graph-empty">
      This run predates graph execution.
    </p>
    <p v-if="runGraph.connectionLost" class="banner" data-testid="connection-lost">connection lost — retrying</p>

    <div v-if="model" class="canvas-wrap">
      <GraphCanvas :nodes="model.nodes" :edges="model.edges" :editable="false">
        <template #node-extra="{ nodeKey }">
          <GateDecision
            v-if="gateOf(nodeKey)"
            :title="`${nodeKey} · pending`"
            :busy="runGraph.inFlight.has(gateOf(nodeKey)!.key)"
            @decide="(d) => runGraph.decide(gateOf(nodeKey)!.key, d.outcome, d.comment)"
          />
          <RouterLink
            v-for="p in otherPending(nodeKey)"
            :key="p.key"
            to="/inbox"
            class="pending-link"
            data-testid="pending-inbox-link"
          >{{ p.kind }} pending — inbox</RouterLink>
        </template>
      </GraphCanvas>
    </div>
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 12px 16px; gap: 8px; }
.head { display: flex; align-items: center; gap: 14px; }
.title { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink-primary); }
.spacer { flex: 1; }
.copy { color: var(--link); font-family: var(--font-mono); font-size: 11px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.banner.error { color: var(--status-failed); }
.canvas-wrap { flex: 1; min-height: 420px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.pending-link { display: block; padding: 4px 8px; color: var(--link); font-size: 11px; }
</style>
```
- [ ] **Step 4: Run them to verify they pass**

```bash
npm run typecheck --workspace sdlc-dashboard
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"   # PowerShell: $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
npm run test:pw --workspace @kroker/ui -- app.pw.ts
```

Expected: PASS — app tier: 10 tests (CONSOLE-1…9 and GRAPH_CANVAS-9). The GRAPH_CANVAS-9 test drives RunView's 1 s clock with `page.clock` — no sleeps.
- [ ] **Step 5: Gate**

Run the whole Node gate (the intermediate commit must be green, not just this task's files):

```bash
python scripts/check_ui.py
python scripts/check_file_size.py
python scripts/check_clauses.py
```

Expected: `ui gate passes`; the file-size ratchet passes; the clause report (advisory, always exit 0) ends `0 untested, 0 dangling` — except between Task 1 and Task 12, where it lists `test cites unknown clause: GRAPH_CANVAS-5`, `-6` and `-8` (Task 1's helper specs cite clauses `graph_canvas.md` declares in Task 12).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t17-msg.txt` with exactly this content (no trailers of any kind):

```text
feat(dashboard): E-76 run mode in RunView

RunView renders the run's pinned graph read-only: status rings, cost,
elapsed and round on nodes, traversal counters and curved back edges on
edges, and approve/revise/reject on a pending gate node through decideGate.
A run that predates graph execution shows an explicit empty state beside
the stage strip. There is no edit path from a run; "open copy in editor"
is the only way to /graphs.
```

Then, one path per `git add`:

```bash
git add interfaces/dashboard/frontend/src/views/RunView.vue
git add interfaces/ui/src/components/graph_canvas/graph_canvas.md
git add interfaces/ui/app.md
git add interfaces/ui/app.pw.ts
git commit -F .workspace/tmp/e76-t17-msg.txt
```
### Task 18: Landing docs + full verification

**Files:**
- Modify: `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md`

**Interfaces:** none (docs describe `main`; this commit rides the branch that lands).

- [ ] **Step 1: Tick and refine the roadmap row**

In `docs/roadmap/pipeline-as-data.md`, replace:

```markdown
- [ ] **E-76 — canvas** → FR-1205.
```

with:

```markdown
- [x] **E-76 — canvas** → FR-1205.
```

and replace:

```markdown
`Run.stageIdx` (`interfaces/dashboard/frontend/src/api/types.ts:18`) is a linear index that cannot express
  graph position and becomes `currentNodes: string[]`; `StageDots.vue` (now `interfaces/ui/src/components/stage_dots/`, E-89) survives by
  mapping active nodes through `canonical_stage` back onto the fixed 15-stage
  strip, so the fleet table keeps its glanceable row and cannot disagree with the
  benchmark.
```

with:

```markdown
`Run.stageIdx` was a linear index that could not express
  graph position; it became `Run.activeStages: string[]` (canonical stage
  names), while `current_nodes` lives in the run's graph state. `StageDots.vue`
  (`interfaces/ui/src/components/stage_dots/`, E-89) renders the canonical
  stage list the catalog serves (18 stages), matched by name, so the fleet
  table keeps its glanceable row and cannot disagree with the benchmark.

  **Landed** (spec `docs/superpowers/specs/2026-09-14-graph-canvas-design.md`,
  plan `docs/superpowers/plans/2026-09-14-graph-canvas.md`): six `@kroker/ui`
  components, edit mode at `/graphs`, run mode in RunView, the pure
  `/graphs/catalog|parse|serialize` routes over `sdlc/dashboard/graph_wire.py`,
  and the strict graph YAML loader. Run mode is exercised on the mock provider;
  live run data arrives with E-75, validation with E-73, save/load with E-77
  (all gated by server-declared capabilities). Open questions E76-OQ-1…5 live
  in the spec §12.
```
- [ ] **Step 2: Mark FR-1205 partial in ROADMAP**

In `ROADMAP.md`, replace:

```markdown
- [ ] **FR-1205** canvas — one renderer, run mode + edit mode; editing a running graph disabled by design; validation via FR-1202 (E-76).
```

with:

```markdown
- [ ] ⚠️ **FR-1205** canvas — one renderer, run mode + edit mode; editing a running graph disabled by design; validation via FR-1202 (E-76 landed: canvas, edit mode, pure graph routes; live run state waits on E-75, validation on E-73).
```
- [ ] **Step 3: Name the new pieces in ARCHITECTURE's tree**

In `ARCHITECTURE.md`, replace:

```text
│   ├── dashboard/             # fleet poller, REST + SSE api, channel adapter (E-10)
```

with:

```text
│   ├── dashboard/             # fleet poller, REST + SSE api, channel adapter (E-10); graph_wire + graph routes (E-76)
```

and replace:

```text
│   ├── dashboard/frontend/    # Vue 3 SPA against the live API
```

with:

```text
│   ├── dashboard/frontend/    # Vue 3 SPA against the live API; graph canvas run + edit views (E-76)
```
- [ ] **Step 4: File the two landing handover notes (spec §11 items 2 and 3)**

`.workspace/` is gitignored: these notes are the orchestrator's record, not part of the commit. The item-1 note (`.workspace/tasks/2026-09-14-e76-needs-from-e73-validate.md`, E-73) was filed at spec time — confirm it exists. If `.workspace/tasks/2026-09-14-fleet-snapshot-fixture-freshness.md` (item 3, filed at spec time) is missing, recreate it with the content below; then write the E-75 note.

`.workspace/tasks/2026-09-14-e76-handover-to-e75.md`:

```markdown
| | |
|---|---|
| From | E-76 (graph canvas) landing — spec §11 handover item 2 |
| Size | M |
| Status | open — owner E-75 |

## What E-75 implements to (spec `docs/superpowers/specs/2026-09-14-graph-canvas-design.md`)

1. The PROVISIONAL routes of spec §5.5-§5.8, using the models already in
   `src/sdlc/dashboard/graph_wire.py` as `response_model=` so no route can
   drift from the recorded fixtures: `POST /graphs/validate` (with E-73),
   `POST /graphs` + `GET /graphs/{sha}` (with E-77),
   `GET /runs/{run_id}/graph` and `GET /runs/{run_id}/graph_state`.
2. Flip the matching `Capabilities` fields in `graph_wire.catalog()` as each
   route becomes real (`validate`, `save`, `load`, `run_graph`); the canvas
   gates every PROVISIONAL call on them and never probes for 404s.
3. `RunState.stages: [{name, state}]` (spec §5.8), a server-side projection
   that lets the fleet row show `skipped` for graph runs (E76-OQ-3).
4. Rules carried from spec §5.7: no field of `graph_state` changes without a
   state change (SSE fingerprint dedupe); `max_traversals` is not repeated in
   state; `pending[].key` is the verbatim inbox key.
5. When `sdlc.graph.validate` exists, `tests/test_dashboard_graph_wire.py`'s
   forcing test fails until `graph_wire` maps its result onto
   `ValidationWire` and `scripts/dump_graph_fixtures.py` records real
   validation, replacing `validation.provisional.json`.
```

`.workspace/tasks/2026-09-14-fleet-snapshot-fixture-freshness.md` (only if missing):

```markdown
| | |
|---|---|
| From | E-76 planner (graph canvas design) — advisor finding |
| Size | S |
| Status | open |

## `fleet-snapshot.json` has no freshness test

`scripts/dump_dashboard_fixtures.py` regenerates
`interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json`
from the pydantic models so `http.test.ts` / `client.test.ts` test the TS
mapper against real shapes. Nothing checks that the committed JSON still
equals what the script would produce, so a model change drifts silently —
exactly what the fixture was meant to catch.

Fix: split the script into `build()` + `main()` and add a fast-tier pytest
comparing `build()` to the committed file **parsed** (no `.gitattributes`;
a CRLF checkout must not false-fail). E-76 does this for its own
`__fixtures__/graph/` and is the pattern to copy. Not E-76 scope.
```
- [ ] **Step 5: Full verification**

Run each on its own (never two pytest runs in one call):

```bash
python -m pytest tests/graph -q
```

```bash
python -m pytest tests/test_dashboard_graph_wire.py tests/test_dashboard_graph_routes.py tests/test_graph_fixtures_fresh.py tests/test_dashboard_api.py -q
```

```bash
python -m pytest -q
```

```bash
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
python scripts/check_clauses.py
python scripts/check_ui.py
```

Expected: the graph suite 117 passed; the dashboard graph set green with 1 skipped (the forcing test); the default suite green; ruff/format clean; mypy no new errors; file sizes pass; clause report `0 untested, 0 dangling`; `ui gate passes` (dashboard Vitest 153, ui Vitest 72, Playwright 48).
- [ ] **Step 6: Commit**

Write `.workspace/tmp/e76-t18-msg.txt` with exactly this content (no trailers of any kind):

```text
docs: E-76 landed -- graph canvas

Ticks the E-76 row and refines its stage-strip text (activeStages over
the served 18-stage canonical list, current_nodes in graph state), marks
FR-1205 partial until E-75 supplies live run state and E-73 validation, and
names graph_wire and the canvas views in ARCHITECTURE's tree.
```

Then, one path per `git add`:

```bash
git add docs/roadmap/pipeline-as-data.md
git add ROADMAP.md
git add ARCHITECTURE.md
git commit -F .workspace/tmp/e76-t18-msg.txt
```
## Spec coverage (self-review)

| spec § | discharged by |
|---|---|
| §2.1 U1 save endpoint | Task 3 `SaveOk`; Task 7 `saveGraph` (mock in memory, http gated); Task 14 `save()`; Task 16 save button |
| §2.1 U2 placement | Task 16 `/graphs`; Task 17 RunView; copy-only via `?from=run:` (CONSOLE-8) |
| §2.1 U3 gate actions | Task 8 `gate_decision`; Task 15 `decide`; Task 17 slot (CONSOLE-5) |
| §2.1 U4 strip by name, 18 served | Task 7 (`stageStates`, catalog store, CONSOLE-3) |
| §2.1 U5 shape-broken text | Task 14 `text_broken`; Task 16 (CONSOLE-7) |
| §2.1 U6 save with errors | Task 14 `save()` keeps validation, `errorCount`; Task 16 "not runnable · N" badge (§8.6) |
| §2.1 U7 graphless runs | Task 15 `no_graph`; Task 17 empty state (CONSOLE-6) |
| §2.1 U8 schema-driven inspector (JSON snippet) | Task 11; Task 16 `GraphInspector` + schemaCoverage (SCHEMA_FORM-3) |
| §2.1 U9 pure routes | Tasks 3–4 |
| D1–D3 server authority, working copy, connectable | Tasks 3, 7, 12 (GRAPH_CANVAS-6), 14 |
| D4 recording mock | Tasks 5, 7 (`mock/graph.ts`, unrecorded → error) |
| D5 split placement | Tasks 1, 8–12 (ui) vs 13–17 (dashboard) |
| D6 wire models in `graph_wire.py` | Task 3 |
| D7 server-supplied keys | Tasks 13 (`pendingByNode`), 15, 17 — no `gate_key`, sha or back-edge computation in TS |
| D8 polling transport | Task 6 `startPoll`; Task 7 `subscribeGraphState` |
| D9 capabilities | Tasks 3, 7, 14–17 |
| D10 strict loader | Task 2 |
| D11 local canvas ops | Task 14 |
| §5 wire contract | Tasks 3 (Python), 7 (TS) |
| §6 Python changes | Tasks 2–5 |
| §7 providers/stores | Tasks 6, 7, 14, 15 |
| §8 edit mode incl. M1–M4, epoch, layout hygiene | Tasks 1, 12, 14, 16 |
| §9 run mode + strip | Tasks 7, 13, 15, 17 |
| §10 tests per tier, clauses | every task; Task 18 full gate |
| §11 handovers | item 1 E-73: `.workspace/tasks/2026-09-14-e76-needs-from-e73-validate.md` (filed at spec time) + the forcing test (Task 3); item 2 E-75: `.workspace/tasks/2026-09-14-e76-handover-to-e75.md` (Task 18 step 4); item 3 inbox: `.workspace/tasks/2026-09-14-fleet-snapshot-fixture-freshness.md` (filed at spec time; Task 18 step 4 re-creates it if missing); docs on landing (Task 18) |
| §12 open questions | not decided here (Global Constraints) |
