// 018 T049 (read-routes rule 4): the recorded fixtures are the contract;
// these mappers turn the snake_case wire into the camelCase mirrors of
// read-types.ts, exactly as the fixtures shape them.
import type {
  AdapterFact,
  Arm,
  CellState,
  Compare,
  CompareArm,
  CompareCell,
  FleetRunSummary,
  FleetSummary,
  GateTimeout,
  HeatCell,
  InterfaceMatrix,
  MatrixCell,
  MatrixColumn,
  MatrixRow,
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

// 018 T072 (data-model §2.4, R-9): the compare read. Nulls stay null -
// an unpriced arm is `not measured`, never a folded-in zero. The mapper
// is idempotent: the raw snake_case wire or an already-mapped shape both
// map cleanly (the view maps whatever its api hands it; the mock
// pre-maps from the same fixture).
const pick = <T,>(raw: Wire, snake: string, camel: string): T | null =>
  ((raw[snake] ?? raw[camel]) as T | null | undefined) ?? null

export function mapCompare(raw: Wire): Compare {
  return {
    available: (pick<boolean>(raw, 'available', 'available')) ?? false,
    root: pick<string>(raw, 'root', 'root') ?? '',
    description: pick<string>(raw, 'description', 'description'),
    graphs: (raw.graphs as string[]) ?? [],
    arms: (raw.arms as Wire[]).map(
      (a): CompareArm => ({
        name: a.name as string,
        harness: (a.harness as string) ?? '',
        model: (a.model as string) ?? '',
        note: pick<string>(a, 'note', 'note'),
        cells: (a.cells as Wire[]).map(
          (c): CompareCell => ({
            graph: c.graph as string,
            sc: pick<number>(c, 'sc', 'sc'),
            costPerCase: pick<number>(c, 'cost_per_case', 'costPerCase'),
          }),
        ),
      }),
    ),
    heatColumns: (pick<string[]>(raw, 'heat_columns', 'heatColumns')) ?? [],
    heatRows: ((pick<Wire[]>(raw, 'heat_rows', 'heatRows')) ?? []).map((r) => ({
      name: r.name as string,
      cells: (r.cells as Wire[]).map(
        (c): HeatCell => ({
          state: c.state as HeatCell['state'],
          value: pick<number>(c, 'value', 'value'),
          n: (pick<number>(c, 'n', 'n')) ?? 0,
        }),
      ),
    })),
  }
}

// 018 T079 (data-model §2.3, R-8): the interfaces read. The wire is
// camelCase already - the mirror spells nothing of its own, and the
// cell state keeps the wire's 'not_measured'.
export function mapInterfaces(raw: Wire): InterfaceMatrix {
  return {
    columns: (raw.columns as Wire[]).map(
      (c): MatrixColumn => ({
        key: c.key as string,
        name: c.name as string,
        ref: c.ref as string,
      }),
    ),
    rows: (raw.rows as Wire[]).map(
      (r): MatrixRow => ({
        harness: r.harness as string,
        sub: (r.sub as string) ?? '',
        planned: (r.planned as boolean) ?? false,
        cells: (r.cells as Wire[]).map(
          (c): MatrixCell => ({
            state: c.state as CellState,
            text: (c.text as string) ?? '',
          }),
        ),
      }),
    ),
    facts: (raw.facts as Wire[]).map(
      (f): AdapterFact => ({
        who: f.who as string,
        severity: f.severity as AdapterFact['severity'],
        text: f.text as string,
      }),
    ),
  }
}
