// A cancel-safe poll chain (E-76 spec §7.3). A recursive setTimeout, never
// setInterval: nothing fires after stop(), including a fetch in flight at
// stop (aborted), and a slow response can never stack a second request.

export type PollStep<T> =
  | { kind: 'value'; value: T; final?: boolean }
  | { kind: 'stop' }

export interface PollOptions {
  baseMs?: number
  capMs?: number
  jitter?: number
  random?: () => number
  failuresBeforeReport?: number
}

export function jittered(ms: number, jitter: number, random: () => number): number {
  return Math.round(ms * (1 - jitter + random() * 2 * jitter))
}

export function startPoll<T>(
  fetchOnce: (signal: AbortSignal) => Promise<PollStep<T>>,
  onValue: (value: T) => void,
  onFailures: (consecutive: number) => void,
  opts: PollOptions = {},
): () => void {
  const baseMs = opts.baseMs ?? 2000
  const capMs = opts.capMs ?? 30000
  const jitter = opts.jitter ?? 0.2
  const random = opts.random ?? Math.random
  const report = opts.failuresBeforeReport ?? 3

  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let controller: AbortController | null = null
  let failures = 0
  let delay = baseMs

  const schedule = (ms: number) => {
    if (cancelled) return
    timer = setTimeout(tick, jittered(ms, jitter, random))
  }

  async function tick() {
    if (cancelled) return
    controller = new AbortController()
    let step: PollStep<T>
    try {
      step = await fetchOnce(controller.signal)
    } catch {
      if (cancelled) return
      failures += 1
      delay = Math.min(delay * 2, capMs)
      if (failures >= report) onFailures(failures)
      schedule(delay)
      return
    }
    if (cancelled) return
    if (failures > 0) onFailures(0)
    failures = 0
    delay = baseMs
    if (step.kind === 'stop') return
    onValue(step.value)
    if (step.final) return
    schedule(baseMs)
  }

  void tick()

  return () => {
    cancelled = true
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    controller?.abort()
  }
}
