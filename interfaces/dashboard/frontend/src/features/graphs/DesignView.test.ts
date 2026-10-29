// v5 Design view (018 T062 RED): the palette (FR-046/V9), the validation
// panel (FR-048/V2/V3), Run this version (R-15), the from=run load and the
// /graphs redirects. DesignView.vue does not exist -- that is this suite's
// RED. Seam assumption named for T063: planned types arrive through an api
// read ``getPlannedTypes(): Promise<string[]>`` (presentation-only, A8; the
// mock fixture lands with T066), and the shipped-default sha the R-15 rule
// compares against comes from ``getShippedGraphs``.
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import preCode from '../../api/__fixtures__/graph/scenarios/pre_code.json'
import shippedFixture from '../../api/__fixtures__/read/graphs-shipped.json'
import type { GraphWire } from '../../api/graph-types'

const api = vi.hoisted(() => ({
  getCatalog: vi.fn(),
  parseGraph: vi.fn(),
  serializeGraph: vi.fn(),
  validateGraph: vi.fn(),
  saveGraph: vi.fn(),
  loadGraph: vi.fn(),
  getRunGraph: vi.fn(),
  getShippedGraphs: vi.fn(),
  getPlannedTypes: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

import DesignView from './DesignView.vue'
import { useCatalogStore } from '../../shared/catalog.store'
import { useGraphEditorStore } from './graphEditor.store'
import { useUiStore } from '../../app/ui.store'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'
import type { CatalogWire } from '../../api/graph-types'

const PRE = preCode.parse as { ok: true; graph: GraphWire; sha: string }
const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'
const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

let pinia: Pinia
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  vi.resetAllMocks()
  useCatalogStore().catalog = catalogJson as unknown as CatalogWire
  api.getCatalog.mockResolvedValue(catalogJson)
  api.validateGraph.mockResolvedValue({ issues: [], back_edges: [] })
  api.getPlannedTypes.mockResolvedValue(['outcome.watch'])
  api.getShippedGraphs.mockResolvedValue({
    graphs: (shippedFixture.graphs as Array<Record<string, unknown>>).map((g) => ({
      name: g['name'], sha: g['sha'], description: g['description'], when: g['when'], counts: [],
    })),
    checks: shippedFixture.checks,
    sections: shippedFixture.sections,
  })
})

const mountAt = async (path: string) => {
  const router: Router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/graphs', component: DesignView },
      { path: '/graphs/:sha', component: DesignView, props: true },
    ],
  })
  await router.push(path)
  await router.isReady()
  const Host = { components: { RouterView }, template: '<RouterView />' }
  const w = mount(Host, { global: { plugins: [router, pinia], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return { w, router }
}

// GraphCanvas mounts on Design; vue-flow and the drop flow need these in
// jsdom (the same shims RunView.test.ts installs).
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

const loadRun = (sha: string | null) => {
  api.getRunGraph.mockResolvedValue({ kind: 'graph', sha, graph: PRE.graph, back_edges: [] })
}

describe('DesignView palette (FR-046, V9, 018 T062 RED)', () => {
  it('groups the catalog by canonical_stage in served order, only stages present', async () => {
    loadRun(DEFAULT_SHA)
    const { w } = await mountAt(`/graphs/${DEFAULT_SHA}?from=run:r1`)
    const titles = w.findAll('[data-testid="palette-group-title"]').map((t) => t.text())
    const served = (catalogJson as unknown as CatalogWire).canonical_stages
    const expected = served.filter((s) => titles.includes(s))
    expect(titles).toEqual(expected)
    expect(titles.length).toBeGreaterThan(0)
    expect(w.findAll('[data-testid="palette-type"]').length).toBeGreaterThan(0)
  })

  it('planned types render dashed and unmapped, and refuse placement (V9)', async () => {
    loadRun(DEFAULT_SHA)
    const { w } = await mountAt(`/graphs/${DEFAULT_SHA}?from=run:r1`)
    const planned = w
      .findAll('[data-testid="palette-type"]')
      .find((t) => t.text().includes('outcome.watch'))
    expect(planned).toBeDefined()
    expect(planned!.classes().join(' ')).toContain('planned')
    expect(planned!.text()).toContain('unmapped')

    const editor = useGraphEditorStore()
    const before = editor.working
    await w.find('[data-testid="graph-canvas"]').trigger('drop', {
      dataTransfer: dtOf('outcome.watch'),
      clientX: 100,
      clientY: 100,
    })
    await flushPromises()
    expect(editor.working).toEqual(before) // no node placed
  })
})

function dtOf(type: string) {
  const dt = new DataTransfer()
  dt.setData('application/x-kroker-node-type', type)
  return dt
}

describe('the validation panel (FR-048, V2/V3, 018 T062 RED)', () => {
  it('reports the five categories with the terminal copy, and no references check', async () => {
    loadRun(DEFAULT_SHA)
    const { w } = await mountAt(`/graphs/${DEFAULT_SHA}?from=run:r1`)
    const panel = w.find('[data-testid="validation-panel"]')
    expect(panel.exists()).toBe(true)
    const text = panel.text()
    for (const label of ['gate shape', 'required inputs', 'reachability', 'bounded cycles', 'terminal reach']) {
      expect(text, label).toContain(label)
    }
    expect(text).toContain('rejected, failed or escalated')
    expect(text).not.toContain('references')
  })

  it('an edgeless non-terminal out-port warns it becomes a completion sink (V3)', async () => {
    // A working copy missing one edge: its source out-port is now edgeless.
    const pruned: GraphWire = JSON.parse(JSON.stringify(PRE.graph))
    pruned.edges = pruned.edges.slice(1)
    api.getRunGraph.mockResolvedValue({ kind: 'graph', sha: DEFAULT_SHA, graph: pruned, back_edges: [] })
    const { w } = await mountAt(`/graphs/${DEFAULT_SHA}?from=run:r1`)
    expect(w.find('[data-testid="validation-panel"]').text()).toContain('completion sink')
  })
})

describe('Run this version (R-15, 018 T062 RED)', () => {
  it('is enabled only for the saved, unchanged shipped default; otherwise it states its reason', async () => {
    loadRun(null) // a run copy: no sha association, so not the saved default
    const { w } = await mountAt(`/graphs/x?from=run:r1`)
    const button = w.find('[data-testid="run-this-version"]')
    expect(button.exists()).toBe(true)
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    expect(w.find('[data-testid="run-reason"]').text()).toBeTruthy()
  })
})

// --- 018 T064 (RED): the button opens the existing start form (T065 wires
// it), the form still carries its budget field, and the start payload sends
// NO graph field (R-15). CONSOLE-28's rail half (the started run's budget
// renders in rail-budget) is already pinned green in RunView.test.ts.

describe('Run this version opens the start form (018 T064 RED)', () => {
  it('enabled for the saved unchanged shipped default; the click opens the form', async () => {
    // Mounted WITHOUT ?from=run (a run copy carries no sha association, so
    // it can never satisfy R-15's saved-unchanged rule). The saved state is
    // reached through the REAL flow — a save the server answers with the
    // default's sha — never by mutating the store handle (under a full-file
    // run the view's store instance is not the test's handle, and the
    // mutation silently lands elsewhere).
    api.loadGraph.mockResolvedValue({ ok: true, sha: DEFAULT_SHA, graph: PRE.graph })
    api.saveGraph.mockResolvedValue({ ok: true, sha: DEFAULT_SHA, validation: null })
    const { w } = await mountAt(`/graphs/${DEFAULT_SHA}`)
    await flushPromises()
    await w.find('[data-testid="design-save"]').trigger('click')
    await flushPromises()
    const button = w.find('[data-testid="run-this-version"]')
    await vi.waitFor(() => {
      expect((button.element as HTMLButtonElement).disabled).toBe(false)
    })
    await button.trigger('click')
    expect(useUiStore().startOpen).toBe(true) // T065 wires openStart
  })
  // The form's budget field and the R-15 no-graph payload are pinned where
  // the modal lives: src/app/shell/StartRunModal.test.ts (boundary rule).
})

describe('the from=run load', () => {
  it('loads through getRunGraph with the run id (FR-1205 path)', async () => {
    loadRun(DEFAULT_SHA)
    await mountAt(`/graphs/${DEFAULT_SHA}?from=run:feature-graph-demo`)
    expect(api.getRunGraph).toHaveBeenCalledWith('feature-graph-demo')
  })
})

// The /graphs redirects (T063 router rules) are pinned in
// src/app/router.redirects.test.ts — features/ may not import app/router.
