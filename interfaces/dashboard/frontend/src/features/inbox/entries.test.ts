// 010 T008 (RED): the entry frame of contracts/inbox-screen.md §3.2, written
// before InboxEntry.vue exists (that unresolved import is the RED cause).
// Field names per data-model §1.1; kind labels and the RouterLink target per
// data-model §2.6 and §3.2. Mount pattern: RunView.test.ts's RouterLink stub.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import InboxEntry from './InboxEntry.vue'
import { useFleetStore } from '../../shared/fleet.store'
import type {
  ClarifyItem,
  GateItem,
  OverrideItem,
  EscalationItem,
} from '../../api/types'

const RouterLinkStub = { props: ['to'], template: '<a data-testid="stub-link"><slot /></a>' }

// Full literals, field names per data-model §1.1.
const gateItem = (): GateItem => ({
  id: 'architecture#1',
  runId: 'feature-add-sso',
  round: 2,
  age: '3h 15m',
  type: 'gate',
  gate: 'architecture',
  title: 'Architecture needs a decision',
  body: 'The architecture gate is waiting for review.',
})

const clarifyItem = (): ClarifyItem => ({
  id: 'q1',
  runId: 'feature-add-sso',
  round: 1,
  age: '2h 00m',
  type: 'clarify',
  title: 'Clarification needed',
  body: 'The proposer needs one more answer.',
  suggestion: 'Use OIDC.',
})

const overrideItem = (): OverrideItem => ({
  id: 'm1',
  runId: 'feature-billing-webhooks',
  round: 1,
  age: '45m',
  type: 'override',
  gate: 'merge',
  title: 'Merge override requested',
  body: 'A check failed; the proposer asks for an override.',
  verdict: '2 of 6 checks failed.',
  checks: [{ name: 'ci', kind: 'ABSOLUTE', ok: false, detail: 'tests red' }],
})

const escalationItem = (): EscalationItem => ({
  id: 'e1',
  runId: 'fix-rate-limit-retry',
  round: 3,
  age: '6h 30m',
  type: 'escalation',
  title: 'Task escalated',
  body: 'The fix attempts ran out.',
  analysis: 'The retry loop could not reproduce the failure locally.',
})

