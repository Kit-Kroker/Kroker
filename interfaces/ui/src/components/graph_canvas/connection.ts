// GRAPH_CANVAS-6, the fence: a connection is accepted iff the canvas is
// editable and the CALLER's `connectable` says so. The component evaluates
// no other rule -- multiplicity, duplicates, cycles are validate.py's.
import type { PortRef } from './types'

export interface HandleConnection {
  source: string
  sourceHandle?: string | null
  target: string
  targetHandle?: string | null
}

export const handleId = (side: 'in' | 'out', port: string) => `${side}:${port}`

const portOf = (handle: string | null | undefined) => (handle ?? '').replace(/^(in|out):/, '')

export function toPortRefs(c: HandleConnection): { from: PortRef; to: PortRef } {
  return { from: { node: c.source, port: portOf(c.sourceHandle) }, to: { node: c.target, port: portOf(c.targetHandle) } }
}

export function acceptConnection(
  editable: boolean,
  connectable: (from: PortRef, to: PortRef) => boolean,
  c: HandleConnection,
): boolean {
  if (!editable) return false
  const { from, to } = toPortRefs(c)
  return connectable(from, to)
}
