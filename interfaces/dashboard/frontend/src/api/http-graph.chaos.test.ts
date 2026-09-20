// Chaos and edge cases for the http graph provider and the mock graph
// (E-76 Task 7). Companion to http-graph.test.ts and mock/graph.test.ts,
// which pin the recorded happy paths; this file pins the hostile ones:
// server failures, non-JSON bodies, capability gating edges, poll-chain
// resilience under errors, and hostile inputs to the mock.

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { createHttpGraphApi } from './http-graph'
import { CapabilityUnavailable, type CatalogWire, type Capability, type GraphWire } from './graph-types'
import { HttpStatusError } from './errors'
import { createMockGraph } from './mock/graph'
import type { GateOutcome } from './types'
import catalogJson from './__fixtures__/graph/catalog.json'

type HttpGraphApi = ReturnType<typeof createHttpGraphApi>

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })
const graph: GraphWire = { schema_version: 1, nodes: [], edges: [] }
const ALL_CAPS: Record<Capability, boolean> = { validate: true, save: true, load: true, run_graph: true }
const NO_CAPS: Record<Capability, boolean> = { validate: false, save: false, load: false, run_graph: false }
const asCatalog = (capabilities: Record<Capability, boolean>) =>
  ({ ...(catalogJson as unknown as CatalogWire), capabilities })
const flushMicro = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

const expectHttpStatus = async (p: Promise<unknown>, status: number) => {
  const err = await p.then(
    () => { throw new Error('expected a rejection, got a resolution') },
    (e) => e,
  )
  expect(err).toBeInstanceOf(HttpStatusError)
  expect((err as HttpStatusError).status).toBe(status)
}

// [method, call] rows for the six graph routes. save posts to /graphs (the
// collection), load GETs /graphs/<sha> -- the exact paths pin the contract.
const ROUTES: [string, (api: HttpGraphApi) => Promise<unknown>][] = [
  ['getCatalog', (api) => api.getCatalog()],
  ['parseGraph', (api) => api.parseGraph({ yaml: 'schema_version: 1\n' })],
  ['serializeGraph', (api) => api.serializeGraph(graph)],
  ['validateGraph', (api) => api.validateGraph(graph)],
  ['saveGraph', (api) => api.saveGraph(graph)],
  ['loadGraph', (api) => api.loadGraph('deadbeef')],
]

// E-75 §7.4: outcome replaces terminal; a running outcome is the only
// non-final body.
const stateBody = (state: 'running' | 'completed') => ({
  kind: 'state', graph_sha: 's', nodes: {}, edges: [], current_nodes: [], pending: [],
  outcome: { state, reason: null, result: null },
})

describe('http graph provider under hostile responses', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  const serveCatalogAndFail = (name: string, status: number) => {
    fetchMock.mockImplementation(async (path: string) =>
      name !== 'getCatalog' && path === '/api/graphs/catalog'
        ? ok(asCatalog(ALL_CAPS))
        : new Response('boom', { status }),
    )
  }

  it.each(ROUTES)('%s turns a 500 into an HttpStatusError carrying 500', async (name, act) => {
    serveCatalogAndFail(name, 500)
    await expectHttpStatus(act(createHttpGraphApi()), 500)
  })

  it.each(ROUTES)('%s turns a 503 into an HttpStatusError carrying 503', async (name, act) => {
    serveCatalogAndFail(name, 503)
    await expectHttpStatus(act(createHttpGraphApi()), 503)
  })

  it('a 200 with a non-JSON body rejects instead of resolving garbage', async () => {
    fetchMock.mockImplementation(async () => new Response('<html>gateway noise</html>', { status: 200 }))
    await expect(createHttpGraphApi().getCatalog()).rejects.toThrow()
  })

  it('a malformed catalog response is not cached -- the retry refetches', async () => {
    fetchMock.mockImplementation(async () => new Response('not json', { status: 200 }))
    const api = createHttpGraphApi()
    await expect(api.getCatalog()).rejects.toThrow()
    await expect(api.getCatalog()).rejects.toThrow()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('a malformed parse response rejects instead of resolving garbage', async () => {
    fetchMock.mockImplementation(async (path: string) =>
      path === '/api/graphs/catalog' ? ok(asCatalog(NO_CAPS)) : new Response('[', { status: 200 }),
    )
    await expect(createHttpGraphApi().parseGraph({ yaml: 'x' })).rejects.toThrow()
  })
})

describe('capability gating edge cases', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('parseGraph and serializeGraph work while every capability is false', async () => {
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(asCatalog(NO_CAPS))  // the real recording
      if (path === '/api/graphs/parse') return ok({ ok: true, graph, sha: 'x' })
      return ok({ ok: true, yaml: 'schema_version: 1\n' })
    })
    const api = createHttpGraphApi()
    await expect(api.parseGraph({ yaml: 'x' })).resolves.toEqual({ ok: true, graph, sha: 'x' })
    await expect(api.serializeGraph(graph)).resolves.toEqual({ ok: true, yaml: 'schema_version: 1\n' })
  })

  it.each([
    ['validateGraph', 'validate', (api: HttpGraphApi) => api.validateGraph(graph)],
    ['saveGraph', 'save', (api: HttpGraphApi) => api.saveGraph(graph)],
    ['loadGraph', 'load', (api: HttpGraphApi) => api.loadGraph('deadbeef')],
    ['getRunGraph', 'run_graph', (api: HttpGraphApi) => api.getRunGraph('r1')],
  ])('%s refuses with CapabilityUnavailable without calling its route', async (_name, cap, act) => {
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(asCatalog(NO_CAPS))
      throw new Error(`gated route ${path} must never be called`)
    })
    await expect(act(createHttpGraphApi())).rejects.toEqual(new CapabilityUnavailable(cap))
    expect(fetchMock.mock.calls.map(([p]) => p)).toEqual(['/api/graphs/catalog'])
  })

  it('the refusal names the missing capability', async () => {
    fetchMock.mockImplementation(async (path: string) =>
      path === '/api/graphs/catalog' ? ok(asCatalog(NO_CAPS)) : ok({}),
    )
    const err = await createHttpGraphApi().validateGraph(graph).then(
      () => { throw new Error('expected a rejection') },
      (e) => e,
    )
    expect(err).toBeInstanceOf(CapabilityUnavailable)
    expect((err as CapabilityUnavailable).capability).toBe('validate')
    expect((err as CapabilityUnavailable).message).toContain('validate')
  })
})

