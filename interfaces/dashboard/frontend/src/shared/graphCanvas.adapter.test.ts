import { describe, it, expect } from 'vitest'
import { edgeKeys, formatElapsed, locLabel, locWithin, nodeKeys, toCanvas } from './graphCanvas.adapter'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import preCode from '../api/__fixtures__/graph/scenarios/pre_code.json'
import graphResponse from '../api/__fixtures__/graph/run_state/graph_response.recorded.json'
import graphState from '../api/__fixtures__/graph/run_state/graph_state.recorded.json'
import validationRecorded from '../api/__fixtures__/graph/run_state/validation.recorded.json'
import type { CatalogWire, GraphStateResponse, GraphWire, Issue, ValidationWire } from '../api/graph-types'

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
    expect(nodes.find((n) => n.key === 'intake')!.ports).toEqual([
      { name: 'ok', side: 'out', kind: 'signal', label: 'ok', optional: false },
      { name: 'brownfield', side: 'out', kind: 'signal', label: 'brownfield', optional: false },
      { name: 'reject', side: 'out', kind: 'signal', label: 'reject', optional: false },
      { name: 'fail', side: 'out', kind: 'data', label: 'fail', optional: false },
    ])
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
    // The recorded validation is pre_code's (E-75 §7.3): its back_edges are
    // the three revise loops of the PRE graph.
    const backEdges = (validationRecorded as unknown as ValidationWire).back_edges
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
  // Re-sourced from the recorded run_state contract (E75-OQ-1): the
  // provisional run_graphs.provisional.json script is gone; blocked gives
  // the decoration picture, escalated the traversal counts.
  const states = graphState as unknown as Record<string, GraphStateResponse>

  it('joins traversals with the pinned max_traversals, defaulting to 0', () => {
    const m = toCanvas(PRE, { typeOf, state: states.escalated_revise_exhausted })
    const loop = m.edges.find((x) => x.key === 'architecture.revise>architect.guidance')!
    expect(loop.counter).toEqual({ used: 2, max: 2 }) // the recorded revisal count
    expect(m.edges.find((x) => x.key === 'plan.revise>planner.guidance')!.counter).toEqual({ used: 0, max: 2 })
    expect(m.edges.find((x) => x.key === 'architect.spec>architecture.artifact')!.counter).toBeUndefined()
  })

  it('decorates status, cost, elapsed and round', () => {
    // The recorded blocked_at_architecture projection: every activation ran
    // AT→AT (elapsed 0m 00s), the gate is still open at `now` (+30s).
    const m = toCanvas(PRE, { typeOf, state: states.blocked_at_architecture, now: new Date('2026-09-17T09:00:30Z') })
    const architect = m.nodes.find((n) => n.key === 'architect')!
    expect(architect.status).toBe('done')
    expect(architect.metrics).toEqual({ cost: '$1.87', elapsed: '0m 00s', round: undefined })
    const gate = m.nodes.find((n) => n.key === 'architecture')!
    expect(gate.metrics).toEqual({ cost: '—', elapsed: '0m 30s', round: undefined })
    expect(m.pendingByNode.architecture).toEqual([{ node: 'architecture', key: 'architecture#1', kind: 'gate' }])
  })

  // --- chaos: FINAL wire shapes the provisional mirror does not know yet ----
  // PendingRef.node is nullable (E-75 §7.4): an unattributed pending has no
  // node to anchor to -- the inbox is its surface. Statuses skipped/cancelled
  // appear in the recorded interrupted scenario (graph_state.recorded.json).

  it('an unattributed pending is keyed nowhere; skipped and cancelled pass through as statuses', () => {
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {
        intake: { status: 'skipped', round: 0, started_at: null, ended_at: null, cost_usd: null },
        architecture: { status: 'cancelled', round: 1, started_at: null, ended_at: null, cost_usd: null },
      },
      edges: [],
      current_nodes: [],
      pending: [
        { node: null, key: 'clarify#1', kind: 'clarify' },
        { node: 'architecture', key: 'architecture#1', kind: 'gate' },
      ],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const m = toCanvas(PRE, { typeOf, state })
    // never a coerced "null" key, never a throw; only the attributed ref keys
    expect(Object.keys(m.pendingByNode)).toEqual(['architecture'])
    expect(m.nodes.find((n) => n.key === 'intake')!.status).toBe('skipped')
    expect(m.nodes.find((n) => n.key === 'architecture')!.status).toBe('cancelled')
  })
})

describe('toCanvas (run mode over the recorded FINAL contract)', () => {
  // E75-OQ-1 (bug canvas-run-mode): the recorded fixtures are the FINAL wire
  // (E-75 design §7.4). The canvas must decorate them as-is and surface the
  // run's outcome so a terminal run view can render it.
  const GRAPH = (graphResponse as unknown as { graph: GraphWire }).graph
  const STATES = graphState as unknown as Record<string, GraphStateResponse>
  const outcomeOf = (m: ReturnType<typeof toCanvas>) => (m as { outcome?: unknown }).outcome
  const statusOf = (m: ReturnType<typeof toCanvas>, key: string): string =>
    String(m.nodes.find((n) => n.key === key)?.status)

  it('blocked: recorded architect cost and gate pending ref, with the running outcome present', () => {
    const m = toCanvas(GRAPH, { typeOf, state: STATES.blocked_at_architecture, now: new Date('2026-09-14T09:35:30Z') })
    const architect = m.nodes.find((n) => n.key === 'architect')!
    expect(architect.status).toBe('done')
    expect(architect.metrics?.cost).toBe('$1.87')
    expect(m.pendingByNode.architecture).toEqual([{ node: 'architecture', key: 'architecture#1', kind: 'gate' }])
    expect(statusOf(m, 'context')).toBe('skipped')
    expect(outcomeOf(m)).toEqual({ state: 'running', reason: null, result: null }) // RED until the wiring lands
  })

  it('escalated: the revise loop counter is the recorded traversal count, with the escalated outcome', () => {
    const m = toCanvas(GRAPH, { typeOf, state: STATES.escalated_revise_exhausted })
    const loop = m.edges.find((x) => x.key === 'architecture.revise>architect.guidance')!
    expect(loop.counter).toEqual({ used: 2, max: 2 }) // static: the recorded revisal count
    expect(outcomeOf(m)).toEqual({ state: 'escalated', reason: 'architecture.revise: exhausted', result: null }) // RED
  })

  it('completed: every node decorated terminal, with the completed outcome present', () => {
    const m = toCanvas(GRAPH, { typeOf, state: STATES.completed })
    expect(m.nodes.filter((n) => n.status !== 'done' && n.status !== 'skipped')).toEqual([])
    expect(statusOf(m, 'context')).toBe('skipped')
    expect(outcomeOf(m)).toEqual({ state: 'completed', reason: null, result: 'deployed:https://example.invalid/pr/1' }) // RED
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
      outcome: { state: 'running', reason: null, result: null },
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
