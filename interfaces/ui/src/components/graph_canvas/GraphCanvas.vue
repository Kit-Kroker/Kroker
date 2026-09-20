<script setup lang="ts">
// One renderer, two modes (E-76 spec §8-§10, FR-1205). Renders display
// primitives only; decides no legality. The single connection rule it runs
// is the caller's `connectable` (GRAPH_CANVAS-6).
import { computed, ref, shallowRef, watch } from 'vue'
import { VueFlow, Handle, Position, BaseEdge, getBezierPath } from '@vue-flow/core'
import type { Connection, Edge, Node, NodeDragEvent } from '@vue-flow/core'
import { CANVAS_STATUSES, type CanvasEdge, type CanvasNode, type Point, type PortRef } from './types'
import { backwardPath, isFinitePoint, layoutGraph, NODE_WIDTH } from './graph_layout'
import { acceptConnection, handleId, toPortRefs } from './connection'

const props = withDefaults(
  defineProps<{
    nodes: CanvasNode[]
    edges: CanvasEdge[]
    editable?: boolean
    connectable?: (from: PortRef, to: PortRef) => boolean
    selectedKey?: string | null
    tidyRequest?: number
  }>(),
  { editable: false, connectable: () => false, selectedKey: null, tidyRequest: 0 },
)

const emit = defineEmits<{
  (e: 'connect', v: { from: PortRef; to: PortRef }): void
  (e: 'move', v: { key: string } & Point): void
  (e: 'remove', v: { kind: 'node' | 'edge'; key: string }): void
  (e: 'select', key: string | null): void
  (e: 'drop-type', v: { type: string } & Point): void
  (e: 'layout-failed', message: string): void
}>()

const laid = ref<Record<string, Point>>({})
const backwardKeys = computed(() => new Set(props.edges.filter((e) => e.backward).map((e) => e.key)))

function relayout(all: boolean) {
  const result = layoutGraph(props.nodes, props.edges, { all, backwardKeys: backwardKeys.value })
  if (result.failed) emit('layout-failed', result.failed)
  laid.value = all ? result.positions : { ...laid.value, ...result.positions }
  if (props.editable) {
    // Positions the layout chose become cosmetic data (spec §8.4).
    for (const [key, p] of Object.entries(result.positions)) emitMove(key, p)
  }
}

function emitMove(key: string, p: Point) {
  // GRAPH_CANVAS-8: never a non-finite coordinate, never an unknown key.
  if (!isFinitePoint(p) || !props.nodes.some((n) => n.key === key)) return
  emit('move', { key, x: p.x, y: p.y })
}

watch(
  () => props.nodes.filter((n) => !isFinitePoint(n.position) && !laid.value[n.key]).map((n) => n.key).join('|'),
  (missing) => { if (missing) relayout(false) },
  { immediate: true },
)
watch(() => props.tidyRequest, (v, old) => { if (v !== old) relayout(true) })

// Decorations (status, metrics, counters, issue counts) are read by the slot
// templates from these maps. vue-flow's own element arrays below change ONLY
// when structure changes: replacing them on every run-state tick drops the
// measured handle bounds and the edges with them (verified 2026-09-14,
// @vue-flow/core 1.48.2).
// GRAPH_CANVAS-4: an unknown status is a product fault, not a default.
// Checked synchronously at setup (so mounting fails) and on every update.
function assertStatuses(nodes: readonly CanvasNode[]) {
  for (const n of nodes) {
    if (n.status !== undefined && !CANVAS_STATUSES.includes(n.status)) {
      throw new Error(`GraphCanvas: unknown status "${n.status}" for node "${n.key}"`)
    }
  }
}
assertStatuses(props.nodes)
watch(() => props.nodes, assertStatuses)
const nodeByKey = computed(() => new Map(props.nodes.map((n) => [n.key, n])))
const edgeByKey = computed(() => new Map(props.edges.map((e) => [e.key, e])))

const flowNodes = shallowRef<Node[]>([])
const flowEdges = shallowRef<Edge[]>([])

