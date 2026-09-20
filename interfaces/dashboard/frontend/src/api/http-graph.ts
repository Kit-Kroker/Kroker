// The http provider's graph surface (E-76 spec §7.2). The three FINAL
// routes are real; the PROVISIONAL ones are wired to their spec paths but
// gated by the server-declared capabilities (D9) instead of probing 404s.
import type { DashboardApi } from './types'
import {
  CapabilityUnavailable,
  isFinalState,
  type Capability,
  type CatalogWire,
  type GraphStateResponse,
  type GraphWire,
} from './graph-types'
import { startPoll, type PollOptions, type PollStep } from './poll'
import { HttpStatusError, isNotFound } from './errors'

type GraphApi = Pick<
  DashboardApi,
  | 'getCatalog' | 'parseGraph' | 'serializeGraph' | 'validateGraph' | 'saveGraph'
  | 'loadGraph' | 'getRunGraph' | 'subscribeGraphState'
>

export function createHttpGraphApi(baseUrl = '/api', pollOpts?: PollOptions): GraphApi {
  const call = async (path: string, init?: RequestInit) => {
    const r = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
    if (!r.ok) throw new HttpStatusError(r.status, `${init?.method ?? 'GET'} ${path}: ${r.status}`)
    return r.json()
  }
  const post = (path: string, body: unknown) =>
    call(path, { method: 'POST', body: JSON.stringify(body) })

  let catalog: Promise<CatalogWire> | null = null
  const getCatalog = () => {
    catalog ??= call('/graphs/catalog').catch((e) => {
      catalog = null // a failed fetch is retried, never cached
      throw e
    })
    return catalog
  }
  const need = async (cap: Capability) => {
    if (!(await getCatalog()).capabilities[cap]) throw new CapabilityUnavailable(cap)
  }
  const run = (runId: string) => `/runs/${encodeURIComponent(runId)}`

  return {
    getCatalog,
    parseGraph: (input) => post('/graphs/parse', input),
    serializeGraph: (graph) => post('/graphs/serialize', { graph }),
    async validateGraph(graph: GraphWire) {
      await need('validate')
      return post('/graphs/validate', { graph })
    },
    async saveGraph(graph) {
      await need('save')
      return post('/graphs', { graph })
    },
    async loadGraph(sha) {
      await need('load')
      return call(`/graphs/${encodeURIComponent(sha)}`)
    },
    async getRunGraph(runId) {
      await need('run_graph')
      return call(`${run(runId)}/graph`)
    },
    subscribeGraphState(runId, cb, onError) {
      const fetchOnce = async (signal: AbortSignal): Promise<PollStep<GraphStateResponse>> => {
        try {
          await need('run_graph')
        } catch (e) {
          if (e instanceof CapabilityUnavailable) return { kind: 'stop' }
          throw e
        }
        try {
          const state: GraphStateResponse = await call(`${run(runId)}/graph_state`, { signal })
          // E-75 §7.4: outcome replaces terminal -- finality is the outcome's
          // state (running polls on; completed/rejected/escalated/failed and
          // the E-77 `unavailable` degradation all end the chain).
          return { kind: 'value', value: state, final: isFinalState(state) }
        } catch (e) {
          if (isNotFound(e)) return { kind: 'stop' }
          throw e
        }
      }
      return startPoll(fetchOnce, cb, (n) => onError?.(n), pollOpts)
    },
  }
}
