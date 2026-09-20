// RunView banner honesty (bug canvas-run-mode, E75-OQ-1 option (a)). The
// view's banners must tell the truth once run mode is wired: an unavailable
// graph_state (E-77: registry_drift / retention_expired) is a final answer
// that deserves its own banner, and "Graph view arrives with E-75." is false
// since E-75 landed. Follows the App.test.ts api-mock and FleetTable.test.ts
// mounting patterns.
import { describe, it, expect, beforeEach, afterEach, vi, beforeAll } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import RunView from './RunView.vue'
import catalogJson from '../api/__fixtures__/graph/catalog.json'
import type { CatalogWire, GraphStateResponse } from '../api/graph-types'
import { useCatalogStore } from '../stores/catalog'
import { useUiStore } from '../stores/ui'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  getRunGraph: vi.fn(),
  subscribeGraphState: vi.fn(),
  decideGate: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }
const GRAPH = { kind: 'graph' as const, sha: 'sha-1', graph: { schema_version: 1 as const, nodes: [], edges: [] }, back_edges: [] }
let deliver: (s: GraphStateResponse) => void

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
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RunView banners', () => {
  it('an unavailable graph_state (retention_expired) shows an honest banner, not an empty canvas', async () => {
    const catalog = {
      ...(catalogJson as unknown as CatalogWire),
      capabilities: { validate: true, save: true, load: true, run_graph: true },
    }
    useCatalogStore().catalog = catalog
    api.getCatalog.mockResolvedValue(catalog)
    api.getRunGraph.mockResolvedValue(GRAPH)
    api.subscribeGraphState.mockImplementation((_id, cb: (s: GraphStateResponse) => void) => {
      deliver = cb
      return () => {}
    })
    const w = mount(RunView, { props: { id: 'r1' }, global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    deliver({ kind: 'unavailable', reason: 'retention_expired' } as unknown as GraphStateResponse)
    await flushPromises()
    const banner = w.find('[data-testid="run-graph-state-unavailable"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('no longer available')
    expect(w.find('[data-testid="run-graph-error"]').exists()).toBe(false)
  })

  it('without the run_graph capability the banner no longer claims E-75', async () => {
    // E75-OQ-1: the recorded catalog now declares run_graph true, so the
    // no-capability case pins an explicit false override.
    const catalog = {
      ...(catalogJson as unknown as CatalogWire),
      capabilities: { validate: true, save: true, load: true, run_graph: false },
    }
    useCatalogStore().catalog = catalog
    api.getCatalog.mockResolvedValue(catalog)
    const w = mount(RunView, { props: { id: 'r1' }, global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()
    const banner = w.find('[data-testid="run-graph-unavailable"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).not.toContain('E-75')
    expect(banner.text()).toContain('not available on this server')
  })
})
