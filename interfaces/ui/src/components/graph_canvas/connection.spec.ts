import { describe, it, expect, vi } from 'vitest'
import { acceptConnection, handleId, toPortRefs } from './connection'

const c = { source: 'architect', sourceHandle: handleId('out', 'spec'), target: 'architecture', targetHandle: handleId('in', 'artifact') }

describe('acceptConnection', () => {
  it('accepts exactly what the caller accepts, passing port refs', () => {  // clause: GRAPH_CANVAS-6
    const yes = vi.fn(() => true)
    expect(acceptConnection(true, yes, c)).toBe(true)
    expect(yes).toHaveBeenCalledWith({ node: 'architect', port: 'spec' }, { node: 'architecture', port: 'artifact' })
    expect(acceptConnection(true, () => false, c)).toBe(false)
  })

  it('evaluates no rule of its own: a self-loop and a repeat both defer to the caller', () => {  // clause: GRAPH_CANVAS-6
    const self = { source: 'a', sourceHandle: 'out:x', target: 'a', targetHandle: 'in:x' }
    expect(acceptConnection(true, () => true, self)).toBe(true)
    expect(acceptConnection(true, () => true, c)).toBe(true)
  })

  it('refuses everything when not editable, without asking', () => {  // clause: GRAPH_CANVAS-5
    const ask = vi.fn(() => true)
    expect(acceptConnection(false, ask, c)).toBe(false)
    expect(ask).not.toHaveBeenCalled()
  })

  it('maps handles to port refs', () => {
    expect(toPortRefs(c)).toEqual({ from: { node: 'architect', port: 'spec' }, to: { node: 'architecture', port: 'artifact' } })
  })
})
