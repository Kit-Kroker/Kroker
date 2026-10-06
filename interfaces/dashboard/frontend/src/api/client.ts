import type { DashboardApi } from './types'
import { createMockApi, MOCK_BUDGET_GATE_PARAM } from './mock'
import { createHttpApi } from './http'

export function selectApi(
  mode: 'mock' | 'http',
  opts?: { simulateLive?: boolean; budgetGate?: boolean },
): DashboardApi {
  return mode === 'http'
    ? createHttpApi()
    : createMockApi({ simulateLive: opts?.simulateLive ?? true, budgetGate: opts?.budgetGate })
}

// 002 R-3: the one source for the mode rule -- feature-local transports
// (features/board) select their http/mock implementation with this, so the
// two selections can never drift.
export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API === 'mock' ? 'mock' : 'http'

export const api: DashboardApi = selectApi(API_MODE, {
  // 011 R-9: /?mockBudgetGate=1 opts the mock inbox into a seventh,
  // budget-gate item (default off; the search part precedes the hash).
  budgetGate:
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).has(MOCK_BUDGET_GATE_PARAM),
})
