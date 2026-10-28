// 018 T049 (data-model §3.2, R-14): camelCase mirrors of the read-route
// wire models (§2), one per route. Mappers live in http-read.ts; mocks live
// in api/mock/<route>.ts.

export interface Arm {
  harness: string | null
  model: string | null
}

export interface Traversal {
  edge: { source: string; sourcePort: string; target: string; targetPort: string }
  used: number
  max: number | null
}

export interface GateTimeout {
  gate: string
  onTimeout: string
}

export interface FleetRunSummary {
  runId: string
  graphSha: string | null
  graphName: string | null
  arm: Arm | null
  traversals: Traversal[]
  outcome: { state: string; reason: string | null; result: string | null } | null
  where: string[]
  gateTimeouts: GateTimeout[]
}

export interface FleetSummary {
  runs: FleetRunSummary[]
  unreadable: string[]
}
