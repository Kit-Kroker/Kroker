// 010 T008 part B (RED): the view states of contracts/inbox-screen.md §3.1,
// written against the stub view -- the RED cause (the stub renders neither
// the state test ids nor entries). The store is seeded directly: the view
// must not refresh on mount (contract §3.4), so no api mock is needed.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'
import InboxView from './InboxView.vue'
import { useInboxStore } from '../../app/inbox.store'
import { entryKey } from '../../shared/entryKey'
import type { ClarifyItem, EscalationItem, GateItem, OverrideItem, UnreadableRun } from '../../api/types'

// Field names per data-model §1.1.
const clarify = (runId: string, id = 'q1'): ClarifyItem => ({
  id,
  runId,
  round: 1,
  age: '2h 00m',
  type: 'clarify',
  title: 'Clarification needed',
  body: 'The proposer needs one more answer.',
  suggestion: 'Use OIDC.',
})

const unreadableRun = (runId: string, error = 'boom'): UnreadableRun => ({ runId, error })

// Full OverrideItem and EscalationItem literals, field names per §1.1.
const override = (runId: string, id = 'merge#1'): OverrideItem => ({
  id,
  runId,
  round: 1,
  age: '2h 00m',
  type: 'override',
  gate: 'merge',
  verdict: '2 checks did not pass',
  title: 'Merge override requested',
  body: 'The merge gate blocked the branch.',
  checks: [
    { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
    { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 - target 0.80' },
  ],
})

const escalation = (runId: string, id = 'task:T07#1'): EscalationItem => ({
  id,
  runId,
  round: 1,
  age: '2h 00m',
  type: 'escalation',
  analysis: 'The task keeps failing the same assertion after four attempts.',
  title: 'Task escalated',
  body: 'A repair attempt needs guidance.',
})

// Full GateItem literal, field names per data-model §1.1.
const gate = (runId: string, id = 'architecture#1'): GateItem => ({
  id,
  runId,
  round: 1,
  age: '2h 00m',
  type: 'gate',
  gate: 'architecture',
  title: 'Architecture needs a decision',
  body: 'Review the architecture proposal.',
})

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }

const mountView = (): VueWrapper =>
  mount(InboxView, {
    global: { plugins: [getActivePinia() as never], stubs: { RouterLink: RouterLinkStub } },
  })

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
})

// Per-entry scoping: an entry is the article with its run id (contract §4).
const entryByRunId = (w: VueWrapper, runId: string) =>
  w.findAll('[data-testid="inbox-entry"]').find((e) => e.attributes('data-run-id') === runId)!

const fieldValue = (entry: ReturnType<VueWrapper['find']>): string =>
  (entry.find('[data-testid="field-control"]').element as HTMLTextAreaElement).value

