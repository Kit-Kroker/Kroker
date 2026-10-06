import { describe, it, expect } from 'vitest'
import { tokensOf, rowPrice, totalPrice, priceLabel, BUDGET_SCOPE_NOTE } from './cost'
import type { RoleCost } from '../api/types'

// 011 T006 (RED): the price rule contract (data-model §2.4). Dollars reach
// the screen only through this module; no rule may print dollars a row did
// not carry, and a missing price must never read as $0.00.

function row(overrides: Partial<RoleCost> = {}): RoleCost {
  return {
    role: 'dev',
    model: 'm',
    calls: 1,
    inputTokens: 100,
    outputTokens: 20,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    cost: null,
    ...overrides,
  }
}

describe('tokensOf', () => {
  it('sums all four token kinds', () => {
    expect(
      tokensOf(
        row({ inputTokens: 100, outputTokens: 20, cacheReadTokens: 7, cacheWriteTokens: 3 }),
      ),
    ).toBe(130)
  })
})

describe('rowPrice', () => {
  it('tokens 0 and cost null is no-usage', () => {
    expect(rowPrice(row({ inputTokens: 0, outputTokens: 0, cost: null }))).toEqual({
      state: 'no-usage',
      usd: null,
    })
  })
  it('tokens 0 and cost 0 is no-usage, not a free run', () => {
    expect(rowPrice(row({ inputTokens: 0, outputTokens: 0, cost: 0 }))).toEqual({
      state: 'no-usage',
      usd: null,
    })
  })
  it('tokens with cost null is not-priced', () => {
    expect(rowPrice(row({ cost: null }))).toEqual({ state: 'not-priced', usd: null })
  })
  it('tokens with cost 0 is not-priced (a 0-with-tokens row carries no price)', () => {
    expect(rowPrice(row({ cost: 0 }))).toEqual({ state: 'not-priced', usd: null })
  })
  it('tokens with a real cost is priced at that cost', () => {
    expect(rowPrice(row({ cost: 3.5 }))).toEqual({ state: 'priced', usd: 3.5 })
  })
  it('a priced row without tokens is still priced (server-side total)', () => {
    expect(rowPrice(row({ inputTokens: 0, outputTokens: 0, cost: 3.5 }))).toEqual({
      state: 'priced',
      usd: 3.5,
    })
  })
})

describe('totalPrice', () => {
  it('all rows priced: priced with the sum', () => {
    expect(totalPrice([row({ cost: 1.5 }), row({ cost: 2.25 })], 3.75)).toEqual({
      state: 'priced',
      usd: 3.75,
      tokens: 240,
    })
  })
  it('priced and unpriced mix: partial with the priced sum only', () => {
    expect(totalPrice([row({ cost: 0.5 }), row({ cost: 0 })], null)).toEqual({
      state: 'partial',
      usd: 0.5,
      tokens: 240,
    })
    expect(totalPrice([row({ cost: 1.5 }), row({ cost: null })], null).usd).toBe(1.5)
  })
  it('all rows not-priced: not-priced, no dollars', () => {
    expect(totalPrice([row({ cost: 0 }), row({ cost: null })], null)).toEqual({
      state: 'not-priced',
      usd: null,
      tokens: 240,
    })
  })
  it('all rows no-usage: no-usage', () => {
    expect(
      totalPrice(
        [row({ inputTokens: 0, outputTokens: 0, cost: null })],
        null,
      ),
    ).toEqual({ state: 'no-usage', usd: null, tokens: 0 })
  })
  it('no roles but a wire total (old summaries): priced with it', () => {
    expect(totalPrice([], 7.88)).toEqual({ state: 'priced', usd: 7.88, tokens: 0 })
  })
  it('no roles and no positive wire total: no-usage', () => {
    expect(totalPrice([], 0)).toEqual({ state: 'no-usage', usd: null, tokens: 0 })
    expect(totalPrice([], null)).toEqual({ state: 'no-usage', usd: null, tokens: 0 })
  })
  it('tokens is the sum of tokensOf over the rows', () => {
    expect(
      totalPrice(
        [
          row({ inputTokens: 100, outputTokens: 20 }),
          row({ inputTokens: 200, outputTokens: 30, cacheWriteTokens: 10 }),
        ],
        null,
      ).tokens,
    ).toBe(360)
  })
})

describe('priceLabel', () => {
  it('priced prints money', () => {
    expect(priceLabel({ state: 'priced', usd: 0.5 })).toBe('$0.50')
  })
  it('partial prints money with the partial marker', () => {
    expect(priceLabel({ state: 'partial', usd: 0.5 })).toBe('$0.50 (partial)')
  })
  it('not-priced prints "not priced", never $0.00', () => {
    expect(priceLabel({ state: 'not-priced', usd: null })).toBe('not priced')
  })
  it('no-usage prints the em dash', () => {
    expect(priceLabel({ state: 'no-usage', usd: null })).toBe('—')
  })
})

describe('no rule returns dollars a row did not carry', () => {
  it('an unpriced row list yields usd null even with a null wire total', () => {
    expect(totalPrice([row({ cost: null })], null).usd).toBeNull()
  })
  it('a 0-with-tokens-only list yields usd null even with a 0 wire total', () => {
    expect(totalPrice([row({ cost: 0 })], 0).usd).toBeNull()
  })
})

describe('BUDGET_SCOPE_NOTE', () => {
  it('is exactly the Python constant sentence', () => {
    expect(BUDGET_SCOPE_NOTE).toBe(
      'counts priced planning-agent spend only. Coding-harness, crew and research-stage spend is not counted.',
    )
  })
})
