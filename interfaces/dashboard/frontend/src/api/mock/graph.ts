// The mock's graph surface (E-76 spec D4, §7.2): a RECORDING, not a
// simulator. Catalog, parse and serialize answers were produced by the real
// Python (scripts/dump_graph_fixtures.py); validation and run state are the
// E-75 RECORDED projections (run_state/*.recorded.json) -- the FINAL wire
// the TS mirror parses. Anything unrecorded is answered as unrecorded --
// never as success -- so Playwright cannot pass on behaviour nothing real
// produced. The only hand-written part is the run script's TRANSITION table
// (which recorded state follows a gate decision) -- mock logic over
// Python-recorded states, no production semantics (canvas-run-mode gate
// ruling 3, 2026-09-20).
import type { DashboardApi, GateOutcome } from '../types'
import type {
  CatalogWire, GraphResponse, GraphStateResponse, GraphWire, ParseWire, ValidationWire,
} from '../graph-types'
import catalogJson from '../__fixtures__/graph/catalog.json'
import graphResponseJson from '../__fixtures__/graph/run_state/graph_response.recorded.json'
import graphStateJson from '../__fixtures__/graph/run_state/graph_state.recorded.json'
import validationRecorded from '../__fixtures__/graph/run_state/validation.recorded.json'

interface Scenario { name: string; yaml: string; parse: ParseWire; serialize: { ok: true; yaml: string } | null }
interface ObjectRecording { name: string; base: string; graph: GraphWire; parse: ParseWire }
interface ScriptState { state: GraphStateResponse; on: Partial<Record<GateOutcome, string>> }
interface RunScript { initial: string; states: Record<string, ScriptState> }

const scenarioModules = import.meta.glob('../__fixtures__/graph/scenarios/*.json', { eager: true, import: 'default' })
const objectModules = import.meta.glob('../__fixtures__/graph/objects/*.json', { eager: true, import: 'default' })
const SCENARIOS = Object.values(scenarioModules) as Scenario[]
const OBJECTS = Object.values(objectModules) as ObjectRecording[]

// The recorded validation is pre_code's (validation + executable problems,
// E-75 §7.3); it answers the pre_code scenario, everything else is
// unrecorded.
const VALIDATION: Record<string, ValidationWire> = {
  pre_code: validationRecorded as unknown as ValidationWire,
}

const RECORDED_RESPONSE = graphResponseJson as unknown as GraphResponse
const RECORDED_STATES = graphStateJson as unknown as Record<string, GraphStateResponse>

const RUN_SCRIPTS: Record<string, RunScript> = {
  // The recorded blocked_at_architecture run: the pending architecture#1
  // gate approves to the recorded completed state, rejects to the recorded
  // rejected one. Terminal states have no outgoing transitions.
  'feature-graph-demo': {
    initial: 'blocked_at_architecture',
    states: {
      blocked_at_architecture: {
        state: RECORDED_STATES.blocked_at_architecture,
        on: { approve: 'completed', reject: 'rejected_at_architecture' },
      },
      completed: { state: RECORDED_STATES.completed, on: {} },
      rejected_at_architecture: { state: RECORDED_STATES.rejected_at_architecture, on: {} },
    },
  },
}

// A LOOKUP KEY ONLY: object keys sorted, arrays untouched. Never a sha, never
// a canonical form, never exported (pinned by mock/graph.test.ts).
function lookupKey(value: unknown): string {
  if (value === undefined || value === null) return ''
  const norm = (v: unknown): unknown =>
    Array.isArray(v)
      ? v.map(norm)
      : v !== null && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, norm((v as Record<string, unknown>)[k])]))
        : v
  return JSON.stringify(norm(value)) ?? ''
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

const UNRECORDED_VALIDATION: ValidationWire = {
  issues: [{ code: 'mock.unrecorded', severity: 'warning', message: 'mock: no recorded validation for this graph', target: { kind: 'graph' } }],
  back_edges: [],
}

type GraphApi = Pick<
  DashboardApi,
  | 'getCatalog' | 'parseGraph' | 'serializeGraph' | 'validateGraph' | 'saveGraph'
  | 'loadGraph' | 'getRunGraph' | 'subscribeGraphState'
>

export interface MockGraph extends GraphApi {
  /** Advance a scripted graph run after mock decideGate succeeded. */
  onDecision(runId: string, key: string, outcome: GateOutcome): void
  /** The seeded run ids that execute a graph. */
  graphRunIds(): string[]
}

