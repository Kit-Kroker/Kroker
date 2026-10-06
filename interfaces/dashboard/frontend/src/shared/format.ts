export function money(n: number): string {
  return '$' + n.toFixed(2)
}

export function tokens(n: number): string {
  return n.toLocaleString('en-US')
}

// 011: counted over the CURRENT threshold (the gate's own figure and its
// raised limit), never total-over-configured-budget.
export function budgetPct(counted: number, threshold: number): number {
  return Math.min(100, (counted / threshold) * 100)
}

export function budgetColor(pct: number): string {
  if (pct > 85) return '#e06c55'
  if (pct > 60) return '#e0b050'
  return '#4fae7f'
}
