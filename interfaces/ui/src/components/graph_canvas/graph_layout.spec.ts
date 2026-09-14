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
