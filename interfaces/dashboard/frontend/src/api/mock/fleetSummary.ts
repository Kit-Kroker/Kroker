// 018 T049 (R-14): the fleet-summary mock, shaped by the recorded fixture
// (F/api/__fixtures__/read/fleet-summary.json) over the mock's own seeded
// runs — the graph-script runs carry the default graph and the dev arm, the
// rest are legacy rows.
import type { FleetRunSummary, FleetSummary } from '../read-types'

const GRAPH_RUN_IDS = new Set([
  'feature-graph-demo',
  'feature-halted-demo',
  'feature-escalated-demo',
  'feature-multisink-demo',
  'feature-retired-demo',
  'feature-budget-demo',
])

// 018 T050: the outcome fixtures mirror their graph scripts (mock/graph.ts)
// — the halted run reads its failed result string, the budget fixture its
// rejected one (quickstart 2, FR-041). Everything else is in flight.
const OUTCOMES: Record<string, FleetRunSummary['outcome']> = {
  'feature-halted-demo': { state: 'failed', reason: null, result: 'failed:quarantined-tasks' },
  'feature-budget-demo': { state: 'rejected', reason: null, result: 'rejected:budget' },
}

const DEFAULT_SHA = 'a021c25b8f7e012faaf9f4de9664d8cc5b11a977c1b878e20d50cfec78b23c38'

const BOUNDED = [
  {
    edge: { source: 'architecture', sourcePort: 'revise', target: 'architect', targetPort: 'guidance' },
    used: 0,
    max: 2,
  },
  {
    edge: { source: 'plan', sourcePort: 'revise', target: 'planner', targetPort: 'guidance' },
    used: 0,
    max: 2,
  },
]

const ARM = { harness: 'opencode', model: 'zai-coding-plan/glm-5.3' }

export function mockFleetSummary(runIds: string[]): FleetSummary {
  const runs: FleetRunSummary[] = runIds.map((runId) => {
    if (!GRAPH_RUN_IDS.has(runId)) {
      return {
        runId,
        graphSha: null,
        graphName: null,
        arm: null,
        traversals: [],
        outcome: null,
        where: [],
        gateTimeouts: [],
      }
    }
    return {
      runId,
      graphSha: DEFAULT_SHA,
      graphName: 'default',
      arm: ARM,
      traversals: BOUNDED,
      outcome: OUTCOMES[runId] ?? { state: 'running', reason: null, result: null },
      where: [],
      gateTimeouts: [],
    }
  })
  return { runs, unreadable: [] }
}
