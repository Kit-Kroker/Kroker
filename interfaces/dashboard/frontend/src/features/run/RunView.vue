<script setup lang="ts">
// 018 T032/T043 (S3/S13): the v5 Observe run view. The old run header (title
// + stage strip) and the Cost tab are gone; the rail carries the run block
// (title, state, budget, the interim open-copy link until T063, and the
// E-77 unavailable reasons as notes, R-5a) with Path, Events and Cost
// sections from the adapters, plus one call to action per pending item
// opening the DecisionCard over the canvas (?decision=). Tabs are Graph and
// Board only; Cost is a rail section (?rail=cost, and ?tab=cost still
// selects it until the CONSOLE-10 rewrite lands). The inspector
// (RunInspector, screen-local) shows configured vs answering model ids.
import { computed, onBeforeUnmount, onMounted, ref, useSlots, watch } from 'vue'
import { useRouter } from 'vue-router'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import Rail from '@kroker/ui/components/rail/Rail.vue'
import type { RailHead } from '@kroker/ui/components/rail/Rail.vue'
import DecisionCard from '@kroker/ui/components/decision_card/DecisionCard.vue'
import { TabBar, type TabItem } from '@kroker/ui'
import { useCatalogStore } from '../../shared/catalog.store'
import { useFleetStore } from '../../shared/fleet.store'
import { useInboxStore } from '../../app/inbox.store'
import { useRunGraphStore } from './runGraph.store'
import { toCanvas } from '../../shared/graphCanvas.adapter'
import type { GraphStateResponse } from '../../api/graph-types'
import type { DashboardApi, InboxItem } from '../../api/types'
import { costRailOf } from './costRail.adapter'
import { railEventsOf } from './railEvents.adapter'
import { decisionCardOf } from '../../shared/decisionCard.adapter'
import { entryKey } from '../../shared/entryKey'
import { BUDGET_SCOPE_NOTE } from '../../shared/cost'
import { money } from '../../shared/format'
import RunInspector from './RunInspector.vue'

defineSlots<{
  board?: (props: { runId: string; projectKey: string | null }) => unknown
}>()

const props = defineProps<{ id: string; tab?: string; rail?: string; decision?: string }>()
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
const graph = computed(() => (runGraph.graph?.kind === 'graph' ? runGraph.graph : null))
const state = computed(() => (runGraph.state?.kind === 'state' ? runGraph.state : null))

// R-5: node transitions are observed between successive polls.
const prevState = ref<GraphStateResponse | null>(null)
watch(state, (_next, old) => { prevState.value = old ?? null })
watch(() => props.id, () => { prevState.value = null })

const model = computed(() =>
  graph.value
    ? toCanvas(graph.value.graph, { typeOf: catalog.typeOf, backEdges: graph.value.back_edges, state: runGraph.state, now: now.value })
    : null,
)
const otherPending = (nodeKey: string) => model.value?.pendingByNode[nodeKey] ?? []

// --- 018 T043: the pending items become rail calls and one card. ---
const inbox = useInboxStore()
const pending = computed(() => state.value?.pending ?? [])
const railCalls = computed(() =>
  pending.value.map((p) => ({ id: p.key, label: `Review ${p.kind} ${p.key}`, kind: 'primary' })),
)

const decisionKey = ref<string | null>(props.decision ?? null)
watch(
  () => props.decision,
  (d) => { decisionKey.value = typeof d === 'string' ? d : null },
)
watch(() => props.id, () => { decisionKey.value = null })

function openDecision(key: string): void {
  decisionKey.value = key
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({ query: { ...current.query, decision: key } })
}
function closeDecision(): void {
  decisionKey.value = null
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({ query: { ...current.query, decision: undefined } })
}

// The card's item: the inbox entry for this run when one exists (the card
// then carries the wire's title/body), else a synthetic gate item from the
// pending ref itself.
const cardItem = computed<InboxItem | null>(() => {
  if (decisionKey.value === null) return null
  const listed = inbox.items.find((i) => i.runId === props.id && i.id === decisionKey.value)
  if (listed) return listed
  const p = pending.value.find((x) => x.key === decisionKey.value)
  if (!p) return null
  return {
    id: p.key, runId: props.id, round: 1, age: '—', type: 'gate',
    gate: p.key.split('#')[0], title: p.key, body: '',
  }
})
const cardModel = computed(() => (cardItem.value ? decisionCardOf(cardItem.value) : null))
const cardBusy = computed(() =>
  cardItem.value !== null && inbox.inFlight.has(entryKey(cardItem.value)),
)