const mountInboxEntry = (
  item: ClarifyItem | GateItem | OverrideItem | EscalationItem,
  extra: { notice?: string; slot?: string } = {},
) =>
  mount(InboxEntry, {
    props: { item, ...(extra.notice !== undefined ? { notice: extra.notice } : {}) },
    slots: extra.slot ? { default: extra.slot } : {},
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('InboxEntry', () => {
  it('the root carries the entry test id and the run/key/type attributes', () => {
    const wrapper = mountInboxEntry(gateItem())
    const root = wrapper.get('[data-testid="inbox-entry"]')
    expect(root.attributes('data-run-id')).toBe('feature-add-sso')
    expect(root.attributes('data-key')).toBe('architecture#1')
    expect(root.attributes('data-type')).toBe('gate')
  })

  it('kind label, age, title and body render under their test ids', () => {
    const wrapper = mountInboxEntry(gateItem())
    expect(wrapper.get('[data-testid="inbox-entry-kind"]').text()).toContain('architecture')
    expect(wrapper.get('[data-testid="inbox-entry-age"]').text()).toBe('3h 15m')
    expect(wrapper.get('[data-testid="inbox-entry-title"]').text()).toBe(
      'Architecture needs a decision',
    )
    expect(wrapper.get('[data-testid="inbox-entry-body"]').text()).toBe(
      'The architecture gate is waiting for review.',
    )
  })

  it('the kind label is the fixed string of data-model 2.6 for each of the four types', () => {
    const cases: [ReturnType<typeof clarifyItem> | GateItem | OverrideItem | EscalationItem, string][] = [
      [clarifyItem(), 'question'],
      [gateItem(), 'gate · architecture'],
      [overrideItem(), 'merge override'],
      [escalationItem(), 'escalation'],
    ]
    for (const [item, label] of cases) {
      const wrapper = mountInboxEntry(item)
      expect(wrapper.get('[data-testid="inbox-entry-kind"]').text()).toBe(label)
    }
  })

  it('the run link shows the run id and links to the run route', () => {
    const wrapper = mountInboxEntry(gateItem())
    const link = wrapper.get('[data-testid="inbox-entry-run"]')
    expect(link.text()).toBe('feature-add-sso')
    const linkComponent = wrapper.findComponent(RouterLinkStub)
    expect(linkComponent.props('to')).toEqual({ name: 'run', params: { id: 'feature-add-sso' } })
  })

  it('an empty body renders no body block (EC7)', () => {
    const item = { ...gateItem(), body: '' }
    const wrapper = mountInboxEntry(item)
    expect(wrapper.find('[data-testid="inbox-entry-body"]').exists()).toBe(false)
  })

  it('the notice renders only when the notice prop is given', () => {
    const without = mountInboxEntry(gateItem())
    expect(without.find('[data-testid="inbox-notice"]').exists()).toBe(false)
    const withNotice = mountInboxEntry(gateItem(), { notice: 'already decided elsewhere' })
    expect(withNotice.get('[data-testid="inbox-notice"]').text()).toBe('already decided elsewhere')
  })

  it('the body block carries the inbox-longtext class (EC8)', () => {
    const wrapper = mountInboxEntry(gateItem())
    expect(wrapper.get('[data-testid="inbox-entry-body"]').classes()).toContain('inbox-longtext')
  })

  it('slot content renders after the notice', () => {
    const wrapper = mountInboxEntry(gateItem(), {
      notice: 'failed: boom',
      slot: '<span data-testid="slot-marker">entry actions</span>',
    })
    const notice = wrapper.get('[data-testid="inbox-notice"]').element
    const slot = wrapper.get('[data-testid="slot-marker"]').element
    expect(notice.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

// --- ClarifyEntry (010 T011, RED; contract §3.3 row 1). The import is
// dynamic with a non-literal specifier on purpose: a static one (and even a
// literal dynamic one — Vite resolves those at transform time) would fail
// this whole file's collection, taking the green InboxEntry tests down with
// it. Runtime resolution keeps the RED scoped to the missing
// ./ClarifyEntry.vue (T012 creates it).
const clarifyEntryPath = './ClarifyEntry.vue'
const mountClarify = async (
  over: { item?: ClarifyItem; busy?: boolean; draft?: string; editing?: boolean } = {},
) => {
  const { default: ClarifyEntry } = await import(/* @vite-ignore */ clarifyEntryPath)
  return mount(ClarifyEntry, {
    props: {
      item: over.item ?? clarifyItem(),
      busy: over.busy ?? false,
      draft: over.draft ?? '',
      editing: over.editing ?? false,
    },
  })
}

describe('ClarifyEntry', () => {
  it('with a suggestion and not editing: suggestion with the longtext class, accept and edit, no field', async () => {
    const wrapper = await mountClarify()
    const suggestion = wrapper.get('[data-testid="inbox-suggestion"]')
    expect(suggestion.classes()).toContain('inbox-longtext')
    expect(suggestion.text()).toBe('Use OIDC.')
    expect(wrapper.get('[data-testid="inbox-accept"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="inbox-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="field-control"]').exists()).toBe(false)
  })

  it('clicking accept emits answer once with the trimmed suggestion', async () => {
    const wrapper = await mountClarify({ item: { ...clarifyItem(), suggestion: '  Use OIDC.  ' } })
    await wrapper.get('[data-testid="inbox-accept"]').trigger('click')
    expect(wrapper.emitted('answer')).toEqual([['Use OIDC.']])
  })

  it('editing shows the Answer field with the draft; typing emits update:draft', async () => {
    const wrapper = await mountClarify({ editing: true, draft: 'partial ans' })
    expect(wrapper.findAll('label').map((l) => l.text())).toContain('Answer')
    const control = wrapper.get('[data-testid="field-control"]')
    expect((control.element as HTMLTextAreaElement).value).toBe('partial ans')
    await control.setValue('typed answer')
    expect(wrapper.emitted('update:draft')).toEqual([['typed answer']])
  })

  it('send is disabled while the draft is blank and sends the trimmed draft otherwise', async () => {
    for (const draft of ['', '   ']) {
      const blank = await mountClarify({ editing: true, draft })
      expect(blank.get('[data-testid="inbox-send"]').attributes('disabled')).toBeDefined()
    }
    const filled = await mountClarify({ editing: true, draft: '  real answer  ' })
    const send = filled.get('[data-testid="inbox-send"]')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')
    expect(filled.emitted('answer')).toEqual([['real answer']])
  })

  it('a blank suggestion hides suggestion, accept and edit, and shows the answer field (EC7)', async () => {
    for (const suggestion of ['', '   ']) {
      const wrapper = await mountClarify({ item: { ...clarifyItem(), suggestion } })
      expect(wrapper.find('[data-testid="inbox-suggestion"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="inbox-accept"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="inbox-edit"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="field-control"]').exists()).toBe(true)
    }
  })

  it('clicking edit emits toggle-edit once', async () => {
    const wrapper = await mountClarify()
    await wrapper.get('[data-testid="inbox-edit"]').trigger('click')
    expect(wrapper.emitted('toggle-edit')).toHaveLength(1)
  })

  it('busy disables accept, edit, send and the field, and clicks emit nothing', async () => {
    const wrapper = await mountClarify({ busy: true, editing: true, draft: 'ready' })
    for (const id of ['inbox-accept', 'inbox-edit', 'inbox-send']) {
      expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    expect(wrapper.get('[data-testid="field-control"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="inbox-accept"]').trigger('click')
    await wrapper.get('[data-testid="inbox-edit"]').trigger('click')
    await wrapper.get('[data-testid="inbox-send"]').trigger('click')
    expect(wrapper.emitted('answer')).toBeUndefined()
    expect(wrapper.emitted('toggle-edit')).toBeUndefined()
    expect(wrapper.emitted('update:draft')).toBeUndefined()
  })
})

// --- GateEntry (010 T014, RED; contract §3.3 row 2). Same non-literal
// dynamic import as ClarifyEntry above: per-test runtime resolution keeps
// the RED scoped to the missing ./GateEntry.vue (T015 creates it) instead
// of failing the whole file's collection. The library GateDecision keeps
// its comment internally and emits ONE object; GateEntry re-emits it as
// TWO arguments (contract §3.3 row 2), which is what these tests pin.
const gateEntryPath = './GateEntry.vue'
const mountGate = async (over: { item?: GateItem; busy?: boolean } = {}) => {
  const { default: GateEntry } = await import(/* @vite-ignore */ gateEntryPath)
  return mount(GateEntry, {
    props: { item: over.item ?? gateItem(), busy: over.busy ?? false },
  })
}

describe('GateEntry', () => {
  it('renders exactly one gate-decision titled with the data-model 2.6 fixed string', async () => {
    const wrapper = await mountGate()
    const decisions = wrapper.findAll('[data-testid="gate-decision"]')
    expect(decisions).toHaveLength(1)
    expect(wrapper.get('[data-testid="gate-decision"]').text()).toContain('architecture · round 2')
  })

  it('clicking approve emits decide as TWO arguments, approve and an empty comment', async () => {
    const wrapper = await mountGate()
    await wrapper.get('[data-testid="gate-approve"]').trigger('click')
    const emissions = wrapper.emitted('decide')
    expect(emissions).toHaveLength(1)
    expect(emissions![0]).toEqual(['approve', ''])
    expect(Array.isArray(emissions![0])).toBe(true)
    expect((emissions![0] as unknown[]).length).toBe(2)
  })

  it('a typed comment and revise emit decide with the trimmed comment', async () => {
    const wrapper = await mountGate()
    await wrapper.get('[data-testid="gate-comment"]').setValue('  tighten the retry loop  ')
    await wrapper.get('[data-testid="gate-revise"]').trigger('click')
    expect(wrapper.emitted('decide')).toEqual([['revise', 'tighten the retry loop']])
  })

  it('revise is disabled while the comment is empty', async () => {
    const wrapper = await mountGate()
    expect(wrapper.get('[data-testid="gate-revise"]').attributes('disabled')).toBeDefined()
  })

  it('busy disables all three gate buttons', async () => {
    const wrapper = await mountGate({ busy: true })
    for (const id of ['gate-approve', 'gate-revise', 'gate-reject']) {
      expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
  })
})

// --- OverrideEntry and EscalationEntry (010 T017, RED; contract §3.3 rows
// 3-4). Same non-literal dynamic imports as above: per-test runtime
// resolution keeps the RED scoped to the two missing components (T018/T019
// create them) instead of failing the whole file's collection.
const overrideEntryPath = './OverrideEntry.vue'
const mountOverride = async (
  over: { item?: OverrideItem; busy?: boolean; draft?: string } = {},
) => {
  const { default: OverrideEntry } = await import(/* @vite-ignore */ overrideEntryPath)
  return mount(OverrideEntry, {
    props: {
      item: over.item ?? overrideItem(),
      busy: over.busy ?? false,
      draft: over.draft ?? '',
    },
  })
}

describe('OverrideEntry', () => {
  it('renders one check-row per check in order, and the verdict with the longtext class', async () => {
    const item = {
      ...overrideItem(),
      checks: [
        { name: 'ci', kind: 'ABSOLUTE' as const, ok: false, detail: 'tests red' },
        { name: 'size', kind: 'ADVISORY' as const, ok: true, detail: 'within budget' },
        { name: 'lint', kind: 'ADVISORY' as const, ok: true },
      ],
    }
    const wrapper = await mountOverride({ item })
    const rows = wrapper.findAll('[data-testid="check-row"]')
    expect(rows).toHaveLength(3)
    expect(rows.map((r) => r.get('.name').text())).toEqual(['ci', 'size', 'lint'])
    const verdict = wrapper.get('[data-testid="inbox-verdict"]')
    expect(verdict.text()).toBe('2 of 6 checks failed.')
    expect(verdict.classes()).toContain('inbox-longtext')
  })

  it('an empty verdict renders no verdict block', async () => {
    const wrapper = await mountOverride({ item: { ...overrideItem(), verdict: '' } })
    expect(wrapper.find('[data-testid="inbox-verdict"]').exists()).toBe(false)
  })

  it('override is disabled while the draft is blank; send-back is enabled', async () => {
    for (const draft of ['', '   ']) {
      const wrapper = await mountOverride({ draft })
      expect(wrapper.get('[data-testid="inbox-override"]').attributes('disabled')).toBeDefined()
      expect(wrapper.get('[data-testid="inbox-send-back"]').attributes('disabled')).toBeUndefined()
    }
  })

  it('a draft override emits resolve(true, trimmed)', async () => {
    const wrapper = await mountOverride({ draft: '  advisory only, safe to merge  ' })
    await wrapper.get('[data-testid="inbox-override"]').trigger('click')
    expect(wrapper.emitted('resolve')).toEqual([[true, 'advisory only, safe to merge']])
  })

  it('send-back emits resolve(false, trimmed), also with an empty draft', async () => {
    const filled = await mountOverride({ draft: '  send back to staging  ' })
    await filled.get('[data-testid="inbox-send-back"]').trigger('click')
    expect(filled.emitted('resolve')).toEqual([[false, 'send back to staging']])
    const blank = await mountOverride({ draft: '' })
    await blank.get('[data-testid="inbox-send-back"]').trigger('click')
    expect(blank.emitted('resolve')).toEqual([[false, '']])
  })

  it('typing in the Justification field emits update:draft', async () => {
    const wrapper = await mountOverride()
    // The Justification field is required (contract §3.3 row 3), so Field
    // appends the marker to the label text; assert the substring.
    expect(
      wrapper.findAll('label').map((l) => l.text()).some((t) => t.includes('Justification')),
    ).toBe(true)
    await wrapper.get('[data-testid="field-control"]').setValue('justified')
    expect(wrapper.emitted('update:draft')).toEqual([['justified']])
  })

  it('busy disables both buttons and the field', async () => {
    const wrapper = await mountOverride({ busy: true, draft: 'ready' })
    for (const id of ['inbox-override', 'inbox-send-back']) {
      expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    expect(wrapper.get('[data-testid="field-control"]').attributes('disabled')).toBeDefined()
  })
})

const escalationEntryPath = './EscalationEntry.vue'
const mountEscalation = async (
  over: { item?: EscalationItem; busy?: boolean; draft?: string } = {},
) => {
  const { default: EscalationEntry } = await import(/* @vite-ignore */ escalationEntryPath)
  return mount(EscalationEntry, {
    props: {
      item: over.item ?? escalationItem(),
      busy: over.busy ?? false,
      draft: over.draft ?? '',
    },
  })
}

describe('EscalationEntry', () => {
  it('shows the analysis with the longtext class', async () => {
    const wrapper = await mountEscalation()
    const analysis = wrapper.get('[data-testid="inbox-analysis"]')
    expect(analysis.text()).toBe('The retry loop could not reproduce the failure locally.')
    expect(analysis.classes()).toContain('inbox-longtext')
  })

  it('an empty analysis renders no analysis block', async () => {
    const wrapper = await mountEscalation({ item: { ...escalationItem(), analysis: '' } })
    expect(wrapper.find('[data-testid="inbox-analysis"]').exists()).toBe(false)
  })

  it('retry and quarantine each send the trimmed draft, also with an empty draft', async () => {
    const filled = await mountEscalation({ draft: '  watch the rate limit  ' })
    await filled.get('[data-testid="inbox-retry"]').trigger('click')
    expect(filled.emitted('resolve')).toEqual([[true, 'watch the rate limit']])
    const blankRetry = await mountEscalation({ draft: '' })
    await blankRetry.get('[data-testid="inbox-retry"]').trigger('click')
    expect(blankRetry.emitted('resolve')).toEqual([[true, '']])
    const blankQuarantine = await mountEscalation({ draft: '' })
    await blankQuarantine.get('[data-testid="inbox-quarantine"]').trigger('click')
    expect(blankQuarantine.emitted('resolve')).toEqual([[false, '']])
  })

  it('typing in the Guidance field emits update:draft', async () => {
    const wrapper = await mountEscalation()
    expect(wrapper.findAll('label').map((l) => l.text())).toContain('Guidance')
    await wrapper.get('[data-testid="field-control"]').setValue('guided')
    expect(wrapper.emitted('update:draft')).toEqual([['guided']])
  })

  it('busy disables both buttons and the field', async () => {
    const wrapper = await mountEscalation({ busy: true, draft: 'ready' })
    for (const id of ['inbox-retry', 'inbox-quarantine']) {
      expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    }
    expect(wrapper.get('[data-testid="field-control"]').attributes('disabled')).toBeDefined()
  })
})

// --- 011 T015 (RED): the budget gate says what approve grants (FR-008) ------
// A gate item whose gate is 'budget' renders gate-budget-note: approving
// grants threshold + budget of the run row (read via the fleet store,
// dollars through money); with the run row unknown the amount is omitted;
// any other gate renders no note. The decide flow is untouched.

const budgetGateItem = (): GateItem => ({
  id: 'budget#1',
  runId: 'r1',
  round: 2,
  age: '1m',
  type: 'gate',
  gate: 'budget',
  title: 'Budget needs a decision',
  body: 'Run cost $40.2000 >= budget $40.00',
})

describe('GateEntry budget note (011 T015)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('a budget gate on a known run states the raised limit', async () => {
    useFleetStore().runs = [
      {
        id: 'r1',
        title: 'T',
        mode: 'brownfield',
        repo: 'r',
        activeStages: ['clarify'],
        stageMarks: null,
        status: 'blocked',
        blocker: '',
        cost: 40.2,
        budget: 20,
        roles: [],
        budgetThreshold: 40,
        budgetCounted: 40.2,
        budgetCrossings: 1,
        budgetNotice: null,
        age: '1m',
        decisions: [],
        projectKey: null,
      } as any,
    ]
    const wrapper = await mountGate({ item: budgetGateItem() })
    expect(wrapper.get('[data-testid="gate-budget-note"]').text()).toBe(
      'Approve raises the limit to $60.00 and the run continues. Any other decision ends the run.',
    )
  })

  it('an unknown run row omits the amount', async () => {
    const wrapper = await mountGate({ item: budgetGateItem() })
    const note = wrapper.get('[data-testid="gate-budget-note"]').text()
    expect(note).toBe(
      'Approve raises the limit and the run continues. Any other decision ends the run.',
    )
    expect(note).not.toContain('$')
  })

  it('a gate that is not budget renders no note', async () => {
    const wrapper = await mountGate()
    expect(wrapper.find('[data-testid="gate-budget-note"]').exists()).toBe(false)
  })
})
