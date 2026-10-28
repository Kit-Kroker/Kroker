// v5 Design store (018 T062 RED). The state machine's surviving core (states,
// D11 local ops, epoch discipline, parse-round-trip inspector apply, save) is
// kept from the E-76 suite; new v5 pins: payload-refusing connect (FR-047),
// undo/redo (S15), the edge max_traversals round trip. The YAML pane pins are
// DELETED with S15 (named in the RED report): the serialize-discard case rode
// openYaml, which the pane's removal retires; loadText stays as the loading
// helper because the parse route stays served (S15).
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import preCode from '../../api/__fixtures__/graph/scenarios/pre_code.json'
import badYaml from '../../api/__fixtures__/graph/scenarios/bad_yaml.json'
import soft from '../../api/__fixtures__/graph/objects/pre_code_architecture_soft.json'
import type { CatalogWire, GraphWire, ParseWire, ValidationWire } from '../../api/graph-types'

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
vi.mock('../../api/client', () => ({ api }))

import { useGraphEditorStore } from './graphEditor.store'
import { useCatalogStore } from '../../shared/catalog.store'

const PRE = preCode.parse as { ok: true; graph: GraphWire; sha: string }
const CATALOG = catalogJson as unknown as CatalogWire
const withCaps = (caps: Partial<CatalogWire['capabilities']>) =>
  ({ ...CATALOG, capabilities: { validate: false, save: false, load: false, run_graph: false, ...caps } })

const portOf = (type: string, name: string) =>
  CATALOG.node_types.find((t) => t.type === type)!.ports.find((p) => p.name === name)!

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

// Deterministic port pairs from the served catalog: an EQUAL pair is an
// equal-payload port combination with NO existing edge between them (the
// RED's first draft reused PRE.edges[0], which M1's kept dedupe pin would
// select instead of adding — the pair is now searched, same intent); an
// UNEQUAL pair is searched from the catalog's payloads (FR-047's refusal
// input).
const equalPair = () => {
  const withType = PRE.graph.nodes.map((n) => ({ n, t: CATALOG.node_types.find((t) => t.type === n.type)! }))
  const has = (a: string, ap: string, b: string, bp: string) =>
    PRE.graph.edges.some((e) => e.source === a && e.source_port === ap && e.target === b && e.target_port === bp)
  for (const a of withType) {
    for (const out of a.t.ports.filter((p) => p.direction === 'out')) {
      for (const b of withType) {
        for (const inn of b.t.ports.filter((p) => p.direction === 'in')) {
          if (a.n.id === b.n.id) continue
          if (out.payload === inn.payload && !has(a.n.id, out.name, b.n.id, inn.name)) {
            return { from: { node: a.n.id, port: out.name }, to: { node: b.n.id, port: inn.name } }
          }
        }
      }
    }
  }
  throw new Error('catalog offers no free equal-payload pair')
}
const unequalPair = () => {
  const withType = PRE.graph.nodes.map((n) => ({ n, t: CATALOG.node_types.find((t) => t.type === n.type)! }))
  for (const a of withType) {
    for (const out of a.t.ports.filter((p) => p.direction === 'out')) {
      for (const b of withType) {
        for (const inn of b.t.ports.filter((p) => p.direction === 'in')) {
          if (a.n.id === b.n.id) continue
          if (out.payload !== inn.payload) {
            return { from: { node: a.n.id, port: out.name }, to: { node: b.n.id, port: inn.name } }
          }
        }
      }
    }
  }
  throw new Error('catalog offers no unequal-payload pair')
}

describe('states (kept from E-76)', () => {
  it('starts empty, loads recorded text into graph_loaded with its sha', async () => {
    const s = useGraphEditorStore()
    expect(s.state).toBe('empty')
    await loaded()
    expect(s.state).toBe('graph_loaded')
    expect(s.sha).toBe(PRE.sha)
  })

  it('shape-broken text goes text_broken with its errors and locks the canvas', async () => {
    const s = useGraphEditorStore()
    api.parseGraph.mockResolvedValueOnce(badYaml.parse)
    await s.loadText(badYaml.yaml)
    expect(s.state).toBe('text_broken')
    expect(s.yamlErrors[0].line).toBe(3)
    expect(s.canvasLocked).toBe(true)
  })
})

describe('D11 canvas operations never round-trip (kept)', () => {
  it('adds, moves and removes locally, bumping the epoch each time', async () => {
    const s = await loaded()
    api.parseGraph.mockClear()
    const e0 = s.epoch
    s.addNode('gate.plan', 5, 5)
    s.move('gate_plan', 50, 60)
    s.remove('node', 'gate_plan')
    expect(s.epoch).toBe(e0 + 3)
    expect(api.parseGraph).not.toHaveBeenCalled()
  })
})

