// v5 Observe run view (018 T031 RED). The banners keep their honesty rules
// but the reasons now live INSIDE the rail's run block (R-5a); the rail and
// the node inspector are new surfaces T032 builds. Reuses the App.test.ts
// api-mock pattern and the tabs file's RUN/catalog/seed bones.
import { describe, it, expect, beforeEach, afterEach, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import RunView from './RunView.vue'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire, GraphStateResponse } from '../../api/graph-types'
import type { Run } from '../../api/types'
import { useCatalogStore } from '../../shared/catalog.store'
import { useFleetStore } from '../../shared/fleet.store'
import { useInboxStore } from '../../app/inbox.store'
import { useUiStore } from '../../app/ui.store'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  getRunGraph: vi.fn(),
  subscribeGraphState: vi.fn(),
  decideGate: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }
const GRAPH = {
  kind: 'graph' as const,
  sha: 'sha-1',
  graph: {
    schema_version: 1 as const,
    nodes: [
      { id: 'arch', type: 'architect' },
      { id: 'cd', type: 'code' },
    ],
    edges: [],
  },
  back_edges: [],
}
const CATALOG_RUN = {
  ...(catalogJson as unknown as CatalogWire),
  capabilities: { validate: true, save: true, load: true, run_graph: true },
}

const RUN: Run = {
  id: 'r1',
  title: 'Demo run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['architecture'],
  status: 'running',
  blocker: null,
  cost: 2.6,
  budget: 20,
  age: '2h 00m',
  decisions: [],
  stageMarks: null,
  roles: [{ role: 'architect', model: 'glm-4.7', calls: 1, inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, cost: null }],
  budgetThreshold: 40,
  budgetCounted: 31,
  budgetCrossings: 0,
  budgetNotice: null,
  projectKey: null,
}

// GraphCanvas mounts whenever a graph is present; vue-flow needs these in jsdom.
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

const seedCatalog = (capabilities = CATALOG_RUN.capabilities) => {
  const catalog = { ...(catalogJson as unknown as CatalogWire), capabilities }
  useCatalogStore().catalog = catalog
  api.getCatalog.mockResolvedValue(catalog)
}

