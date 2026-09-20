import type {
  CatalogWire, GraphResponse, GraphStateResponse, GraphWire, LoadWire, ParseWire, SaveWire,
  SerializeWire, ValidationWire,
} from './graph-types'
import type { DotState } from '@kroker/ui/components/stage_dots/StageDots.vue'

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
  // Canonical stage NAMES (E-76 spec §5.8): a graph can fan out, so more
  // than one may be active. Never an index -- see adapters/fleet.ts.
  activeStages: string[]
  // E-75 §8 / E-76 §9.1 rule 1: a graph run's stage marks, served by the
  // snapshot (RunState.stage_marks open; closed_marks[run_id] closed) and
  // rendered verbatim by the strip. Null = no marks (FeatureWorkflow and
  // not-yet-dispatched runs) = the linear activeStages fallback, unchanged.
  stageMarks: Record<string, DotState> | null
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
  answerClarify(runId: string, key: string, answer: string): Promise<void>
  decideGate(runId: string, key: string, outcome: GateOutcome, comment: string): Promise<void>
  overrideMerge(runId: string, key: string, approve: boolean, justification: string): Promise<void>
  resolveEscalation(runId: string, key: string, retry: boolean, guidance: string): Promise<void>
  startRun(input: StartRunInput): Promise<Run>
  subscribe(cb: (s: FleetState) => void): () => void

  // Graph surface (E-76 spec §7.1). A method whose capability is false in
  // getCatalog() throws CapabilityUnavailable; views gate on capabilities.
  getCatalog(): Promise<CatalogWire>
  parseGraph(input: { yaml: string } | { graph: GraphWire }): Promise<ParseWire>
  serializeGraph(graph: GraphWire): Promise<SerializeWire>
  validateGraph(graph: GraphWire): Promise<ValidationWire>
  saveGraph(graph: GraphWire): Promise<SaveWire>
  loadGraph(sha: string): Promise<LoadWire>
  getRunGraph(runId: string): Promise<GraphResponse>
  subscribeGraphState(runId: string, cb: (s: GraphStateResponse) => void, onError?: (failures: number) => void): () => void
}
