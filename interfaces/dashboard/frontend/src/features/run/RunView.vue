<script setup lang="ts">
// Run mode (E-76 spec §9), now the run tab host (002 R-4/R-13, FR-017/FR-018).
// Read-only by design: there is no edit path from a run; "open copy in
// editor" is the only way to /graphs (FR-1205). The header (title + stage
// strip) sits ABOVE the tab bar so every tab carries the run's identity;
// the graph-specific banners, the copy link and the canvas live inside the
// Graph panel. Board is disabled unless a #board slot is supplied (the app
// layer composes BoardTab through it -- R-13); Gates and Cost are disabled
// with no content (G7). The active tab comes in as a prop (never useRoute:
// the banner tests mount this view routerless), and tab selection calls
// router.replace only when a router is present.
import { computed, onBeforeUnmount, onMounted, ref, useSlots, watch } from 'vue'
import { useRouter } from 'vue-router'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import GateDecision from '@kroker/ui/components/gate_decision/GateDecision.vue'
import StageDots from '@kroker/ui/components/stage_dots/StageDots.vue'
import { TabBar, type TabItem } from '@kroker/ui'
import { useCatalogStore } from '../../shared/catalog.store'
import { useFleetStore } from '../../shared/fleet.store'
import { useRunGraphStore } from './runGraph.store'
import { toCanvas } from '../../shared/graphCanvas.adapter'
import { toStageDots } from '../../shared/stageStrip.adapter'

defineSlots<{
  board?: (props: { runId: string; projectKey: string | null }) => unknown
}>()

const props = defineProps<{ id: string; tab?: string }>()
const slots = useSlots()
const router = useRouter()
const catalog = useCatalogStore()
const fleet = useFleetStore()
const runGraph = useRunGraphStore()

const now = ref(new Date())
let clock: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  void catalog.load()
  void runGraph.start(props.id)
  clock = setInterval(() => { now.value = new Date() }, 1000)
})
watch(() => props.id, (id) => { void runGraph.start(id) })
onBeforeUnmount(() => {
  runGraph.stop()
  if (clock) clearInterval(clock)
})

const run = computed(() => fleet.getOrLoad(props.id))
const dots = computed(() => (run.value ? toStageDots(run.value, catalog.canonicalStages) : []))
const graph = computed(() => (runGraph.graph?.kind === 'graph' ? runGraph.graph : null))
const model = computed(() =>
  graph.value
    ? toCanvas(graph.value.graph, { typeOf: catalog.typeOf, backEdges: graph.value.back_edges, state: runGraph.state, now: now.value })
    : null,
)
const gateOf = (nodeKey: string) => model.value?.pendingByNode[nodeKey]?.find((p) => p.kind === 'gate')
const otherPending = (nodeKey: string) => model.value?.pendingByNode[nodeKey]?.filter((p) => p.kind !== 'gate') ?? []

// The tab host (R-13): Board exists only when the app layer supplied the
// slot; Gates and Cost are placeholders with no content (G7).
const hasBoardSlot = computed(() => typeof slots.board === 'function')
const tabs = computed<TabItem[]>(() => [
  { id: 'graph', label: 'Graph' },
  { id: 'board', label: 'Board', disabled: !hasBoardSlot.value },
  { id: 'gates', label: 'Gates', disabled: true },
  { id: 'cost', label: 'Cost', disabled: true },
])
// R-4: an unknown or disabled value renders Graph and leaves the URL alone.
const active = computed(() => (props.tab === 'board' && hasBoardSlot.value ? 'board' : 'graph'))

function onSelect(id: string) {
  if (id === active.value) return
  // Tolerate a routerless mount (the banner tests); with one, replace --
  // never push -- so tab switches do not pile up history (R-4).
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({
    params: current.params,
    query: { ...current.query, tab: id === 'graph' ? undefined : id },
  })
}
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <header class="head">
      <h1 class="title">{{ run?.title ?? id }}</h1>
      <StageDots :dots="dots" />
    </header>

    <TabBar :tabs="tabs" :active="active" label="Run views" @select="onSelect" />

    <section v-if="active === 'graph'" class="graph-panel">
      <div class="graph-bar">
        <span class="spacer" />
        <RouterLink
          v-if="graph"
          :to="{ path: '/graphs', query: { from: `run:${id}` } }"
          class="copy"
          data-testid="open-copy"
        >open copy in editor</RouterLink>
      </div>

      <p v-if="runGraph.error" class="banner error" data-testid="run-graph-error">{{ runGraph.error }}</p>
      <p v-else-if="!catalog.can('run_graph')" class="banner" data-testid="run-graph-unavailable">Graph view is not available on this server.</p>
      <p v-else-if="runGraph.state?.kind === 'unavailable'" class="banner" data-testid="run-graph-state-unavailable">
        This run's graph state is no longer available ({{ runGraph.state.reason === 'retention_expired' ? 'history retention expired' : 'the graph no longer validates against the current registry' }}).
      </p>
      <p v-else-if="runGraph.graph?.kind === 'no_graph'" class="banner" data-testid="run-graph-empty">
        This run predates graph execution.
      </p>
      <p v-if="runGraph.connectionLost" class="banner" data-testid="connection-lost">connection lost — retrying</p>

      <div v-if="model" class="canvas-wrap">
        <GraphCanvas :nodes="model.nodes" :edges="model.edges" :editable="false">
          <template #node-extra="{ nodeKey }">
            <GateDecision
              v-if="gateOf(nodeKey)"
              :title="`${nodeKey} · pending`"
              :busy="runGraph.inFlight.has(gateOf(nodeKey)!.key)"
              @decide="(d) => runGraph.decide(gateOf(nodeKey)!.key, d.outcome, d.comment)"
            />
            <RouterLink
              v-for="p in otherPending(nodeKey)"
              :key="p.key"
              to="/inbox"
              class="pending-link"
              data-testid="pending-inbox-link"
            >{{ p.kind }} pending — inbox</RouterLink>
          </template>
        </GraphCanvas>
      </div>
    </section>

    <!-- R-13: the slot renders only once the run is known; a bad or pruned
         link must not hang on "loading run..." forever (data-model 5). -->
    <section v-else-if="active === 'board'" data-testid="run-tab-board" class="board-panel">
      <p v-if="run === undefined && fleet.lastFetched === null" class="banner" data-testid="run-board-loading">loading run...</p>
      <p v-else-if="run === undefined" class="banner" data-testid="run-board-not-found">run not found</p>
      <slot v-else name="board" :run-id="id" :project-key="run.projectKey" />
    </section>
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 12px 16px; gap: 8px; }
.head { display: flex; align-items: center; gap: 14px; }
.title { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink-primary); }
/* R-13 rule 4: the Graph panel stays a flex-column child so .canvas-wrap
   keeps its growth (vue-flow measures its container). */
.graph-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 8px; }
.graph-bar { display: flex; align-items: center; gap: 14px; min-height: 15px; }
.board-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 8px; }
.spacer { flex: 1; }
.copy { color: var(--link); font-family: var(--font-mono); font-size: 11px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.banner.error { color: var(--status-failed); }
.canvas-wrap { flex: 1; min-height: 420px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.pending-link { display: block; padding: 4px 8px; color: var(--link); font-size: 11px; }
</style>
