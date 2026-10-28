import { describe, it, expect } from 'vitest'
import { fleetRows, toFleetRow } from './fleet.adapter'
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
    const row = toFleetRow(run)
    expect(row.id).toBe('run-1')
    expect(row.title).toBe('Test run')
    expect(row.mode).toBe('brownfield')
    expect(row.cost).toBeNull()
    expect(row.href).toBe('/runs/run-1')
    expect(row.status.kind).toBe('running')
    expect(row.status.pulsing).toBe(true)
  })
})

// --- v5 fleet rows (018 T048 RED, S6/V10/V6) --------------------------------
// fleetRows(runs, summary byRun, runInContext) is the new export; RED is its
// absence. The summary literal mirrors data-model §3.2's camelCase shape.

interface SummaryRow {
  runId: string
  graphSha: string | null
  graphName: string | null
  arm: { harness: string; model: string } | null
  traversals: { edge: { source: string; sourcePort: string; target: string; targetPort: string }; used: number; max: number | null }[]
  outcome: { state: string; reason: string | null; result: string | null } | null
  where: string[]
  gateTimeouts: { gate: string; onTimeout: string }[]
}

const summaryRow = (over: Partial<SummaryRow>): SummaryRow => ({
  runId: 'run-1',
  graphSha: 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38',
  graphName: 'default',
  arm: { harness: 'opencode', model: 'glm' },
  traversals: [],
  outcome: null,
  where: [],
  gateTimeouts: [],
  ...over,
})

const edgeRef = { source: 'architecture', sourcePort: 'revise', target: 'architect', targetPort: 'guidance' }

describe('fleetRows (v5, 018 T048 RED)', () => {
  it('carries the v5 columns: graph name, harness × model verbatim, traversals, where (V10)', () => {
    const rows = fleetRows(
      [mkRun()],
      { 'run-1': summaryRow({ traversals: [{ edge: edgeRef, used: 2, max: 3 }], where: ['code'] }) } as never,
      null,
    )
    expect(rows).toHaveLength(1)
    const row = rows[0] as Record<string, string>
    expect(row['graph']).toBe('default')
    expect(row['arm']).toBe('opencode × glm')
    expect(row['traversals']).toBe('2/3')
    expect(row['where']).toBe('code')
    expect(row['runId']).toBe('run-1')
    expect(row['title']).toBe('Test run')
  })

  it('a custom graph shows its sha; a legacy run with no summary row reads the em dash', () => {
    const rows = fleetRows(
      [mkRun({ id: 'custom' }), mkRun({ id: 'legacy' })],
      {
        custom: summaryRow({ runId: 'custom', graphName: null, graphSha: '1f953ed56f88' }),
      } as never,
      null,
    ) as Record<string, string>[]
    expect(rows.find((r) => r['runId'] === 'custom')!['graph']).toBe('1f953ed56f88')
    const legacy = rows.find((r) => r['runId'] === 'legacy')!
    expect(legacy['graph']).toBe('—')
    expect(legacy['arm']).toBe('—')
  })

  it('the outcome shows the result string as served, never halted; a null outcome reads the em dash (V6)', () => {
    const rows = fleetRows(
      [mkRun({ id: 'a' }), mkRun({ id: 'b' }), mkRun({ id: 'c' }), mkRun({ id: 'd' })],
      {
        a: summaryRow({ runId: 'a', outcome: { state: 'rejected', reason: null, result: 'rejected:budget' } }),
        b: summaryRow({ runId: 'b', outcome: { state: 'failed', reason: null, result: 'failed:quarantined-tasks' } }),
        c: summaryRow({ runId: 'c', outcome: { state: 'running', reason: null, result: null } }),
      } as never,
      null,
    ) as Record<string, string>[]
    expect(rows.find((r) => r['runId'] === 'a')!['outcome']).toBe('rejected:budget')
    expect(rows.find((r) => r['runId'] === 'b')!['outcome']).toBe('failed:quarantined-tasks')
    expect(rows.find((r) => r['runId'] === 'd')!['outcome']).toBe('—')
    expect(rows.every((r) => !String(r['outcome']).includes('halted'))).toBe(true)
  })

  it('cost: unpriced reads unpriced, never $0.00; a priced run reads money', () => {
    const rows = fleetRows(
      [mkRun({ id: 'free', cost: null }), mkRun({ id: 'paid', cost: 3.1 })],
      {} as never,
      null,
    ) as Record<string, string>[]
    expect(rows.find((r) => r['runId'] === 'free')!['cost']).toBe('unpriced')
    expect(rows.find((r) => r['runId'] === 'free')!['cost']).not.toBe('$0.00')
    expect(rows.find((r) => r['runId'] === 'paid')!['cost']).toBe('$3.10')
  })

  it('the open label: run in context first, then blocked decides, else open (S16)', () => {
    const rows = fleetRows(
      [
        mkRun({ id: 'pinned', status: 'blocked' }),
        mkRun({ id: 'waiting', status: 'blocked' }),
        mkRun({ id: 'cruising', status: 'running' }),
      ],
      {} as never,
      'pinned',
    ) as Record<string, string>[]
    expect(rows.find((r) => r['runId'] === 'pinned')!['openLabel']).toBe('Open run')
    expect(rows.find((r) => r['runId'] === 'waiting')!['openLabel']).toBe('Decide')
    expect(rows.find((r) => r['runId'] === 'cruising')!['openLabel']).toBe('Open')
  })

  it('traversals with no bounded edges read the em dash', () => {
    const rows = fleetRows([mkRun()], { 'run-1': summaryRow({ traversals: [] }) } as never, null) as Record<string, string>[]
    expect(rows[0]['traversals']).toBe('—')
  })
})
