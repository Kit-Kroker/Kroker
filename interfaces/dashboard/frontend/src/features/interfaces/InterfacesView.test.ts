// v5 Interfaces view (018 T078 RED): the harness matrix screen. The view
// renders the library CheckMatrix with the mapped wire; the mapper
// (mapInterfaces) and the mock's getInterfaces are separate describes.
// InterfacesView.vue and both are absent -- that is the RED. The concrete
// wire is the recorded fixture ../api/__fixtures__/read/interfaces.json
// (already camelCase; the cell state keeps its wire spelling 'not_measured').
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InterfacesView from './InterfacesView.vue'
import fixture from '../../api/__fixtures__/read/interfaces.json'
import { mapInterfaces } from '../../api/http-read'
import { createMockApi } from '../../api/mock/index'

const api = vi.hoisted(() => ({
  getInterfaces: vi.fn(),
}))
vi.mock('../../api/client', () => ({ api }))

const cellOf = (harness: string, key: string) => {
  const columns = fixture.columns.map((c) => c.key)
  const row = fixture.rows.find((r) => r.harness === harness)!
  return { ...row.cells[columns.indexOf(key)], harness }
}

beforeEach(() => {
  vi.resetAllMocks()
  api.getInterfaces.mockResolvedValue(fixture)
})

describe('InterfacesView (v5, 018 T078 RED)', () => {
  it('renders the matrix with five rows, one per harness', async () => {
    const w = mount(InterfacesView)
    await flushPromises()
    expect(w.find('[data-testid="if-view"]').exists()).toBe(true)
    const rows = w.findAll('[data-testid="matrix-row"]')
    expect(rows).toHaveLength(5)
    const harnesses = ['claude_code', 'opencode', 'cursor', 'crew', 'pyai']
    harnesses.forEach((h, i) => expect(rows[i].text()).toContain(h))
  })

  it('renders the not measured cells as the wire spells them', async () => {
    const w = mount(InterfacesView)
    await flushPromises()
    const cells = w.findAll('[data-testid="matrix-cell"]')
    // Every row carries the three unmeasured columns; claude_code's whole
    // tail after layers/strict is not_measured.
    const claude = w.findAll('[data-testid="matrix-row"]')[0].findAll('[data-testid="matrix-cell"]')
    expect(claude[2].attributes('data-state')).toBe('not_measured')
    expect(claude[5].attributes('data-state')).toBe('not_measured')
    expect(cells.length).toBe(30) // 5 rows x 6 columns
  })

  it('the family cell is filled on exactly one row (the registry dev harness)', async () => {
    const w = mount(InterfacesView)
    await flushPromises()
    const rows = w.findAll('[data-testid="matrix-row"]')
    const familyStates = rows.map(
      (r) => r.findAll('[data-testid="matrix-cell"]')[2].attributes('data-state'),
    )
    expect(familyStates.filter((s) => s === 'yes')).toEqual(['yes']) // opencode only
    // Three measured rows read not_measured; the planned pyai row's cell
    // is planned - a planned row measures nothing (T074 semantics).
    expect(familyStates.filter((s) => s === 'not_measured')).toHaveLength(3)
    expect(familyStates[4]).toBe('planned')
  })

  it('renders the two facts with their severities, who and text', async () => {
    const w = mount(InterfacesView)
    await flushPromises()
    const facts = w.findAll('[data-testid="matrix-fact"]')
    expect(facts).toHaveLength(2)
    expect(facts[0].attributes('data-severity')).toBe('warn')
    expect(facts[0].text()).toContain('opencode')
    expect(facts[0].text()).toContain('rules_unenforceable')
    expect(facts[1].attributes('data-severity')).toBe('error')
    expect(facts[1].text()).toContain('cursor')
    expect(facts[1].text()).toContain('nothing to enforce')
  })
})

describe('mapInterfaces (018 T078 RED)', () => {
  it('mirrors the wire into the InterfaceMatrix type, spelling kept', () => {
    const matrix = mapInterfaces(fixture as never)
    expect(matrix.columns.map((c: { key: string }) => c.key)).toEqual([
      'layers', 'strict', 'family', 'installed', 'checkpoint', 'session',
    ])
    expect(matrix.rows.map((r: { harness: string }) => r.harness)).toEqual([
      'claude_code', 'opencode', 'cursor', 'crew', 'pyai',
    ])
    const opencode = matrix.rows[1] as Record<string, unknown>
    expect(opencode['planned']).toBe(false)
    const cells = opencode['cells'] as Array<Record<string, unknown>>
    expect(cells[1]).toMatchObject({ state: 'partial' })
    expect(String(cells[1]!['text'])).toContain('refuses')
    expect(cells[5]!['state']).toBe('not_measured') // the wire spelling survives
    const pyai = matrix.rows[4] as Record<string, unknown>
    expect(pyai['planned']).toBe(true)
    expect(matrix.facts).toEqual(fixture.facts)
  })
})

describe('the interfaces mock (018 T078 RED)', () => {
  it('replays the fixture: five rows, one family fill, two facts', async () => {
    const mock = createMockApi({ simulateLive: false })
    const matrix = await mock.getInterfaces()
    expect(matrix.rows).toHaveLength(5)
    const familyIdx = matrix.columns.findIndex((c: { key: string }) => c.key === 'family')
    const familyStates = matrix.rows.map(
      (r: { cells: Array<{ state: string }> }) => r.cells[familyIdx]!.state,
    )
    expect(familyStates.filter((s) => s === 'yes')).toHaveLength(1)
    expect(matrix.facts).toHaveLength(2)
    expect(cellOf('opencode', 'strict').state).toBe('partial') // fixture sanity
  })
})
