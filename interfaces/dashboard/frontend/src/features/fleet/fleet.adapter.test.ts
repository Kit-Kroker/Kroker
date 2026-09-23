import { describe, it, expect } from 'vitest'
import { toFleetRow } from './fleet.adapter'
import type { Run } from '../../api/types'
import catalogJson from '../../api/__fixtures__/graph/catalog.json'

const CANONICAL: string[] = catalogJson.canonical_stages

const mkRun = (over: Partial<Run> = {}): Run => ({
  id: 'run-1',
  title: 'Test run',
  mode: 'brownfield',
  repo: 'org/repo',
  activeStages: ['requirements'],
  status: 'running',
  blocker: null,
  cost: null,
  budget: 50,
  age: '10m',
  decisions: [],
  ...over,
})

describe('fleet adapter', () => {
  it('adapts a run into FleetRowProps preserving null cost', () => {
    const run = mkRun({ cost: null })
    const row = toFleetRow(run, CANONICAL)
    expect(row.id).toBe('run-1')
    expect(row.title).toBe('Test run')
    expect(row.mode).toBe('brownfield')
    expect(row.cost).toBeNull()
    expect(row.href).toBe('/runs/run-1')
    expect(row.status.kind).toBe('running')
    expect(row.status.pulsing).toBe(true)
  })
})
