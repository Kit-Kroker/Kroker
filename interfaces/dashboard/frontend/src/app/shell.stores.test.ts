import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api/client', () => {
  const fakeRuns = [{ id: 'r1', status: 'blocked' }, { id: 'r2', status: 'running' }]
  const api = {
    listRuns: vi.fn(async () => fakeRuns),
    listInbox: vi.fn(async () => [{ id: 'q1', type: 'clarify' }]),
    startRun: vi.fn(async (input: { title: string }) => ({ id: 'feature-new', title: input.title })),
  }
  return { api }
})

import { useInboxStore } from './inbox.store'
import { useUiStore } from './ui.store'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('inbox store', () => {
  it('refresh loads items', async () => {
    const inbox = useInboxStore()
    await inbox.refresh()
    expect(inbox.items).toHaveLength(1)
  })
  it('setDraft and toggleEdit manage UI state', () => {
    const inbox = useInboxStore()
    inbox.setDraft('q1', 'hello')
    expect(inbox.drafts['q1']).toBe('hello')
    inbox.toggleEdit('q1')
    expect(inbox.editing['q1']).toBe(true)
  })
})

describe('ui store', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('toasts appear and auto-dismiss', () => {
    const ui = useUiStore()
    ui.toast('hi')
    expect(ui.toasts).toHaveLength(1)
    vi.advanceTimersByTime(4000)
    expect(ui.toasts).toHaveLength(0)
  })

  it('openStart/closeStart toggle the modal', () => {
    const ui = useUiStore()
    ui.openStart()
    expect(ui.startOpen).toBe(true)
    ui.closeStart()
    expect(ui.startOpen).toBe(false)
  })
})
