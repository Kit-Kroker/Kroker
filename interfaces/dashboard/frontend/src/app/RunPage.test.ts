// T038 (RED): app/RunPage.vue, the run-page composition (R-13). RunPage
// renders ONLY <RunView> and fills its typed #board slot with BoardTab --
// the app layer is the only place features/board is reachable from. The
// module does not exist yet, so every test here fails on that import until
// T039 lands it.
//
// The mount goes through a REAL memory router whose /runs/:id route carries
// the same R-4 props function the app router declares, with RunPage as the
// component -- the composition is exercised exactly as production routes it
// (probe-slot forwarding is qa-happy's tabs file; HERE the slot comes from
// RunPage itself, which is the point). The board side is driven through the
// './board.api' fake (vi.hoisted + importOriginal, pure helpers stay real)
// so the real board store runs; the fleet store is seeded directly.
import { describe, it, expect, beforeEach, afterEach, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import RunPage from './RunPage.vue'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import type { CatalogWire, GraphStateResponse } from '../api/graph-types'
import type { Run } from '../api/types'
import { useCatalogStore } from '../shared/catalog.store'
import { useFleetStore } from '../shared/fleet.store'
import { useUiStore } from './ui.store'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  getRunGraph: vi.fn(),
  subscribeGraphState: vi.fn(),
  decideGate: vi.fn(),
}))
vi.mock('../api/client', () => ({ api, API_MODE: 'mock' as const }))

const boardApi = vi.hoisted(() => ({
  project: vi.fn(),
  versions: vi.fn(),
  tasks: vi.fn(),
  taskDetail: vi.fn(),
  events: vi.fn(),
}))
vi.mock('../features/board/board.api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../features/board/board.api')>()),
  boardApi,
}))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }
const GRAPH = { kind: 'graph' as const, sha: 'sha-1', graph: { schema_version: 1 as const, nodes: [], edges: [] }, back_edges: [] }

// GraphCanvas would mount only on the Graph tab; the stubs are cheap
// insurance for jsdom (same beforeAll as RunView.tabs.test.ts).
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

const RUN_BASE = {
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
}

const catalogWithRunGraph = () => {
  const catalog = {
    ...(catalogJson as unknown as CatalogWire),
    capabilities: { validate: true, save: true, load: true, run_graph: true },
  }
  useCatalogStore().catalog = catalog
  api.getCatalog.mockResolvedValue(catalog)
}

// The run route with R-4's props function and RunPage as the component --
// the shape T039 declares on the app router.
const makeRouter = async (initial: string): Promise<Router> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      {
        path: '/runs/:id',
        component: RunPage,
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

// The poll's first tick fires immediately; microtask drains settle it.
const settle = async () => {
  for (let i = 0; i < 5; i++) await vi.advanceTimersByTimeAsync(0)
}

const mountPage = async (initial: string, projectKey: string | null) => {
  useFleetStore().runs = [{ ...RUN_BASE, projectKey }]
  const router = await makeRouter(initial)
  const Host = { components: { RouterView }, template: '<RouterView />' }
  const w = mount(Host, { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  await settle()
  return { w, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  vi.resetAllMocks()
  vi.spyOn(useUiStore(), 'toast').mockImplementation(() => {})
  api.getRunGraph.mockResolvedValue(GRAPH)
  api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
    cb({ kind: 'state', graph_sha: 'sha-1', nodes: {}, edges: [], current_nodes: [], outcome: { state: 'running', reason: null, result: null }, pending: [] })
    return () => {}
  })
  boardApi.project.mockResolvedValue({
    key: 'kroker', repo: 'org/repo', artifacts: [], stats: {
      project: 'kroker',
      tasks_by_status: { pending: 0, in_progress: 0, done: 0, failed: 0, blocked: 0, quarantined: 0 },
      total_fix_attempts: 0, tasks_with_error: 0, diverged_tasks: 0, event_count: 0,
    },
  })
  boardApi.versions.mockResolvedValue([])
  boardApi.tasks.mockResolvedValue([])
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('RunPage composes the board (R-13)', () => {
  it('renders RunView and fills its board panel with a live BoardTab', async () => {
    const { w } = await mountPage('/runs/r1?tab=board', 'kroker')
    expect(w.find('[data-testid="run-view"]').exists()).toBe(true)
    const panel = w.find('[data-testid="run-tab-board"]')
    expect(panel.exists()).toBe(true)
    // BoardTab's own testid contract (BoardTab.test.ts), rendered INSIDE
    // the panel -- the slot is filled by RunPage, not by a test probe.
    expect(panel.find('[data-testid="board-tab"]').exists()).toBe(true)
    // the board store really started: step 1 fired through the fake
    expect(boardApi.project).toHaveBeenCalledWith('kroker')
  })

  it('the Board tab is ENABLED on the run page (the slot is supplied)', async () => {
    const { w } = await mountPage('/runs/r1?tab=board', 'kroker')
    const boardTab = w.find('[data-testid="tab-board"]')
    expect(boardTab.exists()).toBe(true)
    expect(boardTab.attributes('disabled')).toBeUndefined()
    expect(boardTab.attributes('aria-selected')).toBe('true')
  })
})

describe('BoardTab receives the run identity (FR-020a)', () => {
  it("a seeded run with projectKey 'kroker' starts the board on 'kroker'", async () => {
    const { w } = await mountPage('/runs/r1?tab=board', 'kroker')
    expect(boardApi.project).toHaveBeenCalledWith('kroker')
    expect(w.find('[data-testid="board-banner-no-project"]').exists()).toBe(false)
  })

  it('a run with projectKey null shows the no-project banner; the board is never called', async () => {
    const { w } = await mountPage('/runs/r1?tab=board', null)
    const banner = w.find('[data-testid="board-banner-no-project"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('no board')
    expect(boardApi.project).not.toHaveBeenCalled()
  })
})
