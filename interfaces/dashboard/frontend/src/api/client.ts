import type { DashboardApi } from './types'
import { createMockApi } from './mock'
import { createHttpApi } from './http'

export function selectApi(mode: 'mock' | 'http', opts?: { simulateLive?: boolean }): DashboardApi {
  return mode === 'http' ? createHttpApi() : createMockApi({ simulateLive: opts?.simulateLive ?? true })
}

export const api: DashboardApi = selectApi(import.meta.env.VITE_API === 'mock' ? 'mock' : 'http')
