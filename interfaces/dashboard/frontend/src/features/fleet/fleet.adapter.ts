import type { Run } from '../../api/types'
import type { FleetRunSummary } from '../../api/read-types'
import { money } from '../../shared/format'

// 018 T049 (S6/S16): the v5 Fleet row. toFleetRow stays for its boundaries
// pin, re-typed locally — the fleet_row component and the stage strip are
// retired, and the adapter no longer imports either.

export interface FleetRowLegacy {
  id: string
  title: string
  mode: string
  status: { kind: Run['status']; label: string; pulsing: boolean }
  blocker: string | null
  cost: number | null
  age: string
  href: string
}

export interface FleetRowV5 {
  runId: string
  title: string
  graph: string
  arm: string
  outcome: string
  where: string
  traversals: string
  cost: string
  elapsed: string
  openLabel: 'Decide' | 'Open run' | 'Open'
}

const STATUS_LABEL: Record<Run['status'], string> = {
  running: 'running',
  blocked: 'waiting',
  failed: 'failed',
  done: 'done',
}

export function toFleetRow(run: Run): FleetRowLegacy {
  return {
    id: run.id,
    title: run.title,
    mode: run.mode,
    status: {
      kind: run.status,
      label: STATUS_LABEL[run.status],
      pulsing: run.status === 'running' || run.status === 'blocked',
    },
    blocker: run.blocker,
    cost: run.cost,
    age: run.age,
    href: `/runs/${run.id}`,
  }
}

export function fleetRows(
  runs: Run[],
  byRun: Record<string, FleetRunSummary>,
  runInContext: string | null,
): FleetRowV5[] {
  return runs.map((run) => {
    const summary = byRun[run.id]
    const graph = summary ? (summary.graphName ?? summary.graphSha ?? '—') : '—'
    const arm = summary?.arm
      ? `${summary.arm.harness ?? '—'} × ${summary.arm.model ?? '—'}`
      : '—'
    const outcome = summary?.outcome?.result ?? summary?.outcome?.state ?? '—'
    const where = summary?.where.length ? summary.where.join(', ') : run.blocker || '—'
    const traversals = summary?.traversals.length
      ? summary.traversals.map((t) => `${t.used}/${t.max ?? '—'}`).join(' · ')
      : '—'
    const openLabel: FleetRowV5['openLabel'] =
      run.id === runInContext ? 'Open run' : run.status === 'blocked' ? 'Decide' : 'Open'
    return {
      runId: run.id,
      title: run.title,
      graph,
      arm,
      outcome,
      where,
      traversals,
      cost: run.cost === null ? 'unpriced' : money(run.cost),
      elapsed: run.age,
      openLabel,
    }
  })
}
