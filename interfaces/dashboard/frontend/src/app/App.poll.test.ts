// T5 (sbatch-2026-10-19): the fleet poll must survive a failed first read
// (task .workspace/tasks/2026-10-05-fleet-refresh-failure-stops-the-poll.md).
//
// App.vue's onMounted awaits Promise.all([catalog.load(), fleet.refresh(),
// inbox.refresh()]) BEFORE setInterval — and of the three only fleet.refresh
// can reject today (catalog.load funnels every failure into its error state;
// inbox.refresh caught its way to never-reject in 010 R-6). So one failed
// first fleet read rejects the await, the interval is never created, and the
// dashboard silently stops polling forever. The planned fix starts the poll
// unconditionally with fire-and-forget refreshes; fleet.refresh itself will
// never reject afterwards.
//
// Harness mirrors App.test.ts (vi.mock ../api/client, mount with the real
// router plugin). getCatalog is deliberately absent from the factory, same
// as the existing harness: catalog.load's sync-throw path lands in its
// error branch and never rejects, which is part of the contract tested here.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { api } from '../api/client'
import { useFleetStore } from '../shared/fleet.store'
import type { StartRunInput } from '../api/types'

vi.mock('../api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    listInbox: vi.fn(async () => []),
    getInboxState: vi.fn(async () => ({ items: [], unreadable: [] })),
    getFleetSummary: vi.fn(async () => ({ runs: [], unreadable: [] })),
    getShippedGraphs: vi.fn(async () => ({ graphs: [], checks: [], sections: [] })),
    startRun: vi.fn(),
  },
  // board.api selects its transport through API_MODE at import time
  API_MODE: 'mock' as const,
}))

const listRunsCalls = () => vi.mocked(api.listRuns).mock.calls.length

async function mountApp() {
  const wrapper = mount(App, { global: { plugins: [router] } })
  // Let the first reads settle (and, today, the Promise.all rejection land)
  // before any tick is advanced — plain microtask turns, not the fake-timer
  // async driver, so the settle itself cannot interact with timer faking.
  for (let i = 0; i < 8; i++) await Promise.resolve()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('App fleet poll (T5)', () => {
  it('starts polling even when the first fleet read fails', async () => {
    // RED on main: the awaited Promise.all rejects on the failed first
    // listRuns, setInterval never runs, and the count stays at the first
    // read. Post-fix the poll must be live regardless of first-read outcome.
    vi.useFakeTimers()
    vi.mocked(api.listRuns).mockImplementation(async () => {
      throw new Error('first read fails')
    })
    const w = await mountApp()
    try {
      const first = listRunsCalls()
      expect(first).toBeGreaterThanOrEqual(1)
      await vi.advanceTimersByTimeAsync(5000)
      expect(listRunsCalls()).toBeGreaterThan(first)
    } finally {
      w.unmount()
    }
  })

  it('keeps ticking across multiple consecutive failures', async () => {
    // Pin of the post-fix resilience (RED on main only through the same
    // root cause — the poll never starts): every 5000ms tick attempts a
    // refresh even when each read keeps failing; the poll's job is to
    // outlive an outage, not to stop at its first sight.
    vi.useFakeTimers()
    vi.mocked(api.listRuns).mockImplementation(async () => {
      throw new Error('still down')
    })
    const w = await mountApp()
    try {
      const before = listRunsCalls()
      await vi.advanceTimersByTimeAsync(5000)
      const afterOne = listRunsCalls()
      expect(afterOne).toBeGreaterThan(before)
      await vi.advanceTimersByTimeAsync(5000)
      expect(listRunsCalls()).toBeGreaterThan(afterOne)
    } finally {
      w.unmount()
    }
  })

  it('suppresses the tick while the document is hidden', async () => {
    // PIN (green on main; must survive the fix): a hidden tab does not
    // refresh. Uses a SUCCEEDING first read so the interval exists on main
    // too, then hides, ticks (no calls), re-shows, ticks (calls grow) — the
    // control half proves suppression is the visibility gate, not a dead
    // interval.
    vi.useFakeTimers()
    vi.mocked(api.listRuns).mockResolvedValue([])
    const w = await mountApp()
    try {
      const initial = listRunsCalls()
      expect(initial).toBeGreaterThanOrEqual(1)
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => 'hidden',
      })
      try {
        await vi.advanceTimersByTimeAsync(5000)
        expect(listRunsCalls()).toBe(initial)
      } finally {
        // drop the own-property shadow; the prototype getter (visible)
        // serves again
        delete (document as { visibilityState?: string }).visibilityState
      }
      await vi.advanceTimersByTimeAsync(5000)
      expect(listRunsCalls()).toBeGreaterThan(initial)
    } finally {
      w.unmount()
    }
  })

  it('still propagates a startRun failure to its caller', async () => {
    // PIN (green on main; must survive the fix): making fleet.refresh
    // never-reject is about the poll path only — a startRun API error must
    // keep reaching the caller (the start modal's error surface).
    const fleet = useFleetStore()
    vi.mocked(api.startRun).mockRejectedValueOnce(new Error('start refused'))
    await expect(fleet.startRun({} as StartRunInput)).rejects.toThrow('start refused')
  })
})
