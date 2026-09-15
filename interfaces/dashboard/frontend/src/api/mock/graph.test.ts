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