// The card's actions route through the inbox store (the store owns in-flight,
// notices and the refresh-after-write), exactly as the inbox view does.
const storeAsApi = {
  answerClarify: (r: string, k: string, a: string) => inbox.answerClarify(r, k, a),
  decideGate: (r: string, k: string, o: 'approve' | 'reject' | 'revise', c: string) => inbox.decideGate(r, k, o, c),
  overrideMerge: (r: string, k: string, a: boolean, j: string) => inbox.overrideMerge(r, k, a, j),
  decideTaskGate: (r: string, k: string, o: 'approve' | 'reject' | 'revise', g: string, t: boolean) =>
    inbox.decideTaskGate(r, k, o, g, t),
} as unknown as DashboardApi

async function onCardAct(actId: string, text: string): Promise<void> {
  if (!cardItem.value || !cardModel.value) return
  try {
    await cardModel.value.call(storeAsApi, actId, text, false)
  } catch {
    // The store's send() owns failure notices; a throwing action surfaces
    // nothing more here (the pane closes on the next state).
  }
}

// --- The rail (S3): run block, Path, Events, Cost. ---
const railHead = computed<RailHead>(() => ({
  title: run.value?.title ?? props.id,
  state: run.value?.status ?? '—',
  stateKind: run.value?.status === 'failed' ? 'failed' : run.value?.status === 'done' ? 'done' : 'waiting',
  rows: [{ k: 'where', v: state.value?.current_nodes.join(', ') || (state.value?.outcome.state !== 'running' ? 'final' : '—') }],
  budget: {
    // The run block shows the budget itself; the Cost section itemises it.
    spent: run.value?.budget !== null && run.value?.budget !== undefined ? money(run.value.budget) : 'not measured',
    limit: run.value?.budget == null ? null : (run.value.budgetThreshold ?? run.value.budget),
    pct:
      run.value?.budgetThreshold != null && run.value?.budgetCounted != null
        ? Math.floor((run.value.budgetCounted / run.value.budgetThreshold) * 100)
        : null,
    note: BUDGET_SCOPE_NOTE,
  },
}))

const events = computed(() =>
  railEventsOf({
    decisions: run.value?.decisions ?? [],
    pending: state.value?.pending ?? [],
    prev: prevState.value,
    curr: state.value,
    budgetCrossings: run.value?.budgetCrossings ?? 0,
    open: run.value?.status === 'running',
  }),
)

const cost = computed(() =>
  run.value
    ? costRailOf(run.value, { canonicalStages: catalog.canonicalStages, graph: graph.value?.graph, state: state.value })
    : null,
)

const railTabs = [
  { id: 'path', label: 'Path' },
  { id: 'events', label: 'Events' },
  { id: 'cost', label: 'Cost' },
]

const railActive = computed(() => {
  if (props.rail === 'cost' || props.tab === 'cost') return 'cost'
  if (props.rail === 'events') return 'events'
  return 'path'
})

// --- The tabs (CONSOLE-10's rewrite lands in T055): Graph and Board only. ---
const hasBoardSlot = computed(() => typeof slots.board === 'function')
const tabs = computed<TabItem[]>(() => [
  { id: 'graph', label: 'Graph' },
  { id: 'board', label: 'Board', disabled: !hasBoardSlot.value },
])
const active = computed(() => (props.tab === 'board' && hasBoardSlot.value ? 'board' : 'graph'))

// --- The inspector (S13): configured vs answering model. ---
const selectedKey = ref<string | null>(null)

// Selecting a canvas node: a pending item opens its card (FR-1205);
// otherwise the selection feeds the inspector.
function onCanvasSelect(key: string | null): void {
  selectedKey.value = key
  if (key !== null) {
    const first = model.value?.pendingByNode[key]?.[0]
    if (first) {
      openDecision(first.key)
      return
    }
  }
  if (decisionKey.value !== null) closeDecision()
}
const selectedWire = computed(() =>
  selectedKey.value !== null ? graph.value?.graph.nodes.find((n) => n.id === selectedKey.value) : undefined,
)
const selectedType = computed(() => (selectedWire.value ? catalog.typeOf(selectedWire.value.type) : undefined))
const inspector = computed(() => {
  if (!selectedWire.value) return null
  const configured =
    ((selectedWire.value.role?.model as string | undefined) ?? selectedType.value?.default_id) || 'not measured'
  const answering =
    (selectedType.value?.role
      ? run.value?.roles.find((r) => r.role === selectedType.value?.role)?.model
      : undefined) || 'not measured'
  return {
    title: selectedWire.value.label ?? selectedWire.value.id,
    configured,
    answering,
    isCode: selectedWire.value.type === 'code',
  }
})

function onSelect(id: string) {
  if (id === active.value) return
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({ params: current.params, query: { ...current.query, tab: id === 'graph' ? undefined : id } })
}

