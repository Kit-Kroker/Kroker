import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { FleetRunSummary } from '../api/read-types'

// 018 T049 (R-6, data-model §5): the fleet summary read, one request per
// fleet poll (App.vue refreshes both together). byRun is the Fleet columns'
// per-run source; a run absent from it is a legacy row.
export const useFleetSummaryStore = defineStore('fleetSummary', () => {
  const byRun = ref<Record<string, FleetRunSummary>>({})
  const lastUnreadable = ref<string[]>([])

  async function refresh(): Promise<void> {
    try {
      const summary = await api.getFleetSummary()
      const next: Record<string, FleetRunSummary> = {}
      for (const row of summary.runs) next[row.runId] = row
      byRun.value = next
      lastUnreadable.value = summary.unreadable
    } catch {
      // The fleet store owns the fleet's own error state; the summary's
      // absence degrades rows to legacy columns, never a crash.
    }
  }

  return { byRun, lastUnreadable, refresh }
})
