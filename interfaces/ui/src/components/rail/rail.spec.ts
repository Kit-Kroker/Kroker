import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Rail from './Rail.vue'

// 018 T023 (RED): the v5 rail (run block head, segmented tabs, section slots,
// call-to-action buttons). Stable hooks the implementation (T024) must carry:
// rail-title / rail-state / rail-rows / rail-budget / rail-budget-bar /
// rail-tab / rail-call.

const HEAD = {
  title: 'feature-graph-demo',
  state: 'halted',
  stateKind: 'failed',
  rows: [
    { k: 'round', v: 'r3' },
    { k: 'nodes', v: '12' },
  ],
  budget: { spent: '$2.60', limit: 20, pct: 13, note: 'coding spend only' },
}

const TABS = [
  { id: 'path', label: 'Path' },
  { id: 'events', label: 'Events' },
  { id: 'cost', label: 'Cost' },
]

const mountRail = (props: Record<string, unknown> = {}) =>
  mount(Rail, {
    props: { head: HEAD, tabs: TABS, active: 'path', calls: [], ...props },
    slots: {
      path: 'PATH-SECTION',
      events: 'EVENTS-SECTION',
      cost: 'COST-SECTION',
    },
  })

describe('Rail', () => {
  it('renders the head: title, state, rows and the budget with its bar', () => {  // clause: RAIL-1
    const w = mountRail()
    expect(w.find('[data-testid="rail-title"]').text()).toBe('feature-graph-demo')
    expect(w.find('[data-testid="rail-state"]').text()).toBe('halted')
    const rows = w.findAll('[data-testid="rail-rows"] [data-testid="rail-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('round')
    expect(rows[0].text()).toContain('r3')
    expect(rows[1].text()).toContain('nodes')
    expect(rows[1].text()).toContain('12')
    const budget = w.find('[data-testid="rail-budget"]')
    expect(budget.text()).toContain('$2.60')
    expect(budget.text()).toContain('coding spend only')
    expect(w.find('[data-testid="rail-budget-bar"]').exists()).toBe(true)
  })

  it('with no budget limit the budget reads off and no bar renders', () => {  // clause: RAIL-1
    const w = mountRail({
      head: { ...HEAD, budget: { spent: '$2.60', limit: null, pct: null, note: 'coding spend only' } },
    })
    expect(w.find('[data-testid="rail-budget"]').text()).toContain('off')
    expect(w.find('[data-testid="rail-budget-bar"]').exists()).toBe(false)
  })

  it('shows only the active tab section, follows active, and tabs emit select', async () => {  // clause: RAIL-2
    const w = mountRail()
    expect(w.text()).toContain('PATH-SECTION')
    expect(w.text()).not.toContain('EVENTS-SECTION')
    expect(w.text()).not.toContain('COST-SECTION')

    await w.setProps({ active: 'events' })
    expect(w.text()).toContain('EVENTS-SECTION')
    expect(w.text()).not.toContain('PATH-SECTION')

    const costTab = w
      .findAll('[data-testid="rail-tab"]')
      .find((t) => t.text() === 'Cost')
    expect(costTab).toBeDefined()
    await costTab!.trigger('click')
    expect(w.emitted('select')).toEqual([['cost']])
  })

  it('renders each call as a button in order; a click emits its index', async () => {  // clause: RAIL-3
    const w = mountRail({
      calls: [
        { label: 'Revise plan', kind: 'primary' },
        { label: 'Halt run', kind: 'danger' },
      ],
    })
    const calls = w.findAll('[data-testid="rail-call"]')
    expect(calls).toHaveLength(2)
    expect(calls[0].text()).toBe('Revise plan')
    expect(calls[1].text()).toBe('Halt run')
    await calls[0].trigger('click')
    await calls[1].trigger('click')
    expect(w.emitted('call')).toEqual([[0], [1]])
  })
})

describe('Rail (chaos, 018 T023 RED)', () => {
  it('an empty rows array mounts and renders zero rail-row elements inside rail-rows', () => {  // clause: RAIL-1
    const w = mountRail({ head: { ...HEAD, rows: [] } })
    expect(w.find('[data-testid="rail-rows"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="rail-rows"] [data-testid="rail-row"]')).toHaveLength(0)
  })

  it('a numeric limit of 0 keeps the budget bar on (only null means off)', () => {  // clause: RAIL-1
    const w = mountRail({
      head: { ...HEAD, budget: { spent: '$0.00', limit: 0, pct: 0, note: 'coding spend only' } },
    })
    expect(w.find('[data-testid="rail-budget-bar"]').exists()).toBe(true)
    expect(w.find('[data-testid="rail-budget"]').text()).not.toContain('off')
  })

  it('an active id matching no tab renders no section slot content at all', () => {  // clause: RAIL-2
    const w = mountRail({ active: 'no-such-tab' })
    expect(w.text()).not.toContain('PATH-SECTION')
    expect(w.text()).not.toContain('EVENTS-SECTION')
    expect(w.text()).not.toContain('COST-SECTION')
  })

  it('an empty calls array renders zero rail-call buttons', () => {  // clause: RAIL-3
    const w = mountRail({ calls: [] })
    expect(w.findAll('[data-testid="rail-call"]')).toHaveLength(0)
  })

  it('a tab click emits only select; a call click emits only call', async () => {  // clause: RAIL-2
    const w = mountRail({ calls: [{ label: 'Revise plan', kind: 'primary' }] })
    const tab = w.findAll('[data-testid="rail-tab"]').find((t) => t.text() === 'Events')
    await tab!.trigger('click')
    expect(w.emitted('select')).toEqual([['events']])
    expect(w.emitted('call')).toBeUndefined()

    await w.find('[data-testid="rail-call"]').trigger('click')
    expect(w.emitted('call')).toEqual([[0]])
    expect(w.emitted('select')).toEqual([['events']])  // unchanged: still just the one tab click
  })

  it('a row with an empty v still renders its row element and its k text', () => {  // clause: RAIL-1
    const w = mountRail({ head: { ...HEAD, rows: [{ k: 'round', v: '' }] } })
    const rows = w.findAll('[data-testid="rail-rows"] [data-testid="rail-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('round')
    expect(rows[0].text()).not.toContain('undefined')
  })
})