describe('InboxView states', () => {
  it('not loaded, no error: only the loading state shows', () => {
    const inbox = useInboxStore()
    inbox.items = []
    inbox.loaded = false
    inbox.loadError = null
    inbox.unreadable = []
    const w = mountView()
    expect(w.find('[data-testid="inbox-loading"]').exists()).toBe(true)
    expect(w.find('[data-testid="inbox-loading"]').text()).toBe('loading…')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="inbox-load-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="inbox-entry"]').exists()).toBe(false)
  })

  it('not loaded with a load error: only the load-error state shows, no empty state', () => {
    const inbox = useInboxStore()
    inbox.items = []
    inbox.loaded = false
    inbox.loadError = 'boom'
    inbox.unreadable = []
    const w = mountView()
    expect(w.find('[data-testid="inbox-load-error"]').exists()).toBe(true)
    expect(w.find('[data-testid="inbox-load-error"]').text()).toBe('The inbox could not be loaded.')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="inbox-loading"]').exists()).toBe(false)
  })

  it('loaded with nothing waiting: the explicit empty state shows', () => {
    const inbox = useInboxStore()
    inbox.items = []
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const w = mountView()
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="inbox-empty"]').text()).toBe('Nothing is waiting.')
  })

  it('loaded with items: one entry per item in the given order and the count line', () => {
    const inbox = useInboxStore()
    inbox.items = [
      clarify('run-a'),
      clarify('run-b', 'q2'),
      clarify('run-c', 'q3'),
    ]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const w = mountView()
    const entries = w.findAll('[data-testid="inbox-entry"]')
    expect(entries).toHaveLength(3)
    expect(entries.map((e) => e.attributes('data-run-id'))).toEqual(['run-a', 'run-b', 'run-c'])
    expect(w.find('[data-testid="inbox-count-line"]').text()).toContain('3 waiting')
  })

  it('loaded with zero items and one unreadable run: the incomplete banner names the run and no empty state shows', () => {
    const inbox = useInboxStore()
    inbox.items = []
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = [unreadableRun('r9')]
    const w = mountView()
    const banner = w.find('[data-testid="inbox-incomplete"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain(
      'This list may be incomplete: the pending state of 1 run(s) could not be read.',
    )
    expect(banner.text()).toContain('r9')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
  })

  it('loaded with items and a load error: the could-not-refresh line shows and the list stays', () => {
    const inbox = useInboxStore()
    inbox.items = [clarify('run-a')]
    inbox.loaded = true
    inbox.loadError = 'boom'
    inbox.unreadable = []
    const w = mountView()
    const banner = w.find('[data-testid="inbox-incomplete"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain(
      'The inbox could not be refreshed; showing the last known list.',
    )
    expect(w.find('[data-testid="inbox-entry"]').exists()).toBe(true)
  })

  it('unreadable runs and a load error together: both banner lines, could-not-refresh first', () => {
    const inbox = useInboxStore()
    inbox.items = [clarify('run-a')]
    inbox.loaded = true
    inbox.loadError = 'boom'
    inbox.unreadable = [unreadableRun('r9')]
    const w = mountView()
    const banner = w.find('[data-testid="inbox-incomplete"]')
    expect(banner.exists()).toBe(true)
    const text = banner.text()
    expect(text).toContain('The inbox could not be refreshed; showing the last known list.')
    expect(text).toContain(
      'This list may be incomplete: the pending state of 1 run(s) could not be read.',
    )
    expect(text.indexOf('The inbox could not be refreshed')).toBeLessThan(
      text.indexOf('This list may be incomplete'),
    )
  })

  it('two runs sharing an id render two entries with different run ids and the same key', () => {
    const inbox = useInboxStore()
    inbox.items = [clarify('run-a', 'q1'), clarify('run-b', 'q1')]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const w = mountView()
    const entries = w.findAll('[data-testid="inbox-entry"]')
    expect(entries).toHaveLength(2)
    expect(entries[0].attributes('data-run-id')).toBe('run-a')
    expect(entries[1].attributes('data-run-id')).toBe('run-b')
    expect(entries[0].attributes('data-key')).toBe('q1')
    expect(entries[1].attributes('data-key')).toBe('q1')
  })
})