describe('subscribeGraphState resilience', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  const servePolling = (respond: () => Response) => {
    let statePolls = 0
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(asCatalog(ALL_CAPS))
      if (path === '/api/runs/r1/graph_state') {
        statePolls += 1
        return respond()
      }
      throw new Error(`unexpected fetch ${path}`)
    })
    return () => statePolls
  }

  it('unsubscribing before the first fetch returns delivers nothing and leaks no polls', async () => {
    vi.useFakeTimers()
    const polls = servePolling(() => ok(stateBody('running')))
    const cb = vi.fn()
    const onError = vi.fn()
    const unsub = createHttpGraphApi().subscribeGraphState('r1', cb, onError)
    unsub()
    unsub()
    unsub()
    await vi.advanceTimersByTimeAsync(60000)
    expect(cb).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(polls()).toBeLessThanOrEqual(1)  // the aborted in-flight poll at most
  })

  it('a 404 ends the chain without onError', async () => {
    vi.useFakeTimers()
    const polls = servePolling(() => new Response('gone', { status: 404 }))
    const cb = vi.fn()
    const onError = vi.fn()
    createHttpGraphApi().subscribeGraphState('r1', cb, onError)
    await vi.advanceTimersByTimeAsync(60000)
    expect(polls()).toBe(1)  // isNotFound stops the chain: no retries
    expect(cb).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('a 500 backs off, reports on the third failure, and keeps polling', async () => {
    vi.useFakeTimers()
    const polls = servePolling(() => new Response('down', { status: 500 }))
    const onError = vi.fn()
    createHttpGraphApi('/api', { jitter: 0, random: () => 0.5 }).subscribeGraphState('r1', vi.fn(), onError)
    await vi.advanceTimersByTimeAsync(0)             // fail 1 -> wait 4s
    await vi.advanceTimersByTimeAsync(4000)          // fail 2 -> wait 8s
    expect(onError).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(8000)          // fail 3 -> report
    expect(onError).toHaveBeenLastCalledWith(3)
    const before = polls()
    await vi.advanceTimersByTimeAsync(16000)         // fail 4: the chain survived
    expect(polls()).toBe(before + 1)
  })

  // --- chaos: FINAL wire shapes the provisional finality check misreads ------
  // outcome replaces terminal (E-75 §7.4): a running state with no terminal
  // field must poll on; today `terminal !== null` sees undefined and stops.

  it('an outcome-shaped running state is non-final: changed pending keeps polling', async () => {
    vi.useFakeTimers()
    const bodies = [
      { kind: 'state', graph_sha: 's', nodes: {}, edges: [], current_nodes: [],
        pending: [{ node: 'architecture', key: 'architecture#1', kind: 'gate' }],
        outcome: { state: 'running', reason: null, result: null } },
      { kind: 'state', graph_sha: 's', nodes: {}, edges: [], current_nodes: [],
        pending: [{ node: 'architecture', key: 'architecture#2', kind: 'gate' }],
        outcome: { state: 'running', reason: null, result: null } },
    ]
    let statePolls = 0
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(asCatalog(ALL_CAPS))
      if (path === '/api/runs/r1/graph_state') {
        statePolls += 1
        return ok(bodies[Math.min(statePolls, bodies.length) - 1])
      }
      throw new Error(`unexpected fetch ${path}`)
    })
    const cb = vi.fn()
    createHttpGraphApi('/api', { jitter: 0, random: () => 0.5 }).subscribeGraphState('r1', cb)
    await vi.advanceTimersByTimeAsync(0)             // first delivery: pending #1
    expect(cb).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)          // running is non-final: poll again
    expect(statePolls).toBe(2)
    expect(cb).toHaveBeenCalledTimes(2)
    const second = cb.mock.calls[1][0] as unknown as { pending: { key: string }[] }
    expect(second.pending[0].key).toBe('architecture#2')
  })

  // NOT pinned here: an `unavailable` body already ends the chain cleanly
  // today -- `terminal` is absent, so `!== null` is true by accident and the
  // observable behavior (one fetch, one delivery, no retries) matches the
  // FINAL contract. Its honest RED surface is the RunView banner, which has
  // no branch for it (views/RunView.test.ts).
})