function onRailSelect(id: string) {
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({
    params: current.params,
    query: { ...current.query, rail: id === 'path' ? undefined : id },
  })
}
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <TabBar :tabs="tabs" :active="active" label="Run views" @select="onSelect" />

    <section v-if="active === 'board'" data-testid="run-tab-board" class="board-panel">
      <p v-if="run === undefined && fleet.lastFetched === null" class="banner" data-testid="run-board-loading">loading run...</p>
      <p v-else-if="run === undefined" class="banner" data-testid="run-board-not-found">run not found</p>
      <slot v-else name="board" :run-id="id" :project-key="run.projectKey" />
    </section>

    <section v-else class="observe">
      <div class="rail-col">
        <Rail
          :head="railHead"
          :tabs="railTabs"
          :active="railActive"
          :calls="railCalls"
          @select="onRailSelect"
          @call="(i) => openDecision(railCalls[i]?.id ?? '')"
        >
          <template #headNote>
            <!-- R-5a: the E-77 reasons are notes under the run block. -->
            <p v-if="runGraph.state?.kind === 'unavailable'" class="banner" data-testid="run-graph-state-unavailable">
              This run's graph state is no longer available ({{ runGraph.state.reason === 'retention_expired' ? 'history retention expired' : 'the graph no longer validates against the current registry' }}).
            </p>
            <p v-if="runGraph.graph?.kind === 'no_graph'" class="banner" data-testid="run-graph-empty">
              This run predates graph execution.
            </p>
            <p v-if="runGraph.connectionLost" class="banner" data-testid="connection-lost">connection lost — retrying</p>
            <!-- T063 interim: the open-copy link is an item of the run block. -->
            <RouterLink
              v-if="graph"
              :to="{ path: '/graphs', query: { from: `run:${id}` } }"
              class="copy"
              data-testid="open-copy"
            >open copy in editor</RouterLink>
          </template>
        </Rail>

        <div class="rail-sections">
          <div class="rail-section" data-testid="rail-path">
            <div class="section-title">Path</div>
            <div v-for="n of state?.current_nodes ?? []" :key="n" class="path-node">{{ n }}</div>
            <div v-if="!state?.current_nodes.length" class="path-node dim">—</div>
          </div>

          <div class="rail-section" data-testid="rail-events">
            <div class="section-title">Events</div>
            <div v-for="(row, i) of events.rows" :key="i" class="event-row" :data-kind="row.kind">
              <span v-if="row.at" class="at">{{ row.at.slice(11, 19) }}</span>
              <span class="label">{{ row.label }}</span>
            </div>
            <p v-if="events.note" class="note">{{ events.note }}</p>
            <p v-if="events.note" class="note">Human decisions only while the run is open.</p>
          </div>

          <div class="rail-section" data-testid="rail-cost">
            <div class="section-title">Cost</div>
            <template v-if="cost">
              <div v-if="cost.noBreakdown" class="cost-line">No breakdown recorded for this run.</div>
              <div v-for="r of cost.roleRows" :key="r.role" class="cost-role">
                <span class="name mono">{{ r.role }} · {{ r.model }} · {{ r.calls }}</span>
                <span class="tokens mono dim">{{ r.tokens }}</span>
                <span class="price mono">{{ r.price }}</span>
              </div>
              <div v-if="cost.roleRows.length" class="cost-total mono">
                <span class="dim">{{ cost.totalTokens }}</span>
                <span data-testid="rail-cost-total">{{ cost.totalPrice }}</span>
              </div>
              <div v-if="cost.stageMeasured && cost.stageRows.length" class="cost-stages">
                <div v-for="s of cost.stageRows" :key="s.stage" class="cost-stage mono">
                  <span class="dim">{{ s.stage }}</span><span>{{ s.price }}</span>
                </div>
              </div>
              <div v-else-if="!cost.stageMeasured" class="cost-line">stages: not measured</div>
              <div v-for="r of cost.reviseRows" :key="r.edge" class="cost-stage mono">
                <span class="dim">{{ r.edge }}</span><span>{{ r.used }}/{{ r.max }}{{ r.exhausted ? ' · next revise escalates' : '' }}</span>
              </div>
              <!-- The Cost section's own budget block (CONSOLE-24-26's new home). -->
              <div v-if="cost.budget" class="cost-budget" data-testid="rail-budget">
                <div class="cost-stage">
                  <span class="dim">budget</span><span>{{ cost.budget.amount }}</span>
                </div>
                <div v-if="cost.budget.threshold" class="cost-stage">
                  <span class="dim">limit</span><span>{{ cost.budget.threshold }}</span>
                </div>
                <div v-if="cost.budget.counted" class="cost-stage">
                  <span class="dim">counted</span><span>{{ cost.budget.counted }}</span>
                </div>
                <div v-if="cost.budget.pct" class="cost-stage">
                  <span class="dim">share</span><span>{{ cost.budget.pct }}</span>
                </div>
                <div v-if="cost.budget.crossings" class="cost-stage">
                  <span class="dim">crossings</span><span>{{ cost.budget.crossings }}</span>
                </div>
                <p class="note">{{ cost.budget.note }}</p>
              </div>
              <p v-if="cost.noBudgetSentence" class="cost-line">{{ cost.noBudgetSentence }}</p>
            </template>
          </div>
        </div>
      </div>

      <div class="observe-main">
        <p v-if="runGraph.error" class="banner error" data-testid="run-graph-error">could not load</p>
        <p v-else-if="!catalog.can('run_graph')" class="banner" data-testid="run-graph-unavailable">Graph view is not available on this server.</p>

        <!-- CONSOLE-51: with an unprojectable state the canvas shows its
             empty state — no graph is drawn for a run whose state is gone. -->
        <div v-if="model && runGraph.state?.kind !== 'unavailable'" class="observe-body">
          <div class="canvas-wrap">
            <GraphCanvas
              :nodes="model.nodes"
              :edges="model.edges"
              :editable="false"
              :selected-key="selectedKey"
              @select="onCanvasSelect"
            >
              <template #node-extra="{ nodeKey }">
                <span
                  v-for="p in otherPending(nodeKey)"
                  :key="p.key"
                  class="pending-mark"
                  data-testid="pending-mark"
                >{{ p.kind }} pending</span>
              </template>
            </GraphCanvas>
          </div>
          <div class="side-col">
            <RunInspector
              v-if="inspector"
              :title="inspector.title"
              :configured="inspector.configured"
              :answering="inspector.answering"
              :is-code="inspector.isCode"
            />
            <!-- 018 T043: the decision card over the canvas (FR-1205). -->
            <div v-if="cardModel && cardItem" class="run-card" data-testid="run-card">
              <button class="card-close" data-testid="run-card-close" @click="closeDecision">close</button>
              <p v-if="inbox.notice[entryKey(cardItem)]" class="notice">{{ inbox.notice[entryKey(cardItem)] }}</p>
              <DecisionCard
                v-bind="cardModel.card"
                :busy="cardBusy"
                @act="(id, text) => onCardAct(id, text)"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 12px 16px; gap: 8px; }
