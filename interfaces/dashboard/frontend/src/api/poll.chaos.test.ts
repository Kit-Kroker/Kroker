// Chaos and edge cases for the poll chain (E-76 Task 6). Companion to
// poll.test.ts, which pins the happy paths; this file pins the hostile ones:
// a fetchOnce that throws synchronously, repeated stop(), unhandled-rejection
// and timer-leak hazards, and zero/negative computed delays.
//
// Delay-0 self-rescheduling chains (zero baseMs, negative jittered delays)
// are terminated with a `stop` step on purpose: fake timers drain same-time
// timers greedily, so only a terminating chain keeps those tests bounded.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import process from 'node:process'
import { jittered, startPoll, type PollStep } from './poll'
import { HttpStatusError, isNotFound } from './errors'

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

const noJitter = { jitter: 0, random: () => 0.5 }
const flush = async () => { await vi.advanceTimersByTimeAsync(0) }

describe('jittered under extreme inputs', () => {
  it('jitter 0 pins the delay regardless of random', () => {
    expect(jittered(2000, 0, () => 0)).toBe(2000)
    expect(jittered(2000, 0, () => 1)).toBe(2000)
    expect(jittered(2000, 0, Math.random)).toBe(2000)
  })

  it('jitter 1 spreads across the full 0..2x range', () => {
    expect(jittered(2000, 1, () => 0)).toBe(0)
    expect(jittered(2000, 1, () => 1)).toBe(4000)
  })

  it('jitter beyond 1 computes negative delays (setTimeout clamps to 0)', () => {
    expect(jittered(2000, 5, () => 0)).toBe(-8000)
  })
})

describe('startPoll vs a hostile fetchOnce', () => {
  it('catches a synchronous throw and enters the same failure backoff', async () => {
    let fail = true
    const fetchOnce = vi.fn((): Promise<PollStep<number>> => {
      if (fail) throw new Error('sync boom')  // throws, never returns a promise
      return Promise.resolve({ kind: 'value', value: 1 })
    })
    const onFailures = vi.fn()
    startPoll(fetchOnce, vi.fn(), onFailures, noJitter)
    await flush()                                   // fail 1 -> wait 4s
    await vi.advanceTimersByTimeAsync(4000)         // fail 2 -> wait 8s
    expect(onFailures).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(8000)         // fail 3 -> report
    expect(onFailures).toHaveBeenLastCalledWith(3)
    fail = false
    await vi.advanceTimersByTimeAsync(16000)        // success -> reset
    expect(onFailures).toHaveBeenLastCalledWith(0)
    const calls = fetchOnce.mock.calls.length
    await vi.advanceTimersByTimeAsync(2000)         // back to the base interval
    expect(fetchOnce.mock.calls.length).toBe(calls + 1)
  })

  it('repeated stop() calls are harmless and leave no timers', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1 }))
    const onValue = vi.fn()
    const stop = startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    stop()
    stop()
    stop()
    await vi.advanceTimersByTimeAsync(100000)
    expect(fetchOnce).toHaveBeenCalledTimes(1)  // only the initial call
    expect(onValue).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('repeated stop() during a failure backoff clears the pending timer', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => { throw new Error('down') })
    const stop = startPoll(fetchOnce, vi.fn(), vi.fn(), noJitter)
    await flush()                               // fail 1, retry timer pending
    expect(vi.getTimerCount()).toBe(1)
    stop()
    stop()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(100000)
    expect(fetchOnce).toHaveBeenCalledTimes(1)
  })

  it('stop() leaves no unhandled rejection from an in-flight fetch', async () => {
    const rejections: unknown[] = []
    const onRejection = (reason: unknown) => { rejections.push(reason) }
    process.on('unhandledRejection', onRejection)
    try {
      let reject!: (e: Error) => void
      const fetchOnce = vi.fn(
        (_signal: AbortSignal) =>
          new Promise<PollStep<number>>((_, rej) => { reject = rej }),
      )
      const stop = startPoll(fetchOnce, vi.fn(), vi.fn(), noJitter)
      stop()
      stop()
      reject(new Error('aborted mid-flight'))
      await flush()
      expect(rejections).toEqual([])
    } finally {
      process.off('unhandledRejection', onRejection)
    }
  })

  it('survives stop() called from inside onValue', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => ({ kind: 'value', value: 1 }))
    const onValue = vi.fn()
    let stop!: () => void
    onValue.mockImplementation(() => { stop() })
    stop = startPoll(fetchOnce, onValue, vi.fn(), noJitter)
    await flush()
    expect(onValue).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(100000)
    expect(fetchOnce).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('zero and extreme intervals', () => {
  it('baseMs 0 drains a value chain immediately and still ends on stop', async () => {
    let calls = 0
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => {
      calls += 1
      return calls < 4 ? { kind: 'value', value: calls } : { kind: 'stop' }
    })
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), { ...noJitter, baseMs: 0 })
    await vi.advanceTimersByTimeAsync(10)
    expect(onValue).toHaveBeenCalledTimes(3)
    expect(fetchOnce).toHaveBeenCalledTimes(4)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('survives a jitter config whose computed delay is negative', async () => {
    // delay = 2000 * (1 - 5) = -8000 every cycle; setTimeout clamps it to 0.
    let calls = 0
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => {
      calls += 1
      return calls < 3 ? { kind: 'value', value: calls } : { kind: 'stop' }
    })
    const onValue = vi.fn()
    startPoll(fetchOnce, onValue, vi.fn(), { baseMs: 2000, jitter: 5, random: () => 0 })
    await vi.advanceTimersByTimeAsync(10)
    expect(onValue).toHaveBeenCalledTimes(2)
    expect(fetchOnce).toHaveBeenCalledTimes(3)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('a cap below the base clamps the first retry delay', async () => {
    const fetchOnce = vi.fn(async (): Promise<PollStep<number>> => { throw new Error('down') })
    startPoll(fetchOnce, vi.fn(), vi.fn(), { ...noJitter, baseMs: 2000, capMs: 500 })
    await flush()                                // fail 1: min(4000, 500) = 500
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchOnce).toHaveBeenCalledTimes(2)   // not 4000ms away
    await vi.advanceTimersByTimeAsync(500)
    expect(fetchOnce).toHaveBeenCalledTimes(3)
    expect(vi.getTimerCount()).toBe(1)           // chain still alive, on a 500ms rhythm
  })
})

describe('HttpStatusError and isNotFound', () => {
  it('carries the status and message, and names itself', () => {
    const e = new HttpStatusError(404, 'no such run')
    expect(e).toBeInstanceOf(Error)
    expect(e.status).toBe(404)
    expect(e.message).toBe('no such run')
    expect(e.name).toBe('HttpStatusError')
  })

  it('isNotFound is true only for a 404 HttpStatusError', () => {
    expect(isNotFound(new HttpStatusError(404, 'gone'))).toBe(true)
    expect(isNotFound(new HttpStatusError(500, 'boom'))).toBe(false)
    expect(isNotFound(new HttpStatusError(403, 'no'))).toBe(false)
    expect(isNotFound(new Error('404'))).toBe(false)  // message text is not a status
    expect(isNotFound(null)).toBe(false)
    expect(isNotFound(undefined)).toBe(false)
  })
})
