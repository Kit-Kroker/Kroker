// 018 T063: the /graphs redirects (router rules; the pin lives here in
// app/ because features/ may not import the router — the boundary test
// holds for tests too).
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import preCode from '../api/__fixtures__/graph/scenarios/pre_code.json'
import shippedFixture from '../api/__fixtures__/read/graphs-shipped.json'
import type { GraphWire } from '../api/graph-types'

const api = vi.hoisted(() => ({
  getRunGraph: vi.fn(),
}))
vi.mock('../api/client', () => ({ api, API_MODE: 'mock' as const }))

import { router } from './router'

const PRE = preCode.parse as { ok: true; graph: GraphWire; sha: string }
const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'

const loadRun = (sha: string | null) => {
  api.getRunGraph.mockResolvedValue({ kind: 'graph', sha, graph: PRE.graph, back_edges: [] })
}

beforeEach(() => {
  vi.resetAllMocks()
  // The shell reads the shipped graphs on mount; the redirect test does not
  // care, but the mock must answer if asked.
  loadRun(DEFAULT_SHA)
  void shippedFixture
})

describe('the /graphs redirects (T063 router rules)', () => {
  it('/graphs?sha=X lands on /graphs/X; /graphs?from=run:ID loads the run copy at its sha', async () => {
    await router.push(`/graphs?sha=${DEFAULT_SHA}`)
    await router.isReady()
    expect(router.currentRoute.value.path).toBe(`/graphs/${DEFAULT_SHA}`)

    loadRun(DEFAULT_SHA)
    await router.push('/graphs?from=run:r1')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/graphs/${DEFAULT_SHA}`)
    expect(api.getRunGraph).toHaveBeenCalledWith('r1')
  })
})
