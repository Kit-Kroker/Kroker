export function money(n: number): string {
  return '$' + n.toFixed(2)
}

export function budgetPct(cost: number, budget: number): number {
  return Math.min(100, (cost / budget) * 100)
}

export function budgetColor(pct: number): string {
  if (pct > 85) return '#e06c55'
  if (pct > 60) return '#e0b050'
  return '#4fae7f'
}
