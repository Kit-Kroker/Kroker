// 010 T006 (RED): the store rules of contracts/inbox-screen.md §2, written
// before the implementation (tests 1, 2, 4, 5, 11, 12, 13 here; the
// race/chaos half is the chaos seat's). Fakes the api client with
// manually controlled promises, the pattern of features/run/RunView.test.ts.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useInboxStore } from './inbox.store'
import { HttpStatusError } from '../api/errors'
import { entryKey } from '../shared/entryKey'
import type { ClarifyItem, InboxItem } from '../api/types'

const api = vi.hoisted(() => ({
  getInboxState: vi.fn(),
  answerClarify: vi.fn(),
  decideGate: vi.fn(),
  overrideMerge: vi.fn(),
  resolveEscalation: vi.fn(),
}))
vi.mock('../api/client', () => ({ api }))

type Snapshot = { items: InboxItem[]; unreadable: { runId: string; error: string }[] }

const deferred = <T,>() => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

// Full ClarifyItem literal, field names per data-model §1.1.
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

const emptySnapshot = (): Snapshot => ({ items: [], unreadable: [] })

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useInboxStore', () => {
  // --- contract §2.1: refresh

  it('refresh applies items and unreadable, sets loaded, and clears a previous loadError', async () => {
    const store = useInboxStore()
    ;(store as { loadError?: unknown }).loadError = 'previous failure'
    const d = deferred<Snapshot>()
    api.getInboxState.mockReturnValue(d.promise)
    const a = clarify('feature-add-sso')
    const p = store.refresh()
    d.resolve({ items: [a], unreadable: [{ runId: 'r9', error: 'boom' }] })
    await p
    expect(store.items).toEqual([a])
    expect(store.unreadable).toEqual([{ runId: 'r9', error: 'boom' }])
    expect(store.loaded).toBe(true)
    expect(store.loadError).toBeNull()
  })

  it('a rejected read sets loadError, leaves items, unreadable and loaded untouched, and refresh resolves', async () => {
    const store = useInboxStore()
    const a = clarify('feature-add-sso')
    api.getInboxState.mockResolvedValueOnce({ items: [a], unreadable: [] })
    await store.refresh()
    const d = deferred<Snapshot>()
    api.getInboxState.mockReturnValueOnce(d.promise)
    const p = store.refresh()
    d.reject(new HttpStatusError(500, 'boom'))
    await expect(p).resolves.toBeUndefined()
    expect(store.loadError).toContain('boom')
    expect(store.items).toEqual([a])
    expect(store.unreadable).toEqual([])
    expect(store.loaded).toBe(true)
  })

  // --- T006 chaos half (contract §2.3): races, stale reads, failures

  it('two overlapping refreshes landing in reverse order keep the newer result', async () => {
    const store = useInboxStore()
    const d1 = deferred<Snapshot>()
    const d2 = deferred<Snapshot>()
    api.getInboxState.mockReturnValueOnce(d1.promise).mockReturnValueOnce(d2.promise)
    const list1 = [clarify('feature-add-sso')]
    const list2 = [clarify('feature-usage-metering')]
    const p1 = store.refresh()
    const p2 = store.refresh()
    d2.resolve({ items: list2, unreadable: [] }) // the newer read lands first
    d1.resolve({ items: list1, unreadable: [] })
    await Promise.all([p1, p2])
    expect(store.items).toEqual(list2)
  })

  it('a second call for an entry already in flight sends nothing and resolves', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    api.getInboxState.mockResolvedValue(emptySnapshot())
    const dw = deferred<void>()
    api.answerClarify.mockReturnValueOnce(dw.promise)
    const first = store.answerClarify(item.runId, item.id, 'first')
    expect(store.inFlight.has(k)).toBe(true)
    await expect(store.answerClarify(item.runId, item.id, 'second')).resolves.toBeUndefined()
    expect(api.answerClarify).toHaveBeenCalledTimes(1)
    dw.resolve(undefined)
    await first
    expect(store.inFlight.has(k)).toBe(false)
  })

  it('a stale read that started before the write finished cannot free the settled entry', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    const d1 = deferred<Snapshot>()
    const d2 = deferred<Snapshot>()
    api.getInboxState.mockReturnValueOnce(d1.promise).mockReturnValueOnce(d2.promise)
    const stale = store.refresh() // starts before the write
    const dw = deferred<void>()
    api.answerClarify.mockReturnValueOnce(dw.promise)
    const write = store.answerClarify(item.runId, item.id, 'ans')
    expect(store.inFlight.has(k)).toBe(true)
    dw.resolve(undefined) // the write settles; the action starts its own refresh (d2)
    d1.resolve(emptySnapshot()) // the stale read lands after, listing no such item
    await stale
    expect(api.getInboxState).toHaveBeenCalledTimes(2) // the write's refresh is in flight
    expect(store.inFlight.has(k)).toBe(true) // the stale read must not free it
    d2.resolve(emptySnapshot())
    await write
    expect(store.inFlight.has(k)).toBe(false) // released by the refresh the action started
  })

  it('a 404 shows the already-decided notice and holds the entry until the later refresh', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    api.getInboxState.mockResolvedValueOnce({ items: [item], unreadable: [] })
    await store.refresh()
    const dFollow = deferred<Snapshot>()
    api.getInboxState.mockReturnValueOnce(dFollow.promise)
    api.answerClarify.mockRejectedValueOnce(new HttpStatusError(404, 'nope'))
    const action = store.answerClarify(item.runId, item.id, 'ans')
    await flushPromises()
    expect(store.notice[k]).toBe('already decided elsewhere')
    expect(store.inFlight.has(k)).toBe(true) // held while the follow-up refresh is pending
    dFollow.resolve({ items: [item], unreadable: [] })
    await action
    expect(store.inFlight.has(k)).toBe(false) // released by the later-started refresh
    expect(store.notice[k]).toBe('already decided elsewhere') // still listed: the notice stays
  })

  it('a non-404 failure frees the entry at once, keeps the draft, and never starts a refresh', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    api.getInboxState.mockResolvedValueOnce({ items: [item], unreadable: [] })
    await store.refresh()
    store.setDraft(k, 'keep me')
    api.answerClarify.mockRejectedValueOnce(new HttpStatusError(500, 'boom'))
    await expect(store.answerClarify(item.runId, item.id, 'ans')).resolves.toBeUndefined()
    expect(store.notice[k]).toMatch(/^failed: /)
    expect(store.inFlight.has(k)).toBe(false)
    expect(store.drafts[k]).toBe('keep me')
    expect(api.getInboxState).toHaveBeenCalledTimes(1) // no refresh followed the failure
  })

  it('a failing refresh that started before the write settled leaves the settled entry in flight', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    const dC = deferred<Snapshot>()
    const dFollow = deferred<Snapshot>()
    api.getInboxState
      .mockResolvedValueOnce({ items: [item], unreadable: [] })
      .mockReturnValueOnce(dC.promise)
      .mockReturnValueOnce(dFollow.promise)
    await store.refresh()
    const overlapping = store.refresh() // started before the write settles
    const dw = deferred<void>()
    api.answerClarify.mockReturnValueOnce(dw.promise)
    const write = store.answerClarify(item.runId, item.id, 'ans')
    expect(store.inFlight.has(k)).toBe(true)
    dw.resolve(undefined) // the write settles; the action starts its own refresh (dFollow)
    await flushPromises()
    expect(api.getInboxState).toHaveBeenCalledTimes(3)
    dC.reject(new HttpStatusError(500, 'boom'))
    await expect(overlapping).resolves.toBeUndefined()
    expect(store.inFlight.has(k)).toBe(true) // a failed read changes only loadError
    dFollow.resolve({ items: [item], unreadable: [] })
    await write
    expect(store.inFlight.has(k)).toBe(false) // released by the follow-up refresh
  })

  it('loading is true while a refresh is in progress and false only after both overlapping refreshes finish', async () => {
    const store = useInboxStore()
    const d1 = deferred<Snapshot>()
    const d2 = deferred<Snapshot>()
    api.getInboxState.mockReturnValueOnce(d1.promise).mockReturnValueOnce(d2.promise)
    const p1 = store.refresh()
    expect(store.loading).toBe(true)
    const p2 = store.refresh()
    expect(store.loading).toBe(true)
    d1.resolve(emptySnapshot())
    d2.resolve(emptySnapshot())
    await Promise.all([p1, p2])
    expect(store.loading).toBe(false)
  })

  // --- contract §2.2: the four actions

  it('each action calls the same-named client method with exactly the arguments given', async () => {
    const store = useInboxStore()
    api.getInboxState.mockResolvedValue(emptySnapshot())
    api.answerClarify.mockResolvedValue(undefined)
    api.decideGate.mockResolvedValue(undefined)
    api.overrideMerge.mockResolvedValue(undefined)
    api.resolveEscalation.mockResolvedValue(undefined)

    await store.answerClarify('r1', 'q1', 'text')
    expect(api.answerClarify).toHaveBeenCalledWith('r1', 'q1', 'text')

    await store.decideGate('r1', 'g1', 'approve', 'ok')
    expect(api.decideGate).toHaveBeenCalledWith('r1', 'g1', 'approve', 'ok')

    await store.overrideMerge('r1', 'm1', true, 'because')
    expect(api.overrideMerge).toHaveBeenCalledWith('r1', 'm1', true, 'because')
    const overrideArgs = api.overrideMerge.mock.calls[0] as unknown[]
    expect(overrideArgs[2]).toBe(true)

    await store.resolveEscalation('r1', 'e1', false, '')
    expect(api.resolveEscalation).toHaveBeenCalledWith('r1', 'e1', false, '')
    const escalationArgs = api.resolveEscalation.mock.calls[0] as unknown[]
    expect(escalationArgs[2]).toBe(false)
  })

  // --- contract §2.3: release, cleanup, namespacing

  it('after a write whose applied refresh still lists the entry, the entry is released, usable, with its draft', async () => {
    const store = useInboxStore()
    const item = clarify('feature-add-sso')
    const k = entryKey(item)
    api.getInboxState.mockResolvedValue({ items: [item], unreadable: [] })
    await store.refresh()
    store.setDraft(k, 'keep me')
    api.answerClarify.mockResolvedValue(undefined)
    await store.answerClarify(item.runId, item.id, 'sent')
    expect(api.answerClarify).toHaveBeenCalledWith(item.runId, item.id, 'sent')
    expect(store.inFlight.has(k)).toBe(false)
    expect(store.drafts[k]).toBe('keep me')
    // usable: a second call is not swallowed by the in-flight guard
    await store.answerClarify(item.runId, item.id, 'again')
    expect(api.answerClarify).toHaveBeenCalledTimes(2)
  })

  it('an applied refresh drops drafts, editing and notice for gone keys and keeps listed ones', async () => {
    const store = useInboxStore()
    const listed = clarify('feature-add-sso')
    const gone = clarify('feature-usage-metering')
    const kListed = entryKey(listed)
    const kGone = entryKey(gone)
    store.setDraft(kListed, 'a')
    store.setDraft(kGone, 'g')
    store.toggleEdit(kListed)
    store.toggleEdit(kGone)
    ;(store as { notice?: Record<string, string> }).notice = {
      [kListed]: 'failed: x',
      [kGone]: 'failed: y',
    }
    api.getInboxState.mockResolvedValue({ items: [listed], unreadable: [] })
    await store.refresh()
    expect(store.drafts[kListed]).toBe('a')
    expect(store.drafts[kGone]).toBeUndefined()
    expect(store.editing[kListed]).toBeTruthy()
    expect(store.editing[kGone]).toBeFalsy()
    expect(store.notice[kListed]).toBe('failed: x')
    expect(store.notice[kGone]).toBeUndefined()
  })

  it('two runs sharing an id keep separate drafts and separate in-flight keys', async () => {
    const store = useInboxStore()
    const a = clarify('feature-add-sso', 'q1')
    const b = clarify('feature-usage-metering', 'q1')
    const kA = entryKey(a)
    const kB = entryKey(b)
    store.setDraft(kA, 'x')
    expect(store.drafts[kB]).toBeUndefined()
    api.getInboxState.mockResolvedValue({ items: [a, b], unreadable: [] })
    api.answerClarify.mockResolvedValue(undefined)
    const p = store.answerClarify(a.runId, a.id, 'ans')
    expect(store.inFlight.has(kA)).toBe(true)
    expect(store.inFlight.has(kB)).toBe(false)
    await p
  })

  // --- PIN: the pre-existing signatures (a red PIN is a stop-guard, SG-4)

  it('setDraft and toggleEdit keep their existing signatures (PIN)', () => {
    const store = useInboxStore()
    store.setDraft('q1', 'hello')
    expect(store.drafts['q1']).toBe('hello')
    store.toggleEdit('q1')
    expect(store.editing['q1']).toBe(true)
  })
})
