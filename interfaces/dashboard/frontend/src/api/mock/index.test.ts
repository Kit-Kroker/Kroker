import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createMockApi, tickCosts } from './index'
import { BUDGET_SCOPE_NOTE, totalPrice } from '../../shared/cost'
import type { Run } from '../types'

const mk = (over: Partial<Run>): Run => ({
  id: 'x', title: 't', mode: 'brownfield', repo: 'r', activeStages: ['architecture'], status: 'running',
  blocker: '', cost: 1, budget: 10, age: '1m', decisions: [],
  ...over,
})

afterEach(() => { vi.restoreAllMocks() })

describe('tickCosts', () => {
  it('bumps running runs and leaves others untouched', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [mk({ id: 'a', status: 'running', cost: 1 }), mk({ id: 'b', status: 'done', cost: 5 })]
    const out = tickCosts(runs)
    expect(out[0].cost).toBeCloseTo(1.05, 5)
    expect(out[1].cost).toBe(5)
  })
})

describe('mock api decision flows', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  it('seeds 10 runs and 6 inbox items, including the graph demo run', async () => {
    expect(await api.listRuns()).toHaveLength(10)
    expect(await api.listInbox()).toHaveLength(6)
  })

  it('getInboxState returns the six items and no unreadable runs', async () => {
    // 010 T004 (RED): the mock has one snapshot, so nothing is unreadable
    // and the items are the same list listInbox serves (contract §1).
    const state = await api.getInboxState()
    expect(state.items).toEqual(await api.listInbox())
    expect(state.unreadable).toEqual([])
  })

  it('answers a clarify question and logs a decision', async () => {
    await api.answerClarify('feature-add-sso', 'q1', 'Use OIDC.')
    const inbox = await api.listInbox()
    expect(inbox.find((i) => i.id === 'q1')).toBeUndefined()
    const run = await api.getRun('feature-add-sso')
    expect(run?.decisions.some((d) => d.outcome === 'approve' && d.gate.includes('clarify Q1'))).toBe(true)
  })

  it('advances a run to architecture when the last clarify is answered', async () => {
    await api.answerClarify('feature-add-sso', 'q1', 'OIDC')
    await api.answerClarify('feature-add-sso', 'q2', 'Keep password behind a flag')
    const run = await api.getRun('feature-add-sso')
    expect(run?.activeStages).toEqual(['architecture'])
    expect(run?.status).toBe('running')
  })

  it('throws when the key is not pending on that run', async () => {
    // q1 belongs to feature-add-sso; scoping to another run must fail loudly,
    // not silently succeed (the wrong-run POST is F1's whole finding).
    await expect(
      api.answerClarify('feature-usage-metering', 'q1', 'x'),
    ).rejects.toThrow('no pending item q1 on feature-usage-metering')
  })

  it('approving a gate advances the stage', async () => {
    await api.decideGate('feature-usage-metering', 'g2', 'approve', '')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('running')
    expect(run?.activeStages).toEqual(['planning'])
  })

  it('rejecting a gate fails the branch', async () => {
    await api.decideGate('feature-usage-metering', 'g2', 'reject', 'wrong layering')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('failed')
  })

  it('override approve moves run to deploy', async () => {
    await api.overrideMerge('feature-billing-webhooks', 'g1', true, 'retry branches covered indirectly')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.activeStages).toEqual(['deploy'])
    expect(run?.status).toBe('running')
  })

  it('override send-back drops run to code', async () => {
    await api.overrideMerge('feature-billing-webhooks', 'g1', false, '')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.activeStages).toEqual(['code'])
  })

  it('escalation retry resumes the task', async () => {
    await api.resolveEscalation('fix-rate-limit-retry', 'e1', true, 'inject a clock')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('repair attempt 4')
  })

  it('escalation quarantine keeps the wave going', async () => {
    await api.resolveEscalation('fix-rate-limit-retry', 'e1', false, '')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('quarantined')
    expect(run?.status).toBe('running')
  })

  it('startRun slugs the title and prepends the run', async () => {
    const r = await api.startRun({ title: 'Add SSO to customer portal', description: '', repo: '', mode: 'brownfield' })
    expect(r.id).toBe('feature-add-sso-to-customer')
    expect((await api.listRuns())[0].id).toBe(r.id)
  })
})

