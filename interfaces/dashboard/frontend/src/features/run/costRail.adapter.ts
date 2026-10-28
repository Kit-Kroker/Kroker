import { BUDGET_SCOPE_NOTE, priceLabel, rowPrice, totalPrice } from '../../shared/cost'
import { money, tokens } from '../../shared/format'
import type { Run } from '../../api/types'
import type { GraphStateResponse, GraphWire } from '../../api/graph-types'
import { sameEdge } from '../../api/graph-types'

// 018 T027/T028 (FR-015a, S16, R-5a): the rail's Cost section model. Every
// spec-011 CostTab fact is ported here — dollars still reach the screen only
// through shared/cost's price rules; the stage group sums NodeRunState
// cost_usd by canonical_stage on open runs, and closed runs read "not
// measured" (no record-vocabulary mapping is invented, R-9).

export interface CostRoleRow {
  role: string
  model: string
  calls: number
  tokens: string
  price: string
}

export interface CostStageRow {
  stage: string
  price: string
}

export interface CostReviseRow {
  edge: string
  used: number
  max: number
  exhausted: boolean
}

export interface CostBudgetFigures {
  amount: string
  threshold: string | null
  counted: string | null
  pct: string | null
  crossings: number
  note: string
}

export interface CostRail {
  roleRows: CostRoleRow[]
  totalTokens: string
  totalPrice: string
  noBreakdown: boolean
  stageMeasured: boolean
  stageRows: CostStageRow[]
  reviseRows: CostReviseRow[]
  budget: CostBudgetFigures | null
  noBudgetSentence: string | null
}

export const NO_BUDGET_SENTENCE =
  'No budget. Set one when starting a run (--budget-usd or the start form).'

export function costRailOf(
  run: Run,
  opts: { canonicalStages: readonly string[]; graph?: GraphWire | null; state?: GraphStateResponse | null },
): CostRail {
  const state = opts.state && opts.state.kind === 'state' ? opts.state : null
  const closed = run.status !== 'running'
  // Defensive: an older wire shape may omit roles; it means none.
  const roles = run.roles ?? []

  const roleRows: CostRoleRow[] = roles.map((r) => ({
    role: r.role,
    model: r.model,
    calls: r.calls,
    tokens: `${tokens(r.inputTokens)} ${tokens(r.outputTokens)} ${tokens(r.cacheReadTokens)} ${tokens(r.cacheWriteTokens)}`,
    price: priceLabel(rowPrice(r)),
  }))
  const total = totalPrice(roles, run.cost)

  // R-5a: open runs group per-node cost by canonical stage; a closed run's
  // record-vocabulary stages have no canonical mapping, so nothing is
  // measured and nothing is invented.
  const stageRows: CostStageRow[] = []
  if (!closed && state) {
    for (const stage of opts.canonicalStages) {
      const usd = Object.values(state.nodes)
        .filter((n) => n.canonical_stage === stage && n.cost_usd !== null)
        .reduce((a, n) => a + (n.cost_usd as number), 0)
      const measured = Object.values(state.nodes).some((n) => n.canonical_stage === stage && n.cost_usd !== null)
      if (measured) stageRows.push({ stage, price: money(usd) })
    }
  }

  // S16: every bounded (revise) edge, used from the state's traversal counts.
  const reviseRows: CostReviseRow[] = (opts.graph?.edges ?? [])
    .filter((e) => e.max_traversals !== undefined)
    .map((e) => {
      const used = state?.edges.find((s) => sameEdge(s.edge, e))?.traversals ?? 0
      const max = e.max_traversals as number
      return {
        edge: `${e.source}.${e.source_port}>${e.target}.${e.target_port}`,
        used,
        max,
        exhausted: used >= max,
      }
    })

  const budget =
    run.budget === null
      ? null
      : {
          amount: money(run.budget),
          threshold: run.budgetThreshold === null ? null : money(run.budgetThreshold),
          counted: run.budgetCounted === null ? null : money(run.budgetCounted),
          pct:
            run.budgetThreshold !== null && run.budgetCounted !== null
              ? `${Math.floor((run.budgetCounted / run.budgetThreshold) * 100)}%`
              : null,
          crossings: run.budgetCrossings,
          note: `Budget ${BUDGET_SCOPE_NOTE}`,
        }

  return {
    roleRows,
    totalTokens: tokens(total.tokens),
    totalPrice: priceLabel(total),
    noBreakdown: roles.length === 0 && run.cost !== null && run.cost > 0,
    stageMeasured: !closed,
    stageRows,
    reviseRows,
    budget,
    noBudgetSentence: run.budget === null ? NO_BUDGET_SENTENCE : null,
  }
}
