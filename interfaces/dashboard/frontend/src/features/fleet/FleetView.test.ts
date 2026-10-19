// T5 (sbatch-2026-10-19, RED): the fleet view's honest states, mirroring
// InboxView's 010 treatment (contracts/inbox-screen.md §3.1 shape). The
// store is seeded directly -- the view must not refresh on mount, so no
// api mock exists in this file. The RED cause is the missing state
// branches: FleetView today always renders the table, come what may.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'
import FleetView from './FleetView.vue'
import FleetTable from './FleetTable.vue'
import { useFleetStore } from '../../shared/fleet.store'
import { useCatalogStore } from '../../shared/catalog.store'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'
import type { Run } from '../../api/types'

const RouterLinkStub = {
  props: ['to'],
  template: '<a><slot /></a>',
}

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'feature-x', title: 'A feature', mode: 'brownfield', repo: 'r', activeStages: ['clarify'],
  status: 'blocked', blocker: 'clarify gate', cost: 3.12, budget: 40, age: '2h',
  decisions: [], ...over,
})

beforeEach(() => {
  setActivePinia(createPinia())
  // FleetTable maps rows through catalog.canonicalStages; seed the fixture
  // exactly like FleetTable.test.ts so rendering never depends on a load.
  useCatalogStore().catalog = catalogJson as unknown as CatalogWire
})

const mountView = (): VueWrapper =>
  mount(FleetView, {
    global: { plugins: [getActivePinia() as never], stubs: { RouterLink: RouterLinkStub } },
  })

describe('FleetView states', () => {
  it('not loaded, no error: only the loading state shows, the table waits', () => {
    const fleet = useFleetStore()
    fleet.runs = []
    fleet.loaded = false
    fleet.loadError = null
    const w = mountView()
    expect(w.find('[data-testid="fleet-loading"]').exists()).toBe(true)
    expect(w.findComponent(FleetTable).exists()).toBe(false)
    expect(w.find('[data-testid="fleet-load-error"]').exists()).toBe(false)
  })

  it('not loaded with a load error: only the could-not-be-loaded state shows', () => {
    const fleet = useFleetStore()
    fleet.runs = []
    fleet.loaded = false
    fleet.loadError = 'backend down'
    const w = mountView()
    const err = w.find('[data-testid="fleet-load-error"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toBe('The fleet could not be loaded.')
    expect(w.find('[data-testid="fleet-loading"]').exists()).toBe(false)
    expect(w.findComponent(FleetTable).exists()).toBe(false)
  })

  it('loaded with runs and a refresh error: the stale banner shows and the last known list stays visible', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'r1' }), mkRun({ id: 'r2' })]
    fleet.loaded = true
    fleet.loadError = 'blip'
    const w = mountView()
    const banner = w.find('[data-testid="fleet-incomplete"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('The fleet could not be refreshed; showing the last known list.')
    expect(w.find('[data-testid="fleet-loading"]').exists()).toBe(false)
    expect(w.find('[data-testid="fleet-load-error"]').exists()).toBe(false)
    expect(w.findComponent(FleetTable).exists()).toBe(true)
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(2)
  })
})
