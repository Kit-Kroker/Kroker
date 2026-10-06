import { describe, it, expect } from 'vitest'
import { money, budgetPct, budgetColor, tokens } from './format'

describe('format', () => {
  it('formats USD', () => {
    expect(money(3.1)).toBe('$3.10')
    expect(money(0)).toBe('$0.00')
  })
  it('caps budget pct at 100', () => {
    expect(budgetPct(5, 10)).toBe(50)
    expect(budgetPct(20, 10)).toBe(100)
  })
  // 011 T006 (RED): counted over the CURRENT threshold (§3 trap — never
  // cost/budget), parameters renamed (counted, threshold).
  it('groups token counts with thousands separators', () => {
    expect(tokens(12340)).toBe('12,340')
    expect(tokens(0)).toBe('0')
  })
  it('computes budget pct from counted over threshold', () => {
    expect(budgetPct(31, 40)).toBe(77.5)
    expect(budgetPct(0, 40)).toBe(0)
  })
  it('colors budget by threshold', () => {
    expect(budgetColor(50)).toBe('#4fae7f')
    expect(budgetColor(70)).toBe('#e0b050')
    expect(budgetColor(90)).toBe('#e06c55')
  })
})
