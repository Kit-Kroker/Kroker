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

// 018 R-10: token names, never raw colours — the caller binds them to
// var() and the theme does the rest.
export function budgetColor(pct: number): string {
  if (pct > 85) return 'var(--status-failed)'
  if (pct > 60) return 'var(--status-waiting)'
  return 'var(--status-done)'
}
