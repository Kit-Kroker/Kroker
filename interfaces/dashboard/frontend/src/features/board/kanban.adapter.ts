// 018 T054 (S7, V7; FR-023): board tasks -> kanban columns by wire status.
// Only the six wire statuses form columns, in wire order; anything else a
// provider might send (claimed, queued) is not a board column and drops
// out entirely. Pure — the view owns no state.
import type { KanbanColumn } from '@kroker/ui'
import type { BoardTaskWire, TaskStatus } from './board.types'

const WIRE_ORDER: TaskStatus[] = [
  'pending',
  'in_progress',
  'done',
  'failed',
  'blocked',
  'quarantined',
]

const TITLES: Record<TaskStatus, string> = {
  pending: 'Pending',
  in_progress: 'In progress',
  done: 'Done',
  failed: 'Failed',
  blocked: 'Blocked',
  quarantined: 'Quarantined',
}

export function kanbanOf(tasks: BoardTaskWire[]): KanbanColumn[] {
  const byStatus = new Map<TaskStatus, BoardTaskWire[]>()
  for (const t of tasks) {
    if (!WIRE_ORDER.includes(t.status)) continue
    const list = byStatus.get(t.status) ?? []
    list.push(t)
    byStatus.set(t.status, list)
  }
  const columns: KanbanColumn[] = []
  for (const status of WIRE_ORDER) {
    const list = byStatus.get(status)
    if (!list) continue
    columns.push({
      id: status,
      title: TITLES[status],
      status,
      count: list.length,
      cards: list.map((t) => ({
        id: t.task_id,
        // A task whose row status differs from the authoritative one shows
        // both in its tag (V7); an agreeing task shows its status alone.
        tag:
          t.status === t.authoritative_status
            ? t.status
            : `${t.status} · ${t.authoritative_status}`,
        tagKind: t.status,
        meta: `fix attempts: ${t.fix_attempts}`,
      })),
    })
  }
  return columns
}
