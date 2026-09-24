// T036 (RED): RunView as the run tab host (FR-017/FR-018, R-4, R-13,
// data-model §5). RunView has no `tab` prop and no TabBar yet -- every
// assertion on the tab bar, the board panel and the probe fails until T037.
// The board slot is a string-template probe forwarded through the RouterView
// slot (the composition app/RunPage.vue will use); the router is a REAL
// memory router so tab select's router.replace is observable in
// router.currentRoute.
import { describe, it, expect, beforeEach, afterEach, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import RunView from './RunView.vue'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire, GraphStateResponse } from '../../api/graph-types'
import type { Run } from '../../api/types'
import { useCatalogStore } from '../../shared/catalog.store'
import { useFleetStore } from '../../shared/fleet.store'
import { useUiStore } from '../../app/ui.store'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  getRunGraph: vi.fn(),
  subscribeGraphState: vi.fn(),
  decideGate: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }
const GRAPH = { kind: 'graph' as const, sha: 'sha-1', graph: { schema_version: 1 as const, nodes: [], edges: [] }, back_edges: [] }

// GraphCanvas mounts on the Graph tab; vue-flow needs these in jsdom.
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

const RUN: Run = {
  id: 'r1',
  title: 'Demo run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['architecture'],
  status: 'running',
  blocker: null,
  cost: null,
  budget: null,
  age: '2h 00m',
  decisions: [],
  stageMarks: null,
  projectKey: 'kroker',
}

const catalogWithRunGraph = () => {
  const catalog = {
    ...(catalogJson as unknown as CatalogWire),
    capabilities: { validate: true, save: true, load: true, run_graph: true },
  }
  useCatalogStore().catalog = catalog
  api.getCatalog.mockResolvedValue(catalog)
}

// The run route with R-4's props function (tab only when the query carries a
// string) -- the same shape T037 declares on the app router.
const makeRouter = async (initial: string): Promise<Router> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      {
        path: '/runs/:id',
        component: RunView,
        props: (r) => ({
          id: r.params.id as string,
          ...(typeof r.query.tab === 'string' ? { tab: r.query.tab } : {}),
        }),
      },
    ],
  })
  await router.push(initial)
  await router.isReady()
  return router
}

// The host forwards the board slot into the route component through the
// RouterView slot -- exactly app/RunPage.vue's composition (R-13).
const mountRun = async (initial: string, withBoardSlot = true) => {
  const router = await makeRouter(initial)
  const Host = {
    components: { RouterView: (await import('vue-router')).RouterView },
    template: withBoardSlot
      ? `<RouterView v-slot="{ Component }">
           <component :is="Component">
             <template #board><div data-testid="board-probe">PROBE</div></template>
           </component>
         </RouterView>`
      : `<RouterView v-slot="{ Component }"><component :is="Component" /></RouterView>`,
  }
  const w = mount(Host, { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return { w, router }
}

const seedRun = () => {
  useFleetStore().runs = [RUN]
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.spyOn(useUiStore(), 'toast').mockImplementation(() => {})
  api.getRunGraph.mockResolvedValue(GRAPH)
  api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
    cb({ kind: 'state', graph_sha: 'sha-1', nodes: {}, edges: [], current_nodes: [], outcome: { state: 'running', reason: null, result: null }, pending: [] })
    return () => {}
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RunView as a tab host', () => {
  it('Graph is the default: no tab prop renders the canvas and never the probe', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w } = await mountRun('/runs/r1')
    expect(w.find('[data-testid="run-view"]').exists()).toBe(true)
    expect(w.find('.canvas-wrap').exists()).toBe(true)
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
  })

  it('tab=board with the slot renders the probe and the four tab labels', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1?tab=board')
    expect(router.currentRoute.value.query.tab).toBe('board')
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(true)
    expect(w.find('[data-testid="board-probe"]').text()).toBe('PROBE')
    const bar = w.find('nav.cmp-tab-bar')
    expect(bar.exists()).toBe(true)
    for (const label of ['Graph', 'Board', 'Gates', 'Cost']) {
      expect(bar.text(), label).toContain(label)
    }
    expect(w.find('[data-testid="tab-board"]').attributes('aria-selected')).toBe('true')
  })

  it('without the board slot Board is disabled and clicking it does not switch', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1?tab=board', false)
    const boardTab = w.find('[data-testid="tab-board"]')
    expect(boardTab.exists()).toBe(true)
    expect(boardTab.attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
    await boardTab.trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
    expect(boardTab.attributes('aria-selected')).not.toBe('true')
    expect(router.currentRoute.value.query.tab).toBe('board') // disabled: URL untouched (R-4)
  })

  it('Gates and Cost are disabled and clicking them does not switch', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1')
    for (const id of ['gates', 'cost']) {
      const tab = w.find(`[data-testid="tab-${id}"]`)
      expect(tab.exists()).toBe(true)
      expect(tab.attributes('disabled')).toBeDefined()
      await tab.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query.tab).toBeUndefined()
      expect(tab.attributes('aria-selected')).not.toBe('true')
    }
    expect(w.find('.canvas-wrap').exists()).toBe(true) // still Graph
  })

  it('selecting Graph from Board unmounts the probe and clears ?tab (replace semantics)', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1?tab=board')
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(true)
    await w.find('[data-testid="tab-graph"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tab).toBeUndefined()
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
    expect(w.find('.canvas-wrap').exists()).toBe(true)
  })

  it('an unknown tab prop renders Graph', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1?tab=nonsense')
    expect(w.find('.canvas-wrap').exists()).toBe(true)
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
    expect(router.currentRoute.value.query.tab).toBe('nonsense') // URL untouched (R-4)
  })
})

describe('the board panel waits for the run (R-13)', () => {
  it('a fleet store that has not fetched shows a loading-run line, not the probe', async () => {
    catalogWithRunGraph()
    const { w } = await mountRun('/runs/r1?tab=board')
    const panel = w.find('[data-testid="run-tab-board"]')
    expect(panel.exists()).toBe(true)
    expect(panel.find('[data-testid="run-board-loading"]').text()).toContain('loading run')
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
  })

  it('a completed fetch without the run shows run-not-found, not loading', async () => {
    catalogWithRunGraph()
    const fleet = useFleetStore()
    fleet.runs = []
    fleet.lastFetched = Date.now()
    const { w } = await mountRun('/runs/r1?tab=board')
    const panel = w.find('[data-testid="run-tab-board"]')
    expect(panel.exists()).toBe(true)
    expect(panel.find('[data-testid="run-board-not-found"]').text()).toContain('run not found')
    expect(panel.find('[data-testid="run-board-loading"]').exists()).toBe(false)
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(false)
  })
})

describe('URL discipline (SC-005)', () => {
  it('Board then Graph leaves ?tab undefined; a deep link to tab=board opens Board', async () => {
    seedRun()
    catalogWithRunGraph()
    const { w, router } = await mountRun('/runs/r1?tab=board')
    expect(w.find('[data-testid="board-probe"]').exists()).toBe(true)
    await w.find('[data-testid="tab-graph"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.tab).toBeUndefined()

    // The copied URL /runs/r1?tab=board reopens Board (fresh mount, deep link).
    const { w: w2 } = await mountRun('/runs/r1?tab=board')
    expect(w2.find('[data-testid="board-probe"]').exists()).toBe(true)
  })
})
