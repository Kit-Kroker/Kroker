import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import type { Run, StartRunInput } from '../api/types'

export const useFleetStore = defineStore('fleet', () => {
  const runs = ref<Run[]>([])
  const loading = ref(false)
  const lastFetched = ref<number | null>(null)

  async function refresh() {
    loading.value = true
    try {
      runs.value = await api.listRuns()
    } finally {
      loading.value = false
      lastFetched.value = Date.now()
    }
  }

  function getOrLoad(id: string): Run | undefined {
    return runs.value.find((r) => r.id === id)
  }

  async function startRun(input: StartRunInput): Promise<Run> {
    const r = await api.startRun(input)
    await refresh()
    return r
  }

  const blockedCount = computed(() => runs.value.filter((r) => r.status === 'blocked').length)
  const activeCount = computed(() => runs.value.filter((r) => r.status === 'running' || r.status === 'blocked').length)
  const totalCost = computed(() => +runs.value.reduce((a, r) => a + (r.cost ?? 0), 0).toFixed(2))

  return { runs, loading, lastFetched, refresh, getOrLoad, startRun, blockedCount, activeCount, totalCost }
})
