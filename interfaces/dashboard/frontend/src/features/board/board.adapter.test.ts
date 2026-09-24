// T031 (RED): the board adapter, toTaskRow and toCounters (data-model
// section 3, G5a/G5c). The module ./board.adapter does not exist yet --
// every test fails on that import until T032 lands it. The pulsing rule is
// STATUS_PIP-2 as adopted in B2: only in_progress and blocked pulse.
import { describe, it, expect } from 'vitest'
import { toTaskRow, toCounters, toTaskDetail, toTimeline, toVersionRows } from './board.adapter'
import type {
  ArtifactVersionWire,
  BoardEventWire,
  BoardTaskWire,
  TaskEvidenceWire,
  TaskStatus,
} from './board.types'

const STATUSES: TaskStatus[] = [
  'pending', 'in_progress', 'done', 'failed', 'blocked', 'quarantined',
]

const mkTask = (over: Partial<BoardTaskWire> = {}): BoardTaskWire => ({
  project: 'kroker',
  plan_version: 7,
  task_id: 'T07',
  run_id: 'feature-graph-demo',
  status: 'pending',
  authoritative_status: 'pending',
  row_version: 1,
  fix_attempts: 0,
  error: null,
  branch: null,
  updated_at: '2026-09-24T10:00:00Z',
  ...over,
})

describe('toTaskRow', () => {
  it('keys and labels the row by the task id (G5a)', () => {
    const row = toTaskRow(mkTask({ task_id: 'T014-validate-graph' }))
    expect(row.key).toBe('T014-validate-graph')
    expect(row.label).toBe('T014-validate-graph')
  })

  it('pulses only in_progress and blocked; every other status is static', () => {
    for (const s of STATUSES) {
      const row = toTaskRow(mkTask({ status: s }))
      expect(row.status.kind).toBe(s)
      expect(row.status.pulsing, s).toBe(s === 'in_progress' || s === 'blocked')
    }
  })

  it('passes fix_attempts through', () => {
    expect(toTaskRow(mkTask({ fix_attempts: 4 })).fixAttempts).toBe(4)
    expect(toTaskRow(mkTask()).fixAttempts).toBe(0)
  })

  it('hasError is the error field, not its text (null vs message)', () => {
    expect(toTaskRow(mkTask({ error: null })).hasError).toBe(false)
    expect(toTaskRow(mkTask({ error: 'qa tier timed out' })).hasError).toBe(true)
  })

  it('diverged is status !== authoritative_status, both directions', () => {
    expect(toTaskRow(mkTask()).diverged).toBe(false)
    expect(
      toTaskRow(mkTask({ status: 'failed', authoritative_status: 'done' })).diverged,
    ).toBe(true)
  })
})

// Stat props rows (the ported Stat takes { label, value }); keyword matching
// keeps wording free while pinning presence, the 'this run' label and values.
interface CounterRow {
  label: string
  value: string | number | null | undefined
}

const mentions = (label: string, word: string) =>
  label.toLowerCase().replace(/_/g, ' ').includes(word.replace(/_/g, ' '))

const statusRow = (rows: CounterRow[], s: TaskStatus) =>
  rows.find((r) => mentions(r.label, s) && r.label.toLowerCase().includes('this run'))

