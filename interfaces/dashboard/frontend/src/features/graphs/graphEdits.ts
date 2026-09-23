// Pure edit operations on a working copy (E-76 spec §8.2-§8.3). Each returns
// a NEW graph; none decides legality. The edit-mechanics register (M1-M4) is
// the complete set of guards: each protects the editor's own addressing or
// reversibility, removes no expressiveness (text apply still reaches every
// graph), and reports nothing as a validation result.
import type { EdgeWire, GraphWire, NodeWire } from '../../api/graph-types'
import { edgeKeys, nodeKeys } from '../../shared/graphCanvas.adapter'

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

export type EditResult =
  | { ok: true; graph: GraphWire; select?: string | null; notice?: string }
  | { ok: false; field: string; message: string }

/** A fresh id: the catalog's Python-computed default_id, then _2, _3... (smallest free). */
export function freshId(graph: GraphWire, defaultId: string): string {
  const used = new Set(graph.nodes.map((n) => n.id))
  if (!used.has(defaultId)) return defaultId
  let n = 2
  while (used.has(`${defaultId}_${n}`)) n++
  return `${defaultId}_${n}`
}

// M4: a non-finite coordinate serializes as JSON null and fails NodePosition.
const finite = (x: number, y: number) => Number.isFinite(x) && Number.isFinite(y)

export function addNode(graph: GraphWire, type: string, defaultId: string, x: number, y: number): EditResult {
  const g = clone(graph)
  const id = freshId(g, defaultId)
  const node: NodeWire = { id, type }
  if (finite(x, y)) node.position = { x, y }
  g.nodes.push(node)
  return { ok: true, graph: g, select: id }
}

export function moveNode(graph: GraphWire, key: string, x: number, y: number): EditResult {
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0 || !finite(x, y)) {
    if (!finite(x, y)) console.warn(`graph editor: dropped non-finite position for ${key}`)
    return { ok: true, graph }  // M4 / unknown key: keep the previous value
  }
  const g = clone(graph)
  g.nodes[index].position = { x, y }
  return { ok: true, graph: g }
}

/** Canvas key -> domain id (a duplicate key `id~2` names domain id `id`). */
export function idOfKey(graph: GraphWire, key: string): string | null {
  const index = nodeKeys(graph).indexOf(key)
  return index < 0 ? null : graph.nodes[index].id
}

export function connect(graph: GraphWire, fromKey: string, fromPort: string, toKey: string, toPort: string): EditResult {
  const source = idOfKey(graph, fromKey)
  const target = idOfKey(graph, toKey)
  if (source === null || target === null) return { ok: true, graph }
  const edge: EdgeWire = { source, source_port: fromPort, target, target_port: toPort }
  // M1: the 4-tuple IS edge identity; a second bare copy is unaddressable on
  // the canvas, so connecting onto an existing tuple selects it instead.
  const existing = graph.edges.findIndex(
    (e) => e.source === source && e.source_port === fromPort && e.target === target && e.target_port === toPort,
  )
  if (existing >= 0) return { ok: true, graph, select: edgeKeys(graph)[existing] }
  const g = clone(graph)
  g.edges.push(edge)
  return { ok: true, graph: g, select: edgeKeys(g)[g.edges.length - 1] }
}

export function removeElement(graph: GraphWire, kind: 'node' | 'edge', key: string): EditResult {
  const g = clone(graph)
  if (kind === 'edge') {
    // By canvas key (4-tuple + occurrence), never by tuple: deleting one of
    // two duplicate edges deletes one.
    const index = edgeKeys(graph).indexOf(key)
    if (index >= 0) g.edges.splice(index, 1)
    return { ok: true, graph: g, select: null }
  }
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0) return { ok: true, graph }
  const [removed] = g.nodes.splice(index, 1)
  // Incident edges go with the node -- unless another node still carries the
  // id, in which case those edges cannot be attributed to the deleted copy.
  if (!g.nodes.some((n) => n.id === removed.id)) {
    g.edges = g.edges.filter((e) => e.source !== removed.id && e.target !== removed.id)
  }
  return { ok: true, graph: g, select: null }
}

/**
 * The inspector's candidate graph for a node edit (spec §8.3). A rename
 * rewrites every incident edge endpoint in place, no reordering -- except:
 * M2 refuses a rename onto an id another node uses (the cascade would merge
 * edge sets irreversibly); M3 renames a node whose own id is duplicated
 * WITHOUT touching edges (they cannot be attributed to one copy).
 */
export function nodeEditCandidate(graph: GraphWire, key: string, next: NodeWire): EditResult {
  const index = nodeKeys(graph).indexOf(key)
  if (index < 0) return { ok: false, field: '', message: 'the node is no longer on the canvas' }
  const old = graph.nodes[index]
  const g = clone(graph)
  g.nodes[index] = clone(next)
  if (next.id === old.id) return { ok: true, graph: g }
  const others = graph.nodes.filter((_, i) => i !== index)
  if (others.some((n) => n.id === next.id)) {
    return { ok: false, field: 'id', message: `'${next.id}' is already used by another node, so renaming would merge their edges` }
  }
  if (others.some((n) => n.id === old.id)) {
    return { ok: true, graph: g, select: next.id, notice: `edges stay with '${old.id}': the id was ambiguous` }
  }
  for (const e of g.edges) {
    if (e.source === old.id) e.source = next.id
    if (e.target === old.id) e.target = next.id
  }
  return { ok: true, graph: g, select: next.id }
}

export function edgeEditCandidate(graph: GraphWire, key: string, next: EdgeWire): EditResult {
  const index = edgeKeys(graph).indexOf(key)
  if (index < 0) return { ok: false, field: '', message: 'the edge is no longer on the canvas' }
  const g = clone(graph)
  g.edges[index] = clone(next)
  return { ok: true, graph: g }
}

/** Clearing a label removes the field; never writes ''. */
export function withoutEmptyLabel<T extends { label?: string }>(element: T): T {
  if (element.label !== '') return element
  const { label: _label, ...rest } = element
  return rest as T
}
