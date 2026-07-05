import { describe, it, expect } from 'vitest'
import { selectApi } from './client'

describe('selectApi', () => {
  it('mock provider seeds 7 runs', async () => {
    const api = selectApi('mock')
    expect(await api.listRuns()).toHaveLength(7)
  })

  it('http provider rejects (not wired)', async () => {
    const api = selectApi('http')
    await expect(api.listRuns()).rejects.toThrow(/not wired/)
  })
})
