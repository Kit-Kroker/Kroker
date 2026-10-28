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

// 018 T061 (data-model §2.2, R-7): the shipped-graphs read.

export interface ShippedGraph {
  name: string
  sha: string
  description: string | null
  when: string | null
  counts: { label: string; n: number }[]
}

export type ConfigCheckState = 'pass' | 'fail' | 'off'

export interface ConfigCheck {
  name: string
  state: ConfigCheckState
  text: string
}

export interface ConfigRow {
  k: string
  v: string | null // null renders `not measured`
}

export interface ConfigSection {
  title: string
  note: string
  rows: ConfigRow[]
}

export interface ShippedGraphs {
  graphs: ShippedGraph[]
  checks: ConfigCheck[]
  sections: ConfigSection[]
}