describe('toCounters', () => {
  const tasks: BoardTaskWire[] = [
    mkTask({ task_id: 'T01', status: 'pending', fix_attempts: 1 }),
    mkTask({ task_id: 'T02', status: 'pending' }),
    mkTask({
      task_id: 'T03', status: 'in_progress', fix_attempts: 2,
      error: 'boom', authoritative_status: 'done',
    }),
    mkTask({ task_id: 'T04', status: 'failed', authoritative_status: 'failed', error: 'late failure' }),
    mkTask({ task_id: 'T05', status: 'blocked', authoritative_status: 'in_progress' }),
    mkTask({ task_id: 'T06', status: 'done', authoritative_status: 'done' }),
    mkTask({ task_id: 'T07', status: 'quarantined', authoritative_status: 'quarantined' }),
  ]

  it("counts every TaskStatus under a 'this run' label (G5c)", () => {
    const rows = toCounters(tasks) as CounterRow[]
    const expected: Record<TaskStatus, number> = {
      pending: 2, in_progress: 1, done: 1, failed: 1, blocked: 1, quarantined: 1,
    }
    for (const s of STATUSES) {
      const row = statusRow(rows, s)
      expect(row, `no counter row for ${s}`).toBeDefined()
      expect(row!.value).toBe(expected[s])
    }
  })

  it('sums fix attempts, counts errored and diverged tasks', () => {
    const rows = toCounters(tasks) as CounterRow[]
    expect(rows.find((r) => mentions(r.label, 'fix'))!.value).toBe(3) // 1 + 2
    expect(rows.find((r) => mentions(r.label, 'error'))!.value).toBe(2)
    expect(rows.find((r) => mentions(r.label, 'diverged'))!.value).toBe(2) // T03, T05
  })

  it('the zero state: an empty task list keeps every counter labelled, all zero', () => {
    const rows = toCounters([]) as CounterRow[]
    expect(rows.length).toBeGreaterThan(0)
    for (const s of STATUSES) {
      const row = statusRow(rows, s)
      expect(row, `no counter row for ${s}`).toBeDefined()
      expect(row!.value).toBe(0)
    }
    expect(rows.find((r) => mentions(r.label, 'fix'))!.value).toBe(0)
    expect(rows.find((r) => mentions(r.label, 'error'))!.value).toBe(0)
    expect(rows.find((r) => mentions(r.label, 'diverged'))!.value).toBe(0)
  })
})

// T031 companion (RED): toTaskDetail, toTimeline, toVersionRows (data-model
// section 3). Same keyword-tolerance as toCounters: label wording and value
// formatting are the implementer's freedom, so presence is matched by word
// and values by substance (containment, Number(), null-ness) -- except the
// timeline item shape, which data-model pins exactly.

// The ported DetailPane's field shape is { k, v } (FR-011/G8); accessors
// read that shape with the same word-matching tolerance.
interface DetailField {
  k: string
  v: string | number | null | undefined
}

const lbl = (f: DetailField) => f.k.toLowerCase().replace(/_/g, ' ')
const fieldBy = (fields: DetailField[], word: string) =>
  fields.find((f) => lbl(f).includes(word.replace(/_/g, ' ')))

const mkEvidence = (over: Partial<TaskEvidenceWire> = {}): TaskEvidenceWire => ({
  id: 'e1',
  project: 'kroker',
  plan_version: 7,
  task_id: 'T07',
  run_id: 'feature-graph-demo',
  kind: 'qa',
  sha256: 'deadbeef',
  uri: 'runs/e1.json',
  created_at: '2026-09-24T10:00:00Z',
  ...over,
})

const mkEvent = (over: Partial<BoardEventWire> = {}): BoardEventWire => ({
  id: 1,
  project: 'kroker',
  subject: 'task:7:T07',
  actor: 'workflow:run-1',
  authority: 'authoritative',
  from_status: 'in_progress',
  to_status: 'done',
  at: '2026-09-24T10:00:00Z',
  detail: '',
  ...over,
})

const mkVersion = (over: Partial<ArtifactVersionWire> = {}): ArtifactVersionWire => ({
  id: 1,
  project: 'kroker',
  key: 'plan',
  n: 1,
  run_id: 'feature-graph-demo',
  sha256: 'deadbeef',
  uri: 'artifacts/plan-1.json',
  supersedes: null,
  created_at: '2026-09-24T10:00:00Z',
  ...over,
})

