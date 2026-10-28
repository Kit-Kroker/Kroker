import { describe, it, expect } from 'vitest'
import { kanbanOf } from './kanban.adapter'
import type { BoardTaskWire } from './board.types'

// 018 T053 (RED): board tasks -> kanban columns by wire status (data-model
// §5 line 142, V7). The adapter does not exist yet -- that is the RED. Card
// shape per the Kanban component (T052): { id, title?, tag, tagKind, meta }.

const task = (over: Partial<BoardTaskWire> = {}): BoardTaskWire => ({
  project: 'kroker',
  plan_version: 3,
  task_id: 'T07',
  run_id: 'r1',
  status: 'in_progress',
  authoritative_status: 'in_progress',
  row_version: 1,
  fix_attempts: 0,
  error: null,
  branch: null,
  updated_at: '2026-10-28T09:00:00Z',
  ...over,
})

const columnIds = (tasks: BoardTaskWire[]) =>
  kanbanOf(tasks).map((c: { id: string }) => c.id)

describe('kanbanOf (018 T053 RED)', () => {
  it('columns come only from the wire statuses present, in wire order; never claimed or queued (V7)', () => {
    const tasks = [
      task({ task_id: 'A', status: 'done', authoritative_status: 'done' }),
      task({ task_id: 'B', status: 'pending', authoritative_status: 'pending' }),
      task({ task_id: 'C', status: 'blocked', authoritative_status: 'blocked' }),
    ]
    expect(columnIds(tasks)).toEqual(['pending', 'done', 'blocked'])

    // A status outside the six yields no column of its own.
    const foreign = kanbanOf([
      task({ task_id: 'X', status: 'claimed' as never, authoritative_status: 'claimed' as never }),
      task({ task_id: 'Y', status: 'queued' as never, authoritative_status: 'queued' as never }),
    ] as BoardTaskWire[])
    expect(foreign.map((c: { id: string }) => c.id)).toEqual([])
  })

  it('each column carries its cards with count, and a differing authoritative_status shows both in the tag', () => {
    const tasks = [
      task({ task_id: 'T07', status: 'done', authoritative_status: 'done', fix_attempts: 2 }),
      task({ task_id: 'T09', status: 'done', authoritative_status: 'failed', fix_attempts: 3 }),
      task({ task_id: 'T12', status: 'pending', authoritative_status: 'pending' }),
    ]
    const columns = kanbanOf(tasks)
    const done = columns.find((c: { id: string }) => c.id === 'done')!
    expect(done.count).toBe(2)
    expect(done.cards.map((c: { id: string }) => c.id)).toEqual(['T07', 'T09'])
    const agreeing = done.cards[0]!
    expect(agreeing.tag).toContain('done')
    // The divergent task: the tag carries BOTH the row status and the authoritative one.
    const divergent = done.cards[1]!
    expect(divergent.tag).toContain('done')
    expect(divergent.tag).toContain('failed')
  })

  it('meta carries the fix attempts', () => {
    const columns = kanbanOf([task({ task_id: 'T07', fix_attempts: 3 })])
    const card = columns.find((c: { id: string }) => c.id === 'in_progress')!.cards[0]!
    expect(String(card.meta)).toContain('3')
  })
})
