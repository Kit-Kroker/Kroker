import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { jittered, startPoll, type PollStep } from './poll'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

const noJitter = { jitter: 0, random: () => 0.5 }
const flush = async () => { await vi.advanceTimersByTimeAsync(0) }

describe('jittered', () => {
  it('spreads a delay by ±jitter', () => {
    expect(jittered(2000, 0.2, () => 0)).toBe(1600)
    expect(jittered(2000, 0.2, () => 1)).toBe(2400)
  })
})

describe('startPoll', () => {
  it('fetches immediately, then every base interval', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1 }))
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    await flush()
    expect(fetchOnce).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)
    expect(fetchOnce).toHaveBeenCalledTimes(2)
    expect(onValue).toHaveBeenCalledTimes(2)
  })

  it('never fetches or delivers after stop, even with a fetch in flight', async () => {
    let resolve!: (s: PollStep<number>) => void
    let seenSignal: AbortSignal | null = null
    const fetchOnce = vi.fn((signal: AbortSignal) => {
      seenSignal = signal
      return new Promise<PollStep<number>>((r) => { resolve = r })
    })
    const onValue = vi.fn()
    const stop = startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    stop()
    expect(seenSignal!.aborted).toBe(true)
    resolve({ kind: 'value', value: 1 })
    await vi.advanceTimersByTimeAsync(10000)
    expect(onValue).not.toHaveBeenCalled()
    expect(fetchOnce).toHaveBeenCalledTimes(1)
  })

  it('ends the chain on a final value and on stop', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1, final: true }))
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchOnce).toHaveBeenCalledTimes(1)
    expect(onValue).toHaveBeenCalledTimes(1)

    const stopper = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'stop' }))
    startPoll(stopper, onValue, vi.fn(), noJitter)
    await vi.advanceTimersByTimeAsync(10000)
    expect(stopper).toHaveBeenCalledTimes(1)
  })

  it('backs off on failure, reports after three, and resets on success', async () => {
    let fail = true
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => {
      if (fail) throw new Error('down')
      return { kind: 'value', value: 1 }
    })
    const onFailures = vi.fn()
    startPoll(fetchOnce, vi.fn(), onFailures, noJitter)
    await flush()                                   // fail 1 -> wait 4s
    await vi.advanceTimersByTimeAsync(4000)         // fail 2 -> wait 8s
    expect(onFailures).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(8000)         // fail 3 -> report, wait 16s
    expect(onFailures).toHaveBeenLastCalledWith(3)
    fail = false
    await vi.advanceTimersByTimeAsync(16000)        // success -> reset
    expect(onFailures).toHaveBeenLastCalledWith(0)
    const calls = fetchOnce.mock.calls.length
    await vi.advanceTimersByTimeAsync(2000)         // back to the base interval
    expect(fetchOnce.mock.calls.length).toBe(calls + 1)
  })

  it('caps the backoff', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => { throw new Error('down') })
    startPoll(fetchOnce, vi.fn(), vi.fn(), { ...noJitter, capMs: 5000 })
    await flush()
    await vi.advanceTimersByTimeAsync(4000)
    await vi.advanceTimersByTimeAsync(5000)
    const calls = fetchOnce.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchOnce.mock.calls.length).toBe(calls + 1)
  })
})
