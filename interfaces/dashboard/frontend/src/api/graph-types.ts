// Graph wire shapes (E-76 spec §5). A STRUCTURAL mirror of the pydantic
// models in src/sdlc/dashboard/graph_wire.py, pinned by the recorded
// fixtures in __fixtures__/graph/ (tests/test_graph_fixtures_fresh.py).
// `role` and `gate` stay opaque: the canvas never learns RoleConfig fields.
// FINAL = shipped by E-76; PROVISIONAL = E-73/E-75/E-77 implement.

export interface NodeWire {
  id: string
  type: string
  role?: Record<string, unknown>
  gate?: Record<string, unknown>
  position?: { x: number; y: number }
  label?: string
}

export interface EdgeWire {
  source: string
  source_port: string
  target: string
  target_port: string
  max_traversals?: number
  label?: string
}

export interface GraphWire {
  schema_version: 1
  nodes: NodeWire[]
  edges: EdgeWire[]
}

export interface EdgeRef {
  source: string
  source_port: string
  target: string
  target_port: string
}

export interface ShapeError {
  loc: (string | number)[]
  msg: string
  line: number | null
  column: number | null
}

// --- catalog (FINAL) ---------------------------------------------------------

export interface PortWire {
  name: string
  direction: 'in' | 'out'
  payload: string | null
  required: boolean
  multiplicity: 'one' | 'many'
}

export interface NodeTypeWire {
  type: string
  kind: 'stage' | 'gate'
  role: string | null
  canonical_stage: string | null
  default_id: string
  ports: PortWire[]
  connectable: Record<string, { type: string; port: string }[]>
}

export type Capability = 'validate' | 'save' | 'load' | 'run_graph'

export interface CatalogWire {
  node_types: NodeTypeWire[]
  canonical_stages: string[]
  schemas: { GraphNode: JsonSchema; GraphEdge: JsonSchema }
  capabilities: Record<Capability, boolean>
  max_graph_bytes: number
}

// The JSON Schema subset pydantic emits; schema_form narrows further.
export type JsonSchema = Record<string, unknown>

// --- parse / serialize (FINAL) ----------------------------------------------------

export type ParseWire =
  | { ok: true; graph: GraphWire; sha: string }
  | { ok: false; shape_errors: ShapeError[] }

export type SerializeWire = { ok: true; yaml: string } | { ok: false; shape_errors: ShapeError[] }

// --- validate (PROVISIONAL, E-73 + E-75) ---------------------------------------------

export interface IssueTarget {
  kind: 'graph' | 'node' | 'edge' | 'port'
  id?: string | null
  edge?: EdgeRef | null
  node?: string | null
  port?: string | null
}

export interface Issue {
  code: string
  severity: 'error' | 'warning'
  message: string
  target: IssueTarget
}

export interface ValidationWire {
  issues: Issue[]
  back_edges: EdgeRef[]
}

// --- save / load (PROVISIONAL, E-75 + E-77) --------------------------------------------

export type SaveWire =
  | { ok: true; sha: string; validation: ValidationWire | null }
  | { ok: false; shape_errors: ShapeError[] }

export type LoadWire =
  | { ok: true; sha: string; graph: GraphWire }
  | { ok: false; reason: 'not_found' }

// --- run graph and run state (PROVISIONAL, E-75 on E-74) --------------------------------

export type GraphResponse =
  | { kind: 'graph'; sha: string; graph: GraphWire; back_edges: EdgeRef[] }
  | { kind: 'no_graph'; reason: 'legacy_run' }

export type NodeRunStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale'

export interface NodeRunState {
  status: NodeRunStatus
  round: number
  started_at: string | null
  ended_at: string | null
  cost_usd: number | null
}

export interface PendingRef {
  node: string
  key: string
  kind: 'gate' | 'clarify' | 'escalation'
}

export type GraphStateResponse =
  | { kind: 'no_graph'; reason: 'legacy_run' }
  | {
      kind: 'state'
      graph_sha: string
      nodes: Record<string, NodeRunState>
      edges: { edge: EdgeRef; traversals: number }[]
      current_nodes: string[]
      pending: PendingRef[]
      terminal: null | 'done' | 'failed' | 'escalated'
    }

export class CapabilityUnavailable extends Error {
  constructor(readonly capability: Capability) {
    super(`graph capability "${capability}" is not available on this server`)
    this.name = 'CapabilityUnavailable'
  }
}

export function edgeRefOf(e: EdgeRef): EdgeRef {
  return { source: e.source, source_port: e.source_port, target: e.target, target_port: e.target_port }
}

export function sameEdge(a: EdgeRef, b: EdgeRef): boolean {
  return (
    a.source === b.source &&
    a.source_port === b.source_port &&
    a.target === b.target &&
    a.target_port === b.target_port
  )
}