.observe { display: flex; flex: 1; min-height: 0; gap: 8px; }
.rail-col { display: flex; flex-direction: column; width: 320px; flex: none; gap: 8px; overflow-y: auto; }
.rail-sections { display: flex; flex-direction: column; gap: 10px; }
.section-title { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.06em; color: var(--ink-subtle); }
.observe-main { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 8px; }
.observe-body { display: flex; flex: 1; min-height: 0; gap: 8px; }
.board-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 8px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.banner.error { color: var(--status-failed); }
.canvas-wrap { flex: 1; min-height: 420px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.pending-link { display: block; padding: 4px 8px; color: var(--link); font-size: 11px; }
.rail-section { display: flex; flex-direction: column; gap: 4px; }
.path-node { font-family: var(--font-mono); font-size: 11px; color: var(--ink-tertiary); }
.path-node.dim { color: var(--ink-subtle); }
.event-row { display: flex; gap: 6px; font-family: var(--font-mono); font-size: 11px; color: var(--ink-tertiary); }
.event-row .at { color: var(--ink-subtle); }
.event-row[data-kind='outcome'] .label { color: var(--ink-primary); }
.note { margin: 4px 0 0; font-size: 10.5px; color: var(--ink-subtle); }
.cost-role, .cost-total, .cost-stage { display: flex; justify-content: space-between; gap: 8px; }
.cost-role .name { color: var(--ink-secondary); }
.cost-role .price, .cost-total { color: var(--ink-primary); }
.cost-stages { border-top: 1px solid var(--line); padding-top: 4px; margin-top: 4px; }
.cost-line { color: var(--ink-subtle); font-size: 11px; }
.mono { font-family: var(--font-mono); font-size: 11px; }
.dim { color: var(--ink-subtle); }
.pending-mark { display: block; padding: 2px 8px; color: var(--status-waiting); font-family: var(--font-mono); font-size: 10.5px; }
.side-col { display: flex; flex-direction: column; gap: 8px; }
.run-card { display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
.card-close {
  cursor: pointer; background: none; border: none; padding: 0;
  font-family: var(--font-mono); font-size: 10.5px; color: var(--link);
}
.notice { margin: 0; align-self: flex-start; font-family: var(--font-mono); font-size: 11px; color: var(--status-waiting); }
.copy { color: var(--link); font-family: var(--font-mono); font-size: 11px; padding-top: 4px; }
</style>
