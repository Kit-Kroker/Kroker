// 018 T040 (RED): the deleted entry components' cases port onto the card
// mapping — one DecisionCard per kind, mounted through decisionCardOf, with
// the R-3 action ids asserted through the buttons' emissions and the calls
// routed to the right api verbs. Item literals carry over from the old
// entries.test.ts shapes.
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DecisionCard from '@kroker/ui/components/decision_card/DecisionCard.vue'
import { decisionCardOf } from '../../shared/decisionCard.adapter'
import type { DashboardApi } from '../../api/types'
import type { ClarifyItem, EscalationItem, GateItem, OverrideItem } from '../../api/types'

const recordingApi = () =>
  ({
    answerClarify: vi.fn(async () => {}),
    decideGate: vi.fn(async () => {}),
    overrideMerge: vi.fn(async () => {}),
    decideTaskGate: vi.fn(async () => {}),
  }) as unknown as DashboardApi & Record<'answerClarify' | 'decideGate' | 'overrideMerge' | 'decideTaskGate', ReturnType<typeof vi.fn>>

const clarifyItem = (suggestion = 'Use OIDC.'): ClarifyItem => ({
  id: 'q1', runId: 'feature-add-sso', round: 1, age: '2h 00m', type: 'clarify',
  title: 'Clarification needed', body: 'The proposer needs one more answer.', suggestion,
})

const gateItem = (gate = 'architecture', id = 'architecture#1'): GateItem => ({
  id, runId: 'feature-add-sso', round: 2, age: '3h 15m', type: 'gate', gate,
  title: 'Architecture needs a decision', body: 'The architecture gate is waiting for review.',
})

const overrideItem = (): OverrideItem => ({
  id: 'm1', runId: 'feature-billing-webhooks', round: 1, age: '45m', type: 'override', gate: 'merge',
  title: 'Merge override requested', body: 'A check failed.',
  verdict: '2 of 6 checks failed.',
  checks: [{ name: 'ci', kind: 'ABSOLUTE', ok: false, detail: 'tests red' }],
})

const escalationItem = (): EscalationItem => ({
  id: 'e1', runId: 'fix-rate-limit-retry', round: 3, age: '6h 30m', type: 'escalation',
  title: 'Task escalated', body: 'The fix attempts ran out.',
  analysis: 'The retry loop could not reproduce the failure locally.',
})

// [item, expected act ids]. 'ready' pre-fills the text so needsText actions
// are clickable; the gating case is asserted separately below.
const CASES: [string, ReturnType<typeof gateItem> | ClarifyItem | OverrideItem | EscalationItem, string[]][] = [
  ['clarify with suggestion', clarifyItem(), ['accept', 'answer']],
  ['clarify without suggestion', clarifyItem(''), ['answer']],
  ['generic gate', gateItem(), ['approve', 'revise', 'reject']],
  ['tool_approval', gateItem('tool_approval'), ['approve', 'reject']],
  ['budget', gateItem('budget', 'budget#1'), ['approve', 'reject']],
  ['override', overrideItem(), ['override', 'send-back']],
  ['escalation', escalationItem(), ['approve', 'revise', 'reject']],
]

const mountCard = (item: (typeof CASES)[number][1]) => {
  const { card } = decisionCardOf(item)
  return mount(DecisionCard, {
    props: {
      ...card,
      text: card.text ? { ...card.text, value: card.text.value || 'ready' } : undefined,
    },
  })
}

describe('the card mapping per kind (018 T040 RED)', () => {
  for (const [name, item, expectedIds] of CASES) {
    it(`${name}: every action emits act with the R-3 id and routes to its api verb`, async () => {
      const { call } = decisionCardOf(item)
      const api = recordingApi()
      const w = mountCard(item)
      const buttons = w.findAll('[data-testid="card-action"]')
      expect(buttons.map((b) => b.text())).toHaveLength(expectedIds.length)
      for (let i = 0; i < expectedIds.length; i++) {
        await buttons[i].trigger('click')
        const [id, text] = w.emitted('act')![i] as [string, string]
        expect(id).toBe(expectedIds[i])
        await call(api, id, text, false)
      }
      const fakes = api as unknown as Record<string, ReturnType<typeof vi.fn>>
      const verb =
        item.type === 'clarify'
          ? 'answerClarify'
          : item.type === 'override'
            ? 'overrideMerge'
            : item.type === 'escalation'
              ? 'decideTaskGate'
              : 'decideGate'
      expect(fakes[verb].mock.calls.length).toBe(expectedIds.length)
      for (const other of Object.keys(fakes).filter((k) => k !== verb)) {
        expect(fakes[other]).not.toHaveBeenCalled()
      }
    })
  }

  it('needsText gating works through the component: blank disables, typing enables, click carries the text', async () => {
    const { card, call } = decisionCardOf(gateItem())
    const api = recordingApi()
    const w = mount(DecisionCard, { props: { ...card } })
    const revise = () => w.findAll('[data-testid="card-action"]')[1]
    expect((revise().element as HTMLButtonElement).disabled).toBe(true)
    await revise().trigger('click')
    expect(w.emitted('act')).toBeUndefined()

    await w.find('[data-testid="card-text"]').setValue('tighten the retry loop')
    expect((revise().element as HTMLButtonElement).disabled).toBe(false)
    await revise().trigger('click')
    const [id, text] = w.emitted('act')![0] as [string, string]
    expect(id).toBe('revise')
    await call(api, id, text, false)
    expect(api.decideGate).toHaveBeenCalledWith('feature-add-sso', 'architecture#1', 'revise', 'tighten the retry loop')
  })
})
