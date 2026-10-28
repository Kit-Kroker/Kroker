// 018 T049 (read-routes rule 4): the recorded fixtures are the contract;
// these mappers turn the snake_case wire into the camelCase mirrors of
// read-types.ts, exactly as the fixtures shape them.
import type {
  Arm,
  FleetRunSummary,
  FleetSummary,
  GateTimeout,
  ShippedGraph,
  ShippedGraphs,
  Traversal,
} from './read-types'

type Wire = Record<string, unknown>

const arm = (raw: Wire | null | undefined): Arm | null =>
  raw ? { harness: (raw.harness as string | null) ?? null, model: (raw.model as string | null) ?? null } : null

const traversal = (raw: Wire): Traversal => {
  const e = raw.edge as Wire
  return {
    edge: {
      source: e.source as string,
      sourcePort: e.source_port as string,
      target: e.target as string,
      targetPort: e.target_port as string,
    },
    used: raw.used as number,
    max: (raw.max as number | null) ?? null,
  }
}

const gateTimeout = (raw: Wire): GateTimeout => ({
  gate: raw.gate as string,
  onTimeout: raw.on_timeout as string,
})

export function mapFleetSummary(raw: Wire): FleetSummary {
  return {
    runs: (raw.runs as Wire[]).map(
      (r): FleetRunSummary => ({
        runId: r.run_id as string,
        graphSha: (r.graph_sha as string | null) ?? null,
        graphName: (r.graph_name as string | null) ?? null,
        arm: arm(r.arm as Wire | null),
        traversals: (r.traversals as Wire[]).map(traversal),
        outcome:
          (r.outcome as { state: string; reason: string | null; result: string | null } | null) ?? null,
        where: (r.where as string[]) ?? [],
        gateTimeouts: ((r.gate_timeouts as Wire[]) ?? []).map(gateTimeout),
      }),
    ),
    unreadable: (raw.unreadable as string[]) ?? [],
  }
}

// 018 T061 (data-model §2.2, R-7): the shipped-graphs read. The graph rows
// gain their card counts (nodes/gates/edges); checks and sections pass
// through as served - their text is the panel's copy, verbatim.
export function mapShippedGraphs(raw: Wire): ShippedGraphs {
  return {
    graphs: (raw.graphs as Wire[]).map(
      (g): ShippedGraph => ({
        name: g.name as string,
        sha: g.sha as string,
        description: (g.description as string | null) ?? null,
        when: (g.when as string | null) ?? null,
        counts: [
          { label: 'nodes', n: g.nodes as number },
          { label: 'gates', n: g.gates as number },
          { label: 'edges', n: g.edges as number },
        ],
      }),
    ),
    checks: raw.checks as ShippedGraphs['checks'],
    sections: raw.sections as ShippedGraphs['sections'],
  }
}
