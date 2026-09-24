import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createMockApi, tickCosts } from './index'
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
