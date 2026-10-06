import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import type { Run, StartRunInput } from '../api/types'
import { totalPrice } from './cost'

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
  // 011 R-8 (CONSOLE-27): the header's honest total. usd sums the runs that
  // carry a price (null when none does — a pricing miss must never read as a
  // free fleet); excluded counts the runs whose price state is not-priced or
  // partial, the ones the sum left out. no-usage runs are never excluded.
  const totalCost = computed(() => {
    const priced = runs.value.filter((r) => (r.cost ?? null) !== null)
    const usd =
      priced.length > 0 ? +priced.reduce((a, r) => a + (r.cost as number), 0).toFixed(2) : null
    const excluded = runs.value.filter((r) => {
      const state = totalPrice(r.roles ?? [], (r.cost ?? null) as number | null).state
      return state === 'not-priced' || state === 'partial'
    }).length
    return { usd, excluded }
  })

  return { runs, loading, lastFetched, refresh, getOrLoad, startRun, blockedCount, activeCount, totalCost }
})
