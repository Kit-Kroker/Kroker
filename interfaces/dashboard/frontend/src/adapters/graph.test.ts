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

  // --- chaos: contract corners the happy paths above leave open ----------

  it('keys triple duplicates in server order, for nodes and edges alike', () => {  // duplicate ids/edges
    const TRIPLE: GraphWire = {
      schema_version: 1,
      nodes: [{ id: 'x', type: 'intake' }, { id: 'x', type: 'intake' }, { id: 'x', type: 'intake' }],
      edges: [e('x', 'ok', 'x', 'in'), e('x', 'ok', 'x', 'in'), e('x', 'ok', 'x', 'in')],
    }
    expect(nodeKeys(TRIPLE)).toEqual(['x', 'x~2', 'x~3'])
    expect(edgeKeys(TRIPLE)).toEqual(['x.ok>x.in', 'x.ok>x.in#2', 'x.ok>x.in#3'])
  })

  it('indexes canvas keys back onto server positions, duplicates included', () => {  // duplicate ids/edges
    const m = toCanvas(DUP, { typeOf })
    expect(m.nodeIndex).toEqual({ intake: 0, 'intake~2': 1, ghost_type: 2 } as Record<string, number>)
    expect(m.edgeIndex).toEqual(
      { 'intake.ok>ghost_type.x': 0, 'intake.ok>ghost_type.x#2': 1, 'ghost_type.y>intake.trigger': 2 } as Record<string, number>,
    )
  })

  it('maps a port issue onto its node and labels an unresolvable target', () => {
    const issues: Issue[] = [
      { code: 'p', severity: 'error', message: 'port', target: { kind: 'port', node: 'intake', port: 'ok' } },
      { code: 'gone', severity: 'warning', message: 'van', target: { kind: 'node', id: 'deleted_node' } },
    ]
    const m = toCanvas(DUP, { typeOf, issues })
    expect(m.issues[0]).toMatchObject({ focusKey: 'intake', targetLabel: 'intake.ok' })
    expect(m.nodes.filter((n) => n.issueCount === 1).map((n) => n.key)).toEqual(['intake', 'intake~2'])
    expect(m.issues[1]).toMatchObject({ focusKey: null, targetLabel: 'deleted_node (not on canvas)' })
  })

  it('an unknown type with no edges is read-only with zero ports', () => {
    const LONE: GraphWire = { schema_version: 1, nodes: [{ id: 'mystery', type: 'nope.kind' }], edges: [] }
    const [n] = toCanvas(LONE, { typeOf }).nodes
    expect(n.readonly).toBe(true)
    expect(n.ports).toEqual([])
  })

  it('run decoration: no_graph is un-decorated, zero cost is $0.00 not an em-dash', () => {
    const ng = toCanvas(PRE, { typeOf, state: { kind: 'no_graph', reason: 'legacy_run' } })
    expect(ng.nodes.every((n) => n.status === undefined && n.metrics === undefined)).toBe(true)
    const state: GraphStateResponse = {
      kind: 'state',
      graph_sha: 's',
      nodes: { intake: { status: 'running', round: 1, started_at: '2026-09-14T09:00:00Z', ended_at: null, cost_usd: 0 } },
      edges: [],
      current_nodes: [],
      pending: [],
      terminal: null,
    }
    const m = toCanvas(PRE, { typeOf, state, now: new Date('2026-09-14T09:00:30Z') })
    expect(m.nodes.find((n) => n.key === 'intake')!.metrics).toEqual({ cost: '$0.00', elapsed: '0m 30s', round: undefined })
    // nodes the state does not know stay un-decorated
    expect(m.nodes.find((n) => n.key === 'planner')!.status).toBeUndefined()
  })

  it('loc helpers cover the edges collection and top-level locs; elapsed hits boundaries', () => {
    expect(locWithin(['edges', 1, 'target'], 'edges', 1)).toBe('target')
    expect(locWithin(['nodes', 3, 'id'], 'edges', 3)).toBeNull()  // collection mismatch
    expect(locLabel(['schema_version'])).toBe('schema_version')
    expect(formatElapsed(59_900)).toBe('0m 59s')
    expect(formatElapsed(60_000)).toBe('1m 00s')
    expect(formatElapsed(3_600_000)).toBe('1h 00m')
  })
})
