// The board mapping (002, FR-019): pure, unit-tested without a DOM. Wire
// types in, display primitives out -- literals constructible with no import
// from the ui package except the ported Timeline's item type (data-model
// section 3; G5 rulings throughout).
import type { DetailField } from '@kroker/ui/components/detail_pane/DetailPane.vue'
import type { TimelineItem } from '@kroker/ui/components/timeline/Timeline.vue'
import type {
  ArtifactVersionWire, BoardEventWire, BoardTaskWire, TaskDetailWire, TaskStatus,
} from './board.types'

const STATUSES: readonly TaskStatus[] = [
  'pending', 'in_progress', 'done', 'failed', 'blocked', 'quarantined',
]

export interface TaskRow {
  key: string
  /** G5a: the task id is the row label (no title exists on the wire). */
  label: string
  status: { kind: TaskStatus; pulsing: boolean }
  fixAttempts: number
  hasError: boolean
  diverged: boolean
}

/** STATUS_PIP-2 as adopted in B2: only in_progress and blocked pulse. */
export function toTaskRow(task: BoardTaskWire): TaskRow {
  return {
    key: task.task_id,
    label: task.task_id,
    status: {
      kind: task.status,
      pulsing: task.status === 'in_progress' || task.status === 'blocked',
    },
    fixAttempts: task.fix_attempts,
    hasError: task.error !== null,
    diverged: task.status !== task.authoritative_status,
  }
}

export interface CounterRow {
  /** Stat props; every label says "this run" (G5c -- project stats never shown). */
  label: string
  value: string | number
  pip?: string
}

export function toCounters(tasks: BoardTaskWire[]): CounterRow[] {
  const rows: CounterRow[] = STATUSES.map((s) => ({
    label: `${s.replace('_', ' ')} · this run`,
    value: tasks.filter((t) => t.status === s).length,
    pip: s,
  }))
  rows.push(
    { label: 'fix attempts · this run', value: tasks.reduce((n, t) => n + t.fix_attempts, 0) },
    { label: 'tasks with error · this run', value: tasks.filter((t) => t.error !== null).length, pip: 'failed' },
    { label: 'diverged · this run', value: tasks.filter((t) => t.status !== t.authoritative_status).length },
  )
  return rows
}

export interface EvidenceRow {
  kind: string
  sha256: string
  uri: string
}

export interface TaskDetailView {
  eyebrow: 'Task'
  title: string
  fields: DetailField[]
  /** G5e: task evidence as a detail-pane section. */
  evidence: EvidenceRow[]
}

export function toTaskDetail(detail: TaskDetailWire): TaskDetailView {
  const { task, evidence } = detail
  return {
    eyebrow: 'Task',
    title: task.task_id,
    fields: [
      { k: 'Status', v: task.status },
      { k: 'Authoritative status', v: task.authoritative_status },
      { k: 'Fix attempts', v: task.fix_attempts },
      // DETAIL_PANE-2: absent values pass null, never a placeholder string.
      { k: 'Branch', v: task.branch },
      { k: 'Error', v: task.error },
      { k: 'Updated', v: task.updated_at, mono: true },
    ],
    evidence: evidence.map((e) => ({ kind: e.kind, sha256: e.sha256, uri: e.uri })),
  }
}

export function toTimeline(events: BoardEventWire[]): TimelineItem[] {
  return [...events]
    .sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0)) // oldest first (US-2)
    .map((e) => ({
      id: e.id,
      to: e.to_status ?? '—',
      from: e.from_status ?? undefined,
      kind: e.to_status ?? undefined,
      detail: e.detail,
      at: e.at,
      actor: e.actor,
    }))
}

export interface VersionRow {
  id: number
  key: string
  n: number
  sha256: string
  created_at: string
}

/** G5d: keep only this run's versions, newest (surrogate id) first. */
export function toVersionRows(versions: ArtifactVersionWire[], runId: string): VersionRow[] {
  return versions
    .filter((v) => v.run_id === runId)
    .sort((a, b) => b.id - a.id)
    .map((v) => ({ id: v.id, key: v.key, n: v.n, sha256: v.sha256, created_at: v.created_at }))
}
