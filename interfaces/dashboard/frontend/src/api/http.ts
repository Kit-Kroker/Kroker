import type { DashboardApi } from './types'

const notWired = (method: string) => () =>
  Promise.reject(new Error(`Dashboard http provider not wired (VITE_API=http): ${method}`))

export function createHttpApi(): DashboardApi {
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
