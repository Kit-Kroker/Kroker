import type { DashboardApi } from './types'
import { getMockApi } from './mock'

const notWired = (method: string) => () =>
  Promise.reject(new Error(`Dashboard http provider not wired (VITE_API=http): ${method}`))

function httpApi(): DashboardApi {
  return {
    listRuns: notWired('listRuns'),
    getRun: notWired('getRun'),
    listInbox: notWired('listInbox'),
    answerClarify: notWired('answerClarify'),
    decideGate: notWired('decideGate'),
    overrideMerge: notWired('overrideMerge'),
    resolveEscalation: notWired('resolveEscalation'),
    startRun: notWired('startRun'),
  }
}

export function selectApi(mode: 'mock' | 'http'): DashboardApi {
  return mode === 'http' ? httpApi() : getMockApi()
}

export const api: DashboardApi = selectApi(import.meta.env.VITE_API === 'http' ? 'http' : 'mock')
