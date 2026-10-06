import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CostTab from './CostTab.vue'
import { useFleetStore } from '../../shared/fleet.store'
import { BUDGET_SCOPE_NOTE } from '../../shared/cost'
import type { Run, RoleCost } from '../../api/types'

// 011 T009 (RED): the Cost tab, one test per row of contract §3 (states,
// rows, totals, budget block). Test ids are data-model §2.6.

const mk = (over: Partial<Run> = {}): Run => ({
  id: 'r1',
  title: 'T',
  mode: 'brownfield',
  repo: 'r',
  activeStages: ['clarify'],
  stageMarks: null,
  status: 'running',
  blocker: '',
  cost: null,
  budget: null,
  roles: [],
  budgetThreshold: null,
  budgetCounted: null,
  budgetCrossings: 0,
  budgetNotice: null,
  age: '1m',
  decisions: [],
  projectKey: null,
  ...over,
})

const role = (over: Partial<RoleCost> = {}): RoleCost => ({
  role: 'dev',
  model: 'm',
  calls: 1,
  inputTokens: 1000,
  outputTokens: 200,
  cacheReadTokens: 10,
  cacheWriteTokens: 5,
  cost: null,
  ...over,
})

const mountTab = (run: Run | undefined) => {
  const fleet = useFleetStore()
  if (run) fleet.runs = [run]
  return mount(CostTab, { props: { runId: run?.id ?? 'r1' } })
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('CostTab states (contract §3)', () => {
  it('renders the cost-tab root and the research note, loading and loaded', () => {
    const loading = mountTab(undefined)
    expect(loading.find('[data-testid="cost-tab"]').exists()).toBe(true)
    expect(loading.find('[data-testid="cost-research-note"]').text()).toBe(
      'The research stage has its own search, fetch and cost limits; they are separate from the run budget, and its own spend is not listed here.',
    )
    const loaded = mountTab(mk())
    expect(loaded.find('[data-testid="cost-research-note"]').text()).toBe(
      'The research stage has its own search, fetch and cost limits; they are separate from the run budget, and its own spend is not listed here.',
    )
  })

  it('run not fetched yet: cost-empty says Loading', () => {
    const w = mountTab(undefined)
    expect(w.find('[data-testid="cost-empty"]').text()).toContain('Loading')
  })

  it('loaded with no usage and no budget: cost-empty, no usage recorded yet', () => {
    const w = mountTab(mk())
    expect(w.find('[data-testid="cost-empty"]').text()).toContain('No usage recorded yet.')
  })

  it('loaded with no usage but a budget: empty state and the budget block together', () => {
    const w = mountTab(mk({ budget: 20, budgetThreshold: 40, budgetCounted: 0 }))
    expect(w.find('[data-testid="cost-empty"]').text()).toContain('No usage recorded yet.')
    expect(w.find('[data-testid="cost-budget"]').exists()).toBe(true)
    expect(w.find('[data-testid="cost-budget"]').text()).toContain('$20.00')
  })

  it('no breakdown but a wire total (N9): cost-no-breakdown plus the total', () => {
    const w = mountTab(mk({ roles: [], cost: 7.88 }))
    expect(w.find('[data-testid="cost-no-breakdown"]').text()).toContain(
      'No breakdown recorded for this run.',
    )
    expect(w.find('[data-testid="cost-total-price"]').text()).toContain('$7.88')
  })
})

describe('CostTab role rows (contract §3)', () => {
  const run = () =>
    mk({
      cost: 2.6,
      roles: [
        role({ role: 'architect', model: 'glm', calls: 2, cost: 1.85 }),
        role({ role: 'qa', model: 'glm', calls: 1, cost: 0.75 }),
        role({ role: 'dev', model: 'm', calls: 1, cost: 0 }),
      ],
    })

  it('one cost-row per role in wire order, tagged with data-role', () => {
    const w = mountTab(run())
    const rows = w.findAll('[data-testid="cost-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[0].attributes('data-role')).toBe('architect')
    expect(rows[1].attributes('data-role')).toBe('qa')
    expect(rows[2].attributes('data-role')).toBe('dev')
    expect(rows[0].text()).toContain('architect')
    expect(rows[0].text()).toContain('glm')
    expect(rows[0].text()).toContain('2')
  })

  it('cost-row-tokens shows all four counts thousands-separated', () => {
    const w = mountTab(run())
    const tokens = w.find('[data-testid="cost-row"][data-role="architect"] [data-testid="cost-row-tokens"]')
    const text = tokens.text()
    for (const piece of ['1,000', '200', '10', '5']) {
      expect(text).toContain(piece)
    }
  })

  it('a priced role shows its dollars', () => {
    const w = mountTab(run())
    const price = w.find('[data-testid="cost-row"][data-role="architect"] [data-testid="cost-row-price"]')
    expect(price.text()).toContain('$1.85')
  })

  it('a not-priced role reads "not priced", never $0.00', () => {
    const w = mountTab(run())
    const dev = w.find('[data-testid="cost-row"][data-role="dev"] [data-testid="cost-row-price"]')
    expect(dev.text()).toContain('not priced')
    expect(dev.text()).not.toContain('$0.00')
  })

  it('totals: token sum and the partial total price', () => {
    const w = mountTab(run())
    expect(w.find('[data-testid="cost-total-tokens"]').text()).toContain('3,645')
    expect(w.find('[data-testid="cost-total-price"]').text()).toContain('$2.60 (partial)')
  })
})

describe('CostTab budget block (contract §3)', () => {
  it('no budget: the set-one-when-starting sentence', () => {
    const w = mountTab(mk())
    expect(w.find('[data-testid="cost-budget"]').text()).toContain(
      'No budget. Set one when starting a run (--budget-usd or the start form).',
    )
  })

  it('open run with a budget: budget, limit, counted, whole percent, crossings, note', () => {
    const w = mountTab(
      mk({ budget: 20, budgetThreshold: 40, budgetCounted: 31, budgetCrossings: 1 }),
    )
    const block = w.find('[data-testid="cost-budget"]').text()
    expect(block).toContain('$20.00')
    expect(block).toContain('$40.00')
    expect(w.find('[data-testid="cost-budget-counted"]').text()).toContain(
      'counted toward budget $31.00',
    )
    expect(w.find('[data-testid="cost-budget-pct"]').text()).toBe('77%')
    expect(w.find('[data-testid="cost-budget-crossings"]').text()).toContain('1')
    expect(w.find('[data-testid="cost-budget-note"]').text()).toBe('Budget ' + BUDGET_SCOPE_NOTE)
  })

  it('closed run with a budget: counted and crossings but no percent', () => {
    const w = mountTab(
      mk({
        status: 'done',
        budget: 20,
        budgetThreshold: null,
        budgetCounted: 2.6,
        budgetCrossings: 1,
      }),
    )
    expect(w.find('[data-testid="cost-budget-counted"]').text()).toContain(
      'counted toward budget $2.60',
    )
    expect(w.find('[data-testid="cost-budget-crossings"]').text()).toContain('1')
    expect(w.find('[data-testid="cost-budget-note"]').text()).toBe('Budget ' + BUDGET_SCOPE_NOTE)
    expect(w.find('[data-testid="cost-budget-pct"]').exists()).toBe(false)
  })
})
