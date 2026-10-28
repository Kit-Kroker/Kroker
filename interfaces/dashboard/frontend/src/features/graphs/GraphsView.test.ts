// v5 Graphs catalog (018 T060 RED): one CatalogCard per shipped graph, the
// action navigating to /graphs/<sha>, and the PipelineConfig panel (checks +
// sections). The view today is the old graph editor host, so every v5 hook
// here is absent -- that is the RED. Mount pattern follows FleetView.test.ts
// (pinia + a real memory router); the api mock replays the recorded fixture.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import GraphsView from './GraphsView.vue'
import fixture from '../../api/__fixtures__/read/graphs-shipped.json'

const api = vi.hoisted(() => ({
  getShippedGraphs: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'

// The mapped shape DashboardApi.getShippedGraphs serves (camelCase; counts
// built from the wire's nodes/gates/edges).
const shipped = (over: Record<string, unknown> = {}) => ({
  graphs: (fixture.graphs as Array<Record<string, unknown>>).map((g) => ({
    name: g['name'],
    sha: g['sha'],
    description: g['description'],
    when: g['when'],
    counts: [
      { label: 'nodes', n: g['nodes'] },
      { label: 'gates', n: g['gates'] },
      { label: 'edges', n: g['edges'] },
    ],
  })),
  checks: fixture.checks,
  sections: fixture.sections,
  ...over,
})

const makeRouter = async (): Promise<Router> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/graphs', component: GraphsView },
      { path: '/graphs/:sha', component: { template: '<div data-testid="design-route" />' } },
    ],
  })
  await router.push('/graphs')
  await router.isReady()
  return router
}

const mountView = async () => {
  const router = await makeRouter()
  const Host = { components: { RouterView }, template: '<RouterView />' }
  const w = mount(Host, { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  api.getShippedGraphs.mockResolvedValue(shipped())
})

describe('GraphsView (v5, 018 T060 RED)', () => {
  it('renders one card per shipped graph, by name', async () => {
    const { w } = await mountView()
    const names = w.findAll('[data-testid="catalog-name"]').map((n) => n.text())
    expect(names).toEqual(['default', 'default-research', 'seeded'])
    // A null description/when reads not measured on the card (FR-915).
    expect(w.text()).toContain('not measured')
  })

  it("the card's action navigates to /graphs/<sha>", async () => {
    const { w, router } = await mountView()
    const actions = w.findAll('[data-testid="catalog-action"]')
    expect(actions).toHaveLength(3)
    expect(actions[0].text()).toBe('Open in Design')
    await actions[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/graphs/${DEFAULT_SHA}`)
  })

  it('the PipelineConfig panel renders the three checks and the five sections', async () => {
    const { w } = await mountView()
    const checks = w.findAll('[data-testid="config-check"]')
    expect(checks).toHaveLength(3)
    expect(checks.map((c) => c.attributes('data-state'))).toEqual(['pass', 'pass', 'pass'])
    expect(checks[0].text()).toContain('validate_run_roles')

    const sections = w.findAll('[data-testid="config-section"]')
    expect(sections.map((s) => s.find('[data-testid="config-section-title"]').text())).toEqual([
      'Roles', 'Proposer roles', 'Gates', 'Limits', 'Arms',
    ])
  })

  it('null section values read not measured, never null', async () => {
    const { w } = await mountView()
    const limits = w
      .findAll('[data-testid="config-section"]')
      .find((s) => s.text().includes('Limits'))!
    const rows = limits.findAll('[data-testid="config-row"]')
    expect(rows).toHaveLength(9)
    expect(w.text()).not.toContain('null')
    expect(w.text()).toContain('not measured')
  })

  it('the V8 note renders the check text verbatim, carrying the colliding ids when it fails', async () => {
    api.getShippedGraphs.mockResolvedValue(
      shipped({
        checks: [
          {
            name: 'validate_run_roles',
            state: 'fail',
            text: "adversary model 'zai:glm-5.3' is the same model as 'dev' ('zai:glm-5.3')"
              + ' — a second opinion from the same weights is not a second opinion',
          },
          ...fixture.checks.slice(1),
        ],
      }),
    )
    const { w } = await mountView()
    const check = w.find('[data-testid="config-check"]')
    expect(check.attributes('data-state')).toBe('fail')
    expect(check.text()).toContain("same weights")
    expect(check.text()).toContain("'zai:glm-5.3'")
  })
})
