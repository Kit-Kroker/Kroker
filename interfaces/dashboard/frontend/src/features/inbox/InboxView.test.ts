// v5 inbox (018 T040 RED): a row list (one row per item, keyed by entryKey)
// plus a detail pane rendering the item's DecisionCard, selection mirrored
// in ?item=. The load states, the incomplete banner and the store rules keep
// their contracts (ported from the 010 tests). RED: the current view has no
// rows or card pane, and the empty-state text differs.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import InboxView from './InboxView.vue'
import { useInboxStore } from '../../app/inbox.store'
import { entryKey } from '../../shared/entryKey'
import type { ClarifyItem, EscalationItem, GateItem, OverrideItem, UnreadableRun } from '../../api/types'

const clarify = (runId: string, id = 'q1'): ClarifyItem => ({
  id, runId, round: 1, age: '2h 00m', type: 'clarify',
  title: 'Clarification needed', body: 'The proposer needs one more answer.', suggestion: 'Use OIDC.',
})

const gate = (runId: string, id = 'architecture#1'): GateItem => ({
  id, runId, round: 1, age: '3h 15m', type: 'gate', gate: 'architecture',
  title: 'Architecture needs a decision', body: 'Review the architecture proposal.',
})

const override = (runId: string, id = 'merge#1'): OverrideItem => ({
  id, runId, round: 1, age: '45m', type: 'override', gate: 'merge',
  verdict: '2 checks did not pass', title: 'Merge override requested',
  body: 'The merge gate blocked the branch.',
  checks: [{ name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' }],
})

const escalation = (runId: string, id = 'task:T07#1'): EscalationItem => ({
  id, runId, round: 1, age: '6h 30m', type: 'escalation',
  analysis: 'Keeps failing the same assertion.', title: 'Task escalated',
  body: 'A repair attempt needs guidance.',
})

const unreadableRun = (runId: string, error = 'boom'): UnreadableRun => ({ runId, error })

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }

const makeRouter = async (initial: string): Promise<Router> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      {
        path: '/inbox',
        component: InboxView,
        props: (r) => ({ ...(typeof r.query.item === 'string' ? { item: r.query.item } : {}) }),
      },
    ],
  })
  await router.push(initial)
  await router.isReady()
  return router
}

const mountView = async (initial = '/inbox') => {
  const router = await makeRouter(initial)
  const Host = { components: { RouterView }, template: '<RouterView />' }
  const w = mount(Host, { global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } } })
  await flushPromises()
  return { w, router }
}

const seed = (items: Parameters<typeof entryKey>[0][] | [], extra: { unreadable?: UnreadableRun[]; loadError?: string | null } = {}) => {
  const inbox = useInboxStore()
  inbox.items = items as never
  inbox.loaded = true
  inbox.loadError = extra.loadError ?? null
  inbox.unreadable = extra.unreadable ?? []
  return inbox
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
})

const rowByKey = (w: Awaited<ReturnType<typeof mountView>>['w'], key: string) =>
  w.findAll('[data-testid="inbox-row"]').find((r) => r.attributes('data-key') === key)!

describe('InboxView list (v5, 018 T040 RED)', () => {
  it('renders one row per item in store order with kind label, age, title and run id', async () => {
    const items = [clarify('run-a'), gate('run-b'), override('run-c'), escalation('run-d')]
    seed(items)
    const { w } = await mountView()
    const rows = w.findAll('[data-testid="inbox-row"]')
    expect(rows).toHaveLength(4)
    expect(rows.map((r) => r.attributes('data-key'))).toEqual(items.map((i) => entryKey(i)))
    rows.forEach((row, i) => {
      expect(row.text()).toContain(items[i].type)
      expect(row.text()).toContain(items[i].age)
      expect(row.text()).toContain(items[i].title)
      expect(row.text()).toContain(items[i].runId)
    })
  })

  it('no selection renders no card pane; clicking a row shows that item card; another click swaps it', async () => {
    const items = [clarify('run-a'), gate('run-b')]
    seed(items)
    const { w } = await mountView()
    expect(w.find('[data-testid="inbox-card"]').exists()).toBe(false)

    await rowByKey(w, entryKey(items[1])).trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="inbox-card"]').exists()).toBe(true)
    expect(w.find('[data-testid="inbox-card"]').text()).toContain('Architecture needs a decision')

    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="inbox-card"]').text()).toContain('Clarification needed')
  })

  it('?item= opens with that card shown; clicking a row sets the query; clicking it again clears it', async () => {
    const items = [clarify('run-a'), gate('run-b')]
    seed(items)
    const deep = encodeURIComponent(entryKey(items[1]))
    const { w, router } = await mountView(`/inbox?item=${deep}`)
    expect(w.find('[data-testid="inbox-card"]').text()).toContain('Architecture needs a decision')

    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.item).toBe(entryKey(items[0]))

    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.item).toBeUndefined()
    expect(w.find('[data-testid="inbox-card"]').exists()).toBe(false)
  })
})

