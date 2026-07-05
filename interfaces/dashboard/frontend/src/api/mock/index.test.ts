import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createMockApi, tickCosts } from './index'
import type { Run } from '../types'

const mk = (over: Partial<Run>): Run => ({
  id: 'x', title: 't', mode: 'brownfield', repo: 'r', stageIdx: 5, status: 'running',
  blocker: '', cost: 1, budget: 10, age: '1m', skipCtx: false, stageNote: '', decisions: [],
  ...over,
})

describe('tickCosts', () => {
  it('bumps running runs and leaves others untouched', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const runs = [mk({ id: 'a', status: 'running', cost: 1 }), mk({ id: 'b', status: 'done', cost: 5 })]
    const out = tickCosts(runs)
    expect(out[0].cost).toBeCloseTo(1.05, 5)
    expect(out[1].cost).toBe(5)
    vi.restoreAllMocks()
  })
})

describe('mock api decision flows', () => {
  let api: ReturnType<typeof createMockApi>
  beforeEach(() => {
    api = createMockApi({ simulateLive: false })
  })

  it('seeds 7 runs and 5 inbox items', async () => {
    expect(await api.listRuns()).toHaveLength(7)
    expect(await api.listInbox()).toHaveLength(5)
  })

  it('answers a clarify question and logs a decision', async () => {
    await api.answerClarify('q1', 'Use OIDC.')
    const inbox = await api.listInbox()
    expect(inbox.find((i) => i.id === 'q1')).toBeUndefined()
    const run = await api.getRun('feature-add-sso')
    expect(run?.decisions.some((d) => d.outcome === 'approve' && d.gate.includes('clarify Q1'))).toBe(true)
  })

  it('advances a run to architecture when the last clarify is answered', async () => {
    await api.answerClarify('q1', 'OIDC')
    await api.answerClarify('q2', 'Keep password behind a flag')
    const run = await api.getRun('feature-add-sso')
    expect(run?.stageIdx).toBe(5)
    expect(run?.status).toBe('running')
  })

  it('approving a gate advances the stage', async () => {
    await api.decideGate('g2', 'approve', '')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('running')
    expect(run?.stageIdx).toBeGreaterThan(5)
  })

  it('rejecting a gate fails the branch', async () => {
    await api.decideGate('g2', 'reject', 'wrong layering')
    const run = await api.getRun('feature-usage-metering')
    expect(run?.status).toBe('failed')
  })

  it('override approve moves run to deploy (stageIdx 12)', async () => {
    await api.overrideMerge('g1', true, 'retry branches covered indirectly')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.stageIdx).toBe(12)
    expect(run?.status).toBe('running')
  })

  it('override send-back drops run to code (stageIdx 7)', async () => {
    await api.overrideMerge('g1', false, '')
    const run = await api.getRun('feature-billing-webhooks')
    expect(run?.stageIdx).toBe(7)
  })

  it('escalation retry resumes the task', async () => {
    await api.resolveEscalation('e1', true, 'inject a clock')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('repair attempt 4')
  })

  it('escalation quarantine keeps the wave going', async () => {
    await api.resolveEscalation('e1', false, '')
    const run = await api.getRun('fix-rate-limit-retry')
    expect(run?.blocker).toContain('quarantined')
    expect(run?.status).toBe('running')
  })

  it('startRun slugs the title and prepends the run', async () => {
    const r = await api.startRun({ title: 'Add SSO to customer portal', repo: '', mode: 'brownfield' })
    expect(r.id).toBe('feature-add-sso-to-customer')
    expect((await api.listRuns())[0].id).toBe(r.id)
  })
})
