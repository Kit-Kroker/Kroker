import { describe, it, expect, vi, afterEach } from 'vitest'
import { selectApi } from './client'
import snapshot from './__fixtures__/fleet-snapshot.json'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('selectApi', () => {
  it('mock provider seeds 7 runs', async () => {
    const api = selectApi('mock', { simulateLive: false })
    expect(await api.listRuns()).toHaveLength(7)
  })

  it('http provider fetches and maps the fleet snapshot', async () => {
    const api = selectApi('http')
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify(snapshot), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const runs = await api.listRuns()
    expect(runs.find((r) => r.id === 'feature-add-sso')?.title).toBe('Add SSO to customer portal')
    expect(fetchMock).toHaveBeenCalledWith('/api/inbox', expect.anything())
  })

  it('http startRun falls back to a locally-built run when the fresh snapshot does not contain it', async () => {
    const api = selectApi('http')
    const fetchMock = vi.fn(
      async (_path: string, init?: RequestInit) =>
        init?.method === 'POST'
          ? new Response(JSON.stringify({ run_id: 'feature-x' }), { status: 200 })
          : new Response(JSON.stringify(snapshot), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const run = await api.startRun({
      title: 'Feature X', description: '', repo: '', mode: 'brownfield',
    })
    expect(run.id).toBe('feature-x')
    expect(run.status).toBe('running')
  })
})
