// v5 FleetTable (018 T048 RED): the table takes v5 rows as props —
// { rows, runInContext } — and renders the S6 columns. RED: the component
// still reads the fleet store and renders the stage strip.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FleetTable from './FleetTable.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a data-testid="row-link"><slot /></a>',
}

interface V5Row {
  runId: string
  title: string
  graph: string
  arm: string
  outcome: string
  where: string
  traversals: string
  cost: string
  elapsed: string
  openLabel: 'Decide' | 'Open run' | 'Open'
}

const row = (over: Partial<V5Row> = {}): V5Row => ({
  runId: 'run-1',
  title: 'A feature',
  graph: 'default',
  arm: 'opencode × glm',
  outcome: 'running',
  where: 'code',
  traversals: '2/3',
  cost: '$3.10',
  elapsed: '2h 14m',
  openLabel: 'Open',
  ...over,
})

const mountTable = (rows: V5Row[], runInContext: string | null = null) =>
  mount(FleetTable, {
    props: { rows, runInContext },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('FleetTable (v5, 018 T048 RED)', () => {
  it('renders one fleet-row per row with the v5 cells', () => {
    const w = mountTable([row(), row({ runId: 'run-2', openLabel: 'Decide' })])
    const rows = w.findAll('[data-testid="fleet-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].find('.col-graph').text()).toBe('default')
    expect(rows[0].find('.col-arm').text()).toBe('opencode × glm')
    expect(rows[0].find('.col-outcome').text()).toBe('running')
    expect(rows[0].find('.col-traversals').text()).toBe('2/3')
    expect(rows[0].text()).toContain('$3.10')
    expect(rows[0].text()).toContain('2h 14m')
  })

  it('the open label renders as the fleet-open control per row', () => {
    const w = mountTable([row({ openLabel: 'Decide' }), row({ runId: 'run-2', openLabel: 'Open run' })])
    const opens = w.findAll('[data-testid="fleet-open"]')
    expect(opens).toHaveLength(2)
    expect(opens[0].text()).toBe('Decide')
    expect(opens[1].text()).toBe('Open run')
  })

  // 018: the 'one stage dot per canonical stage, 18 marks' case is DELETED
  // with CONSOLE-3 (S6 retires the stage strip); T050 tombstones the clause.

  it('an empty rows list renders the empty state', () => {
    const w = mountTable([])
    expect(w.find('[data-testid="fleet-empty"]').exists()).toBe(true)
    expect(w.findAll('[data-testid="fleet-row"]')).toHaveLength(0)
  })
})
