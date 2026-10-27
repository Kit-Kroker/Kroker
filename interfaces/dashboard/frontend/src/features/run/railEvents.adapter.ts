import type { Decision } from '../../api/types'
import type { GraphStateResponse, PendingRef } from '../../api/graph-types'

// 018 T029/T030 (R-5, FR-015/FR-022): the rail's Events section, composed
// client-side from sources the backend already holds — there is no live
// event feed (events.jsonl is written at run end). Timed sources (decisions,
// board events) lead newest first; observed poll transitions, pending
// items, budget crossings and the final outcome follow; closed-run
// RunSummary decisions are untimed and render after the timed block.

// The board event fields this adapter reads, as a structural type: a
// features/ screen may never import another features/ screen's modules
// (boundaries.test.ts), and the app layer passes the wire through.
export interface RailBoardEvent {
  subject: string
  to_status: string | null
  at: string
}

export type RailEventKind = 'decision' | 'pending' | 'observed' | 'board' | 'budget' | 'outcome'
export type RailEventTiming = 'timed' | 'observed' | 'untimed'

export interface RailEventRow {
  at: string
  label: string
  kind: RailEventKind
  timing: RailEventTiming
}

export interface RailEvents {
  rows: RailEventRow[]
  unavailable: boolean
  note: string | null
}

export interface RailEventsInput {
  decisions?: Decision[]
  closedDecisions?: Decision[]
  pending?: PendingRef[]
  prev?: GraphStateResponse | null
  curr?: GraphStateResponse | null
  boardEvents?: RailBoardEvent[]
  budgetCrossings?: number
  open?: boolean
}

const UNAVAILABLE_ROW: RailEventRow = {
  at: '',
  label: 'Decision history is not available for this run',
  kind: 'decision',
  timing: 'untimed',
}

const OPEN_NOTE = 'automatic and timed-out decisions appear when the run ends'

interface TimedRow extends RailEventRow {
  sort: number
}

export function railEventsOf(input: RailEventsInput): RailEvents {
  const decisions = input.decisions ?? []
  const closed = input.closedDecisions ?? []
  const pending = input.pending ?? []
  const board = input.boardEvents ?? []
  const crossings = input.budgetCrossings ?? 0
  const curr = input.curr && input.curr.kind === 'state' ? input.curr : null
  const prev = input.prev && input.prev.kind === 'state' ? input.prev : null

  // (a) timed block: decisions and board events, newest first; empty-ts
  // decisions sink to the block's end; on a shared timestamp the decision
  // sorts first (stable, deterministic).
  const timed: TimedRow[] = []
  for (const d of decisions) {
    timed.push({
      at: d.ts,
      label: `${d.outcome} ${d.gate}`,
      kind: 'decision',
      timing: 'timed',
      sort: d.ts ? Date.parse(d.ts) : Number.NEGATIVE_INFINITY,
    })
  }
  for (const e of board) {
    timed.push({
      at: e.at,
      label: `${e.subject} -> ${e.to_status}`,
      kind: 'board',
      timing: 'timed',
      sort: Date.parse(e.at),
    })
  }
  timed.sort((a, b) => b.sort - a.sort)
  const rows: RailEventRow[] = timed.map(({ at, label, kind, timing }) => ({ at, label, kind, timing }))

  // (b) closed RunSummary-derived decisions: untimed, after the timed
  // block; a rejection reads "not approved" (R-4).
  for (const d of closed) {
    rows.push({
      at: '',
      label: `${d.outcome === 'reject' ? 'not approved' : d.outcome} ${d.gate}`,
      kind: 'decision',
      timing: 'untimed',
    })
  }

  // (c) transitions observed between two polls, alphabetical by node; a
  // node absent from prev counts as idle. The first poll observes nothing.
  if (prev && curr) {
    const ids = [...new Set([...Object.keys(prev.nodes), ...Object.keys(curr.nodes)])].sort()
    for (const id of ids) {
      const from = prev.nodes[id]?.status ?? 'idle'
      const to = curr.nodes[id]?.status ?? 'idle'
      if (from !== to) {
        rows.push({ at: '', label: `${id}: ${from} -> ${to}`, kind: 'observed', timing: 'observed' })
      }
    }
  }

  // (d) pending items for this run (opened) — the inbox is their surface,
  // but the rail lists them as review rows.
  for (const p of pending) {
    rows.push({ at: '', label: `Review ${p.kind} ${p.key}`, kind: 'pending', timing: 'untimed' })
  }

  // (e) budget crossings, count only.
  if (crossings > 0) {
    rows.push({ at: '', label: `Budget crossed ${crossings}x`, kind: 'budget', timing: 'untimed' })
  }

  // (f) the outcome, once final.
  if (curr?.outcome && curr.outcome.state !== 'running') {
    const o = curr.outcome
    rows.push({
      at: '',
      label: `Run ${o.state}${o.result ? `: ${o.result}` : ''}`,
      kind: 'outcome',
      timing: 'untimed',
    })
  }

  const hasSource = rows.length > 0
  return {
    rows: hasSource ? rows : [UNAVAILABLE_ROW],
    unavailable: !hasSource,
    note: input.open ? OPEN_NOTE : null,
  }
}
