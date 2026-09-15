<script setup lang="ts">
// Run mode (E-76 spec §9). Read-only by design: there is no edit path from a
// run; "open copy in editor" is the only way to /graphs (FR-1205).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import GateDecision from '@kroker/ui/components/gate_decision/GateDecision.vue'
import StageDots from '@kroker/ui/components/stage_dots/StageDots.vue'
import { useCatalogStore } from '../stores/catalog'
import { useFleetStore } from '../stores/fleet'
import { useRunGraphStore } from '../stores/runGraph'
import { toCanvas } from '../adapters/graph'
import { toStageDots } from '../adapters/fleet'

const props = defineProps<{ id: string }>()
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
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <header class="head">
      <h1 class="title">{{ run?.title ?? id }}</h1>
      <StageDots :dots="dots" />
      <span class="spacer" />
      <RouterLink
        v-if="graph"
        :to="{ path: '/graphs', query: { from: `run:${id}` } }"
        class="copy"
        data-testid="open-copy"
      >open copy in editor</RouterLink>
    </header>

    <p v-if="runGraph.error" class="banner error" data-testid="run-graph-error">{{ runGraph.error }}</p>
    <p v-else-if="!catalog.can('run_graph')" class="banner" data-testid="run-graph-unavailable">Graph view arrives with E-75.</p>
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
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 12px 16px; gap: 8px; }
.head { display: flex; align-items: center; gap: 14px; }
.title { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink-primary); }
.spacer { flex: 1; }
.copy { color: var(--link); font-family: var(--font-mono); font-size: 11px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.banner.error { color: var(--status-failed); }
.canvas-wrap { flex: 1; min-height: 420px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.pending-link { display: block; padding: 4px 8px; color: var(--link); font-size: 11px; }
</style>
