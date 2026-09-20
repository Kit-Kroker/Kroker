import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { createHttpGraphApi } from './http-graph'
import { CapabilityUnavailable } from './graph-types'
import catalogJson from './__fixtures__/graph/catalog.json'
import preCode from './__fixtures__/graph/scenarios/pre_code.json'
import recorded from './__fixtures__/graph/run_state/graph_state.recorded.json'

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('http graph provider', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(catalogJson)
      if (path === '/api/graphs/parse') return ok(preCode.parse)
      return new Response('nope', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('fetches the catalog once per session', async () => {
    const api = createHttpGraphApi()
    await api.getCatalog()
    await api.getCatalog()
    expect(fetchMock.mock.calls.filter(([p]) => p === '/api/graphs/catalog')).toHaveLength(1)
  })

  it('does not cache a failed catalog fetch', async () => {
    fetchMock.mockImplementationOnce(async () => new Response('down', { status: 502 }))
    const api = createHttpGraphApi()
    await expect(api.getCatalog()).rejects.toThrow('502')
    expect((await api.getCatalog()).canonical_stages).toHaveLength(18)
  })

  it('posts parse input verbatim to the shipped route', async () => {
    const api = createHttpGraphApi()
    await api.parseGraph({ yaml: preCode.yaml })
    const [path, init] = fetchMock.mock.calls.find(([p]) => p === '/api/graphs/parse')!
    expect(path).toBe('/api/graphs/parse')
    expect(JSON.parse(init.body)).toEqual({ yaml: preCode.yaml })
  })

  it.each([
    ['validateGraph', 'validate'],
    ['saveGraph', 'save'],
    ['loadGraph', 'load'],
    ['getRunGraph', 'run_graph'],
  ] as const)('%s refuses without calling the route while %s is not declared', async (method, cap) => {
    // E-77 (FR-026): the recorded catalog now declares save/load, so the
    // refusal cases pin an explicit no-capability catalog (as the chaos
    // suite does with NO_CAPS) instead of leaning on the recording.
    const noCaps = { ...(catalogJson as object), capabilities: { validate: false, save: false, load: false, run_graph: false } }
    fetchMock.mockImplementationOnce(async (path: string) => ok(noCaps))
    const api = createHttpGraphApi()
    const arg = method === 'loadGraph' || method === 'getRunGraph' ? 'x' : ({ schema_version: 1, nodes: [], edges: [] } as never)
    await expect((api[method] as (a: unknown) => Promise<unknown>)(arg)).rejects.toEqual(new CapabilityUnavailable(cap))
    expect(fetchMock.mock.calls.map(([p]) => p)).toEqual(['/api/graphs/catalog'])
  })

  it('never polls run state while run_graph is not declared', async () => {
    // E75-OQ-1: the recorded catalog now declares run_graph true, so the
    // refusal case pins an explicit no-capability catalog (the :56 pattern)
    // instead of leaning on the recording.
    const noRunGraph = { ...catalogJson, capabilities: { ...catalogJson.capabilities, run_graph: false } }
    fetchMock.mockImplementation(async (path: string) =>
      path === '/api/graphs/catalog' ? ok(noRunGraph) : new Response('nope', { status: 404 }))
    vi.useFakeTimers()
    const api = createHttpGraphApi()
    const cb = vi.fn()
    api.subscribeGraphState('r1', cb)
    await vi.advanceTimersByTimeAsync(10000)
    expect(cb).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls.map(([p]) => p)).toEqual(['/api/graphs/catalog'])
  })

  it('polls run state when declared and ends the chain on a non-running outcome', async () => {
    // Body re-shaped to the FINAL wire (E-75 §7.4): outcome replaces
    // terminal; the recorded-bodies test below pins the same finality over
    // real projections. This row keeps the URL-encoding pin ('r 1').
    vi.useFakeTimers()
    const catalog = { ...catalogJson, capabilities: { ...catalogJson.capabilities, run_graph: true } }
    let polls = 0
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(catalog)
      polls += 1
      return ok({
        kind: 'state', graph_sha: 's', nodes: {}, edges: [], current_nodes: [], pending: [],
        outcome: { state: polls >= 2 ? 'completed' : 'running', reason: null, result: null },
      })
    })
    const api = createHttpGraphApi()
    const cb = vi.fn()
    api.subscribeGraphState('r 1', cb)
    await vi.advanceTimersByTimeAsync(60000)
    expect(polls).toBe(2)
    expect(cb).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.some(([p]) => p === '/api/runs/r%201/graph_state')).toBe(true)
  })

  it('polls on a running outcome and ends the chain on a completed outcome (recorded FINAL bodies)', async () => {
    // E75-OQ-1: the FINAL wire replaces terminal with outcome; finality is
    // outcome.state !== 'running'. The bodies are the recorded fixtures, so
    // this also pins the poll parsing the FINAL shape.
    vi.useFakeTimers()
    const catalog = { ...catalogJson, capabilities: { ...catalogJson.capabilities, run_graph: true } }
    let polls = 0
    fetchMock.mockImplementation(async (path: string) => {
      if (path === '/api/graphs/catalog') return ok(catalog)
      polls += 1
      return ok(polls === 1 ? recorded.blocked_at_architecture : recorded.completed)
    })
    const api = createHttpGraphApi()
    const cb = vi.fn()
    api.subscribeGraphState('r 1', cb)
    await vi.advanceTimersByTimeAsync(60000)
    expect(polls).toBe(2) // a running outcome must keep the chain alive
    expect(cb).toHaveBeenCalledTimes(2)
    expect(cb.mock.calls[0][0].nodes.context.status).toBe('skipped') // FINAL body passes through verbatim
    expect(cb.mock.calls.at(-1)![0].outcome).toEqual({
      state: 'completed', reason: null, result: 'deployed:https://example.invalid/pr/1',
    })
  })
})