const positionOf = (n: CanvasNode): Point => (isFinitePoint(n.position) ? n.position : laid.value[n.key] ?? { x: 0, y: 0 })

watch(
  () => JSON.stringify([props.editable, props.nodes.map((n) => [n.key, positionOf(n), n.ports, n.readonly ?? false])]),
  () => {
    flowNodes.value = props.nodes.map((n) => ({
      id: n.key,
      type: 'kroker',
      position: positionOf(n),
      data: { key: n.key },
      draggable: props.editable,
    }))
  },
  { immediate: true },
)
watch(
  () => JSON.stringify(props.edges.map((e) => [e.key, e.from, e.to, e.backward])),
  () => {
    flowEdges.value = props.edges.map((e) => ({
      id: e.key,
      type: e.backward ? 'backward' : 'forward',
      source: e.from.node,
      sourceHandle: handleId('out', e.from.port),
      target: e.to.node,
      targetHandle: handleId('in', e.to.port),
      data: { key: e.key },
    }))
  },
  { immediate: true },
)

const edgeText = (key: string): string | undefined => {
  const e = edgeByKey.value.get(key)
  if (!e) return undefined
  return e.counter ? `${e.counter.used}/${e.counter.max}` : e.label
}

const accepts = (c: Connection) => acceptConnection(props.editable, props.connectable, c)

function onConnect(c: Connection) {
  if (accepts(c)) emit('connect', toPortRefs(c))
}

function onDragStop(ev: NodeDragEvent) {
  if (!props.editable) return
  for (const n of ev.nodes) emitMove(n.id, n.position)
}

function onKey(ev: KeyboardEvent) {
  if (!props.editable || !props.selectedKey) return
  if (ev.key !== 'Delete' && ev.key !== 'Backspace') return
  const kind = props.nodes.some((n) => n.key === props.selectedKey) ? 'node' : 'edge'
  emit('remove', { kind, key: props.selectedKey })
}

const root = ref<HTMLElement | null>(null)
function onDrop(ev: DragEvent) {
  if (!props.editable) return
  const type = ev.dataTransfer?.getData('application/x-kroker-node-type')
  if (!type || !root.value) return
  const box = root.value.getBoundingClientRect()
  const p = { x: ev.clientX - box.left - NODE_WIDTH / 2, y: ev.clientY - box.top - 20 }
  if (isFinitePoint(p)) emit('drop-type', { type, ...p })
}

const inPorts = (n: CanvasNode) => n.ports.filter((p) => p.side === 'in')
const outPorts = (n: CanvasNode) => n.ports.filter((p) => p.side === 'out')

defineExpose({ relayout })
</script>

