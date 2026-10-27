import { describe, it, expect } from 'vitest'
import { railEventsOf } from './railEvents.adapter'
import type { RailBoardEvent } from './railEvents.adapter'
import type { Decision } from '../../api/types'
import type { GraphStateResponse, PendingRef } from '../../api/graph-types'

// 018 T029 (RED): the rail's Events section (R-5) — live decisions, closed
// untimed decisions, observed node transitions, pending items, budget
// crossings and the outcome, in one pinned order.

const dec = (over: Partial<Decision> = {}): Decision => ({
  ts: '',
  gate: 'merge',
  outcome: 'approve',
  comment: '',
  decider: 'owner',
  ...over,
})

const boardEvent = (over: Partial<RailBoardEvent> = {}): RailBoardEvent => ({
  subject: 'task:1:t5',
  to_status: 'done',
  at: '2026-10-27T12:00:00Z',
  ...over,
})

const nodeState = (status: string) => ({
  status,
  round: 1,
  started_at: null,
  ended_at: null,
  cost_usd: null,
  canonical_stage: null,
})

const mkState = (nodes: Record<string, { status: string }>, outcome = { state: 'running', reason: null, result: null }) =>
  ({
    kind: 'state',
    graph_sha: 's',
    nodes: Object.fromEntries(Object.entries(nodes).map(([k, v]) => [k, nodeState(v.status)])),
    edges: [],
    current_nodes: [],
    pending: [],
    outcome,
  }) as unknown as GraphStateResponse

