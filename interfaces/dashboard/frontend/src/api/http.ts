import type {
  ClarifyItem, DashboardApi, Decision, EscalationItem, FleetState, GateItem,
  GateOutcome, InboxItem, OverrideItem, Run, StartRunInput, Status,
} from './types'

// Mirrors sdlc/benchmarks/heatmap.py CANONICAL_STAGES. StageDots maps active
// stages back onto its fixed strip, so this list is the join key between the
// dashboard and the benchmark axis.
const CANONICAL_STAGES = [
  'intake', 'constitution', 'context', 'requirements', 'research',
  'clarify', 'architecture', 'planning', 'code', 'review', 'adversary',
  'handoff', 'deep_review', 'analyze', 'qa', 'quality_gate', 'deploy',
  'retro',
]

function age(fromIso: string | null | undefined, now: Date): string {
  if (!fromIso) return ''
  const ms = now.getTime() - new Date(fromIso).getTime()
  const mins = Math.max(0, Math.floor(ms / 60000))
  const d = Math.floor(mins / 1440)
  if (d > 0) return `${d}d ${Math.floor((mins % 1440) / 60)}h`
  const h = Math.floor(mins / 60)
  return `${h}h ${String(mins % 60).padStart(2, '0')}m`
}

function hhmm(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

function liveStatus(status: string): Status {
  return status.startsWith('awaiting:') ? 'blocked' : 'running'
}

function closedStatus(outcome: string): Status {
  return outcome.startsWith('rejected') || outcome.startsWith('failed')
    ? 'failed'
    : 'done'
}

function blocker(status: string, pendingCount: number): string {
  if (!status.startsWith('awaiting:')) return ''
  const gate = status.slice('awaiting:'.length)
  return pendingCount > 1 ? `${gate} gate — ${pendingCount} items` : `${gate} gate`
}

function decisions(raw: any[]): Decision[] {
  return (raw ?? []).map((d) => ({
    ts: hhmm(d.decided_at),
    gate: `${d.gate} r${d.round}`,
    outcome: d.outcome as GateOutcome,
    comment: d.comments ?? '',
    decider: d.reviewer ?? d.decided_by,
  }))
}

function mapRun(s: any, pendingCount: number, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    stageIdx: Math.max(0, CANONICAL_STAGES.indexOf(s.current_stage ?? '')),
    status: liveStatus(s.status),
    blocker: blocker(s.status, pendingCount),
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: decisions(s.decisions),
  }
}

function mapClosed(s: any, now: Date): Run {
  return {
    id: s.run_id,
    title: s.title,
    mode: s.mode,
    repo: s.repo_url ?? '',
    stageIdx: Math.max(0, CANONICAL_STAGES.indexOf(s.terminal_stage ?? '')),
    status: closedStatus(s.outcome),
    blocker: '',
    cost: s.cost_usd_total,
    budget: s.budget_usd,
    age: age(s.started_at, now),
    decisions: [],
  }
}

function mapPending(runId: string, p: any, now: Date): InboxItem {
  const base = { id: p.key, runId, round: p.round ?? 1, age: age(p.opened_at, now) }
  if (p.kind === 'clarify') {
    return {
      ...base, type: 'clarify', title: p.question, body: p.why_it_matters,
      suggestion: p.suggested_answer ?? '',
    } as ClarifyItem
  }
  if (p.kind === 'merge_gate') {
    return {
      ...base, type: 'override', gate: 'merge',
      title: `Merge gate — round ${p.round}`,
      body: 'Merging requires an audited human override (FR-106).',
      verdict: p.verdict ?? '',
      checks: (p.checks ?? []).map((c: any) => ({
        // CheckClass is lowercase on the wire ("absolute"); CheckRow.kind is
        // uppercase. Normalize here, not by widening the TS union.
        name: c.name, ok: c.passed, detail: c.detail,
        kind: String(c.classification).toUpperCase(),
      })),
    } as OverrideItem
  }
  if (p.kind === 'task_escalation') {
    return {
      ...base, type: 'escalation',
      title: `${p.task_id} — resolver exhausted (${p.attempts})`,
      body: `Task ${p.task_id} could not be closed by the fix loop.`,
      analysis: p.analysis ?? '',
    } as EscalationItem
  }
  return {
    ...base, type: 'gate', gate: p.gate,
    title: `${p.gate} (round ${p.round})`, body: p.spec_summary ?? '',
  } as GateItem
}

export function mapSnapshot(snap: any, now: Date = new Date()): FleetState {
  const pendingByRun = new Map<string, any[]>()
  for (const r of snap.inbox ?? []) pendingByRun.set(r.run_id, r.pending)

  const runs = [
    ...(snap.runs ?? []).map((s: any) =>
      mapRun(s, (pendingByRun.get(s.run_id) ?? []).length, now)),
    ...(snap.closed ?? []).map((s: any) => mapClosed(s, now)),
  ]
  const inbox: InboxItem[] = []
  for (const r of snap.inbox ?? []) {
    for (const p of r.pending) inbox.push(mapPending(r.run_id, p, now))
  }
  const errors = (snap.errors ?? []).map((e: any) => ({
    runId: e.run_id, error: e.error,
  }))
  return { runs, inbox, errors }
}

export function createHttpApi(baseUrl = '/api'): DashboardApi {
  const json = async (path: string, init?: RequestInit) => {
    const r = await fetch(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
    if (!r.ok) throw new Error(`${init?.method ?? 'GET'} ${path}: ${r.status}`)
    return r.status === 204 ? null : r.json()
  }

  const snapshot = async (): Promise<FleetState> =>
    mapSnapshot(await json('/inbox'))

  const find = async (id: string) =>
    (await snapshot()).inbox.find((i) => i.id === id)

  const decide = async (id: string, outcome: GateOutcome, text: string) => {
    const it = await find(id)
    if (!it) return
    await json(`/runs/${encodeURIComponent(it.runId)}/decide`, {
      method: 'POST', body: JSON.stringify({ key: id, outcome, text }),
    })
  }

  return {
    async listRuns() { return (await snapshot()).runs },
    async getRun(id) { return (await snapshot()).runs.find((r) => r.id === id) },
    async listInbox() { return (await snapshot()).inbox },

    async answerClarify(id, answer) {
      const it = await find(id)
      if (!it) return
      await json(`/runs/${encodeURIComponent(it.runId)}/answer`, {
        method: 'POST', body: JSON.stringify({ key: id, text: answer }),
      })
    },
    decideGate: (id, outcome, comment) => decide(id, outcome, comment),
    overrideMerge: (id, approve, justification) =>
      decide(id, approve ? 'approve' : 'revise', justification),
    resolveEscalation: (id, retry, guidance) =>
      decide(id, retry ? 'approve' : 'reject', guidance),

    async startRun(input: StartRunInput) {
      const { run_id } = await json('/runs', {
        method: 'POST',
        body: JSON.stringify({
          title: input.title, description: input.description,
          mode: input.mode, repo: input.repo,
        }),
      })
      const run = (await snapshot()).runs.find((r) => r.id === run_id)
      if (!run) throw new Error(`started ${run_id} but it is not in the fleet`)
      return run
    },

    subscribe(cb) {
      const es = new EventSource(`${baseUrl}/events`)
      es.onmessage = (e) => cb(mapSnapshot(JSON.parse(e.data)))
      return () => es.close()
    },
  }
}
