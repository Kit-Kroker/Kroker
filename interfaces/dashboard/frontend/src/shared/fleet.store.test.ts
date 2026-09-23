import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api/client', () => {
  const fakeRuns = [{ id: 'r1', status: 'blocked' }, { id: 'r2', status: 'running' }]
  const api = {
    listRuns: vi.fn(async () => fakeRuns),
    listInbox: vi.fn(async () => [{ id: 'q1', type: 'clarify' }]),
    startRun: vi.fn(async (input: { title: string }) => ({ id: 'feature-new', title: input.title })),
  }
  return { api }
})

import { useFleetStore } from './fleet.store'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('fleet store', () => {
  it('refresh loads runs', async () => {
    const fleet = useFleetStore()
    await fleet.refresh()
    expect(fleet.runs).toHaveLength(2)
    expect(fleet.blockedCount).toBe(1)
    expect(fleet.activeCount).toBe(2)
  })

  it('getOrLoad finds by id', async () => {
    const fleet = useFleetStore()
    await fleet.refresh()
    expect(fleet.getOrLoad('r2')?.id).toBe('r2')
  })

  it('startRun refreshes the fleet', async () => {
    const fleet = useFleetStore()
    await fleet.startRun({ title: 'New', description: '', repo: '', mode: 'brownfield' })
    expect(fleet.runs).toHaveLength(2)
  })
})