// 010 T011 part B (RED): the clarify wiring of contract §3.4. The store's
// actions are spied (call-through), the store seeded as above; the RED
// cause is the empty slot -- the view renders no kind component yet.
describe('InboxView clarify wiring', () => {
  it('(9) an accept click calls answerClarify with the item runId, id and the trimmed suggestion', async () => {
    const inbox = useInboxStore()
    const a = clarify('run-a')
    inbox.items = [a]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const spy = vi.spyOn(inbox, 'answerClarify').mockResolvedValue(undefined)
    const w = mountView()
    await entryByRunId(w, 'run-a').find('[data-testid="inbox-accept"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-a', 'q1', 'Use OIDC.')
  })

  it('(10) toggle-edit with an empty draft copies the suggestion; with a typed draft it leaves the draft', async () => {
    const inbox = useInboxStore()
    const a = clarify('run-a')
    const b = clarify('run-b', 'q1')
    inbox.items = [a, b]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    inbox.setDraft(entryKey(b), 'typed already')
    const setDraftSpy = vi.spyOn(inbox, 'setDraft')
    const w = mountView()
    await entryByRunId(w, 'run-a').find('[data-testid="inbox-edit"]').trigger('click')
    expect(inbox.drafts[entryKey(a)]).toBe('Use OIDC.')
    expect(inbox.editing[entryKey(a)]).toBe(true)
    await entryByRunId(w, 'run-b').find('[data-testid="inbox-edit"]').trigger('click')
    expect(inbox.drafts[entryKey(b)]).toBe('typed already')
    expect(inbox.editing[entryKey(b)]).toBe(true)
    // only the empty-draft entry got the suggestion copied in
    expect(setDraftSpy).toHaveBeenCalledTimes(1)
    expect(setDraftSpy).toHaveBeenCalledWith(entryKey(a), 'Use OIDC.')
  })

  it('(11) an entry in flight renders busy while the other stays enabled', () => {
    const inbox = useInboxStore()
    const a = clarify('run-a')
    const b = clarify('run-b', 'q1')
    inbox.items = [a, b]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    inbox.inFlight = new Set([entryKey(a)])
    const w = mountView()
    const busy = entryByRunId(w, 'run-a')
    const idle = entryByRunId(w, 'run-b')
    expect(busy.find('[data-testid="inbox-accept"]').attributes('disabled')).toBeDefined()
    expect(busy.find('[data-testid="inbox-edit"]').attributes('disabled')).toBeDefined()
    expect(idle.find('[data-testid="inbox-accept"]').attributes('disabled')).toBeUndefined()
    expect(idle.find('[data-testid="inbox-edit"]').attributes('disabled')).toBeUndefined()
  })

  it('(12) two runs sharing an id: fields stay separate and sending uses that item runId and its own text', async () => {
    const inbox = useInboxStore()
    const a = { ...clarify('run-a'), suggestion: '' } // no suggestion: field always shown
    const b = clarify('run-b', 'q1')
    inbox.items = [a, b]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    inbox.editing = { [entryKey(b)]: true }
    const spy = vi.spyOn(inbox, 'answerClarify').mockResolvedValue(undefined)
    const w = mountView()
    const entryA = entryByRunId(w, 'run-a')
    const entryB = entryByRunId(w, 'run-b')
    await entryA.find('[data-testid="field-control"]').setValue('text for a')
    // typing in A leaves B's field empty
    expect(fieldValue(entryB)).toBe('')
    await entryB.find('[data-testid="field-control"]').setValue('text for b')
    await entryB.find('[data-testid="inbox-send"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-b', 'q1', 'text for b')
    expect(inbox.drafts[entryKey(a)]).toBe('text for a')
  })

  it('(13) typed text survives two refreshes that replace items with fresh equal objects', async () => {
    const inbox = useInboxStore()
    const fresh = (): ClarifyItem => ({ ...clarify('run-a'), suggestion: '' })
    inbox.items = [fresh()]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const w = mountView()
    await w.find('[data-testid="field-control"]').setValue('persisted answer')
    inbox.items = [fresh()]
    inbox.items = [fresh()]
    await w.vm.$nextTick()
    expect(fieldValue(entryByRunId(w, 'run-a'))).toBe('persisted answer')
  })
})

