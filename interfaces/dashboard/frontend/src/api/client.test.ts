import { describe, it, expect, vi, afterEach } from 'vitest'
import { selectApi } from './client'
import snapshot from './__fixtures__/fleet-snapshot.json'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
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

  it('defaults to the http provider when VITE_API is unset', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API', '')
    // Env is read at module init, so the default is only observable through
    // a fresh import. Behavioral distinction, not object identity: with no
    // fetch stub the http provider has no backend and rejects, where the
    // mock provider would resolve seeded runs.
    const { api } = await import('./client')
    await expect(api.listRuns()).rejects.toThrow()
  })

  it('selects the mock provider when VITE_API is mock', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API', 'mock')
    const { api } = await import('./client')
    try {
      expect(await api.listRuns()).toHaveLength(7)
    } finally {
      // The module-level api constructs the mock with simulateLive, whose
      // interval would otherwise outlive the test.
      ;(api as unknown as { dispose?: () => void }).dispose?.()
    }
  })
})