describe('toTaskDetail', () => {
  it("eyebrow 'Task', title the task id", () => {
    const out = toTaskDetail({ task: mkTask({ task_id: 'T014-validate-graph' }), evidence: [] })
    expect(out.eyebrow).toBe('Task')
    expect(out.title).toBe('T014-validate-graph')
  })

  it('fields cover status, authoritative status, fix attempts, branch, error, updated', () => {
    const out = toTaskDetail({
      task: mkTask({
        status: 'in_progress',
        authoritative_status: 'done',
        fix_attempts: 2,
        branch: 'feat/graph-editor',
        error: 'qa tier timed out',
        updated_at: '2026-09-24T12:30:00Z',
      }),
      evidence: [],
    }) as { fields: DetailField[] }
    const fields = out.fields
    for (const word of ['authoritative', 'fix', 'branch', 'error', 'updated']) {
      expect(fieldBy(fields, word), `no field mentioning ${word}`).toBeDefined()
    }
    // plain status must not be confused with the authoritative-status field
    const statusField = fields.find((f) => lbl(f).includes('status') && !lbl(f).includes('authoritative'))
    expect(statusField, 'no plain status field').toBeDefined()
    expect(String(statusField!.v)).toContain('progress')
    expect(String(fieldBy(fields, 'authoritative')!.v)).toContain('done')
    expect(Number(fieldBy(fields, 'fix')!.v)).toBe(2)
    expect(String(fieldBy(fields, 'branch')!.v)).toContain('feat/graph-editor')
    expect(String(fieldBy(fields, 'error')!.v)).toContain('qa tier timed out')
    expect(String(fieldBy(fields, 'updated')!.v)).toContain('2026')
  })

  it('null branch and error pass null, never a placeholder string', () => {
    const out = toTaskDetail({ task: mkTask(), evidence: [] }) as { fields: DetailField[] }
    expect(fieldBy(out.fields, 'branch')!.v).toBeNull()
    expect(fieldBy(out.fields, 'error')!.v).toBeNull()
  })

  it('evidence items reach the detail (G5e), shape-agnostic by uri', () => {
    const evidence = [
      mkEvidence(),
      mkEvidence({ id: 'e2', kind: 'deep_review', uri: 'runs/e2.json' }),
    ]
    const out = toTaskDetail({ task: mkTask(), evidence })
    expect(JSON.stringify(out)).toContain('runs/e1.json')
    expect(JSON.stringify(out)).toContain('runs/e2.json')
  })
})

describe('toTimeline', () => {
  it('orders oldest first (US-2 acceptance)', () => {
    const events = [
      mkEvent({ id: 3, at: '2026-09-24T12:00:00Z' }),
      mkEvent({ id: 1, at: '2026-09-24T10:00:00Z' }),
      mkEvent({ id: 2, at: '2026-09-24T11:00:00Z' }),
    ]
    expect(toTimeline(events).map((x) => x.id)).toEqual([1, 2, 3])
  })

  it('maps a null from_status event to the exact item shape', () => {
    const ev = mkEvent({
      id: 9,
      from_status: null,
      to_status: 'done',
      detail: 'gate approve',
      actor: 'workflow:run-1',
    })
    const [item] = toTimeline([ev])
    expect(item.id).toBe(9)
    expect(item.to).toBe('done')
    expect(item.from).toBeUndefined()
    expect(item.kind).toBe('done')
    expect(item.detail).toBe('gate approve')
    expect(item.at).toBe(ev.at)
    expect(item.actor).toBe('workflow:run-1')
  })

  it('a null to_status maps to the em dash (and kind undefined)', () => {
    const [item] = toTimeline([mkEvent({ id: 5, to_status: null, from_status: 'done' })])
    expect(item.to).toBe('—')
    expect(item.kind).toBeUndefined()
  })
})

describe('toVersionRows', () => {
  it("keeps only this run's versions, newest id first (G5d)", () => {
    const versions = [
      mkVersion({ id: 12, run_id: 'another-run' }),
      mkVersion({ id: 5, run_id: 'feature-graph-demo' }),
      mkVersion({ id: 9, run_id: 'another-run' }),
      mkVersion({ id: 3, run_id: 'feature-graph-demo' }),
    ]
    const rows = toVersionRows(versions, 'feature-graph-demo') as { id: number }[]
    expect(rows.map((r) => r.id)).toEqual([5, 3])
  })

  it('an empty input yields an empty list', () => {
    expect(toVersionRows([], 'feature-graph-demo')).toEqual([])
  })
})