describe('payload-refusing connect (FR-047, 018 T062 RED)', () => {
  it('an equal-payload connect creates the edge', async () => {
    const s = await loaded()
    const { from, to } = equalPair()
    const before = s.working!.edges.length
    s.connect(from.node, from.port, to.node, to.port)
    expect(s.working!.edges.length).toBeGreaterThan(before)
  })

  it('an unequal-payload connect is refused with a reason and creates no edge', async () => {
    const s = await loaded()
    const { from, to } = unequalPair()
    const before = s.working!.edges
    s.connect(from.node, from.port, to.node, to.port)
    expect(s.working!.edges).toBe(before) // no edge created
    expect(s.notice).toBeTruthy()
    expect(String(s.notice)).toMatch(/payload/)
  })
})

describe('undo and redo (S15, 018 T062 RED)', () => {
  it('undo restores the previous working copy; redo reapplies the edit', async () => {
    const s = await loaded()
    const before = s.working
    s.addNode('gate.plan', 5, 5)
    expect(s.working!.nodes.some((n) => n.id === 'gate_plan')).toBe(true)
    s.undo()
    expect(s.working).toEqual(before)
    s.redo()
    expect(s.working!.nodes.some((n) => n.id === 'gate_plan')).toBe(true)
  })
})

describe('inspector apply (kept; the edge round trip is new)', () => {
  it('commits the parsed graph on success (node gate change)', async () => {
    const s = await loaded()
    s.select('architecture')
    api.parseGraph.mockResolvedValueOnce(soft.parse)
    await s.applyInspector({ ...s.selectedNode!.node, gate: { policy: 'soft' } })
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: soft.graph })
    expect(s.working!.nodes.find((n) => n.id === 'architecture')!.gate).toEqual({ policy: 'soft' })
  })

  it('an edge max_traversals edit round-trips through parse (S15, 018 T062 RED)', async () => {
    const s = await loaded()
    const key = `${PRE.graph.edges[0]!.source}.${PRE.graph.edges[0]!.source_port}>${PRE.graph.edges[0]!.target}.${PRE.graph.edges[0]!.target_port}`
    s.select(key)
    expect(s.selectedEdge).not.toBeNull()
    const edited = { ...s.selectedEdge!.edge, max_traversals: 5 }
    const expected: GraphWire = JSON.parse(JSON.stringify(s.working))
    const idx = s.working!.edges.indexOf(s.selectedEdge!.edge)
    expected.edges[idx] = edited
    api.parseGraph.mockResolvedValueOnce({ ok: true, graph: expected, sha: 'sha-edited' })
    await s.applyInspector(edited)
    expect(api.parseGraph).toHaveBeenLastCalledWith({ graph: expected })
    expect(s.working!.edges[idx]!.max_traversals).toBe(5)
  })

  it('locks canvas operations while an inspector apply is in flight (kept)', async () => {
    const s = await loaded()
    s.select('architecture')
    const pending = deferred<ParseWire>()
    api.parseGraph.mockReturnValueOnce(pending.promise)
    const applying = s.applyInspector({ ...s.selectedNode!.node, gate: { policy: 'soft' } })
    expect(s.canvasLocked).toBe(true)
    pending.resolve(soft.parse as ParseWire)
    await applying
    expect(s.canvasLocked).toBe(false)
  })
})

describe('save (kept)', () => {
  it('records the sha and the validation it returned', async () => {
    const s = await loaded()
    api.saveGraph.mockResolvedValueOnce({ ok: true, sha: PRE.sha, validation: { issues: [], back_edges: [] } })
    await s.save()
    expect(s.savedSha).toBe(PRE.sha)
    expect(s.runnable).toBe(true)
  })

  it('a refused save keeps the saved sha and raises a notice', async () => {
    const s = await loaded()
    api.saveGraph.mockResolvedValueOnce({ ok: false, shape_errors: [{ loc: [], msg: 'x', line: null, column: null }] })
    await s.save()
    expect(s.savedSha).toBeNull()
    expect(s.notice).toContain('save refused')
  })

  it('a layout-only move keeps the content sha; an edge change alters it (FR-049, 018 T062 RED)', async () => {
    const s = await loaded()
    // Layout-only: a move leaves the content the sha is computed over.
    s.move('intake', 111, 222)
    api.saveGraph.mockResolvedValueOnce({ ok: true, sha: PRE.sha, validation: null })
    await s.save()
    expect(s.sha).toBe(PRE.sha)

    // An edge change is a content change: the server answers a new sha.
    s.connect(...(Object.values(equalPair()).flatMap((p) => [p.node, p.port]) as [string, string, string, string]))
    api.saveGraph.mockResolvedValueOnce({ ok: true, sha: 'sha-after-edge', validation: null })
    await s.save()
    expect(s.sha).toBe('sha-after-edge')
  })

  it('a missing sha and a legacy run land as notices, not throws (kept)', async () => {
    const s = await loaded()
    api.loadGraph.mockResolvedValueOnce({ ok: false, reason: 'not_found' })
    await s.loadSha('nope')
    expect(s.notice).toBe('no saved graph nope')
    api.getRunGraph.mockResolvedValueOnce({ kind: 'no_graph', reason: 'legacy_run' })
    await s.openRunCopy('r1')
    expect(s.notice).toBe('this run predates graph execution')
  })
})

