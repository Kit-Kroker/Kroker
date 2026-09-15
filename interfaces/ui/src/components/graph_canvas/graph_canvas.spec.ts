import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import GraphCanvas from './GraphCanvas.vue'
import type { CanvasNode } from './types'

// vue-flow needs real layout, so rendering clauses are Playwright-tier
// (graph_canvas.pw.ts). jsdom covers the fail-fast contract and events that
// do not depend on measured geometry.
beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
  globalThis.DataTransfer ??= class {
    private data = new Map<string, string>()
    setData(format: string, data: string) { this.data.set(format, data) }
    getData(format: string) { return this.data.get(format) ?? '' }
  } as unknown as typeof DataTransfer
})

const node = (key: string, extra: Partial<CanvasNode> = {}): CanvasNode => ({
  key, title: key, ports: [], issueCount: 0, position: { x: 0, y: 0 }, ...extra,
})

describe('GraphCanvas', () => {
  it('fails rendering on an unknown status', () => {  // clause: GRAPH_CANVAS-4
    expect(() => mount(GraphCanvas, { props: { nodes: [node('a', { status: 'sideways' as never })], edges: [] } })).toThrow(/sideways/)
  })

  it('emits no remove in run mode and removes the selection in edit mode', async () => {  // clause: GRAPH_CANVAS-5
    const ro = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], selectedKey: 'a' } })
    await ro.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(ro.emitted('remove')).toBeUndefined()
    const rw = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], selectedKey: 'a', editable: true } })
    await rw.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(rw.emitted('remove')).toEqual([[{ kind: 'node', key: 'a' }]])
  })

  it('lays out an unpositioned node and emits its finite position only when editable', () => {  // clause: GRAPH_CANVAS-8
    const rw = mount(GraphCanvas, { props: { nodes: [node('a', { position: undefined })], edges: [], editable: true } })
    const moves = rw.emitted('move') as [{ key: string; x: number; y: number }][]
    expect(moves).toHaveLength(1)
    expect(Number.isFinite(moves[0][0].x) && Number.isFinite(moves[0][0].y)).toBe(true)
    const ro = mount(GraphCanvas, { props: { nodes: [node('a', { position: undefined })], edges: [] } })
    expect(ro.emitted('move')).toBeUndefined()
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('an empty canvas mounts silently: no moves, no layout failure', () => {  // clause: GRAPH_CANVAS-8
    const w = mount(GraphCanvas, { props: { nodes: [], edges: [], editable: true } })
    expect(w.emitted('move')).toBeUndefined()
    expect(w.emitted('layout-failed')).toBeUndefined()
  })

  it('Delete with no selection removes nothing; an edge key removes as an edge', async () => {  // clause: GRAPH_CANVAS-5
    const w = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], editable: true } })
    await w.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(w.emitted('remove')).toBeUndefined()
    const we = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], editable: true, selectedKey: 'e1' } })
    await we.find('[data-testid="graph-canvas"]').trigger('keydown', { key: 'Delete' })
    expect(we.emitted('remove')).toEqual([[{ kind: 'edge', key: 'e1' }]])
  })

  it('tidyRequest re-lays out every node once per distinct request', async () => {  // clause: GRAPH_CANVAS-8
    const w = mount(GraphCanvas, { props: { nodes: [node('a'), node('b')], edges: [], editable: true } })
    expect(w.emitted('move')).toBeUndefined()  // fully positioned: the auto-layout watch stays quiet
    await w.setProps({ tidyRequest: 1 })
    const moves = w.emitted('move') as [{ key: string; x: number; y: number }][]
    expect(moves.map((m) => m[0].key).sort()).toEqual(['a', 'b'])
    for (const m of moves) expect(Number.isFinite(m[0].x) && Number.isFinite(m[0].y)).toBe(true)
    await w.setProps({ tidyRequest: 1 })  // the same request again: no re-fire
    expect((w.emitted('move') as unknown[]).length).toBe(moves.length)
  })

  it('drop-type fires in edit mode only, for palette payloads only, canvas-relative', async () => {  // clause: GRAPH_CANVAS-5
    const payload = new DataTransfer()
    payload.setData('application/x-kroker-node-type', 'architect')
    const w = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], editable: true } })
    await w.find('[data-testid="graph-canvas"]').trigger('drop', { dataTransfer: payload, clientX: 210, clientY: 120 })
    // node-centred (NODE_WIDTH/2, half a node tall) and canvas-relative, not viewport-absolute
    expect(w.emitted('drop-type')).toEqual([[{ type: 'architect', x: 115, y: 100 }]])
    const ro = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [] } })
    await ro.find('[data-testid="graph-canvas"]').trigger('drop', { dataTransfer: payload, clientX: 210, clientY: 120 })
    expect(ro.emitted('drop-type')).toBeUndefined()
    const foreign = mount(GraphCanvas, { props: { nodes: [node('a')], edges: [], editable: true } })
    await foreign.find('[data-testid="graph-canvas"]').trigger('drop', { dataTransfer: new DataTransfer(), clientX: 10, clientY: 10 })
    expect(foreign.emitted('drop-type')).toBeUndefined()
  })
})
