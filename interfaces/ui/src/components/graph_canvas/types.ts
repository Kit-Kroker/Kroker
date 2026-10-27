// Display primitives for the graph canvas (E-76 spec §10.2). Constructible
// as literals; no domain type and no vue-flow type ever appears here
// (FR-1400). The dashboard's adapters/graph.ts builds these.

// 'skipped'/'cancelled' are the E-75 §7.4 run-end states (a node the graph
// never routes to; a live node cut down by a closed execution).
export type CanvasStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale' | 'skipped' | 'cancelled'

export const CANVAS_STATUSES: readonly CanvasStatus[] = ['idle', 'running', 'blocked', 'done', 'failed', 'stale', 'skipped', 'cancelled']

export interface CanvasPort {
  name: string
  side: 'in' | 'out'
  kind: 'signal' | 'data'
  label: string
  optional: boolean
}

export interface CanvasNode {
  key: string
  title: string
  subtitle?: string
  ports: CanvasPort[]
  status?: CanvasStatus
  metrics?: { cost?: string; elapsed?: string; round?: string }
  issueCount: number
  position?: { x: number; y: number }
  /** A node whose type is not in the catalog: handles render, none connect. */
  readonly?: boolean
  /** 018 data-model §4.1: a run-outcome sink node ('node' by default). */
  kind?: 'node' | 'sink'
  sink?: CanvasSink
}

/** 018 data-model §4.1: a sink lights for the outcome the run took. */
export interface CanvasSink {
  outcome: 'completed' | 'rejected' | 'failed' | 'escalated'
  lit: boolean
  sub: string
}

export interface PortRef {
  node: string
  port: string
}

export interface CanvasEdge {
  key: string
  from: PortRef
  to: PortRef
  label?: string
  backward: boolean
  counter?: { used: number; max: number }
  issueCount: number
  /** 018 data-model §4.1: shown under the payloads toggle, selection or a revise loop. */
  payload?: string
  /** 018 data-model §4.1: e.g. "next revise escalates the run". */
  note?: string
}

export interface Point {
  x: number
  y: number
}