describe('railEventsOf (018 T029 RED)', () => {
  it('merges decisions and board events into one timed block, newest first', () => {
    const r = railEventsOf({
      decisions: [
        dec({ ts: '2026-10-27T10:00:00Z', gate: 'architecture', outcome: 'approve' }),
        dec({ ts: '2026-10-27T11:30:00Z', gate: 'plan', outcome: 'reject' }),
      ],
      boardEvents: [boardEvent()],
    })
    expect(r.rows.map((row) => row.label)).toEqual(['task:1:t5 -> done', 'reject plan', 'approve architecture'])
    expect(r.rows.every((row) => row.timing === 'timed' && row.at !== '')).toBe(true)
  })

  it('closed decisions follow the timed block untimed, "not approved" in place of reject', () => {
    const r = railEventsOf({
      decisions: [dec({ ts: '2026-10-27T11:30:00Z', gate: 'plan', outcome: 'reject' })],
      closedDecisions: [
        dec({ gate: 'merge', outcome: 'reject' }),
        dec({ gate: 'budget', outcome: 'approve', decider: 'auto' }),
      ],
    })
    expect(r.rows.slice(1)).toEqual([
      { at: '', label: 'not approved merge', kind: 'decision', timing: 'untimed' },
      { at: '', label: 'approve budget', kind: 'decision', timing: 'untimed' },
    ])
  })

  it('observed transitions label the node status change and skip unchanged nodes', () => {
    const r = railEventsOf({
      prev: mkState({ a: { status: 'done' }, b: { status: 'running' } }),
      curr: mkState({ a: { status: 'done' }, b: { status: 'blocked' } }),
    })
    expect(r.rows).toEqual([
      { at: '', label: 'b: running -> blocked', kind: 'observed', timing: 'observed' },
    ])
  })

  it('pending items, budget crossings and the final outcome follow in that order', () => {
    const pending: PendingRef[] = [{ node: 'architecture', key: 'architecture#1', kind: 'gate' }]
    const r = railEventsOf({
      pending,
      budgetCrossings: 2,
      curr: mkState({}, { state: 'failed', reason: null, result: 'failed:quarantined-tasks' }),
    })
    expect(r.rows.slice(-3)).toEqual([
      { at: '', label: 'Review gate architecture#1', kind: 'pending', timing: 'untimed' },
      { at: '', label: 'Budget crossed 2x', kind: 'budget', timing: 'untimed' },
      { at: '', label: 'Run failed: failed:quarantined-tasks', kind: 'outcome', timing: 'untimed' },
    ])
  })

  it('with no source at all, the single unavailable row stands in', () => {
    const r = railEventsOf({ open: false })
    expect(r.unavailable).toBe(true)
    expect(r.rows).toEqual([
      { at: '', label: 'Decision history is not available for this run', kind: 'decision', timing: 'untimed' },
    ])
    expect(r.note).toBeNull()
  })

  it('an open run carries the closed-decisions note; a closed run does not', () => {
    const source = { decisions: [dec({ ts: '2026-10-27T10:00:00Z' })] }
    expect(railEventsOf({ ...source, open: true }).note).toBe(
      'automatic and timed-out decisions appear when the run ends',
    )
    expect(railEventsOf({ ...source, open: false }).note).toBeNull()
  })

  // --- chaos (018 T029 RED) ------------------------------------------------

  it('a decision and a board event sharing a timestamp: the decision sorts first, deterministically', () => {
    const r = railEventsOf({
      decisions: [dec({ ts: '2026-10-27T12:00:00Z', gate: 'merge', outcome: 'approve' })],
      boardEvents: [boardEvent({ at: '2026-10-27T12:00:00Z' })],
    })
    expect(r.rows.map((row) => row.label)).toEqual(['approve merge', 'task:1:t5 -> done'])
  })

  it('a transition on the FIRST poll (no prev) is not an event: nothing was observed before', () => {
    const r = railEventsOf({ curr: mkState({ a: { status: 'running' } }) })
    expect(r.rows.some((row) => row.kind === 'observed')).toBe(false)
  })

  it('prev present but curr absent (a failed poll): no observed rows, no crash', () => {
    const r = railEventsOf({ prev: mkState({ a: { status: 'running' } }) })
    expect(r.rows.some((row) => row.kind === 'observed')).toBe(false)
  })

  it('a node new in curr counts as a transition from idle, labelled with the curr status', () => {
    const r = railEventsOf({ prev: mkState({}), curr: mkState({ c: { status: 'running' } }) })
    expect(r.rows).toEqual([
      { at: '', label: 'c: idle -> running', kind: 'observed', timing: 'observed' },
    ])
  })

  it('zero budget crossings render no budget row; one crossing reads 1x', () => {
    const quiet = railEventsOf({ budgetCrossings: 0 })
    expect(quiet.rows.some((row) => row.kind === 'budget')).toBe(false)

    const crossed = railEventsOf({ budgetCrossings: 1 })
    expect(crossed.rows).toContainEqual({
      at: '',
      label: 'Budget crossed 1x',
      kind: 'budget',
      timing: 'untimed',
    })
  })

  it('a still-running outcome renders no outcome row', () => {
    const r = railEventsOf({ curr: mkState({}) })
    expect(r.rows.some((row) => row.kind === 'outcome')).toBe(false)
  })

  it('an unattributed pending (node null) still renders its review row', () => {
    const r = railEventsOf({ pending: [{ node: null, key: 'e#2', kind: 'escalation' } as PendingRef] })
    expect(r.rows).toContainEqual({
      at: '',
      label: 'Review escalation e#2',
      kind: 'pending',
      timing: 'untimed',
    })
  })

  it('closedDecisions alone on a closed run ARE the history: unavailable stays false', () => {
    const r = railEventsOf({
      closedDecisions: [dec({ gate: 'merge', outcome: 'reject' })],
      open: false,
    })
    expect(r.unavailable).toBe(false)
    expect(r.rows).toEqual([
      { at: '', label: 'not approved merge', kind: 'decision', timing: 'untimed' },
    ])
  })

  it('decisions with an empty ts render after the timestamped ones, timing timed with at "" — no sort crash', () => {
    const r = railEventsOf({
      decisions: [
        dec({ ts: '', gate: 'merge', outcome: 'approve' }),
        dec({ ts: '2026-10-27T10:00:00Z', gate: 'plan', outcome: 'approve' }),
      ],
    })
    expect(r.rows.map((row) => row.label)).toEqual(['approve plan', 'approve merge'])
    expect(r.rows[0].at).toBe('2026-10-27T10:00:00Z')
    expect(r.rows[1]).toMatchObject({ timing: 'timed', at: '' })
  })
})