// 010 T014 part B (RED): the gate wiring of contract §3.4 row 2. The RED
// cause is the missing gate branch -- the view renders no GateEntry, so no
// gate-decision controls exist. GateDecision keeps its comment internally
// (research R-7); the entry adapts its one-object payload to two arguments.
describe('InboxView gate wiring', () => {
  it('(14) approve and revise call decideGate with the runId, id, outcome and comment', async () => {
    const inbox = useInboxStore()
    const a = gate('run-a')
    inbox.items = [a]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const spy = vi.spyOn(inbox, 'decideGate').mockResolvedValue(undefined)
    const w = mountView()
    const entry = entryByRunId(w, 'run-a')
    await entry.find('[data-testid="gate-approve"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-a', 'architecture#1', 'approve', '')
    await entry.find('[data-testid="gate-comment"]').setValue('needs work  ')
    await entry.find('[data-testid="gate-revise"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenCalledWith('run-a', 'architecture#1', 'revise', 'needs work')
  })

  it('(15) two runs sharing a gate id: comments stay separate and survive two refreshes', async () => {
    const inbox = useInboxStore()
    inbox.items = [gate('run-a'), gate('run-b')]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const spy = vi.spyOn(inbox, 'decideGate').mockResolvedValue(undefined)
    const w = mountView()
    await entryByRunId(w, 'run-a').find('[data-testid="gate-comment"]').setValue('first comment')
    await entryByRunId(w, 'run-b').find('[data-testid="gate-comment"]').setValue('second comment')
    // SC-005: two applied refreshes with fresh equal objects must not
    // disturb either entry's in-progress comment.
    inbox.items = [gate('run-a'), gate('run-b')]
    inbox.items = [gate('run-a'), gate('run-b')]
    await w.vm.$nextTick()
    await entryByRunId(w, 'run-b').find('[data-testid="gate-revise"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-b', 'architecture#1', 'revise', 'second comment')
    // FR-012: the first entry's comment is untouched by the second's send.
    expect((entryByRunId(w, 'run-a').find('[data-testid="gate-comment"]').element as HTMLTextAreaElement).value).toBe('first comment')
  })
})

// 010 T017 part B (RED): the override and escalation wiring of contract
// §3.4 rows 3-4. The RED cause is the two missing v-if branches -- the view
// renders no OverrideEntry or EscalationEntry, so their controls do not
// exist. The store spies stand in for the actions; the view only routes.
describe('InboxView override and escalation wiring', () => {
  it('(16) override and send-back call overrideMerge with booleans and the justification', async () => {
    const inbox = useInboxStore()
    const a = override('run-a')
    inbox.items = [a]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const spy = vi.spyOn(inbox, 'overrideMerge').mockResolvedValue(undefined)
    const w = mountView()
    const entry = entryByRunId(w, 'run-a')
    await entry.find('[data-testid="field-control"]').setValue('because reasons')
    await entry.find('[data-testid="inbox-override"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-a', 'merge#1', true, 'because reasons')
    expect(spy.mock.calls[0]![2]).toBe(true)
    await entry.find('[data-testid="inbox-send-back"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenCalledWith('run-a', 'merge#1', false, 'because reasons')
    expect(spy.mock.calls[1]![2]).toBe(false)
  })

  it('(17) retry and quarantine call resolveEscalation with booleans and the guidance', async () => {
    const inbox = useInboxStore()
    const e = escalation('run-e')
    inbox.items = [e]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    const spy = vi.spyOn(inbox, 'resolveEscalation').mockResolvedValue(undefined)
    const w = mountView()
    const entry = entryByRunId(w, 'run-e')
    await entry.find('[data-testid="field-control"]').setValue('inject a clock')
    await entry.find('[data-testid="inbox-retry"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith('run-e', 'task:T07#1', true, 'inject a clock')
    expect(spy.mock.calls[0]![2]).toBe(true)
    await entry.find('[data-testid="inbox-quarantine"]').trigger('click')
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenCalledWith('run-e', 'task:T07#1', false, 'inject a clock')
    expect(spy.mock.calls[1]![2]).toBe(false)
  })

  it('(18) a notice in the store shows on its own entry only', () => {
    const inbox = useInboxStore()
    const a = override('run-a')
    const b = escalation('run-b')
    inbox.items = [a, b]
    inbox.loaded = true
    inbox.loadError = null
    inbox.unreadable = []
    inbox.notice = { [entryKey(a)]: 'failed: boom' }
    const w = mountView()
    const shown = entryByRunId(w, 'run-a').find('[data-testid="inbox-notice"]')
    expect(shown.exists()).toBe(true)
    expect(shown.text()).toBe('failed: boom')
    expect(entryByRunId(w, 'run-b').find('[data-testid="inbox-notice"]').exists()).toBe(false)
  })
})