<template>
  <div
    ref="root"
    class="cmp-graph-canvas"
    :class="{ 'is-editable': editable }"
    tabindex="0"
    data-testid="graph-canvas"
    @keydown="onKey"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :nodes-draggable="editable"
      :nodes-connectable="editable"
      :elements-selectable="true"
      :delete-key-code="null"
      :is-valid-connection="accepts"
      :fit-view-on-init="true"
      :min-zoom="0.2"
      @connect="onConnect"
      @node-drag-stop="onDragStop"
      @node-click="(e) => emit('select', e.node.id)"
      @edge-click="(e) => emit('select', e.edge.id)"
      @pane-click="emit('select', null)"
    >
      <template #node-kroker="{ id }">
        <div
          v-if="nodeByKey.get(id)"
          class="cmp-graph-node"
          :class="[nodeByKey.get(id)!.status ? `cmp-graph-node-${nodeByKey.get(id)!.status}` : '', { 'is-readonly': nodeByKey.get(id)!.readonly, 'is-selected': id === selectedKey }]"
          data-testid="graph-node"
          :data-key="id"
        >
          <div class="head">
            <span class="title">{{ nodeByKey.get(id)!.title }}</span>
            <span v-if="nodeByKey.get(id)!.issueCount > 0" class="issues" data-testid="node-issues">{{ nodeByKey.get(id)!.issueCount }}</span>
          </div>
          <div v-if="nodeByKey.get(id)!.subtitle" class="subtitle">{{ nodeByKey.get(id)!.subtitle }}</div>
          <div v-if="nodeByKey.get(id)!.metrics" class="metrics" data-testid="node-metrics">
            <span v-if="nodeByKey.get(id)!.metrics!.round">{{ nodeByKey.get(id)!.metrics!.round }}</span>
            <span v-if="nodeByKey.get(id)!.metrics!.elapsed">{{ nodeByKey.get(id)!.metrics!.elapsed }}</span>
            <span v-if="nodeByKey.get(id)!.metrics!.cost">{{ nodeByKey.get(id)!.metrics!.cost }}</span>
          </div>
          <div class="ports">
            <div class="col">
              <div v-for="p in inPorts(nodeByKey.get(id)!)" :key="p.name" class="port in" :class="{ optional: p.optional, signal: p.kind === 'signal' }">
                <Handle :id="handleId('in', p.name)" type="target" :position="Position.Left" :connectable="editable && !nodeByKey.get(id)!.readonly" />
                {{ p.label }}
              </div>
            </div>
            <div class="col out">
              <div v-for="p in outPorts(nodeByKey.get(id)!)" :key="p.name" class="port out" :class="{ signal: p.kind === 'signal' }">
                {{ p.label }}
                <Handle :id="handleId('out', p.name)" type="source" :position="Position.Right" :connectable="editable && !nodeByKey.get(id)!.readonly" />
              </div>
            </div>
          </div>
          <slot name="node-extra" :node-key="id" />
        </div>
      </template>

      <template #edge-forward="edge">
        <g
          class="cmp-graph-edge"
          :class="{ 'has-issues': (edgeByKey.get(edge.id)?.issueCount ?? 0) > 0, 'is-selected': edge.id === selectedKey }"
          data-testid="graph-edge"
          :data-key="edge.id"
        >
          <BaseEdge
            :id="edge.id"
            :path="getBezierPath(edge)[0]"
            :label-x="getBezierPath(edge)[1]"
            :label-y="getBezierPath(edge)[2]"
            :label="edgeText(edge.id)"
          />
        </g>
      </template>

      <template #edge-backward="edge">
        <g
          class="cmp-graph-edge cmp-graph-edge-backward"
          :class="{ 'has-issues': (edgeByKey.get(edge.id)?.issueCount ?? 0) > 0, 'is-selected': edge.id === selectedKey }"
          data-testid="graph-edge"
          :data-key="edge.id"
        >
          <BaseEdge
            :id="edge.id"
            :path="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[0]"
            :label-x="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[1]"
            :label-y="backwardPath(edge.sourceX, edge.sourceY, edge.targetX, edge.targetY)[2]"
            :label="edgeText(edge.id)"
          />
        </g>
      </template>
    </VueFlow>
  </div>
</template>

<style>
/* vue-flow's structural rules, re-declared with tokens (GRAPH_CANVAS-7).
   @vue-flow/core/dist/style.css is NOT imported: it carries colour literals
   (#b1b1b7, #555, white), verified 2026-09-14 against 1.48.2. */
