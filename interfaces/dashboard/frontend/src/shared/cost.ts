import type { RoleCost } from '../api/types'
import { money } from './format'

// 011 R-2: the one price rule. Dollars reach the screen only through this
// module. A row with tokens and a dollar value of null OR 0 is not priced
// (opencode reports a numeric 0 on subscription models; a call that used
// tokens on a priced model costs more than zero), a row with neither tokens
// nor dollars has no usage, and no rule may print dollars a row did not
// carry -- a missing price must never read as $0.00.

export type PriceState = 'priced' | 'partial' | 'not-priced' | 'no-usage'

export const BUDGET_SCOPE_NOTE =
  'counts priced planning-agent spend only. Coding-harness, crew and research-stage spend is not counted.'

export function tokensOf(r: RoleCost): number {
  return r.inputTokens + r.outputTokens + r.cacheReadTokens + r.cacheWriteTokens
}

export function rowPrice(r: RoleCost): {
  state: 'priced' | 'not-priced' | 'no-usage'
  usd: number | null
} {
  if (tokensOf(r) === 0 && (r.cost === null || r.cost === 0)) {
    return { state: 'no-usage', usd: null }
  }
  if (r.cost === null || r.cost === 0) {
    return { state: 'not-priced', usd: null }
  }
  return { state: 'priced', usd: r.cost }
}

export function totalPrice(
  roles: RoleCost[],
  wireTotal: number | null,
): { state: PriceState; usd: number | null; tokens: number } {
  if (roles.length === 0) {
    // N9: closed runs written before role tracking carry only the wire
    // total. A positive total is priced with that value; anything else
    // means no usage was recorded.
    if (wireTotal !== null && wireTotal > 0) {
      return { state: 'priced', usd: wireTotal, tokens: 0 }
    }
    return { state: 'no-usage', usd: null, tokens: 0 }
  }
  const tokens = roles.reduce((a, r) => a + tokensOf(r), 0)
  const prices = roles.map(rowPrice)
  const priced = prices.filter((p) => p.state === 'priced')
  const notPriced = prices.some((p) => p.state === 'not-priced')
  if (priced.length === 0) {
    // Some rows may be no-usage; the deciding factor is whether ANY row
    // carried tokens.
    return { state: notPriced ? 'not-priced' : 'no-usage', usd: null, tokens }
  }
  if (notPriced) {
    const usd = priced.reduce((a, p) => a + (p.usd as number), 0)
    return { state: 'partial', usd, tokens }
  }
  const usd = priced.reduce((a, p) => a + (p.usd as number), 0)
  return { state: 'priced', usd, tokens }
}

export function priceLabel(p: { state: PriceState; usd: number | null }): string {
  if (p.state === 'not-priced') return 'not priced'
  if (p.state === 'no-usage') return '—'
  // priced and partial always carry a non-null usd by construction; the
  // null check keeps the type honest without inventing dollars.
  if (p.usd === null) return '—'
  return p.state === 'partial' ? `${money(p.usd)} (partial)` : money(p.usd)
}