export function createMockGraph(): MockGraph {
  const byText = new Map(SCENARIOS.map((s) => [s.yaml, s]))
  const byGraph = new Map<string, { parse: ParseWire; base: string }>()
  for (const s of SCENARIOS) if (s.parse.ok) byGraph.set(lookupKey(s.parse.graph), { parse: s.parse, base: s.name })
  for (const o of OBJECTS) byGraph.set(lookupKey(o.graph), { parse: o.parse, base: o.base })
  const serialized = new Map<string, string>()
  for (const s of SCENARIOS) if (s.parse.ok && s.serialize) serialized.set(lookupKey(s.parse.graph), s.serialize.yaml)

  let scenario: string | null = null
  let savedSeq = 0
  const saved = new Map<string, GraphWire>()
  const runState = new Map<string, string>(Object.entries(RUN_SCRIPTS).map(([id, s]) => [id, s.initial]))
  const listeners = new Map<string, Set<(s: GraphStateResponse) => void>>()

  const catalog: CatalogWire = {
    ...(catalogJson as unknown as CatalogWire),
    // The mock exercises every flow regardless of what the recording
    // declares (the shipped catalog's capabilities track the server's
    // rollout, not the mock's coverage).
    capabilities: { validate: true, save: true, load: true, run_graph: true },
  }

  const nearest = (key: string) => {
    if (!key) return ''
    let best = ''
    let bestLen = -1
    for (const k of byGraph.keys()) {
      let i = 0
      while (i < k.length && i < key.length && k[i] === key[i]) i++
      if (i > bestLen) { bestLen = i; best = byGraph.get(k)!.base }
    }
    return best
  }

  const stateOf = (runId: string): GraphStateResponse => {
    const script = RUN_SCRIPTS[runId]
    if (!script) return { kind: 'no_graph', reason: 'legacy_run' }
    return clone(script.states[runState.get(runId)!].state)
  }

  return {
    async getCatalog() { return clone(catalog) },

    async parseGraph(input: { yaml: string } | { graph: GraphWire }) {
      if (!input || typeof input !== 'object') {
        return { ok: false, shape_errors: [{ loc: [], msg: 'mock: invalid input', line: null, column: null }] }
      }
      if ('yaml' in input && typeof input.yaml === 'string') {
        const hit = byText.get(input.yaml)
        if (!hit) return { ok: false, shape_errors: [{ loc: [], msg: 'mock: unrecorded input', line: null, column: null }] }
        scenario = hit.name
        return clone(hit.parse)
      }
      if ('graph' in input && input.graph && typeof input.graph === 'object') {
        const key = lookupKey(input.graph)
        const hit = byGraph.get(key)
        if (!hit) {
          console.warn(`mock parseGraph: unrecorded graph (nearest recording: ${nearest(key)})`, key)
          return { ok: false, shape_errors: [{ loc: [], msg: 'mock: unrecorded graph', line: null, column: null }] }
        }
        scenario = hit.base
        return clone(hit.parse)
      }
      return { ok: false, shape_errors: [{ loc: [], msg: 'mock: neither yaml nor graph provided', line: null, column: null }] }
    },

    async serializeGraph(graph) {
      const yaml = serialized.get(lookupKey(graph)) ?? JSON.stringify(graph, null, 2)
      return { ok: true, yaml }
    },

    async validateGraph() {
      const hit = scenario ? VALIDATION[scenario] : undefined
      return clone(hit ?? UNRECORDED_VALIDATION)
    },

    async saveGraph(graph) {
      const hit = byGraph.get(lookupKey(graph))
      const sha = hit && hit.parse.ok ? hit.parse.sha : `mock-sha-${++savedSeq}`
      saved.set(sha, clone(graph))
      return { ok: true, sha, validation: clone(scenario ? VALIDATION[scenario] ?? UNRECORDED_VALIDATION : UNRECORDED_VALIDATION) }
    },

    async loadGraph(sha) {
      const graph = saved.get(sha)
      return graph ? { ok: true, sha, graph: clone(graph) } : { ok: false, reason: 'not_found' }
    },

    async getRunGraph(runId): Promise<GraphResponse> {
      // The recorded run graph of the shipped default pipeline (E-75 §7.1).
      if (!RUN_SCRIPTS[runId]) return { kind: 'no_graph', reason: 'legacy_run' }
      return clone(RECORDED_RESPONSE)
    },

    subscribeGraphState(runId, cb) {
      // Deliver now and on every scripted transition; no timer, so a
      // Playwright flow is deterministic.
      const set = listeners.get(runId) ?? new Set()
      listeners.set(runId, set)
      set.add(cb)
      queueMicrotask(() => { if (set.has(cb)) cb(stateOf(runId)) })
      return () => { set.delete(cb) }
    },

    onDecision(runId, key, outcome) {
      const script = RUN_SCRIPTS[runId]
      if (!script) return
      const current = script.states[runState.get(runId)!]
      const pending = current.state.kind === 'state' && current.state.pending.some((p) => p.key === key)
      const next = current.on[outcome]
      if (!pending || !next) return
      runState.set(runId, next)
      for (const listener of listeners.get(runId) ?? []) listener(stateOf(runId))
    },

    graphRunIds() { return Object.keys(RUN_SCRIPTS) },
  }
}
