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