describe('InboxView states (rules ported from 010)', () => {
  it('not loaded, no error: only the loading state shows', async () => {
    const inbox = useInboxStore()
    inbox.items = []
    inbox.loaded = false
    inbox.loadError = null
    inbox.unreadable = []
    const { w } = await mountView()
    expect(w.find('[data-testid="inbox-loading"]').text()).toBe('loading…')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="inbox-load-error"]').exists()).toBe(false)
  })

  it('not loaded with a load error: only the load-error state shows', async () => {
    useInboxStore().items = []
    useInboxStore().loaded = false
    useInboxStore().loadError = 'boom'
    useInboxStore().unreadable = []
    const { w } = await mountView()
    expect(w.find('[data-testid="inbox-load-error"]').text()).toBe('The inbox could not be loaded.')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
    expect(w.find('[data-testid="inbox-loading"]').exists()).toBe(false)
  })

  it('loaded with nothing waiting: the explicit empty state shows', async () => {
    seed([])
    const { w } = await mountView()
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="inbox-empty"]').text()).toBe('Nothing waiting on you')
  })

  it('loaded with zero items and one unreadable run: the incomplete banner names the run', async () => {
    seed([], { unreadable: [unreadableRun('r9')] })
    const { w } = await mountView()
    const banner = w.find('[data-testid="inbox-incomplete"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain(
      'This list may be incomplete: the pending state of 1 run(s) could not be read.',
    )
    expect(banner.text()).toContain('r9')
    expect(w.find('[data-testid="inbox-empty"]').exists()).toBe(false)
  })

  it('items and a load error together: could-not-refresh line first, list stays', async () => {
    seed([clarify('run-a')], { loadError: 'boom' })
    const { w } = await mountView()
    const text = w.find('[data-testid="inbox-incomplete"]').text()
    expect(text).toContain('The inbox could not be refreshed; showing the last known list.')
    expect(text).toContain('This list may be incomplete')
    expect(text.indexOf('The inbox could not be refreshed')).toBeLessThan(text.indexOf('This list may be incomplete'))
    expect(w.findAll('[data-testid="inbox-row"]')).toHaveLength(1)
  })
})

describe('InboxView deciding through the card (v5, 018 T040 RED)', () => {
  it('the card approve action calls decideGate with runId, id, approve and empty text', async () => {
    const items = [gate('run-b')]
    const inbox = seed(items)
    const spy = vi.spyOn(inbox, 'decideGate').mockResolvedValue(undefined)
    const { w } = await mountView()
    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    const approve = w
      .findAll('[data-testid="card-action"]')
      .find((b) => b.text() === 'Approve')!
    await approve.trigger('click')
    await flushPromises()
    expect(spy).toHaveBeenCalledWith('run-b', 'architecture#1', 'approve', '')
  })

  it('an entry in flight has every card action disabled', async () => {
    const items = [gate('run-b')]
    const inbox = seed(items)
    inbox.inFlight = new Set([entryKey(items[0])])
    const { w } = await mountView()
    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    for (const b of w.findAll('[data-testid="card-action"]')) {
      expect((b.element as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('a store notice shows in the card pane; a failed send leaves a failed notice; resolving empties the view', async () => {
    const items = [gate('run-b')]
    const inbox = seed(items)
    inbox.notice = { [entryKey(items[0])]: 'already decided elsewhere' }
    const { w } = await mountView()
    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="inbox-notice"]').text()).toBe('already decided elsewhere')

    // A failed send leaves the failure notice on the entry.
    vi.spyOn(inbox, 'decideGate').mockRejectedValue(new Error('boom'))
    inbox.notice = {}
    const { w: w2 } = await mountView()
    await rowByKey(w2, entryKey(items[0])).trigger('click')
    await w2.findAll('[data-testid="card-action"]')[0].trigger('click')
    await flushPromises()
    expect(w2.find('[data-testid="inbox-notice"]').text()).toContain('failed')

    // The empty-after-resolve state: the entry leaves, the empty state shows.
    vi.spyOn(inbox, 'decideGate').mockImplementation(async () => {
      inbox.items = []
    })
    const { w: w3 } = await mountView()
    await rowByKey(w3, entryKey(items[0])).trigger('click')
    await w3.findAll('[data-testid="card-action"]')[0].trigger('click')
    await flushPromises()
    expect(w3.find('[data-testid="inbox-empty"]').text()).toBe('Nothing waiting on you')
    expect(w3.find('[data-testid="inbox-card"]').exists()).toBe(false)
  })

  it('the clarify card seeds the empty draft with the suggestion and never overwrites a typed one (R-12)', async () => {
    const items = [clarify('run-a'), { ...clarify('run-b', 'q2'), suggestion: 'Fresh idea.' }]
    const inbox = seed(items)
    inbox.setDraft(entryKey(items[1]), 'typed already')
    const { w } = await mountView()
    await rowByKey(w, entryKey(items[0])).trigger('click')
    await flushPromises()
    expect((w.find('[data-testid="card-text"]').element as HTMLTextAreaElement).value).toBe('Use OIDC.')

    await rowByKey(w, entryKey(items[1])).trigger('click')
    await flushPromises()
    expect((w.find('[data-testid="card-text"]').element as HTMLTextAreaElement).value).toBe('typed already')
    expect(inbox.drafts[entryKey(items[1])]).toBe('typed already')
  })
})
