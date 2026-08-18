export type Status = 'running' | 'blocked' | 'failed' | 'done'
export type GateOutcome = 'approve' | 'revise' | 'reject'
export type ProjectMode = 'brownfield' | 'greenfield'

export interface Decision {
  ts: string
  gate: string
  outcome: GateOutcome
  comment: string
  decider: string
}

export interface Run {
  id: string
  title: string
  mode: ProjectMode
  repo: string
  stageIdx: number
  status: Status
  blocker: string
  cost: number | null
  budget: number | null
  age: string
  decisions: Decision[]
}

export interface ClarifyItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'clarify'
  title: string
  body: string
  suggestion: string
}

export interface GateItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'gate'
  gate: string
  title: string
  body: string
}

export interface CheckRow {
  name: string
  kind: 'ABSOLUTE' | 'ADVISORY'
  ok: boolean
  detail: string
}

export interface OverrideItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'override'
  gate: 'merge'
  title: string
  body: string
  verdict: string
  checks: CheckRow[]
}

export interface EscalationItem {
  id: string
  runId: string
  round: number
  age: string
  type: 'escalation'
  title: string
  body: string
  analysis: string
}

export type InboxItem =
  | ClarifyItem
  | GateItem
  | OverrideItem
  | EscalationItem

export interface StartRunInput {
  title: string
  description: string
  repo: string
  mode: ProjectMode
}

export interface FleetState {
  runs: Run[]
  inbox: InboxItem[]
  errors: { runId: string; error: string }[]
}

export interface DashboardApi {
  listRuns(): Promise<Run[]>
  getRun(id: string): Promise<Run | undefined>
  listInbox(): Promise<InboxItem[]>
  answerClarify(id: string, answer: string): Promise<void>
  decideGate(id: string, outcome: GateOutcome, comment: string): Promise<void>
  overrideMerge(id: string, approve: boolean, justification: string): Promise<void>
  resolveEscalation(id: string, retry: boolean, guidance: string): Promise<void>
  startRun(input: StartRunInput): Promise<Run>
  subscribe(cb: (s: FleetState) => void): () => void
}