describe('mock graph under hostile use', () => {
  it('getRunGraph for an unknown run answers no_graph/legacy_run, never throws', async () => {
    await expect(createMockGraph().getRunGraph('bogus-run')).resolves.toEqual({
      kind: 'no_graph',
      reason: 'legacy_run',
    })
  })

  it('onDecision for an unknown run is a silent no-op that corrupts nothing', async () => {
    const mock = createMockGraph()
    const cb = vi.fn()
    mock.subscribeGraphState('feature-graph-demo', cb)
    await flushMicro()                               // initial delivery: the recorded blocked script
    expect(cb).toHaveBeenCalledTimes(1)
    expect(() => mock.onDecision('bogus-run', 'k', 'approve')).not.toThrow()
    await flushMicro()
    expect(cb).toHaveBeenCalledTimes(1)              // no listener noise
    mock.onDecision('feature-graph-demo', 'architecture#1', 'approve')  // still works
    await flushMicro()
    expect(cb).toHaveBeenCalledTimes(2)              // state advanced to the recorded completed
    expect(cb.mock.calls[1][0]).toMatchObject({ kind: 'state', outcome: { state: 'completed' } })
  })

  it('onDecision for a non-pending gate key is a silent no-op', async () => {
    const mock = createMockGraph()
    const cb = vi.fn()
    mock.subscribeGraphState('feature-graph-demo', cb)
    await flushMicro()
    cb.mockClear()
    expect(() => mock.onDecision('feature-graph-demo', 'no-such-key', 'reject')).not.toThrow()
    expect(() => mock.onDecision('feature-graph-demo', 'architecture#2', 'approve')).not.toThrow()  // wrong phase replay
    await flushMicro()
    expect(cb).not.toHaveBeenCalled()
  })

  it('parseGraph answers ok:false for a payload with neither yaml nor graph', async () => {
    const mock = createMockGraph()
    await expect(mock.parseGraph({} as never)).resolves.toMatchObject({ ok: false })
    await expect(mock.parseGraph({ garbage: 1 } as never)).resolves.toMatchObject({ ok: false })
    const r = await mock.parseGraph({} as never)
    expect((r as { ok: false; shape_errors: { msg: string }[] }).shape_errors[0].msg).toContain('mock:')
  })

  it('parseGraph answers ok:false for unrecorded yaml', async () => {
    const mock = createMockGraph()
    const r = await mock.parseGraph({ yaml: 'schema_version: 1\nnodes: []\n' })
    expect(r).toMatchObject({ ok: false })
    expect((r as { ok: false; shape_errors: { msg: string }[] }).shape_errors[0].msg).toContain('unrecorded')
  })

  it('a failed parse does not poison the validation scenario', async () => {
    const mock = createMockGraph()
    await mock.parseGraph({ yaml: 'totally unrecorded' })
    const v = await mock.validateGraph()
    expect(v.issues[0].code).toBe('mock.unrecorded')
  })

  it('loadGraph with empty, whitespace, or unknown sha answers not_found', async () => {
    const mock = createMockGraph()
    await expect(mock.loadGraph('')).resolves.toEqual({ ok: false, reason: 'not_found' })
    await expect(mock.loadGraph('   ')).resolves.toEqual({ ok: false, reason: 'not_found' })
    await expect(mock.loadGraph('deadbeef')).resolves.toEqual({ ok: false, reason: 'not_found' })
  })

  it('serializeGraph never fails, even for an unrecorded graph', async () => {
    const mock = createMockGraph()
    const r = await mock.serializeGraph({ schema_version: 1, nodes: [], edges: [] })
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.yaml.length).toBeGreaterThan(0)
  })

  it('validateGraph before any parse answers mock.unrecorded', async () => {
    const v = await createMockGraph().validateGraph()
    expect(v.issues).toHaveLength(1)
    expect(v.issues[0]).toMatchObject({ code: 'mock.unrecorded', severity: 'warning' })
    expect(v.back_edges).toEqual([])
  })

  it('unsubscribing before the microtask delivery, repeatedly, delivers nothing', async () => {
    const mock = createMockGraph()
    const cb = vi.fn()
    const unsub = mock.subscribeGraphState('feature-graph-demo', cb)
    unsub()
    unsub()
    await flushMicro()
    expect(cb).not.toHaveBeenCalled()
    expect(() => unsub()).not.toThrow()
  })
})

// Silence the unused-type lint when GateOutcome is only used for the mock's
// decision signature above.
export type { GateOutcome }
