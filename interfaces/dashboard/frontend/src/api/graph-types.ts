// Graph wire shapes (E-76 spec §5). A STRUCTURAL mirror of the pydantic
// models in src/sdlc/dashboard/graph_wire.py, pinned by the recorded
// fixtures in __fixtures__/graph/ (tests/test_graph_fixtures_fresh.py).
// `role` and `gate` stay opaque: the canvas never learns RoleConfig fields.
// Sections marked FINAL match the landed wire (E-76/E-73/E-75/E-77).

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

// --- validate (FINAL, E-73 + E-75) ---------------------------------------------

export interface IssueTarget {
  kind: 'graph' | 'node' | 'edge' | 'port'
  id?: string | null
  edge?: EdgeRef | null
  node?: string | null
  port?: string | null
}

export interface Issue {
  code: string
  // E-75 design §7.3: not_executable is legal but unrunnable by this
  // worker -- the validator's severity, distinct from error/warning.
  severity: 'error' | 'warning' | 'not_executable'
  message: string
  target: IssueTarget
}

export interface ValidationWire {
  issues: Issue[]
  back_edges: EdgeRef[]
}

// --- save / load (FINAL, E-75 + E-77) --------------------------------------------

export type SaveWire =
  | { ok: true; sha: string; validation: ValidationWire | null }
  | { ok: false; shape_errors: ShapeError[] }

export type LoadWire =
  | { ok: true; sha: string; graph: GraphWire }
  | { ok: false; reason: 'not_found' }

// --- run graph and run state (FINAL, E-75 §7.4 as landed by E-75/E-77) ------
// The mirror of graph_wire.py's run-state models, caught up to the recorded
// fixtures in __fixtures__/graph/run_state/ (tests/test_graph_fixtures_fresh.py).

export type GraphResponse =
  | { kind: 'graph'; sha: string; graph: GraphWire; back_edges: EdgeRef[] }
  | { kind: 'no_graph'; reason: 'legacy_run' }

// The run-state status set (graph_wire.NodeRunState.status): skipped = a node
// the run's graph never routes to; cancelled = a live node cut down by a
// closed execution.
export type NodeRunStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale' | 'skipped' | 'cancelled'

export interface NodeRunState {
  status: NodeRunStatus
  round: number
  started_at: string | null
  ended_at: string | null
  cost_usd: number | null
  /** E-77 US3/FR-003: resolve_stage of the node's type; null when unknown. */
  canonical_stage?: string | null
}

// E-75 §7.4: node is null for an unattributed pending (opened outside any
// activation) -- the inbox is its surface, no canvas node anchors it.
export interface PendingRef {
  node: string | null
  key: string
  kind: 'gate' | 'clarify' | 'escalation'
}

// E-75 §7.4: outcome replaces terminal. state 'running' is the ONLY
// non-final state; the poll ends on anything else.
export interface RunOutcomeWire {
  state: 'running' | 'completed' | 'rejected' | 'escalated' | 'failed'
  reason: string | null
  result: string | null
}

/** E-77 R-10/FR-021: the run exists but its state cannot be projected. */
export interface GraphStateUnavailable {
  kind: 'unavailable'
  reason: 'registry_drift' | 'retention_expired'
  problems: string[]
}

export type GraphStateResponse =
  | { kind: 'no_graph'; reason: 'legacy_run' }
  | GraphStateUnavailable
  | {
      kind: 'state'
      graph_sha: string
      nodes: Record<string, NodeRunState>
      /** Back edges only; an absent edge means 0 traversals. */
      edges: { edge: EdgeRef; traversals: number }[]
      /** Distinct node ids of state.live, sorted. */
      current_nodes: string[]
      pending: PendingRef[]
      outcome: RunOutcomeWire
    }

/** Finality (E-75 §7.4): anything but a running state ends the poll. */
export function isFinalState(state: GraphStateResponse): boolean {
  return state.kind !== 'state' || state.outcome.state !== 'running'
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