const mountView = async (runOverride?: Run) => {
  useFleetStore().runs = [runOverride ?? RUN]
  const w = mount(RunView, { props: { id: 'r1' }, global: { stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}

describe('RunView banners (v5: the reasons live under the rail run block)', () => {
  it('retention_expired: the honest note renders inside the rail, never an error', async () => {
    seedCatalog()
    api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
      cb({ kind: 'unavailable', reason: 'retention_expired' } as unknown as GraphStateResponse)
      return () => {}
    })
    const w = await mountView()
    const banner = w.find('[data-testid="run-graph-state-unavailable"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('no longer available')
    // R-5a: the reason is a note under the rail's run block.
    expect(banner.element.closest('[data-testid="rail"]')).not.toBeNull()
    expect(w.find('[data-testid="run-graph-error"]').exists()).toBe(false)
  })

  it('registry_drift: the same rail note carries the registry wording', async () => {
    seedCatalog()
    api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
      cb({ kind: 'unavailable', reason: 'registry_drift' } as unknown as GraphStateResponse)
      return () => {}
    })
    const w = await mountView()
    const banner = w.find('[data-testid="run-graph-state-unavailable"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('registry')
    expect(banner.element.closest('[data-testid="rail"]')).not.toBeNull()
  })

  it('a provider failure reads exactly "could not load" (CONSOLE-51)', async () => {
    seedCatalog()
    api.getRunGraph.mockRejectedValue(new Error('provider down'))
    const w = await mountView()
    const error = w.find('[data-testid="run-graph-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toBe('could not load')
  })

  it('without the run_graph capability the banner no longer claims E-75', async () => {
    seedCatalog({ validate: true, save: true, load: true, run_graph: false })
    const w = await mountView()
    const banner = w.find('[data-testid="run-graph-unavailable"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).not.toContain('E-75')
    expect(banner.text()).toContain('not available on this server')
  })
})

describe('the v5 rail renders the run block (018 T031 RED)', () => {
  it('title, state, path, events and cost render as rail sections', async () => {
    seedCatalog()
    api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
      cb({
        kind: 'state',
        graph_sha: 'sha-1',
        nodes: {},
        edges: [],
        current_nodes: ['intake', 'architect'],
        outcome: { state: 'running', reason: null, result: null },
        pending: [{ node: 'architecture', key: 'architecture#1', kind: 'gate' }],
      })
      return () => {}
    })
    const w = await mountView()
    expect(w.find('[data-testid="rail"]').exists()).toBe(true)
    expect(w.find('[data-testid="rail-title"]').text()).toBe('Demo run')
    expect(w.find('[data-testid="rail-state"]').text()).toBe('running')
    expect(w.find('[data-testid="rail-path"]').text()).toContain('intake')
    expect(w.find('[data-testid="rail-path"]').text()).toContain('architect')
    expect(w.find('[data-testid="rail-events"]').text()).toContain('Review gate architecture#1')
    const cost = w.find('[data-testid="rail-cost"]')
    expect(cost.exists()).toBe(true)
    expect(cost.find('[data-testid="rail-budget"]').text()).toContain('20.00')
    // The interim open-copy link survives inside the rail until T063.
    expect(w.find('[data-testid="rail"] [data-testid="open-copy"]').exists()).toBe(true)
  })

  it('with nothing waiting, the events section carries the unavailable-history row', async () => {
    seedCatalog()
    const w = await mountView()
    expect(w.find('[data-testid="rail-events"]').text()).toContain(
      'Decision history is not available for this run',
    )
  })
})

describe('the v5 inspector (018 T031 RED)', () => {
  const select = async (w: ReturnType<typeof mount>, key: string) => {
    w.findComponent(GraphCanvas).vm.$emit('select', key)
    await flushPromises()
  }

  it('a selected stage node shows configured vs answering model ids and marks a difference', async () => {
    seedCatalog()
    const w = await mountView()
    await select(w, 'arch')
    expect(w.find('[data-testid="run-inspector"]').exists()).toBe(true)
    // configured: the catalog type's default_id ('architect'); answering: the
    // Run role's model ('glm-4.7').
    expect(w.find('[data-testid="inspector-configured"]').text()).toBe('architect')
    expect(w.find('[data-testid="inspector-answering"]').text()).toBe('glm-4.7')
    expect(w.find('[data-testid="inspector-model-diff"]').exists()).toBe(true)
  })

  it('matching ids mark no difference', async () => {
    seedCatalog()
    const w = await mountView({
      ...RUN,
      roles: [{ role: 'architect', model: 'architect', calls: 1, inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0, cost: null }],
    })
    await select(w, 'arch')
    expect(w.find('[data-testid="inspector-configured"]').text()).toBe('architect')
    expect(w.find('[data-testid="inspector-answering"]').text()).toBe('architect')
    expect(w.find('[data-testid="inspector-model-diff"]').exists()).toBe(false)
  })

  it("the code node's inspector shows the read-only inner loop and no button (FR-017)", async () => {
    seedCatalog()
    const w = await mountView()
    await select(w, 'cd')
    const inspector = w.find('[data-testid="run-inspector"]')
    expect(inspector.exists()).toBe(true)
    expect(inspector.find('.cmp-step-list').exists()).toBe(true)
    expect(inspector.findAll('button')).toHaveLength(0)
  })
})

describe('RunView v5 chaos (018 T031 RED)', () => {
  const select = async (w: ReturnType<typeof mount>, key: string | null) => {
    w.findComponent(GraphCanvas).vm.$emit('select', key)
    await flushPromises()
  }

  it('selecting an unknown node key renders no inspector and throws nothing', async () => {
    seedCatalog()
    const w = await mountView()
    await select(w, 'nope')
    expect(w.find('[data-testid="run-inspector"]').exists()).toBe(false)
  })

  it('deselecting (select null) removes the inspector again', async () => {
    seedCatalog()
    const w = await mountView()
    await select(w, 'arch')
    expect(w.find('[data-testid="run-inspector"]').exists()).toBe(true)
    await select(w, null)
    expect(w.find('[data-testid="run-inspector"]').exists()).toBe(false)
  })

  it('a run without a budget: the rail budget reads off with no bar (null means off)', async () => {
    seedCatalog()
    const w = await mountView({ ...RUN, budget: null, budgetThreshold: null, budgetCounted: null })
    await flushPromises()
    expect(w.find('[data-testid="rail-budget"]').text()).toContain('off')
    expect(w.find('[data-testid="rail-budget-bar"]').exists()).toBe(false)
  })

  it('budgetCrossings 1 with a delivered state: the events section counts the crossing', async () => {
    seedCatalog()
    const w = await mountView({ ...RUN, budgetCrossings: 1 })
    await flushPromises()
    expect(w.find('[data-testid="rail-events"]').text()).toContain('Budget crossed 1x')
  })

  it('a run with no roles at all: the architect inspector answers "not measured"', async () => {
    seedCatalog()
    const w = await mountView({ ...RUN, roles: [] })
    await flushPromises()
    await select(w, 'arch')
    expect(w.find('[data-testid="inspector-configured"]').text()).toBe('architect')
    expect(w.find('[data-testid="inspector-answering"]').text()).toBe('not measured')
  })

  it('the code node: configured reads the catalog default (code), answering is not measured', async () => {
    seedCatalog()
    const w = await mountView()
    await select(w, 'cd')
    expect(w.find('[data-testid="inspector-configured"]').text()).toBe('code')
    expect(w.find('[data-testid="inspector-answering"]').text()).toBe('not measured')
  })
})

describe('the rail call to actions and the canvas card (018 T042 RED)', () => {
  const select = async (w: ReturnType<typeof mount>, key: string | null) => {
    w.findComponent(GraphCanvas).vm.$emit('select', key)
    await flushPromises()
  }

  const GRAPH_WITH_ARCH = {
    kind: 'graph' as const,
    sha: 'sha-1',
    graph: {
      schema_version: 1 as const,
      nodes: [
        { id: 'architecture', type: 'architect' },
        { id: 'arch', type: 'architect' },
      ],
      edges: [],
    },
    back_edges: [],
  }

  const pendingRef = (key: string) => ({ node: 'architecture', key, kind: 'gate' as const })

  const stateWith = (pending: ReturnType<typeof pendingRef>[]) =>
    ({
      kind: 'state',
      graph_sha: 'sha-1',
      nodes: {},
      edges: [],
      current_nodes: [],
      outcome: { state: 'running', reason: null, result: null },
      pending,
    }) as unknown as GraphStateResponse

  // T043 reads the run's items from the inbox store filtered by run; seed it
  // directly so the card mapping has its item whichever source wins.
  const seedInboxGate = () => {
    const inbox = useInboxStore()
    inbox.items = [
      {
        id: 'architecture#1', runId: 'r1', round: 1, age: '1m', type: 'gate',
        gate: 'architecture', title: 'architecture (round 1)', body: '',
      },
    ]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    return inbox
  }

  const subscribeDelivering = (first: GraphStateResponse) => {
    let deliver: (s: GraphStateResponse) => void = () => {}
    api.subscribeGraphState.mockImplementation((_id: string, cb: (s: GraphStateResponse) => void) => {
      deliver = cb
      cb(first)
      return () => {}
    })
    return () => deliver
  }

  const makeRouter = async (initial: string) => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        {
          path: '/runs/:id',
          component: RunView,
          props: (r) => ({
            id: r.params.id as string,
            ...(typeof r.query.rail === 'string' ? { rail: r.query.rail } : {}),
            ...(typeof r.query.decision === 'string' ? { decision: r.query.decision } : {}),
          }),
        },
      ],
    })
    await router.push(initial)
    await router.isReady()
    return router
  }

  const mountRouted = async (initial: string) => {
    seedCatalog()
    useFleetStore().runs = [RUN]
    const router = await makeRouter(initial)
    const Host = { components: { RouterView }, template: '<RouterView />' }
    const w = mount(Host, { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    return { w, router }
  }

  it('each pending item renders one rail call, two render two in order, none renders zero', async () => {
    seedCatalog()
    seedInboxGate()
    const getDeliver = subscribeDelivering(stateWith([pendingRef('architecture#1')]))
    const w = await mountView()
    let calls = w.findAll('[data-testid="rail-call"]')
    expect(calls).toHaveLength(1)
    expect(calls[0].text()).toContain('Review')
    expect(calls[0].text()).toContain('architecture#1')

    getDeliver()(stateWith([pendingRef('architecture#1'), pendingRef('merge#1')]))
    await flushPromises()
    calls = w.findAll('[data-testid="rail-call"]')
    expect(calls).toHaveLength(2)
    expect(calls[0].text()).toContain('architecture#1')
    expect(calls[1].text()).toContain('merge#1')

    getDeliver()(stateWith([]))
    await flushPromises()
    expect(w.findAll('[data-testid="rail-call"]')).toHaveLength(0)
  })

  it('clicking a call opens its card over the canvas; the close button closes it', async () => {
    seedCatalog()
    seedInboxGate()
    subscribeDelivering(stateWith([pendingRef('architecture#1')]))
    const w = await mountView()
    expect(w.find('[data-testid="run-card"]').exists()).toBe(false)

    await w.find('[data-testid="rail-call"]').trigger('click')
    await flushPromises()
    const pane = w.find('[data-testid="run-card"]')
    expect(pane.exists()).toBe(true)
    expect(pane.find('[data-testid="decision-card"]').exists()).toBe(true)
    expect(pane.text()).toContain('architecture#1')

    await w.find('[data-testid="run-card-close"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="run-card"]').exists()).toBe(false)
  })

  it('?decision= opens the card; closing clears the query', async () => {
    seedInboxGate()
    subscribeDelivering(stateWith([pendingRef('architecture#1')]))
    const { w, router } = await mountRouted('/runs/r1?decision=architecture%231')
    expect(w.find('[data-testid="run-card"]').exists()).toBe(true)
    expect(w.find('[data-testid="run-card"]').text()).toContain('architecture#1')

    await w.find('[data-testid="run-card-close"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.decision).toBeUndefined()
    expect(w.find('[data-testid="run-card"]').exists()).toBe(false)
  })

  it('selecting a canvas node with a pending opens the same card; a node without one does not', async () => {
    seedCatalog()
    seedInboxGate()
    subscribeDelivering(stateWith([pendingRef('architecture#1')]))
    const w = await mountView()
    await select(w, 'architecture')
    expect(w.find('[data-testid="run-card"]').exists()).toBe(true)
    expect(w.find('[data-testid="run-card"]').text()).toContain('architecture#1')

    await select(w, 'arch')
    await flushPromises()
    expect(w.find('[data-testid="run-card"]').exists()).toBe(false)
  })

  it('after a decision and a pending-free refresh, the call and the canvas mark are gone', async () => {
    seedCatalog()
    seedInboxGate()
    const getDeliver = subscribeDelivering(stateWith([pendingRef('architecture#1')]))
    api.decideGate.mockResolvedValue(undefined)
    const w = await mountView()
    await w.find('[data-testid="rail-call"]').trigger('click')
    await flushPromises()

    const approve = w
      .findAll('[data-testid="card-action"]')
      .find((b) => b.text() === 'Approve')!
    await approve.trigger('click')
    await flushPromises()
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'architecture#1', 'approve', '')

    getDeliver()(stateWith([]))
    await flushPromises()
    expect(w.findAll('[data-testid="rail-call"]')).toHaveLength(0)
    // Previews the T043 removal: the interim GateDecision mark must not survive.
    expect(w.find('[data-testid="gate-decision"]').exists()).toBe(false)
  })

  it('events show both live notes on an open run, and only the untimed rows on a closed one (FR-022)', async () => {
    seedCatalog()
    const decided = [{ ts: '10:00', gate: 'architecture r2', outcome: 'approve' as const, comment: '', decider: 'owner' }]

    const open = await mountView({ ...RUN, decisions: decided })
    const openEvents = open.find('[data-testid="rail-events"]').text()
    expect(openEvents).toContain('approve architecture r2')
    expect(openEvents).toContain('Human decisions only while the run is open.')
    expect(openEvents).toContain('automatic and timed-out decisions appear when the run ends')

    const closed = await mountView({ ...RUN, status: 'done', decisions: decided })
    const closedEvents = closed.find('[data-testid="rail-events"]').text()
    expect(closedEvents).toContain('approve architecture r2')
    expect(closedEvents).not.toContain('Human decisions only while the run is open.')
  })
})
