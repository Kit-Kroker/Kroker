import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { Run } from '../api/types'

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

// --- 011 T008 (RED): the honest header total (R-8, CONSOLE-27) --------------
// totalCost becomes { usd, excluded }: usd is the sum of run.cost over runs
// that carry one (null when NO run does); excluded counts runs whose price
// STATE is 'not-priced' or 'partial' (totalPrice over the roles) — no-usage
// and fully priced runs are never excluded. These tests set fleet.runs
// directly; the mocked client is not refreshed.

import { totalPrice } from './cost'

const mkRun = (over: Record<string, unknown>): Run =>
  ({
    id: 'r',
    title: 't',
    mode: 'brownfield',
    repo: 'r',
    activeStages: [],
    status: 'running',
    blocker: '',
    cost: null,
    budget: null,
    age: '1m',
    decisions: [],
    roles: [],
    ...over,
  }) as unknown as Run

const mkRole = (cost: number | null) => ({
  role: 'dev',
  cost,
  inputTokens: 100,
  outputTokens: 10,
  cacheReadTokens: 0,
  cacheWriteTokens: 0,
})

describe('totalCost is the honest header total (011 T008)', () => {
  it('sums the priced runs and excludes none when all are priced', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'a', cost: 2, roles: [] }), mkRun({ id: 'b', cost: 3.4, roles: [] })] as never
    expect(fleet.totalCost.usd).toBe(5.4)
    expect(fleet.totalCost.excluded).toBe(0)
  })

  it('sums what was priced and excludes the partial and not-priced runs', () => {
    const fleet = useFleetStore()
    fleet.runs = [
      mkRun({ id: 'priced', cost: 5, roles: [] }),
      mkRun({ id: 'partial', cost: 1, roles: [mkRole(1), mkRole(0)] }),
      mkRun({ id: 'not-priced', cost: null, roles: [mkRole(0)] }),
    ] as never
    expect(fleet.totalCost.usd).toBe(6)
    expect(fleet.totalCost.excluded).toBe(2)
    // exclusion is by price STATE: partial and not-priced are excluded,
    // priced is not — the same verdict totalPrice hands the Cost tab.
    expect(totalPrice([mkRole(1), mkRole(0)], 1).state).toBe('partial')
    expect(totalPrice([mkRole(0)], null).state).toBe('not-priced')
  })

  it('is null when runs exist but none was ever priced', () => {
    const fleet = useFleetStore()
    fleet.runs = [
      mkRun({ id: 'a', cost: null, roles: [mkRole(0)] }),
      mkRun({ id: 'b', cost: null, roles: [mkRole(null)] }),
    ] as never
    expect(fleet.totalCost.usd).toBeNull()
    expect(fleet.totalCost.excluded).toBe(2)
  })

  it('is null with nothing excluded when there are no runs at all', () => {
    const fleet = useFleetStore()
    fleet.runs = [] as never
    expect(fleet.totalCost.usd).toBeNull()
    expect(fleet.totalCost.excluded).toBe(0)
  })

  it('never excludes a no-usage run', () => {
    const fleet = useFleetStore()
    fleet.runs = [mkRun({ id: 'a', cost: null, roles: [] }), mkRun({ id: 'b', cost: null, roles: [] })] as never
    expect(fleet.totalCost.usd).toBeNull()
    expect(fleet.totalCost.excluded).toBe(0)
  })
})