// --- kept chaos (pane-independent E-76 pins) ----------------------------------

describe('kept store discipline (E-76, unchanged by S15)', () => {
  it('a failed apply after a load goes text_broken too, keeping the last good copy', async () => {
    const s = await loaded()
    const good = s.working
    api.parseGraph.mockResolvedValueOnce(badYaml.parse)
    await s.loadText(badYaml.yaml)
    expect(s.state).toBe('text_broken')
    expect(s.working).toBe(good)
  })

  it('refuses over-cap text without calling the server', async () => {
    const s = useGraphEditorStore()
    useCatalogStore().catalog = { ...withCaps({}), max_graph_bytes: 10 }
    await s.loadText('schema_version: 1\n')
    expect(api.parseGraph).not.toHaveBeenCalled()
    expect(s.yamlErrors[0].msg).toContain('exceeds 10 bytes')
  })

  it('M2 refuses a rename onto an in-use id without calling the server', async () => {
    const s = await loaded()
    s.select('planner')
    api.parseGraph.mockClear()
    await s.applyInspector({ ...s.selectedNode!.node, id: 'architect' })
    expect(api.parseGraph).not.toHaveBeenCalled()
    expect(s.inspectorErrors[0]).toEqual({ path: 'id', msg: "'architect' is already used by another node, so renaming would merge their edges" })
  })

  it('error mapping: inside-only errors omit the elsewhere line; outside-only errors are just the line; select clears', async () => {
    const s = await loaded()
    s.select('intake')  // intake is nodes[3] in the recorded (alphabetically sorted) graph
    api.parseGraph.mockResolvedValueOnce({
      ok: false,
      shape_errors: [{ loc: ['nodes', 3, 'gate', 'policy'], msg: 'bad enum', line: null, column: null }],
    })
    await s.applyInspector({ ...s.selectedNode!.node })
    expect(s.inspectorErrors).toEqual([{ path: 'gate.policy', msg: 'bad enum' }])
    api.parseGraph.mockResolvedValueOnce({
      ok: false,
      shape_errors: [{ loc: ['nodes', 0, 'id'], msg: 'bad id', line: null, column: null }],
    })
    await s.applyInspector({ ...s.selectedNode!.node })
    expect(s.inspectorErrors).toEqual([{ path: '', msg: '1 shape error(s) elsewhere in the graph' }])
    s.select('architect')
    expect(s.inspectorErrors).toEqual([])
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

  it('discards a REJECTED validation that an edit overtook: no stale notice', async () => {
    vi.useFakeTimers()
    const s = await loaded()
    let reject!: (e: unknown) => void
    api.validateGraph.mockReturnValueOnce(new Promise((_, rej) => { reject = rej }))
    await vi.advanceTimersByTimeAsync(400)
    s.move('intake', 1, 1)
    reject(new Error('validation 500'))
    await vi.advanceTimersByTimeAsync(0)
    expect(s.validation).toBeNull()
    expect(s.notice).toBeNull()
  })

  it('coalesces a burst of edits into one debounced validate carrying the latest copy', async () => {
    vi.useFakeTimers()
    const s = await loaded()
    await vi.advanceTimersByTimeAsync(400)
    api.validateGraph.mockClear()
    s.move('intake', 1, 1)
    await vi.advanceTimersByTimeAsync(100)
    s.move('intake', 2, 2)
    await vi.advanceTimersByTimeAsync(100)
    s.move('intake', 3, 3)
    await vi.advanceTimersByTimeAsync(399)
    expect(api.validateGraph).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(api.validateGraph).toHaveBeenCalledTimes(1)
    expect(api.validateGraph).toHaveBeenLastCalledWith(s.working)
  })

  it('a second text apply during an in-flight one is dropped, never queued', async () => {
    const s = useGraphEditorStore()
    const pending = deferred<ParseWire>()
    api.parseGraph.mockReturnValueOnce(pending.promise)
    const first = s.loadText('x: 1')
    expect(s.applying).toBe(true)
    api.parseGraph.mockResolvedValueOnce(PRE)
    await s.loadText(preCode.yaml)
    expect(api.parseGraph).toHaveBeenCalledTimes(1)
    pending.resolve(PRE)
    await first
    expect(s.state).toBe('graph_loaded')
  })
})
