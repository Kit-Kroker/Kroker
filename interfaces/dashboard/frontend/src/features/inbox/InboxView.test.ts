// 010 T008 part B (RED): the view states of contracts/inbox-screen.md §3.1,
// written against the stub view -- the RED cause (the stub renders neither
// the state test ids nor entries). The store is seeded directly: the view
// must not refresh on mount (contract §3.4), so no api mock is needed.
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'
import InboxView from './InboxView.vue'
import { useInboxStore } from '../../app/inbox.store'
import type { ClarifyItem, UnreadableRun } from '../../api/types'

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

const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }

const mountView = (): VueWrapper =>
  mount(InboxView, {
    global: { plugins: [getActivePinia() as never], stubs: { RouterLink: RouterLinkStub } },
  })

beforeEach(() => {
  setActivePinia(createPinia())
})

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