// T027 companion (RED): the four board-oriented mock runs T028 must add
// (contracts/board-client.md mock contract). Pinned by shape only -- no
// project name or implementation detail is hardcoded. Every it fails
// today: no run carries a projectKey yet.
describe('mock runs cover the board scenarios (T028)', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  it('has a run on a real board project (non-null projectKey)', async () => {
    const runs = await api.listRuns()
    expect(runs.some((r) => r.projectKey != null)).toBe(true)
  })

  it('has a run with no board project (projectKey null)', async () => {
    const runs = await api.listRuns()
    expect(runs.some((r) => r.projectKey === null)).toBe(true)
  })

  it('has a run whose projectKey can 404 on the mock board', async () => {
    // Asserted by value distinctness only: a non-null key exists, and the
    // runs carry >= 3 distinct projectKeys including null, so at least two
    // board projects exist beyond any single rich one.
    const runs = await api.listRuns()
    const keys = runs.map((r) => r.projectKey)
    expect(runs.some((r) => r.projectKey != null)).toBe(true)
    expect(new Set(keys).has(null)).toBe(true)
    expect(new Set(keys).size).toBeGreaterThanOrEqual(3)
  })

  it('has a run whose project is reachable with an empty board', async () => {
    // The empty-state project is a THIRD distinct non-null key: one project
    // cannot at once hold the rich board, 404, and be reachable-but-empty,
    // so >= 3 non-null keys is the runs-side precondition for all four
    // scenarios coexisting (the mock board decides which is which).
    const runs = await api.listRuns()
    const nonNull = new Set(runs.map((r) => r.projectKey).filter((k) => k != null))
    expect(nonNull.size).toBeGreaterThanOrEqual(3)
  })
})

// --- 011 T007 (RED): mock seeds cover the four contract cases (§2.2) -------
// feature-graph-demo stays the budget run (status unchanged); dark-mode is
// the closed all-priced case; audit-export the N9 no-breakdown closed case;
// onboarding-v2 the all-not-priced case with its own budget. The seed counts
// (10 runs, 6 inbox items) are pinned by the first describe; not repeated.

describe('mock cost seeds (011 T007)', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  const find = async (id: string): Promise<Run> => {
    const run = (await api.listRuns()).find((r) => r.id === id)
    expect(run, `seed run ${id} missing`).toBeDefined()
    return run as Run
  }

  it('feature-graph-demo is the budget run: one not-priced dev role, one crossing', async () => {
    const r = await find('feature-graph-demo')
    expect(r.status).toBe('blocked') // unchanged by this task
    expect(r.budget).toBe(20)
    expect(r.budgetThreshold).toBe(40) // raised once
    expect(r.budgetCounted).toBeCloseTo(2.6, 5)
    expect(r.budgetCrossings).toBe(1)
    expect(r.cost).toBeCloseTo(2.6, 5) // the priced sum
    expect(r.roles).toHaveLength(3)
    const [architect, qa, dev] = r.roles
    expect(architect.role).toBe('architect')
    expect(architect.cost).toBeCloseTo(1.85, 5)
    expect(architect.inputTokens + architect.outputTokens).toBeGreaterThan(0)
    expect(qa.role).toBe('qa')
    expect(qa.cost).toBeCloseTo(0.75, 5)
    expect(qa.inputTokens + qa.outputTokens).toBeGreaterThan(0)
    expect(dev.role).toBe('dev')
    expect(dev.cost).toBe(0) // not-priced: 0 with tokens
    expect(dev.inputTokens + dev.outputTokens).toBeGreaterThan(0)
  })

  it('feature-dark-mode is closed, all priced, no budget fields', async () => {
    const r = await find('feature-dark-mode')
    expect(r.status).toBe('done')
    expect(r.budget).toBeNull()
    expect(r.budgetThreshold).toBeNull()
    expect(r.budgetCounted).toBeNull()
    expect(r.roles).toHaveLength(3)
    for (const role of r.roles) expect(role.cost).not.toBeNull()
    const sum = r.roles.reduce((acc, x) => acc + (x.cost ?? 0), 0)
    expect(sum).toBeCloseTo(7.88, 5)
    expect(r.cost).toBeCloseTo(7.88, 5)
  })

  it('feature-audit-export is the N9 closed case: a total with no breakdown', async () => {
    const r = await find('feature-audit-export')
    expect(r.status).toBe('done')
    expect(r.roles).toEqual([])
    expect(r.cost).toBeCloseTo(14.02, 5)
  })

  it('feature-onboarding-v2 is all not-priced with its own budget', async () => {
    const r = await find('feature-onboarding-v2')
    expect(r.status).toBe('blocked') // NOT running, so tickCosts never touches it
    expect(r.roles.length).toBeGreaterThan(0)
    expect(r.roles.some((x) => x.cost === 0)).toBe(true)
    expect(r.roles.some((x) => x.cost === null)).toBe(true)
    for (const role of r.roles) {
      expect(role.inputTokens + role.outputTokens).toBeGreaterThan(0)
    }
    expect(r.cost).toBeNull()
    expect(r.budget).toBe(50)
    expect(r.budgetThreshold).toBe(50)
    expect(r.budgetCounted).toBe(0)
    expect(r.budgetCrossings).toBe(0)
  })

  it('startRun honours a budget and returns the scope notice', async () => {
    const r = await api.startRun({
      title: 'Budgeted run',
      description: '',
      repo: '',
      mode: 'greenfield',
      budget: 5,
    } as never)
    expect(r.budget).toBe(5)
    expect(r.budgetNotice).not.toBeNull()
    expect(r.budgetNotice as string).toContain(BUDGET_SCOPE_NOTE)
    expect((r.budgetNotice as string).startsWith('Budget $5.00')).toBe(true)
  })

  it('startRun without a budget keeps notice and budget null', async () => {
    const r = await api.startRun({
      title: 'Plain run',
      description: '',
      repo: '',
      mode: 'greenfield',
      budget: null,
    } as never)
    expect(r.budget).toBeNull()
    expect(r.budgetNotice).toBeNull()
  })
})

