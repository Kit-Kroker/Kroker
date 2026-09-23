import { describe, it, expect, vi } from 'vitest'
import {
  addNode, connect, edgeEditCandidate, freshId, idOfKey, moveNode, nodeEditCandidate, removeElement, withoutEmptyLabel,
} from './graphEdits'
import type { GraphWire } from '../../api/graph-types'

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

  // --- chaos: contract corners the happy paths above leave open ----------

  it('connect and remove with unknown keys are silent no-ops', () => {  // M-guard family
    const g = G()
    const c = connect(g, 'ghost', 'ok', 'architect', 'requirements')
    expect(c.ok && c.graph).toBe(g)
    expect(c.ok && c.select).toBeUndefined()
    const ge = G()
    ge.edges.push(e('intake', 'ok', 'architect', 'requirements'))
    const r = removeElement(ge, 'edge', 'intake.ok>architect.requirements#9')
    expect(r.ok && r.graph.edges).toHaveLength(3)
    const rn = removeElement(ge, 'node', 'ghost')
    expect(rn.ok && rn.graph).toBe(ge)
  })

  it('editing an element that is no longer on the canvas fails with a mechanic message', () => {
    expect(nodeEditCandidate(G(), 'ghost', { id: 'x', type: 'intake' })).toEqual({
      ok: false, field: '', message: 'the node is no longer on the canvas',
    })
    expect(edgeEditCandidate(G(), 'ghost', e('a', 'b', 'c', 'd'))).toEqual({
      ok: false, field: '', message: 'the edge is no longer on the canvas',
    })
  })
})
