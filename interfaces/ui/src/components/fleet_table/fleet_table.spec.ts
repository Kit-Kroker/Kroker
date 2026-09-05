import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FleetTable from './FleetTable.vue'
import type { FleetRowProps } from '../fleet_row/FleetRow.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="to" data-testid="fleet-row"><slot /></a>',
}

const mkRow = (id: string): FleetRowProps => ({
  id,
  title: `Title ${id}`,
  mode: 'brownfield',
  dots: [{ stage: 'code', state: 'active' }],
  status: { kind: 'running', label: 'running', pulsing: true },
  blocker: null,
  cost: 1.5,
  age: '5m',
  href: `/runs/${id}`,
})

describe('FleetTable', () => {
  it('renders one row per supplied run in supplied order', () => {  // clause: FLEET_TABLE-1
    const rows = [mkRow('r1'), mkRow('r2'), mkRow('r3')]
    const w = mount(FleetTable, {
      props: { rows },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    const foundRows = w.findAll('[data-testid="fleet-row"]')
    expect(foundRows).toHaveLength(3)
    expect(foundRows[0].text()).toContain('r1')
    expect(foundRows[1].text()).toContain('r2')
    expect(foundRows[2].text()).toContain('r3')
  })

  it('renders header and empty state when rows is empty', () => {  // clause: FLEET_TABLE-1.1
    const w = mount(FleetTable, {
      props: { rows: [] },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.find('.cmp-fleet-table-head').exists()).toBe(true)
    expect(w.find('[data-testid="fleet-empty"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(0)
  })
})
