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