// --- 011 T007 (RED): tickCosts funds a role, never invents a total (R-7) ----
// For a RUNNING run with roles the increment lands on the FIRST role's cost
// and run.cost is recomputed as totalPrice(roles, null).usd; running runs
// without roles keep today's direct bump; non-running runs are untouched
// (pinned by the first tickCosts describe). random 0.5 -> increment 0.05.

describe('tickCosts funds the first role (011 T007)', () => {
  const roleRow = (role: string, cost: number | null) => ({
    role,
    cost,
    inputTokens: 100,
    outputTokens: 10,
  })

  it('lands the increment on the first role and recomputes the partial total', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [
      mk({
        id: 'a',
        status: 'running',
        cost: 1.0,
        roles: [roleRow('architect', 1.0), roleRow('dev', 0)] as never,
      }),
    ]
    const out = tickCosts(runs)
    const [architect, dev] = (out[0] as { roles: { cost: number | null }[] }).roles
    expect(architect.cost).toBeCloseTo(1.05, 5) // 1.0 + 0.05
    expect(dev.cost).toBe(0) // untouched
    expect(out[0].cost).toBe(totalPrice(out[0].roles as never, null).usd)
    expect(out[0].cost).toBeCloseTo(1.05, 5) // the partial priced sum 1.05
  })

  it('funds a not-priced first role instead of inventing a total', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [
      mk({
        id: 'a',
        status: 'running',
        cost: null,
        roles: [roleRow('dev', 0)] as never, // not-priced: 0 with tokens
      }),
    ]
    const out = tickCosts(runs)
    expect((out[0] as { roles: { cost: number | null }[] }).roles[0].cost).toBeCloseTo(0.05, 5)
    expect(out[0].cost).toBeCloseTo(0.05, 5)
  })

  it('recomputes a null cost from the roles instead of adding to null', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [
      mk({
        id: 'a',
        status: 'running',
        cost: null,
        roles: [roleRow('architect', 1.0), roleRow('dev', null)] as never,
      }),
    ]
    const out = tickCosts(runs)
    expect(out[0].cost).toBe(totalPrice(out[0].roles as never, null).usd)
    expect(out[0].cost).toBeCloseTo(1.05, 5)
  })

  it('keeps the direct bump for a running run with no roles', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [mk({ id: 'a', status: 'running', cost: 1 })]
    expect(tickCosts(runs)[0].cost).toBeCloseTo(1.05, 5)
  })
})

// --- 011 T015 (RED): the default-off budget-gate switch ----------------------
// MockOptions.budgetGate (default false): with it off (and by default) the
// inbox seed stays at exactly SIX items, none of gate 'budget'; with it on a
// SEVENTH item is appended, exactly as data-model §2.4 gives it. Nothing at
// runtime creates a budget gate, so the switch is the only source.

describe('the budget-gate switch (011 T015)', () => {
  it('by default the inbox stays at six items, none of gate budget', async () => {
    const def = createMockApi({ simulateLive: false })
    const noOptions = createMockApi()
    for (const api of [def, noOptions]) {
      const inbox = await api.listInbox()
      expect(inbox).toHaveLength(6)
      expect(inbox.some((i) => (i as { gate?: string }).gate === 'budget')).toBe(false)
      const state = await api.getInboxState()
      expect(state.items).toHaveLength(6)
      expect(state.items.some((i) => (i as { gate?: string }).gate === 'budget')).toBe(false)
    }
  })

  it('budgetGate: true seeds the seventh item verbatim with the note math intact', async () => {
    const api = createMockApi({ simulateLive: false, budgetGate: true })
    const inbox = await api.listInbox()
    expect(inbox).toHaveLength(7)
    const seventh = inbox[6]
    expect(seventh).toEqual({
      id: 'budget#2',
      type: 'gate',
      gate: 'budget',
      runId: 'feature-graph-demo',
      round: 2,
      age: '1m',
      title: 'Budget (round 2) — graph demo',
      body: 'Run cost $40.2000 >= budget $40.00',
    })
    // The note math holds: the seeded run has budget 20, one crossing
    // already approved (current limit 40); approving raises it to $60.00.
    const run = (await api.listRuns()).find((r) => r.id === 'feature-graph-demo')
    expect(run?.budget).toBe(20)
    expect(run?.budgetThreshold).toBe(40)
  })

  it('exports the URL param constant', async () => {
    const mod = await import('./index')
    expect(mod.MOCK_BUDGET_GATE_PARAM).toBe('mockBudgetGate')
  })
})