.cmp-graph-canvas .vue-flow { position: relative; width: 100%; height: 100%; overflow: hidden; z-index: 0; direction: ltr; }
.cmp-graph-canvas .vue-flow__container { position: absolute; height: 100%; width: 100%; left: 0; top: 0; }
.cmp-graph-canvas .vue-flow__pane { z-index: 1; }
.cmp-graph-canvas .vue-flow__pane.draggable { cursor: grab; }
.cmp-graph-canvas .vue-flow__transformationpane { transform-origin: 0 0; z-index: 2; pointer-events: none; }
.cmp-graph-canvas .vue-flow__viewport { z-index: 4; overflow: clip; }
.cmp-graph-canvas .vue-flow__edge-labels { position: absolute; width: 100%; height: 100%; pointer-events: none; user-select: none; }
.cmp-graph-canvas .vue-flow__edges { pointer-events: none; overflow: visible; }
.cmp-graph-canvas .vue-flow__edge-path,
.cmp-graph-canvas .vue-flow__connection-path { stroke: var(--line-strong); stroke-width: 1.5; fill: none; }
.cmp-graph-canvas .vue-flow__edge { pointer-events: visibleStroke; cursor: pointer; }
.cmp-graph-canvas .cmp-graph-edge.is-selected .vue-flow__edge-path { stroke: var(--accent); }
.cmp-graph-canvas .cmp-graph-edge.has-issues .vue-flow__edge-path { stroke: var(--status-failed); }
.cmp-graph-canvas .vue-flow__edge-textbg { fill: var(--ground-3); }
.cmp-graph-canvas .vue-flow__edge-text { fill: var(--ink-tertiary); font-family: var(--font-mono); font-size: 11px; }
.cmp-graph-canvas .vue-flow__connection { pointer-events: none; }
.cmp-graph-canvas .vue-flow__connectionline { z-index: 1001; }
.cmp-graph-canvas .vue-flow__nodes { pointer-events: none; transform-origin: 0 0; }
.cmp-graph-canvas .vue-flow__node { position: absolute; user-select: none; pointer-events: all; transform-origin: 0 0; box-sizing: border-box; cursor: default; }
.cmp-graph-canvas .vue-flow__node.draggable { cursor: grab; }
.cmp-graph-canvas .vue-flow__handle { position: absolute; pointer-events: none; min-width: 7px; min-height: 7px; background: var(--line-strong); border-radius: 50%; }
.cmp-graph-canvas .vue-flow__handle.connectable { pointer-events: all; cursor: crosshair; }
.cmp-graph-canvas .vue-flow__handle-left { top: 50%; left: 0; transform: translate(-50%, -50%); }
.cmp-graph-canvas .vue-flow__handle-right { top: 50%; right: 0; transform: translate(50%, -50%); }
.cmp-graph-canvas .vue-flow__panel { position: absolute; z-index: 5; margin: 15px; }
</style>

<style scoped>
.cmp-graph-canvas { position: relative; width: 100%; height: 100%; min-height: 360px; background: var(--ground-1); outline: none; }
.cmp-graph-node {
  width: 190px; background: var(--ground-3); border: 1px solid var(--line); border-radius: 6px;
  color: var(--ink-secondary); font-family: var(--font-sans); font-size: 12px;
}
.cmp-graph-node.is-readonly { border-style: dashed; }
.cmp-graph-node.is-selected { border-color: var(--accent); }
.head { display: flex; justify-content: space-between; padding: 6px 8px 2px; color: var(--ink-primary); font-weight: 600; }
.issues { background: var(--status-failed); color: var(--ground-0); border-radius: 8px; padding: 0 6px; font-size: 11px; }
.subtitle { padding: 0 8px; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 11px; }
.metrics { display: flex; gap: 8px; padding: 2px 8px; color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; }
.ports { display: flex; justify-content: space-between; padding: 4px 0 6px; }
.col { display: flex; flex-direction: column; }
.col.out { align-items: flex-end; }
.port { position: relative; height: 18px; line-height: 18px; padding: 0 10px; font-family: var(--font-mono); font-size: 11px; color: var(--ink-tertiary); }
.port.optional { color: var(--ink-subtle); }
.port.signal { font-style: italic; }
.cmp-graph-node-idle { border-color: var(--line); }
.cmp-graph-node-running { box-shadow: 0 0 0 2px var(--status-running); }
.cmp-graph-node-blocked { box-shadow: 0 0 0 2px var(--status-blocked); }
.cmp-graph-node-done { box-shadow: 0 0 0 2px var(--status-done); }
.cmp-graph-node-failed { box-shadow: 0 0 0 2px var(--status-failed); }
.cmp-graph-node-stale { box-shadow: 0 0 0 2px var(--status-skipped); }
.cmp-graph-node-skipped { box-shadow: 0 0 0 2px var(--status-skipped); }
.cmp-graph-node-cancelled { box-shadow: 0 0 0 2px var(--status-quarantined); }
.cmp-graph-node-running,
.cmp-graph-node-blocked { animation: fc-pulse 1.6s infinite; }
@keyframes fc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
</style>
