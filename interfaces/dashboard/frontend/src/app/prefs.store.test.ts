import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    listInbox: vi.fn(async () => []),
    getInboxState: vi.fn(async () => ({ items: [], unreadable: [] })),
  },
  // board.api selects its transport through API_MODE at import time
  API_MODE: 'mock' as const,
}))

import App from './App.vue'
import { router } from './router'
import { usePrefsStore } from './prefs.store'

const flush = () => new Promise((r) => setTimeout(r, 0))

let getItemSpy: ReturnType<typeof vi.spyOn>
let setItemSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  setActivePinia(createPinia())
  getItemSpy = vi.spyOn(Storage.prototype, 'getItem')
  setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
})

afterEach(() => {
  // Do not leak data-theme into other test files' document.
  delete document.documentElement.dataset.theme
  vi.restoreAllMocks()
})

describe('prefs store (018 T006, S4 session-only)', () => {
  it('defaults to dark theme, all three toggles off and no run in context', () => {
    const prefs = usePrefsStore()
    expect(prefs.theme).toBe('dark')
    expect(prefs.payloadsEverywhere).toBe(false)
    expect(prefs.terminalsEverywhere).toBe(false)
    expect(prefs.grid).toBe(false)
    expect(prefs.runInContext).toBeNull()
  })

  it('App.vue reflects theme=light as data-theme and removes the attribute on dark', async () => {
    const prefs = usePrefsStore()
    prefs.theme = 'light'
    const w = mount(App, { global: { plugins: [router] } })
    await flush()
    expect(document.documentElement.dataset.theme).toBe('light')

    prefs.theme = 'dark'
    await flush()
    // Back to the default means the attribute goes away entirely, not 'dark'.
    expect(document.documentElement.dataset.theme).toBeUndefined()
    w.unmount()
  })

  it('never reads from or writes to localStorage', async () => {
    usePrefsStore()
    const prefs = usePrefsStore()
    prefs.theme = 'light'
    prefs.payloadsEverywhere = true
    const w = mount(App, { global: { plugins: [router] } })
    await flush()
    w.unmount()
    expect(getItemSpy).not.toHaveBeenCalled()
    expect(setItemSpy).not.toHaveBeenCalled()
  })
})

describe('prefs store (018 T006, chaos)', () => {
  it('the three toggles are independent state', () => {
    const prefs = usePrefsStore()
    prefs.payloadsEverywhere = true
    expect(prefs.terminalsEverywhere).toBe(false)
    expect(prefs.grid).toBe(false)
    expect(prefs.theme).toBe('dark')
    expect(prefs.runInContext).toBeNull()

    prefs.terminalsEverywhere = true
    expect(prefs.payloadsEverywhere).toBe(true)
    expect(prefs.grid).toBe(false)

    prefs.grid = true
    expect(prefs.payloadsEverywhere).toBe(true)
    expect(prefs.terminalsEverywhere).toBe(true)
  })

  it('App clears a stale data-theme left by a previous page and follows the store', async () => {
    // A previous page/test left the attribute set; mount must reflect the
    // store (dark -> attribute removed), not inherit the stale DOM state.
    document.documentElement.dataset.theme = 'light'
    const prefs = usePrefsStore()
    const w = mount(App, { global: { plugins: [router] } })
    await flush()
    expect(document.documentElement.dataset.theme).toBeUndefined()

    prefs.theme = 'light'
    await flush()
    expect(document.documentElement.dataset.theme).toBe('light')
    w.unmount()
  })

  it('a second App mount after dark does not keep a stale light attribute', async () => {
    const prefs = usePrefsStore()
    prefs.theme = 'light'
    const first = mount(App, { global: { plugins: [router] } })
    await flush()
    expect(document.documentElement.dataset.theme).toBe('light')
    first.unmount()

    prefs.theme = 'dark'
    const second = mount(App, { global: { plugins: [router] } })
    await flush()
    expect(document.documentElement.dataset.theme).toBeUndefined()
    second.unmount()
  })

  it('runInContext round-trips an id and back to null without coercion', () => {
    const prefs = usePrefsStore()
    prefs.runInContext = 'run-123'
    expect(prefs.runInContext).toBe('run-123')
    prefs.runInContext = null
    // null stays null — not coerced to undefined or the empty string.
    expect(prefs.runInContext).toBeNull()
    expect(prefs.runInContext).not.toBe(undefined)
    expect(prefs.runInContext).not.toBe('')
  })
})
