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
import { useUiStore } from '../app/ui.store'

const GRAPH = { kind: 'graph' as const, sha: 'sha-1', graph: { schema_version: 1 as const, nodes: [], edges: [] }, back_edges: [] }
const state = (over: Partial<Extract<GraphStateResponse, { kind: 'state' }>> = {}): GraphStateResponse => ({
  kind: 'state', graph_sha: 'sha-1', nodes: {}, edges: [], current_nodes: [],
  outcome: { state: 'running', reason: null, result: null },
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

// --- chaos: superseded starts, sha-guard corners, connection thresholds -----

describe('chaos: races and hostile deliveries', () => {
  it('a start superseded by ANOTHER start never subscribes the loser', async () => {
    let resolveLoser!: (v: unknown) => void
    api.getRunGraph.mockReturnValueOnce(new Promise((r) => { resolveLoser = r }))
    const loser = useRunGraphStore().start('r1')
    await Promise.resolve()
    const winner = useRunGraphStore().start('r2')  // bumps the generation mid-flight
    resolveLoser(GRAPH)
    await Promise.all([loser, winner])
    const s = useRunGraphStore()
    expect(s.runId).toBe('r2')
    expect(api.subscribeGraphState).toHaveBeenCalledTimes(1)
    expect(api.subscribeGraphState).toHaveBeenCalledWith('r2', expect.any(Function), expect.any(Function))
  })

  it('a no_graph state delivery never trips the sha guard', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    deliver({ kind: 'no_graph', reason: 'legacy_run' })
    expect(s.state).toEqual({ kind: 'no_graph', reason: 'legacy_run' })
    expect(s.error).toBeNull()
    expect(unsubscribe).not.toHaveBeenCalled()
  })

  it('connection loss flips at exactly three failures and a fresh start clears it', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    onErr(2)
    expect(s.connectionLost).toBe(false)
    onErr(3)
    expect(s.connectionLost).toBe(true)
    await s.start('r1')
    expect(s.connectionLost).toBe(false)
    expect(s.error).toBeNull()
    expect(unsubscribe).toHaveBeenCalledTimes(1)  // the restart stopped the old subscription first
  })

  it('stop() is idempotent and a decide with no run is a no-op', async () => {
    const s = useRunGraphStore()
    await s.decide('k', 'approve', '')
    expect(api.decideGate).not.toHaveBeenCalled()
    await s.start('r1')
    s.stop()
    s.stop()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('a non-404 decision failure toasts decision failed, not the race wording', async () => {
    const s = useRunGraphStore()
    await s.start('r1')
    api.decideGate.mockRejectedValueOnce(new HttpStatusError(502, 'down'))
    await s.decide('architecture#2', 'approve', '')
    expect(useUiStore().toast).toHaveBeenCalledWith(expect.stringContaining('decision failed'), expect.any(String))
  })
})
