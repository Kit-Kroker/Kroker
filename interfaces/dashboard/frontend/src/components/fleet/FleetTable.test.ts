import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FleetTable from './FleetTable.vue'
import { useFleetStore } from '../../stores/fleet'
import type { Run } from '../../api/types'

const RouterLinkStub = {
  props: ['to'],
  template: '<a data-testid="row-link"><slot /></a>',
}

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'feature-x', title: 'A feature', mode: 'brownfield', repo: 'r', stageIdx: 4,
  status: 'blocked', blocker: 'clarify gate', cost: 3.12, budget: 40, age: '2h',
  decisions: [], ...over,
})

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('FleetTable', () => {
  it('renders a header and one row per run', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'r1' }), mkRun({ id: 'r2', status: 'done' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(2)
    expect(w.text()).toContain('RUN')
    expect(w.text()).toContain('STATUS')
  })

  it('renders 14 stage dots per row', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun()]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.findAll('[data-testid="stage-dot"]')).toHaveLength(14)
  })

  it('formats cost and age', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ cost: 3.1, age: '2h 14m' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    expect(w.text()).toContain('$3.10')
    expect(w.text()).toContain('2h 14m')
  })

  it('renders status pip with stable class and no inline style', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ status: 'blocked' })]
    const w = mount(FleetTable, { global: { stubs: { RouterLink: RouterLinkStub } } })
    const pip = w.find('.cmp-status-pip')
    expect(pip.exists()).toBe(true)
    expect(pip.classes()).toContain('cmp-status-pip-blocked')
    expect(pip.attributes('style')).toBeUndefined()
  })
})
