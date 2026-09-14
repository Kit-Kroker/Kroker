// Display primitives for the graph canvas (E-76 spec §10.2). Constructible
// as literals; no domain type and no vue-flow type ever appears here
// (FR-1400). The dashboard's adapters/graph.ts builds these.

export type CanvasStatus = 'idle' | 'running' | 'blocked' | 'done' | 'failed' | 'stale'

export const CANVAS_STATUSES: readonly CanvasStatus[] = ['idle', 'running', 'blocked', 'done', 'failed', 'stale']

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
}

export interface Point {
  x: number
  y: number
}
