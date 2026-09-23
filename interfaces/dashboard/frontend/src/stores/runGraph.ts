// Run mode's live state (E-76 spec §7.3, §9). One subscription per RunView;
// the view calls stop() on unmount and on run change. Gate decisions in flight
// are tracked HERE by key, never in component state, so a stale poll cannot
// re-enable the controls.
import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { api } from '../api/client'
import { isNotFound } from '../api/errors'
import type { GateOutcome } from '../api/types'
import type { GraphResponse, GraphStateResponse } from '../api/graph-types'
import { useCatalogStore } from '../shared/catalog.store'
import { useUiStore } from '../app/ui.store'

export const useRunGraphStore = defineStore('runGraph', () => {
  const catalog = useCatalogStore()
  const ui = useUiStore()

  const runId = ref<string | null>(null)
  const graph = shallowRef<GraphResponse | null>(null)
  const state = shallowRef<GraphStateResponse | null>(null)
  const error = ref<string | null>(null)
  const connectionLost = ref(false)
  const inFlight = ref<Set<string>>(new Set())
  // A key whose decide 404'd stays busy for exactly one more state.
  const lostRace = new Set<string>()

  let unsubscribe: (() => void) | null = null
  let lastFingerprint = ''
  let generation = 0

  function stop() {
    unsubscribe?.()
    unsubscribe = null
    generation += 1
  }

  function receive(next: GraphStateResponse) {
    const fingerprint = JSON.stringify(next)
    if (fingerprint === lastFingerprint) return
    lastFingerprint = fingerprint
    const g = graph.value
    if (next.kind === 'state' && g?.kind === 'graph' && next.graph_sha !== g.sha) {
      // The pin broke (FR-1203): surface it, never refetch silently.
      error.value = `run state is for graph ${next.graph_sha}, but the run pins ${g.sha}`
      stop()
      return
    }
    state.value = next
    const listed = new Set(next.kind === 'state' ? next.pending.map((p) => p.key) : [])
    for (const key of [...inFlight.value]) {
      if (!listed.has(key) || lostRace.has(key)) {
        inFlight.value.delete(key)
        lostRace.delete(key)
      }
    }
    inFlight.value = new Set(inFlight.value)
  }

  async function start(id: string) {
    stop()
    const mine = generation
    runId.value = id
    graph.value = null
    state.value = null
    error.value = null
    connectionLost.value = false
    inFlight.value = new Set()
    lastFingerprint = ''
    await catalog.load()
    if (mine !== generation) return
    if (!catalog.can('run_graph')) return
    try {
      const response = await api.getRunGraph(id)
      if (mine !== generation) return
      graph.value = response
      if (response.kind === 'no_graph') return
      unsubscribe = api.subscribeGraphState(id, receive, (failures) => { connectionLost.value = failures >= 3 })
    } catch (e) {
      if (mine === generation) error.value = String(e)
    }
  }

  async function decide(key: string, outcome: GateOutcome, comment: string) {
    const id = runId.value
    if (!id || inFlight.value.has(key)) return
    inFlight.value = new Set(inFlight.value).add(key)
    try {
      await api.decideGate(id, key, outcome, comment)
    } catch (e) {
      if (isNotFound(e)) {
        // FR-302: another surface decided first. Busy until the next state.
        ui.toast('this gate was already decided elsewhere', 'var(--status-blocked)')
        lostRace.add(key)
      } else {
        ui.toast(`decision failed: ${String(e)}`, 'var(--status-failed)')
        const next = new Set(inFlight.value)
        next.delete(key)
        inFlight.value = next
      }
    }
  }

  return { runId, graph, state, error, connectionLost, inFlight, start, stop, decide }
})
