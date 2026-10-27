import { describe, it, expect } from 'vitest'
import { costRailOf } from './costRail.adapter'
import { BUDGET_SCOPE_NOTE } from '../../shared/cost'
import type { Run, RoleCost } from '../../api/types'
import type { GraphStateResponse, GraphWire } from '../../api/graph-types'

// 018 T027 (RED): the rail's Cost section, ported from the CostTab facts
// (FR-015a) plus the stage group by canonical_stage (R-5a, S16). Helpers copy
// CostTab.test.ts's mk()/role() shape.

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

const OPTS = { canonicalStages: ['intake', 'context', 'architect'] as readonly string[] }

describe('costRailOf (018 T027 RED)', () => {
  it('role rows in wire order with role, model, calls; per-role tokens; honest per-role prices', () => {
    const run = mk({
      cost: 2.6,
      roles: [
        role({ role: 'architect', model: 'glm', calls: 2, cost: 1.85 }),
        role({ role: 'qa', model: 'glm', calls: 1, cost: 0.75 }),
        role({ role: 'dev', model: 'm', calls: 1, cost: 0 }),
      ],
    })
    const rail = costRailOf(run, OPTS)
    expect(rail.roleRows.map((r) => [r.role, r.model, r.calls])).toEqual([
      ['architect', 'glm', 2],
      ['qa', 'glm', 1],
      ['dev', 'm', 1],
    ])
    const architect = rail.roleRows[0]
    expect(architect.tokens).toContain('1,000')
    expect(architect.tokens).toContain('200')
    expect(architect.tokens).toContain('10')
    expect(architect.tokens).toContain('5')
    expect(architect.price).toBe('$1.85')
    expect(rail.roleRows[2].price).toBe('not priced')
    expect(rail.roleRows[2].price).not.toBe('$0.00')
    expect(rail.totalTokens).toBe('3,645')
    expect(rail.totalPrice).toBe('$2.60 (partial)')
  })

  it('every row not-priced: the total says not priced, never $0.00', () => {
    const run = mk({
      roles: [role({ role: 'architect' }), role({ role: 'qa' })],
      cost: null,
    })
    const rail = costRailOf(run, OPTS)
    expect(rail.totalPrice).toBe('not priced')
    expect(rail.totalPrice).not.toBe('$0.00')
  })

  it('budget figures on an open run: amount, threshold, counted, pct, crossings and the scope note', () => {
    const run = mk({
      status: 'running',
      budget: 20,
      budgetThreshold: 40,
      budgetCounted: 31,
      budgetCrossings: 1,
    })
    const rail = costRailOf(run, OPTS)
    expect(rail.budget).toEqual({
      amount: '$20.00',
      threshold: '$40.00',
      counted: '$31.00',
      pct: '77%',
      crossings: 1,
      note: 'Budget ' + BUDGET_SCOPE_NOTE,
    })
    expect(rail.noBudgetSentence).toBeNull()
  })

  it('budget on a closed run: threshold and pct drop out, the counted spend stays', () => {
    const run = mk({
      status: 'done',
      budget: 20,
      budgetThreshold: null,
      budgetCounted: 2.6,
      budgetCrossings: 1,
    })
    const rail = costRailOf(run, OPTS)
    expect(rail.budget).toMatchObject({ amount: '$20.00', threshold: null, pct: null, counted: '$2.60', crossings: 1 })
  })

  it('no budget: the budget block is null and the CostTab sentence stands in', () => {
    const rail = costRailOf(mk({ budget: null }), OPTS)
    expect(rail.budget).toBeNull()
    expect(rail.noBudgetSentence).toBe(
      'No budget. Set one when starting a run (--budget-usd or the start form).',
    )
  })

  it('roles empty but a positive wire total (N9): noBreakdown with the honest total', () => {
    const rail = costRailOf(mk({ roles: [], cost: 7.88 }), OPTS)
    expect(rail.noBreakdown).toBe(true)
    expect(rail.totalPrice).toBe('$7.88')
  })

  it('stage group on an open run: canonical order, nodes summed, absent stages left out (R-5a)', () => {
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {
        a: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 1.5, canonical_stage: 'architect' },
        b: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 0.25, canonical_stage: 'architect' },
        c: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 0.1, canonical_stage: 'intake' },
      },
      edges: [],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, state })
    expect(rail.stageMeasured).toBe(true)
    expect(rail.stageRows).toEqual([
      { stage: 'intake', price: '$0.10' },
      { stage: 'architect', price: '$1.75' },
    ])
  })

  it('stage group on a closed run: not measured (R-5a)', () => {
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {
        a: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 1.5, canonical_stage: 'architect' },
      },
      edges: [],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'done' }), { ...OPTS, state })
    expect(rail.stageMeasured).toBe(false)
    expect(rail.stageRows).toEqual([])
  })

  it('revise traversals list every bounded back edge with its exhaustion (S16)', () => {
    const graph = {
      schema_version: 1,
      nodes: [{ id: 'architecture', type: 'architecture' }, { id: 'architect', type: 'architect' }, { id: 'plan', type: 'plan' }, { id: 'planner', type: 'planner' }],
      edges: [
        { source: 'architecture', source_port: 'revise', target: 'architect', target_port: 'guidance', max_traversals: 2 },
        { source: 'plan', source_port: 'revise', target: 'planner', target_port: 'guidance', max_traversals: 3 },
      ],
    } as unknown as GraphWire
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {},
      edges: [
        { edge: { source: 'architecture', source_port: 'revise', target: 'architect', target_port: 'guidance' }, traversals: 2 },
        { edge: { source: 'plan', source_port: 'revise', target: 'planner', target_port: 'guidance' }, traversals: 1 },
      ],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, graph, state })
    expect(rail.reviseRows).toEqual([
      { edge: 'architecture.revise>architect.guidance', used: 2, max: 2, exhausted: true },
      { edge: 'plan.revise>planner.guidance', used: 1, max: 3, exhausted: false },
    ])
  })

  // --- chaos (018 T027 RED) ------------------------------------------------

  it('a role with all-zero tokens and null cost is no-usage: price reads the em dash', () => {
    const rail = costRailOf(
      mk({ roles: [role({ inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 })] }),
      OPTS,
    )
    expect(rail.roleRows[0].price).toBe('—')
    expect(rail.roleRows[0].price).not.toBe('not priced')
    expect(rail.roleRows[0].price).not.toBe('$0.00')
  })

  it('budget set but budgetCounted null: counted and pct are null, never a "null" string or $NaN', () => {
    const rail = costRailOf(mk({ status: 'running', budget: 20, budgetThreshold: 40, budgetCounted: null }), OPTS)
    expect(rail.budget!.counted).toBeNull()
    expect(rail.budget!.pct).toBeNull()
    expect(JSON.stringify(rail.budget)).not.toContain('null"')
    expect(JSON.stringify(rail.budget)).not.toContain('$NaN')
  })

  it('a budget of 0 is set, not absent: amount $0.00 and no stand-in sentence', () => {
    const rail = costRailOf(mk({ status: 'running', budget: 0 }), OPTS)
    expect(rail.budget).not.toBeNull()
    expect(rail.budget!.amount).toBe('$0.00')
    expect(rail.noBudgetSentence).toBeNull()
  })

  it('null-cost nodes contribute nothing; an all-null stage is left out, a mixed stage sums to $1.50', () => {
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {
        a: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 1.5, canonical_stage: 'architect' },
        b: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: null, canonical_stage: 'architect' },
        c: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: null, canonical_stage: 'context' },
      },
      edges: [],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, state })
    expect(rail.stageRows).toEqual([{ stage: 'architect', price: '$1.50' }])
    expect(rail.stageRows.some((r) => r.stage === 'context')).toBe(false)
    expect(rail.stageRows.some((r) => r.price === '$0.00')).toBe(false)
  })

  it('a node with canonical_stage null lands in no stage row and throws nothing', () => {
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {
        a: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 2, canonical_stage: null },
        b: { status: 'done', round: 1, started_at: null, ended_at: null, cost_usd: 0.5, canonical_stage: 'intake' },
      },
      edges: [],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, state })
    expect(rail.stageRows).toEqual([{ stage: 'intake', price: '$0.50' }])
    expect(rail.stageRows.some((r) => r.stage === 'null')).toBe(false)
  })

  it('edges without max_traversals never reach reviseRows, even when the state records traversals for them', () => {
    const graph = {
      schema_version: 1,
      nodes: [{ id: 'architecture', type: 'architecture' }, { id: 'architect', type: 'architect' }],
      edges: [
        { source: 'architecture', source_port: 'revise', target: 'architect', target_port: 'guidance', max_traversals: 2 },
        { source: 'architect', source_port: 'revise', target: 'architecture', target_port: 'guidance' },
      ],
    } as unknown as GraphWire
    const state = {
      kind: 'state',
      graph_sha: 's',
      nodes: {},
      edges: [
        { edge: { source: 'architecture', source_port: 'revise', target: 'architect', target_port: 'guidance' }, traversals: 2 },
        { edge: { source: 'architect', source_port: 'revise', target: 'architecture', target_port: 'guidance' }, traversals: 5 },
      ],
      current_nodes: [],
      pending: [],
      outcome: { state: 'running', reason: null, result: null },
    } as unknown as GraphStateResponse
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, graph, state })
    expect(rail.reviseRows).toEqual([
      { edge: 'architecture.revise>architect.guidance', used: 2, max: 2, exhausted: true },
    ])
  })

  it('graph without a state lists the bounded edges at zero traversals, max from the graph', () => {
    const graph = {
      schema_version: 1,
      nodes: [{ id: 'architecture', type: 'architecture' }, { id: 'architect', type: 'architect' }],
      edges: [
        { source: 'architecture', source_port: 'revise', target: 'architect', target_port: 'guidance', max_traversals: 2 },
      ],
    } as unknown as GraphWire
    const rail = costRailOf(mk({ status: 'running' }), { ...OPTS, graph })
    expect(rail.reviseRows).toEqual([
      { edge: 'architecture.revise>architect.guidance', used: 0, max: 2, exhausted: false },
    ])
  })

  it('roles empty and wire total null: no breakdown banner and the em-dash total, distinct from N9', () => {
    const rail = costRailOf(mk({ roles: [], cost: null }), OPTS)
    expect(rail.noBreakdown).toBe(false)
    expect(rail.totalPrice).toBe('—')
  })
})
