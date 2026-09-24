import type { DashboardApi } from './types'
import { createMockApi } from './mock'
import { createHttpApi } from './http'

export function selectApi(mode: 'mock' | 'http', opts?: { simulateLive?: boolean }): DashboardApi {
  return mode === 'http' ? createHttpApi() : createMockApi({ simulateLive: opts?.simulateLive ?? true })
}

// 002 R-3: the one source for the mode rule -- feature-local transports
// (features/board) select their http/mock implementation with this, so the
// two selections can never drift.
export const API_MODE: 'mock' | 'http' = import.meta.env.VITE_API === 'mock' ? 'mock' : 'http'

export const api: DashboardApi = selectApi(API_MODE)
