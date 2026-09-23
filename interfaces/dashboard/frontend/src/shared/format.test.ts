import { describe, it, expect } from 'vitest'
import { money, budgetPct, budgetColor } from './format'

describe('format', () => {
  it('formats USD', () => {
    expect(money(3.1)).toBe('$3.10')
    expect(money(0)).toBe('$0.00')
  })
  it('caps budget pct at 100', () => {
    expect(budgetPct(5, 10)).toBe(50)
    expect(budgetPct(20, 10)).toBe(100)
  })
  it('colors budget by threshold', () => {
    expect(budgetColor(50)).toBe('#4fae7f')
    expect(budgetColor(70)).toBe('#e0b050')
    expect(budgetColor(90)).toBe('#e06c55')
  })
})
