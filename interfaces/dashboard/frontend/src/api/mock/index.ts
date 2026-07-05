import type {
  DashboardApi,
  GateOutcome,
  Run,
  InboxItem,
  ClarifyItem,
  GateItem,
  OverrideItem,
  EscalationItem,
  StartRunInput,
} from '../types'

export function tickCosts(runs: Run[]): Run[] {
  return runs.map((r) =>
    r.status === 'running'
      ? { ...r, cost: +(r.cost + 0.02 + Math.random() * 0.06).toFixed(2) }
      : r,
  )
}

function seedRuns(): Run[] {
  return [
    {
      id: 'feature-add-sso',
      title: 'Add SSO to customer portal',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 4,
      status: 'blocked',
      blocker: 'clarify gate — 2 questions',
      cost: 3.12,
      budget: 40,
      age: '2h 14m',
      skipCtx: false,
      stageNote: 'clarify: 2 low-confidence questions routed to human (gate round 1). 4 others auto-answered ≥ 0.95.',
      decisions: [
        { ts: '09:12', gate: 'clarify r1 (partial)', outcome: 'approve', comment: '4 questions auto-answered, confidence ≥ 0.95', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'feature-billing-webhooks',
      title: 'Outbound webhooks for billing events',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      stageIdx: 11,
      status: 'blocked',
      blocker: 'merge gate — advisory: coverage',
      cost: 18.4,
      budget: 60,
      age: '9h 03m',
      skipCtx: false,
      stageNote: 'quality_gate: absolutes green · advisory diff coverage 0.68 < 0.80 — awaiting human GateDecision.',
      decisions: [
        { ts: '02:20', gate: 'architecture r1', outcome: 'approve', comment: 'delta grounded in CodebaseMap', decider: 'human · mika' },
        { ts: '03:05', gate: 'plan r1', outcome: 'approve', comment: '7 tasks / 3 waves, DAG valid', decider: 'policy (soft)' },
        { ts: '08:44', gate: 'task T-04 repair', outcome: 'approve', comment: 'review fix loop 1/2 green', decider: 'policy' },
      ],
    },
    {
      id: 'feature-onboarding-v2',
      title: 'Self-serve onboarding flow (new service)',
      mode: 'greenfield',
      repo: 'git@github.com:acme/onboard',
      stageIdx: 7,
      status: 'running',
      blocker: '',
      cost: 9.75,
      budget: 50,
      age: '4h 41m',
      skipCtx: true,
      stageNote: 'code: wave 2/3 — 4 tasks in flight in isolated worktrees, cut from integration head (ADR-14).',
      decisions: [
        { ts: '11:02', gate: 'clarify r1', outcome: 'approve', comment: 'all suggestions accepted', decider: 'human · sam' },
        { ts: '11:38', gate: 'architecture r1', outcome: 'revise', comment: 'split auth from profile service', decider: 'human · sam' },
        { ts: '12:19', gate: 'architecture r2', outcome: 'approve', comment: '', decider: 'human · sam' },
        { ts: '12:31', gate: 'plan r1', outcome: 'approve', comment: 'confidence 0.97', decider: 'policy (soft)' },
      ],
    },
    {
      id: 'fix-rate-limit-retry',
      title: 'Fix: retry budget exhausted under burst load',
      mode: 'brownfield',
      repo: 'git@github.com:acme/gateway',
      stageIdx: 10,
      status: 'blocked',
      blocker: 'escalation — T-07 resolver 3/3',
      cost: 6.2,
      budget: 30,
      age: '6h 27m',
      skipCtx: false,
      stageNote: 'qa: T-07 red after 3 resolver attempts — escalated to human (retry-with-guidance | quarantine).',
      decisions: [{ ts: '13:15', gate: 'plan r1', outcome: 'approve', comment: '', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-usage-metering',
      title: 'Usage metering for billing tiers',
      mode: 'brownfield',
      repo: 'git@github.com:acme/billing',
      stageIdx: 5,
      status: 'blocked',
      blocker: 'architecture gate — round 1',
      cost: 2.05,
      budget: 45,
      age: '1h 02m',
      skipCtx: false,
      stageNote: 'architecture: delta spec awaiting approval (adds MeteringService; 3 contracts added, 0 removed).',
      decisions: [{ ts: '14:30', gate: 'clarify r1', outcome: 'approve', comment: 'auto, confidence 0.96', decider: 'policy (soft)' }],
    },
    {
      id: 'feature-audit-export',
      title: 'Audit-trail export (events.jsonl + report)',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 13,
      status: 'running',
      blocker: '',
      cost: 14.02,
      budget: 40,
      age: '11h 50m',
      skipCtx: false,
      stageNote: 'retro: RunSummary building; learnings retained to Hindsight.',
      decisions: [
        { ts: '05:12', gate: 'merge r1', outcome: 'approve', comment: 'all checks green', decider: 'policy (soft)' },
        { ts: '06:01', gate: 'deploy r1', outcome: 'approve', comment: 'PR #482 merged, staging deploy', decider: 'human · mika' },
      ],
    },
    {
      id: 'feature-dark-mode',
      title: 'Dark mode for settings pages',
      mode: 'brownfield',
      repo: 'git@github.com:acme/portal',
      stageIdx: 14,
      status: 'done',
      blocker: '',
      cost: 7.88,
      budget: 30,
      age: '1d 3h',
      skipCtx: false,
      stageNote: '',
      decisions: [
        { ts: 'yday', gate: 'merge r1', outcome: 'approve', comment: '', decider: 'policy (soft)' },
        { ts: 'yday', gate: 'deploy r1', outcome: 'approve', comment: '', decider: 'human · sam' },
      ],
    },
  ]
}

function seedInbox(): InboxItem[] {
  return [
    {
      id: 'q1',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q1 — Which identity protocol should SSO support?',
      confidence: '0.82',
      body: 'The repo has no auth-provider abstraction. Requirements mention "enterprise SSO" but not a protocol; the CodebaseMap shows session middleware in portal/auth/session.py.',
      suggestion: 'OIDC (Authorization Code + PKCE). It fits the existing session middleware; defer SAML to a follow-up run if an enterprise customer requires it.',
    },
    {
      id: 'q2',
      type: 'clarify',
      runId: 'feature-add-sso',
      round: 1,
      age: '38m',
      title: 'Q2 — Should password login remain enabled after SSO ships?',
      confidence: '0.74',
      body: 'US-1 is silent on migration. Disabling password auth immediately would lock out users whose IdP mapping fails on first login.',
      suggestion: 'Keep password auth behind a feature flag for 2 releases, then retire it once SSO adoption is > 95%.',
    },
    {
      id: 'g2',
      type: 'gate',
      gate: 'architecture',
      runId: 'feature-usage-metering',
      round: 1,
      age: '54m',
      title: 'Architecture (delta) — usage metering',
      body: 'Adds MeteringService (event ingest + hourly rollup), modifies billing-worker to emit usage events, adds 3 contracts (UsageEvent, MeterReading, TierQuota). No removals. Grounded in CodebaseMap @ a41c9e.',
    },
    {
      id: 'g1',
      type: 'override',
      gate: 'merge',
      runId: 'feature-billing-webhooks',
      round: 1,
      age: '1h 12m',
      title: 'Merge gate — advisory check needs a decision',
      body: 'All absolute checks pass. One advisory check fails; merging requires an audited human override (FR-106).',
      verdict: 'MergeVerdict 0.91 — approve. Uncovered lines are retry/backoff branches exercised indirectly by the integration suite; direct unit coverage would need an injected clock.',
      checks: [
        { name: 'lint', kind: 'ABSOLUTE', ok: true, detail: 'clean' },
        { name: 'security (critical)', kind: 'ABSOLUTE', ok: true, detail: '0 critical findings' },
        { name: 'build / integration', kind: 'ABSOLUTE', ok: true, detail: 'green · 4m12s' },
        { name: 'diff coverage', kind: 'ADVISORY', ok: false, detail: '0.68 — target 0.80' },
        { name: 'criterion→test traceability', kind: 'ADVISORY', ok: true, detail: '9/9 criteria mapped' },
        { name: 'review severity', kind: 'ADVISORY', ok: true, detail: 'max severity: medium' },
      ],
    },
    {
      id: 'e1',
      type: 'escalation',
      runId: 'fix-rate-limit-retry',
      round: 1,
      age: '2h 05m',
      title: 'T-07 "retry budget accounting" — resolver exhausted (3/3)',
      body: 'QA fix loop hit MAX_REPAIR_ATTEMPTS. The task branch stays parked on its worktree; wave 3 is holding.',
      analysis: 'test_retry_budget flakes on wall-clock timing. A reliable fix needs an injected clock in RateLimiter, but rate_limiter/core.py is outside the task’s declared file scope. Recommend widening scope or quarantining.',
    },
  ]
}

export interface MockOptions {
  simulateLive?: boolean
}

export function createMockApi(opts: MockOptions = {}): DashboardApi & { dispose(): void } {
  const simulateLive = opts.simulateLive ?? true
  let runs: Run[] = seedRuns()
  let inbox: InboxItem[] = seedInbox()

  const delay = () => new Promise<void>((r) => setTimeout(r, 120 + Math.random() * 180))

  const now = () => {
    const d = new Date()
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  }
  const patchRun = (id: string, patch: Partial<Run> | ((r: Run) => Partial<Run>)) => {
    runs = runs.map((r) => (r.id === id ? { ...r, ...(typeof patch === 'function' ? patch(r) : patch) } : r))
  }
  const addDecision = (runId: string, d: { ts?: string; gate: string; outcome: GateOutcome; comment?: string; decider?: string }) =>
    patchRun(runId, (r) => ({
      decisions: [...r.decisions, { ts: now(), decider: 'human · you', comment: '', ...d }],
    }))
  const removeItem = (id: string) => {
    inbox = inbox.filter((i) => i.id !== id)
  }
  const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

  const api: DashboardApi & { dispose(): void } = {
    async listRuns() {
      await delay()
      return clone(runs)
    },
    async getRun(id: string) {
      await delay()
      const r = runs.find((x) => x.id === id)
      return r ? clone(r) : undefined
    },
    async listInbox() {
      await delay()
      return clone(inbox)
    },

    async answerClarify(id: string, answer: string) {
      await delay()
      const it = inbox.find((i) => i.id === id) as ClarifyItem | undefined
      if (!it) return
      removeItem(id)
      addDecision(it.runId, {
        gate: `clarify Q${it.id.slice(1)} r${it.round}`,
        outcome: 'approve',
        comment: answer.length > 60 ? answer.slice(0, 57) + '…' : answer,
      })
      const left = inbox.some((i) => i.runId === it.runId && i.type === 'clarify')
      if (!left) {
        patchRun(it.runId, { status: 'running', stageIdx: 5, blocker: '', stageNote: 'architecture: drafting delta spec from Clarifications @ r1.' })
      }
    },

    async decideGate(id: string, outcome: GateOutcome, comment: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'gate') as GateItem | undefined
      if (!it) return
      removeItem(id)
      addDecision(it.runId, { gate: `${it.gate} r${it.round}`, outcome, comment })
      if (outcome === 'approve') {
        patchRun(it.runId, (r) => ({ status: 'running', stageIdx: r.stageIdx + 1, blocker: '', stageNote: 'gate approved — pipeline resumed.' }))
      } else if (outcome === 'revise') {
        patchRun(it.runId, { status: 'running', blocker: `revising — round ${it.round + 1}`, stageNote: `revise: producing stage re-entered with your comments (round ${it.round + 1} of MAX_GATE_ROUNDS=2).` })
      } else {
        patchRun(it.runId, { status: 'failed', blocker: `rejected at ${it.gate}`, stageNote: 'branch abandoned — rejection recorded with identity + timestamp.' })
      }
    },

    async overrideMerge(id: string, approve: boolean, justification: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'override') as OverrideItem | undefined
      if (!it) return
      removeItem(id)
      if (approve) {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'approve', comment: `ADVISORY OVERRIDE: ${justification}`, decider: 'human · you (override)' })
        patchRun(it.runId, { status: 'running', stageIdx: 12, blocker: '', stageNote: 'deploy: DeployPlan proposed — PR opened against main.' })
      } else {
        addDecision(it.runId, { gate: `merge r${it.round}`, outcome: 'revise', comment: justification || 'raise diff coverage to 0.80' })
        patchRun(it.runId, { status: 'running', stageIdx: 7, blocker: 'revising — coverage', stageNote: 'code: developer session resumed to add coverage for retry/backoff branches.' })
      }
    },

    async resolveEscalation(id: string, retry: boolean, guidance: string) {
      await delay()
      const it = inbox.find((i) => i.id === id && i.type === 'escalation') as EscalationItem | undefined
      if (!it) return
      removeItem(id)
      if (retry) {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'approve', comment: `retry w/ guidance: ${guidance || '(none)'}` })
        patchRun(it.runId, { status: 'running', blocker: 'repair attempt 4 (guided)', stageNote: 'qa: resolver resumed same harness session with your guidance.' })
      } else {
        addDecision(it.runId, { gate: 'escalation T-07', outcome: 'reject', comment: guidance ? `quarantined: ${guidance}` : 'quarantined' })
        patchRun(it.runId, { status: 'running', blocker: 'T-07 quarantined', stageNote: 'qa: T-07 quarantined; remaining tasks proceed — plan marked partial.' })
      }
    },

    async startRun(input: StartRunInput) {
      await delay()
      const t = input.title.trim()
      const id = 'feature-' + t
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .split('-')
        .slice(0, 4)
        .join('-')
      const run: Run = {
        id,
        title: t,
        mode: input.mode,
        repo: input.repo || 'git@github.com:acme/portal',
        stageIdx: 3,
        status: 'running',
        blocker: '',
        cost: 0.04,
        budget: 40,
        age: 'just now',
        skipCtx: input.mode === 'greenfield',
        stageNote: 'requirements: Product agent drafting stories from IdeaBrief.',
        decisions: [],
      }
      runs = [run, ...runs]
      return clone(run)
    },

    dispose() {
      if (timer) clearInterval(timer)
    },
  }

  let timer: ReturnType<typeof setInterval> | null = null
  if (simulateLive && typeof window !== 'undefined') {
    timer = setInterval(() => {
      runs = tickCosts(runs)
    }, 4000)
  }

  return api
}
