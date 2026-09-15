import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NodePalette from './NodePalette.vue'

const items = [
  { type: 'gate.plan', kind: 'gate' as const, stage: 'planning' },
  { type: 'architect', kind: 'stage' as const, stage: 'architecture' },
  { type: 'mystery', kind: 'stage' as const, stage: null },
]

describe('NodePalette', () => {
  it('groups stages before gates, keeping supplied order', () => {  // clause: NODE_PALETTE-1
    const w = mount(NodePalette, { props: { items } })
    expect(w.findAll('[data-testid="palette-item"]').map((b) => b.attributes('data-type'))).toEqual(['architect', 'mystery', 'gate.plan'])
    expect(w.text()).toContain('unknown')
  })

  it('renders an empty state for no items', () => {  // clause: NODE_PALETTE-1
    const w = mount(NodePalette, { props: { items: [] } })
    expect(w.find('[data-testid="palette-empty"]').exists()).toBe(true)
  })

  it('emits pick with the type, unless disabled', async () => {  // clause: NODE_PALETTE-2
    const w = mount(NodePalette, { props: { items } })
    await w.find('[data-type="architect"]').trigger('click')
    expect(w.emitted('pick')).toEqual([['architect']])
    const off = mount(NodePalette, { props: { items, disabled: true } })
    await off.find('[data-type="architect"]').trigger('click')
    expect(off.emitted('pick')).toBeUndefined()
  })

  it('carries the type as the drag payload', async () => {  // clause: NODE_PALETTE-2
    const w = mount(NodePalette, { props: { items } })
    const data: Record<string, string> = {}
    const dataTransfer = { setData: (k: string, v: string) => { data[k] = v } }
    await w.find('[data-type="gate.plan"]').trigger('dragstart', { dataTransfer })
    expect(data).toEqual({ 'application/x-kroker-node-type': 'gate.plan' })
  })

  // --- chaos: contract corners the happy paths above leave open ----------

  it('while disabled, dragging carries no payload and the list still renders', async () => {  // clause: NODE_PALETTE-2
    const w = mount(NodePalette, { props: { items, disabled: true } })
    expect(w.findAll('[data-testid="palette-item"]')).toHaveLength(3)  // disabled is not an empty shell
    const data: Record<string, string> = {}
    const dataTransfer = { setData: (k: string, v: string) => { data[k] = v } }
    await w.find('[data-type="architect"]').trigger('dragstart', { dataTransfer })
    expect(data).toEqual({})
  })

  it('an unknown stage shows unknown on its own row, never a guessed stage', () => {  // NODE_PALETTE-1 failure mode
    const w = mount(NodePalette, { props: { items } })
    const mystery = w.find('[data-type="mystery"]')
    expect(mystery.text()).toContain('unknown')
    expect(mystery.text()).not.toContain('architecture')
    expect(mystery.text()).not.toContain('planning')
  })
})
