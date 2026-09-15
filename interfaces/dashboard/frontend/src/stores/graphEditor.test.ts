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

  // --- chaos: stale epochs, reachable races, error mapping -------------------

  it('discards a REJECTED validation that an edit overtook: no stale notice', async () => {
    vi.useFakeTimers()
    const s = await loaded()
    let reject!: (e: unknown) => void
    api.validateGraph.mockReturnValueOnce(new Promise((_, rej) => { reject = rej }))
    await vi.advanceTimersByTimeAsync(400)
    s.move('intake', 1, 1)  // epoch moves while the request is in flight
    reject(new Error('validation 500'))
    await vi.advanceTimersByTimeAsync(0)
    expect(s.validation).toBeNull()
    expect(s.notice).toBeNull()  // a stale failure is discarded, not surfaced
  })

  it('a failed serialize during load never becomes an unhandled rejection', async () => {
    const rejections: unknown[] = []
    const onRejection = (r: unknown) => { rejections.push(r) }
    process.on('unhandledRejection', onRejection)
    try {
      const s = useGraphEditorStore()
      api.parseGraph.mockResolvedValueOnce(PRE)
      api.serializeGraph.mockRejectedValueOnce(new Error('serialize 500'))
      s.loadGraph(PRE.graph, PRE.sha)  // fire-and-forget openYaml inside
      await new Promise((r) => setTimeout(r, 0))
      expect(rejections).toEqual([])
    } finally {
      process.off('unhandledRejection', onRejection)
    }
  })

  it('coalesces a burst of edits into one debounced validate carrying the latest copy', async () => {
    vi.useFakeTimers()
    const s = await loaded()
    await vi.advanceTimersByTimeAsync(400)  // flush the load's own validate
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
    await s.loadText(preCode.yaml)  // dropped while applying
    expect(api.parseGraph).toHaveBeenCalledTimes(1)
    pending.resolve(PRE)
    await first
    expect(s.state).toBe('graph_loaded')
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

  it('a refused save keeps the saved sha and raises a notice', async () => {
    const s = await loaded()
    api.saveGraph.mockResolvedValueOnce({ ok: false, shape_errors: [{ loc: [], msg: 'x', line: null, column: null }] })
    await s.save()
    expect(s.savedSha).toBeNull()
    expect(s.notice).toContain('save refused')
  })

  it('a missing sha and a legacy run land as notices, not throws', async () => {
    const s = await loaded()
    api.loadGraph.mockResolvedValueOnce({ ok: false, reason: 'not_found' })
    await s.loadSha('nope')
    expect(s.notice).toBe('no saved graph nope')
    api.getRunGraph.mockResolvedValueOnce({ kind: 'no_graph', reason: 'legacy_run' })
    await s.openRunCopy('r1')
    expect(s.notice).toBe('this run predates graph execution')
  })
})
