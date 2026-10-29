// v5 Compare view (018 T071 RED): arms × graphs with SC and $/case, the
// description line, the rework heatmap, and the unavailable empty state.
// CompareView.vue, the mapCompare export and the mock's getCompare are all
// absent -- that is the RED. Wire shapes per data-model §2.4; the concrete
// example is the recorded fixture ../api/__fixtures__/read/compare.json.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CompareView from './CompareView.vue'
import fixture from '../../api/__fixtures__/read/compare.json'
import { mapCompare } from '../../api/http-read'
import { createMockApi } from '../../api/mock/index'

const api = vi.hoisted(() => ({
  getCompare: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'
const SEEDED_SHA = 'c1bbef2d33379ca4252d8971ed4b65934dd54e7d4c306a887698df0f0520c5ab'
const DESCRIPTION =
  'SC weights quality 0.6 · cost 0.2 · speed 0.2, judge anthropic:claude-sonnet-5'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

const mountView = async (wire: unknown = fixture) => {
  api.getCompare.mockResolvedValue(wire)
  const w = mount(CompareView, { global: { stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return w
}

describe('CompareView (v5, 018 T071 RED)', () => {
  it('renders one row per arm with its name and note, and SC and $/case per graph', async () => {
    const withNote = {
      ...(fixture as object),
      arms: (fixture as { arms: Array<Record<string, unknown>> }).arms.map((a, i) => ({
        ...a,
        note: i === 0 ? 'recovered arm label' : a['note'],
      })),
    }
    const w = await mountView(withNote)
    const rows = w.findAll('[data-testid="cmp-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('glm-5.2')
    expect(rows[0].text()).toContain('recovered arm label')
    expect(rows[1].text()).toContain('glm-5.3')
    for (const row of rows) {
      expect(row.text()).toContain('1.0') // SC per graph
    }
    expect(rows[1].text()).toContain('1.5') // $/case, default graph
    expect(rows[1].text()).toContain('2.0') // $/case, seeded graph
  })

  it('a null cost per case reads not measured, never $0.00', async () => {
    const w = await mountView()
    const glm52 = w.findAll('[data-testid="cmp-row"]')[0]
    expect(glm52.text()).toContain('not measured')
    expect(glm52.text()).not.toContain('$0.00')
  })

  it('the description line comes from the wire', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="cmp-desc"]').text()).toBe(DESCRIPTION)
  })

  it('the heatmap columns render in wire order', async () => {
    const w = await mountView()
    const heat = w.find('[data-testid="cmp-heat"]')
    expect(heat.exists()).toBe(true)
    expect(heat.findAll('[data-testid="heat-column"]').map((h) => h.text())).toEqual(['code'])
  })

  it('an unavailable root renders the empty state naming the root', async () => {
    const w = await mountView({ ...fixture, available: false, root: 'D:/srv/runs' })
    const empty = w.find('[data-testid="cmp-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('D:/srv/runs')
    expect(w.find('[data-testid="cmp-row"]').exists()).toBe(false)
  })
})

describe('mapCompare (018 T071 RED)', () => {
  it('maps the recorded fixture to camelCase with nulls and order intact', () => {
    const compare = mapCompare(fixture as never)
    expect(compare.available).toBe(true)
    expect(compare.graphs).toEqual([DEFAULT_SHA, SEEDED_SHA])
    expect(compare.arms.map((a: { name: string }) => a.name)).toEqual(['glm-5.2', 'glm-5.3'])
    const glm52 = compare.arms[0] as Record<string, unknown>
    expect(glm52['harness']).toBe('opencode')
    expect(glm52['model']).toBe('zai-coding-plan/glm-5.2')
    expect(glm52['note']).toBeNull()
    const cells = glm52['cells'] as Array<Record<string, unknown>>
    expect(cells.map((c) => c['graph'])).toEqual([DEFAULT_SHA, SEEDED_SHA])
    expect(cells[0]!['sc']).toBe(1.0)
    expect(cells[0]!['costPerCase']).toBeNull()
    expect(cells[1]!['costPerCase']).toBe(1.0)
    expect(compare.heatColumns).toEqual(['code'])
    expect(compare.heatRows).toHaveLength(2)
    expect(compare.heatRows[0]!.cells[0]).toMatchObject({ state: 'low_n', value: 0.0, n: 2 })
  })
})

describe('the compare mock (018 T071 RED)', () => {
  it('replays the fixture: two arms, one null cost per case, the description and the heat column', async () => {
    const mock = createMockApi({ simulateLive: false })
    const compare = await mock.getCompare()
    expect(compare.available).toBe(true)
    expect(compare.arms.map((a: { name: string }) => a.name)).toEqual(['glm-5.2', 'glm-5.3'])
    const glm52 = compare.arms[0] as Record<string, unknown>
    const cells = glm52['cells'] as Array<Record<string, unknown>>
    expect(cells[0]!['costPerCase']).toBeNull()
    expect(compare.description).toBe(DESCRIPTION)
    expect(compare.heatColumns).toEqual(['code'])
  })
})
