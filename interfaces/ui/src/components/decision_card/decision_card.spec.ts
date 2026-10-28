import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DecisionCard from './DecisionCard.vue'

// 018 T034 (RED): the decision card shell (FR-601's one card for every kind).
// Stable hooks the implementation (T035) must carry: card-kicker / card-schema
// / card-title / card-where / card-field / card-foot / card-text /
// card-action / action-title.

const PROPS = {
  kicker: 'architecture r1',
  schema: 'gate',
  title: 'Approve the architecture',
  where: 'feature-graph-demo · node architecture',
  fields: [
    { k: 'Round', v: 'r1' },
    { k: 'Cost', v: '$1.87', mono: true },
  ],
  foot: 'decided by policy (soft)',
}

const ACTIONS = [
  { id: 'revise', label: 'Revise', title: 'send the plan back to the architect', variant: 'primary', needsText: true },
  { id: 'approve', label: 'Approve', title: 'grant this increment', variant: 'default' },
]

describe('DecisionCard', () => {
  it('renders kicker, schema chip, title, where, fields and foot', () => {  // clause: DECISION_CARD-1
    const w = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    expect(w.find('[data-testid="card-kicker"]').text()).toBe('architecture r1')
    expect(w.find('[data-testid="card-schema"]').text()).toBe('gate')
    expect(w.find('[data-testid="card-title"]').text()).toBe('Approve the architecture')
    expect(w.find('[data-testid="card-where"]').text()).toBe('feature-graph-demo · node architecture')
    const fields = w.findAll('[data-testid="card-field"]')
    expect(fields).toHaveLength(2)
    expect(fields[0].text()).toContain('Round')
    expect(fields[0].text()).toContain('r1')
    expect(fields[1].text()).toContain('Cost')
    expect(fields[1].text()).toContain('$1.87')
    expect(w.find('[data-testid="card-foot"]').text()).toBe('decided by policy (soft)')
  })

  it('renders the text area only when text is given, labelled and empty initially', () => {  // clause: DECISION_CARD-2
    const bare = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    expect(bare.find('[data-testid="card-text"]').exists()).toBe(false)

    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: '', required: true } },
    })
    const area = w.find('[data-testid="card-text"]')
    expect(area.exists()).toBe(true)
    const tag = (area.element as HTMLElement).tagName.toLowerCase()
    expect(tag).toBe('textarea')
    expect(`${area.attributes('aria-label') ?? ''} ${area.attributes('placeholder') ?? ''}`).toContain('Answer')
    expect((area.element as HTMLTextAreaElement).value).toBe('')
  })

  it('shows each action consequence as visible text; needsText gates its button on input', async () => {  // clause: DECISION_CARD-3
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: '', required: true } },
    })
    const actions = w.findAll('[data-testid="card-action"]')
    expect(actions).toHaveLength(2)
    expect(actions[0].text()).toBe('Revise')
    expect(actions[1].text()).toBe('Approve')
    // The consequence is visible text beside the button, not a tooltip.
    const titles = w.findAll('[data-testid="action-title"]').map((t) => t.text())
    expect(titles).toContain('send the plan back to the architect')
    expect(titles).toContain('grant this increment')

    expect((actions[0].element as HTMLButtonElement).disabled).toBe(true)
    await w.find('[data-testid="card-text"]').setValue('split the auth service')
    expect((w.findAll('[data-testid="card-action"]')[0].element as HTMLButtonElement).disabled).toBe(false)
  })

  it('busy disables every action', () => {  // clause: DECISION_CARD-4
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, busy: true, text: { label: 'Answer', hint: 'one line, plain text', value: 'x', required: true } },
    })
    for (const b of w.findAll('[data-testid="card-action"]')) {
      expect((b.element as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('a click emits act with the action id and the current text', async () => {  // clause: DECISION_CARD-5
    const bare = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    const approve = bare.findAll('[data-testid="card-action"]')[1]
    await approve.trigger('click')
    expect(bare.emitted('act')).toEqual([['approve', '']])

    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: '', required: true } },
    })
    await w.find('[data-testid="card-text"]').setValue('split the auth service')
    await w.findAll('[data-testid="card-action"]')[0].trigger('click')
    expect(w.emitted('act')).toEqual([['revise', 'split the auth service']])
  })

  it('a gated action emits nothing while its text requirement is unmet', async () => {  // clause: DECISION_CARD-6
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: '', required: true } },
    })
    await w.findAll('[data-testid="card-action"]')[0].trigger('click')
    expect(w.emitted('act')).toBeUndefined()
  })

  // --- chaos (018 T034 RED) ------------------------------------------------

  it('an empty fields array renders no card-field rows; an empty foot renders present and empty', () => {  // clause: DECISION_CARD-1
    const w = mount(DecisionCard, { props: { ...PROPS, fields: [], foot: '', actions: ACTIONS } })
    expect(w.findAll('[data-testid="card-field"]')).toHaveLength(0)
    const foot = w.find('[data-testid="card-foot"]')
    expect(foot.exists()).toBe(true)
    expect(foot.text()).toBe('')
  })

  it('a non-empty initial text value satisfies needsText immediately, not only after typing', () => {  // clause: DECISION_CARD-2
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: 'pre-filled', required: true } },
    })
    expect((w.find('[data-testid="card-text"]').element as HTMLTextAreaElement).value).toBe('pre-filled')
    expect((w.findAll('[data-testid="card-action"]')[0].element as HTMLButtonElement).disabled).toBe(false)
  })

  it('clearing the textarea disables the needsText action again', async () => {  // clause: DECISION_CARD-3
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, text: { label: 'Answer', hint: 'one line, plain text', value: 'draft', required: true } },
    })
    expect((w.findAll('[data-testid="card-action"]')[0].element as HTMLButtonElement).disabled).toBe(false)
    await w.find('[data-testid="card-text"]').setValue('')
    expect((w.findAll('[data-testid="card-action"]')[0].element as HTMLButtonElement).disabled).toBe(true)
  })

  it('needsText with no text prop at all: the action stays disabled and never emits', async () => {  // clause: DECISION_CARD-3
    const bare = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    expect(bare.find('[data-testid="card-text"]').exists()).toBe(false)
    const revise = bare.findAll('[data-testid="card-action"]')[0]
    expect((revise.element as HTMLButtonElement).disabled).toBe(true)
    await revise.trigger('click')
    expect(bare.emitted('act')).toBeUndefined()
  })

  it('two clicks on the same enabled action emit act twice with the same payload (no dedupe)', async () => {  // clause: DECISION_CARD-5
    const w = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    const approve = w.findAll('[data-testid="card-action"]')[1]
    await approve.trigger('click')
    await approve.trigger('click')
    expect(w.emitted('act')).toEqual([['approve', ''], ['approve', '']])
  })

  it('busy wins over satisfied text: the gated action stays disabled', () => {  // clause: DECISION_CARD-4
    const w = mount(DecisionCard, {
      props: { ...PROPS, actions: ACTIONS, busy: true, text: { label: 'Answer', hint: 'one line, plain text', value: 'ready text', required: true } },
    })
    expect((w.findAll('[data-testid="card-action"]')[0].element as HTMLButtonElement).disabled).toBe(true)
  })

  it('a mono field styles its value with a class containing mono', () => {  // clause: DECISION_CARD-1
    const w = mount(DecisionCard, { props: { ...PROPS, actions: ACTIONS } })
    const costRow = w.findAll('[data-testid="card-field"]')[1]
    expect(costRow.text()).toContain('$1.87')
    expect(costRow.find('[class*="mono"]').exists()).toBe(true)
  })
})
