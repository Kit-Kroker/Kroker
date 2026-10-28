import { describe, it, expect, vi } from 'vitest'
import { decisionCardOf } from './decisionCard.adapter'
import type { DashboardApi } from '../api/types'

// 018 T038 (RED): one decision-card mapping for every inbox kind (R-3's
// table). Fixtures are plain literals in the item shapes of api/types.

const recordingApi = () =>
  ({
    answerClarify: vi.fn(async () => {}),
    decideGate: vi.fn(async () => {}),
    overrideMerge: vi.fn(async () => {}),
    decideTaskGate: vi.fn(async () => {}),
  }) as unknown as DashboardApi & Record<'answerClarify' | 'decideGate' | 'overrideMerge' | 'decideTaskGate', ReturnType<typeof vi.fn>>

describe('decisionCardOf (018 T038 RED)', () => {
  const clarify = {
    id: 'q1', runId: 'r1', round: 2, age: '1m', type: 'clarify' as const,
    title: 'Which auth?', body: 'OIDC or session cookies?', suggestion: 'Use OIDC.',
  }
  const gate = {
    id: 'architecture#1', runId: 'r1', round: 1, age: '2m', type: 'gate' as const,
    gate: 'architecture', title: 'architecture (round 1)', body: 'the spec',
  }

  it('a clarify with a suggestion offers accept and answer, both routing to answerClarify', async () => {
    const { card, call } = decisionCardOf(clarify)
    expect(card.schema).toBe('clarify')
    expect(card.title).toBe('Which auth?')
    expect(card.kicker).toContain('r2')
    expect(card.where).toContain('r1')
    expect(card.actions).toEqual([
      expect.objectContaining({ id: 'accept', label: 'Accept suggestion' }),
      expect.objectContaining({ id: 'answer' }),
    ])
    const answer = card.actions.find((a) => a.id === 'answer')!
    expect(answer.needsText).toBe(true)
    expect(card.text).toMatchObject({ label: 'Answer', required: true })

    const api = recordingApi()
    await call(api, 'accept', '', false)
    expect(api.answerClarify).toHaveBeenCalledWith('r1', 'q1', '')
    await call(api, 'answer', 'Use OIDC then.', false)
    expect(api.answerClarify).toHaveBeenLastCalledWith('r1', 'q1', 'Use OIDC then.')
  })

  it('a clarify without a suggestion drops the accept action', () => {
    const { card } = decisionCardOf({ ...clarify, suggestion: '' })
    expect(card.actions.map((a) => a.id)).toEqual(['answer'])
  })

  it('a generic gate offers approve, revise (needsText), reject in order, all to decideGate', async () => {
    const { card, call } = decisionCardOf(gate)
    expect(card.schema).toBe('gate')
    expect(card.actions.map((a) => a.id)).toEqual(['approve', 'revise', 'reject'])
    expect(card.actions.find((a) => a.id === 'revise')!.needsText).toBe(true)

    const api = recordingApi()
    await call(api, 'approve', '', false)
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'architecture#1', 'approve', '')
    await call(api, 'revise', 'wrong layer', false)
    expect(api.decideGate).toHaveBeenLastCalledWith('r1', 'architecture#1', 'revise', 'wrong layer')
    await call(api, 'reject', 'no', false)
    expect(api.decideGate).toHaveBeenLastCalledWith('r1', 'architecture#1', 'reject', 'no')
  })

  it('a tool_approval gate offers only Approve and Deny, footed by the timeout rule (V4)', async () => {
    const { card, call } = decisionCardOf({ ...gate, gate: 'tool_approval' })
    expect(card.actions).toHaveLength(2)
    expect(card.actions.map((a) => a.id)).toEqual(['approve', 'reject'])
    const everyWord = card.actions.map((a) => `${a.label} ${a.title}`).join(' ')
    expect(everyWord).not.toMatch(/halt/i)
    expect(card.foot).toBe('a timeout counts as not approved')

    const api = recordingApi()
    await call(api, 'reject', '', false)
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'architecture#1', 'reject', '')
  })

  it('the budget gate prices its consequences into the action titles (V6)', async () => {
    const { card, call } = decisionCardOf({ ...gate, gate: 'budget' })
    expect(card.actions.find((a) => a.id === 'approve')!.title).toContain('one more increment')
    expect(card.actions.find((a) => a.id === 'reject')!.title).toContain('rejected:budget')

    const api = recordingApi()
    await call(api, 'approve', '', false)
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'architecture#1', 'approve', '')
  })

  it('an override offers override (needsText) and send-back, routed to overrideMerge', async () => {
    const item = {
      id: 'merge#1', runId: 'r1', round: 3, age: '4m', type: 'override' as const,
      gate: 'merge' as const, title: 'Merge gate — round 3', body: 'audited override',
      verdict: '', checks: [],
    }
    const { card, call } = decisionCardOf(item)
    expect(card.schema).toBe('override')
    expect(card.actions.map((a) => a.id)).toEqual(['override', 'send-back'])
    expect(card.actions.find((a) => a.id === 'override')!.needsText).toBe(true)

    const api = recordingApi()
    await call(api, 'override', 'retry branches covered indirectly', false)
    expect(api.overrideMerge).toHaveBeenCalledWith('r1', 'merge#1', true, 'retry branches covered indirectly')
    await call(api, 'send-back', 'not yet', false)
    expect(api.overrideMerge).toHaveBeenLastCalledWith('r1', 'merge#1', false, 'not yet')
  })

  it('a task escalation routes everything through decideTaskGate with the thaw flag (V5)', async () => {
    const item = {
      id: 'e1', runId: 'r1', round: 4, age: '6m', type: 'escalation' as const,
      title: 't5 — resolver exhausted (3)', body: 'could not close', analysis: '',
    }
    const { card, call } = decisionCardOf(item)
    expect(card.schema).toBe('escalation')
    expect(card.actions.map((a) => a.id)).toEqual(['approve', 'revise', 'reject'])
    expect(card.actions.find((a) => a.id === 'approve')!.title).toContain('accept as done')
    const revise = card.actions.find((a) => a.id === 'revise')!
    expect(revise.label).toBe('retry')
    expect(revise.needsText).toBe(true)
    expect(card.actions.find((a) => a.id === 'reject')!.title).toContain('failed:quarantined-tasks')

    const api = recordingApi()
    await call(api, 'approve', '', false)
    expect(api.decideTaskGate).toHaveBeenCalledWith('r1', 'e1', 'approve', '', false)
    await call(api, 'revise', 'retry with a clock', true)
    expect(api.decideTaskGate).toHaveBeenLastCalledWith('r1', 'e1', 'revise', 'retry with a clock', true)
    await call(api, 'revise', 'retry plain', false)
    expect(api.decideTaskGate).toHaveBeenLastCalledWith('r1', 'e1', 'revise', 'retry plain', false)
    await call(api, 'reject', '', false)
    expect(api.decideTaskGate).toHaveBeenLastCalledWith('r1', 'e1', 'reject', '', false)
    expect(api.decideGate).not.toHaveBeenCalled()
  })

  it('an unknown gate falls back to the generic gate actions (EC4)', () => {
    const { card } = decisionCardOf({ ...gate, gate: 'research' })
    expect(card.actions.map((a) => a.id)).toEqual(['approve', 'revise', 'reject'])
  })

  it('every action of every kind invokes exactly one api method once', async () => {
    const item = {
      id: 'merge#1', runId: 'r1', round: 3, age: '4m', type: 'override' as const,
      gate: 'merge' as const, title: 'Merge gate — round 3', body: 'b', verdict: '', checks: [],
    }
    const cases = [
      decisionCardOf(clarify),
      decisionCardOf({ ...clarify, suggestion: '' }),
      decisionCardOf(gate),
      decisionCardOf({ ...gate, gate: 'tool_approval' }),
      decisionCardOf({ ...gate, gate: 'budget' }),
      decisionCardOf(item),
      decisionCardOf({
        id: 'e1', runId: 'r1', round: 4, age: '6m', type: 'escalation' as const,
        title: 't5', body: 'b', analysis: '',
      }),
    ]
    for (const { card, call } of cases) {
      for (const action of card.actions) {
        const api = recordingApi()
        await call(api, action.id, 'x', false)
        const fakes = api as unknown as Record<string, ReturnType<typeof vi.fn>>
        const hit = Object.values(fakes).filter((f) => f.mock.calls.length > 0)
        expect(hit).toHaveLength(1)
        expect(hit[0].mock.calls).toHaveLength(1)
      }
    }
  })

  it('the timeout copy comes only from the timeouts map for that gate', () => {
    const timed = decisionCardOf(gate, { architecture: 'reject the round' })
    expect(timed.timeout).toBe('reject the round')
    expect(timed.card.foot).not.toContain('undefined')

    const unlisted = decisionCardOf(gate, { merge: 'reject the round' })
    expect(unlisted.timeout).toBeNull()

    const untimed = decisionCardOf(gate)
    expect(untimed.timeout).toBeNull()
    expect(untimed.card.foot).not.toContain('undefined')
  })

  // --- chaos (018 T038 RED) ------------------------------------------------

  it('accept with typed text ignores the text: the suggestion-side mapping is sent, never the typing', async () => {
    const { card, call } = decisionCardOf(clarify)
    expect(card.actions.some((a) => a.id === 'accept')).toBe(true)
    const api = recordingApi()
    await call(api, 'accept', 'I typed my own answer', false)
    expect(api.answerClarify).toHaveBeenLastCalledWith('r1', 'q1', '')
    const args = api.answerClarify.mock.calls.flat()
    expect(args).not.toContain('I typed my own answer')
  })

  it('the gate kicker carries its round: r1 at round 1, r7 at round 7', () => {
    expect(decisionCardOf(gate).card.kicker).toContain('r1')
    expect(decisionCardOf({ ...gate, id: 'architecture#7', round: 7 }).card.kicker).toContain('r7')
  })

  it('an override with empty verdict and no checks renders no undefined anywhere', () => {
    const item = {
      id: 'merge#1', runId: 'r1', round: 3, age: '4m', type: 'override' as const,
      gate: 'merge' as const, title: 'Merge gate — round 3', body: 'b', verdict: '', checks: [],
    }
    const { card } = decisionCardOf(item)
    const rendered = JSON.stringify([card.fields ?? [], card.foot ?? ''])
    expect(rendered).not.toContain('undefined')
  })

  it('a task escalation reject consequence names quarantine and the quarantine tail verbatim', () => {
    const item = {
      id: 'e1', runId: 'r1', round: 4, age: '6m', type: 'escalation' as const,
      title: 't5', body: 'b', analysis: '',
    }
    const reject = decisionCardOf(item).card.actions.find((a) => a.id === 'reject')!
    expect(reject.title).toContain('quarantine')
    expect(reject.title).toContain('failed:quarantined-tasks')
  })

  it('an unknown action id resolves without calling anything', async () => {
    const { call } = decisionCardOf(gate)
    const api = recordingApi()
    await expect(call(api, 'nope', '', false)).resolves.toBeUndefined()
    const fakes = api as unknown as Record<string, ReturnType<typeof vi.fn>>
    for (const f of Object.values(fakes)) expect(f).not.toHaveBeenCalled()
  })

  it('a tool_approval timeout comes from its own map copy; the V4 foot stands regardless', () => {
    const timed = decisionCardOf({ ...gate, gate: 'tool_approval' }, { tool_approval: 'timed out: denied by the clock' })
    expect(timed.timeout).toBe('timed out: denied by the clock')
    expect(timed.card.foot).toBe('a timeout counts as not approved')
  })

  it('a budget gate absent from the timeouts map has timeout null (the fallback copy is the view\'s)', () => {
    const rail = decisionCardOf({ ...gate, gate: 'budget' }, { merge: 'other gate copy' })
    expect(rail.timeout).toBeNull()
  })
})
