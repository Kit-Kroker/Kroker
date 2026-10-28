// v5 FleetView (018 T048 RED): the view composes the fleet and fleetSummary
// stores into FleetTable's v5 rows and forwards prefs.runInContext. The
// honest-state rules (loading / load-error / stale banner) are ported as-is.
// The 'one stage dot per canonical stage' case is DELETED with CONSOLE-3
// (S6 retires the stage strip; T050 tombstones the clause).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'
import FleetView from './FleetView.vue'
import FleetTable from './FleetTable.vue'
import { useFleetStore } from '../../shared/fleet.store'
import { useCatalogStore } from '../../shared/catalog.store'
import { usePrefsStore } from '../../app/prefs.store'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'
import type { Run } from '../../api/types'

// T049 lands shared/fleetSummary.store.ts. The mock is a vi.hoisted state
// object the factory closes over -- no import of the absent module anywhere
// (Vite resolves even dynamic literal imports at transform time), so this
// file's RED stays scoped to the view wiring.
const summaryState = vi.hoisted(() => ({ byRun: {} as Record<string, unknown> }))
vi.mock('../../shared/fleetSummary.store', () => ({
  useFleetSummaryStore: () => summaryState,
}))

const RouterLinkStub = {
  props: ['to'],
  template: '<a><slot /></a>',
}

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'feature-x', title: 'A feature', mode: 'brownfield', repo: 'r', activeStages: ['clarify'],
  status: 'blocked', blocker: 'clarify gate', cost: 3.12, budget: 40, age: '2h',
  decisions: [], ...over,
})

const summaryOf = (runId: string, graphName: string | null) => ({
  runId,
  graphSha: graphName ? 'a021c25b8f7e' : null,
  graphName,
  arm: graphName ? { harness: 'opencode', model: 'glm' } : null,
  traversals: [],
  outcome: null,
  where: [],
  gateTimeouts: [],
})

beforeEach(() => {
  setActivePinia(createPinia())
  // The catalog seed FleetTable's old path needed; harmless if the v5 table
  // stops reading it, so it stays.
  useCatalogStore().catalog = catalogJson as unknown as CatalogWire
})

const mountView = (): VueWrapper =>
  mount(FleetView, {
    global: { plugins: [getActivePinia() as never], stubs: { RouterLink: RouterLinkStub } },
  })

describe('FleetView states (ported)', () => {
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

describe('FleetView composes the v5 table (018 T048 RED)', () => {
  it('passes rows built from the fleet and summary stores and prefs.runInContext', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'r1' }), mkRun({ id: 'r2' })]
    fleet.loaded = true
    fleet.loadError = null
    summaryState.byRun = { r1: summaryOf('r1', 'default') }
    usePrefsStore().runInContext = 'r1'

    const w = mountView()
    const table = w.findComponent(FleetTable)
    expect(table.exists()).toBe(true)
    const rows = table.props('rows') as Array<Record<string, unknown>>
    expect(rows).toHaveLength(2)
    expect(rows[0]['graph']).toBe('default')
    expect(rows[1]['graph']).toBe('—')
    expect(table.props('runInContext')).toBe('r1')
  })
})
