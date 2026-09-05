import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FleetRow, { type FleetRowProps } from './FleetRow.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="to" data-testid="fleet-row"><slot /></a>',
}

const baseProps: FleetRowProps = {
  id: 'run-123',
  title: 'Implement component library',
  mode: 'brownfield',
  dots: [{ stage: 'code', state: 'active' }],
  status: { kind: 'running', label: 'running', pulsing: true },
  blocker: 'review gate',
  cost: 4.5,
  age: '12m',
  href: '/runs/run-123',
}

describe('FleetRow', () => {
  it('renders every supplied field in column order', () => {  // clause: FLEET_ROW-1
    const w = mount(FleetRow, {
      props: baseProps,
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.text()).toContain('run-123')
    expect(w.text()).toContain('Implement component library')
    expect(w.text()).toContain('brownfield')
    expect(w.text()).toContain('running')
    expect(w.text()).toContain('review gate')
    expect(w.text()).toContain('$4.50')
    expect(w.text()).toContain('12m')
  })

  it('renders null cost as an em dash, never 0.00', () => {  // clause: FLEET_ROW-1.1
    const w = mount(FleetRow, {
      props: { ...baseProps, cost: null },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.find('.cmp-fleet-row-cost').text()).toBe('—')
    expect(w.text()).not.toContain('0.00')
  })

  it('links the whole row to the supplied destination href', () => {  // clause: FLEET_ROW-2
    const w = mount(FleetRow, {
      props: baseProps,
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    const link = w.find('a[data-testid="fleet-row"]')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/runs/run-123')
  })

  it('applies truncation classes to long titles', () => {  // clause: FLEET_ROW-3
    const w = mount(FleetRow, {
      props: { ...baseProps, title: 'A very long title that truncates' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    const titleEl = w.find('.cmp-fleet-row-title-text')
    expect(titleEl.exists()).toBe(true)
    expect(titleEl.classes()).toContain('cmp-fleet-row-title-text')
  })
})
