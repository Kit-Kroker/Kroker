<script setup lang="ts">
// v5 Design (018 T063, S9/S15): the shared Observe canvas in edit mode.
// The palette is built from the served catalog grouped by canonical_stage
// (FR-046), planned types render dashed and unplaceable (V9), connections
// with unequal payloads are refused at drop time (FR-047, in the store),
// the inspector edits edges and shows read-only knobs, and the validation
// panel carries the backend validator's categories with V2/V3 copy. "Run
// this version" starts only the saved, unchanged shipped default (R-15).
// The YAML pane is retired with S15: no text surface exists here.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import type { PortRef } from '@kroker/ui/components/graph_canvas/types'
import GraphInspector from './GraphInspector.vue'
import { api } from '../../api/client'
import { useCatalogStore } from '../../shared/catalog.store'
import { useGraphEditorStore } from './graphEditor.store'
import { useUiStore } from '../../app/ui.store'
import { nodeKeys, toCanvas } from '../../shared/graphCanvas.adapter'

const props = defineProps<{ sha?: string }>()
const route = useRoute()
const catalog = useCatalogStore()
const editor = useGraphEditorStore()
const ui = useUiStore()

// V9: the planned node types (feedback A-4), a presentation-only read.
const planned = ref<Set<string>>(new Set())
// R-15: the shipped default's sha the run rule compares against.
const defaultSha = ref<string | null>(null)

onMounted(async () => {
  await catalog.load()
  void api.getPlannedTypes().then((list) => { planned.value = new Set(list) }).catch(() => {})
  void api
    .getShippedGraphs()
    .then((s) => { defaultSha.value = s.graphs.find((g) => g.name === 'default')?.sha ?? null })
    .catch(() => {})
  const from = route.query.from
  if (typeof from === 'string' && from.startsWith('run:') && catalog.can('run_graph')) {
    await editor.openRunCopy(from.slice(4))
  } else if (props.sha && catalog.can('load')) {
    await editor.loadSha(props.sha)
  }
})

const model = computed(() =>
  editor.working
    ? toCanvas(editor.working, {
        typeOf: catalog.typeOf,
        issues: editor.validation?.issues,
        backEdges: editor.validation?.back_edges,
      })
    : null,
)

// FR-046: the palette from the catalog, grouped by canonical_stage in the
// served order — only stages that carry types.
const paletteGroups = computed(() => {
  const stages = catalog.catalog?.canonical_stages ?? []
  const groups: { title: string; types: string[] }[] = []
  for (const stage of stages) {
    const types = catalog.nodeTypes.filter((t) => t.canonical_stage === stage).map((t) => t.type)
    if (types.length) groups.push({ title: stage, types })
  }
  return groups
})
const plannedTypes = computed(() => [...planned.value].filter((t) => !catalog.typeOf(t)))

// V9: a planned type refuses placement — and the store's addNode refuses
// anything the catalog does not serve.
function onDropType(d: { type: string; x: number; y: number }) {
  if (planned.value.has(d.type)) return
  editor.addNode(d.type, d.x, d.y)
}

function typeOfKey(key: string): string | undefined {
  const g = editor.working
  if (!g) return undefined
  const i = nodeKeys(g).indexOf(key)
  return i < 0 ? undefined : g.nodes[i].type
}
function connectable(from: PortRef, to: PortRef): boolean {
  const s = typeOfKey(from.node)
  const t = typeOfKey(to.node)
  return !!s && !!t && catalog.connectable(s, from.port, t, to.port)
}

// V3: an edgeless non-terminal out-port becomes a completion sink; the
// panel warns before the drop ever creates one.
const edgelessOutPorts = computed(() => {
  if (!editor.working) return []
  const wired = new Set(editor.working.edges.map((e) => `${e.source}.${e.source_port}`))
  const out: string[] = []
  for (const n of editor.working.nodes) {
    const t = catalog.typeOf(n.type)
    if (!t) continue
    for (const p of t.ports) {
      if (p.direction === 'out' && !wired.has(`${n.id}.${p.name}`)) out.push(`${n.id}.${p.name}`)
    }
  }
  return out
})

// R-15: enabled only for the saved, unchanged shipped default.
const canRun = computed(
  () => defaultSha.value !== null && editor.savedSha === defaultSha.value && editor.sha === editor.savedSha,
)
const runReason = computed(() => {
  if (canRun.value) return null
  if (editor.savedSha === null) return 'this graph has not been saved'
  if (editor.sha !== editor.savedSha) return 'the working copy has unsaved changes'
  return 'only the shipped default can be started from Design'
})
</script>

<template>
  <main data-testid="design-view" data-screen-label="Design" class="view">
    <aside class="palette" data-testid="design-palette">
      <section v-for="g in paletteGroups" :key="g.title" class="group">
        <h4 class="group-title" data-testid="palette-group-title">{{ g.title }}</h4>
        <button
          v-for="t in g.types"
          :key="t"
          class="type"
          data-testid="palette-type"
          :disabled="editor.canvasLocked"
          @click="editor.addNode(t, 40, 40)"
        >{{ t }}</button>
      </section>
      <section v-if="plannedTypes.length" class="group" aria-label="planned">
        <button
          v-for="t in plannedTypes"
          :key="t"
          class="type planned"
          data-testid="palette-type"
          :title="'planned node type — it cannot be placed yet'"
          disabled
        >{{ t }} · unmapped</button>
      </section>
    </aside>

    <section class="center">
      <header class="toolbar">
        <button class="btn" data-testid="design-undo" :disabled="!editor.canUndo" @click="editor.undo()">undo</button>
        <button class="btn" data-testid="design-redo" :disabled="!editor.canRedo" @click="editor.redo()">redo</button>
        <button class="btn" data-testid="design-tidy" :disabled="editor.canvasLocked" @click="editor.tidy()">tidy</button>
        <span class="state" data-testid="design-state" :data-state="editor.state">{{ editor.state }}</span>
        <span v-if="editor.sha" class="sha" data-testid="design-sha">{{ editor.sha.slice(0, 12) }}</span>
        <span v-if="editor.validation && !editor.runnable" class="badge" data-testid="not-runnable">not runnable · {{ editor.errorCount }}</span>
        <span v-if="editor.notice" class="notice" data-testid="design-notice">{{ editor.notice }}</span>
        <span class="spacer" />
        <!-- R-15 (T065): the enabled button opens the existing start form —
             sending no graph field; the run always starts on the shipped
             default. -->
        <button
          class="btn run"
          data-testid="run-this-version"
          :disabled="!canRun"
          @click="ui.openStart()"
        >Run this version</button>
        <span v-if="runReason" class="reason" data-testid="run-reason">{{ runReason }}</span>
        <button
          class="btn save"
          data-testid="design-save"
          :disabled="!catalog.can('save') || editor.state !== 'graph_loaded'"
          @click="editor.save()"
        >save</button>
      </header>

      <div class="canvas-wrap">
        <p v-if="editor.state === 'empty'" class="banner">open a graph from the catalog, or drop a node type.</p>
        <GraphCanvas
          v-if="model && editor.state === 'graph_loaded'"
          :nodes="model.nodes"
          :edges="model.edges"
          :editable="!editor.canvasLocked"
          :connectable="connectable"
          :selected-key="editor.selection"
          :tidy-request="editor.tidyRequest"
          @connect="(c) => editor.connect(c.from.node, c.from.port, c.to.node, c.to.port)"
          @move="(m) => editor.move(m.key, m.x, m.y)"
          @remove="(r) => editor.remove(r.kind, r.key)"
          @select="editor.select"
          @drop-type="onDropType"
          @layout-failed="(msg) => (editor.notice = `layout failed: ${msg}`)"
        />
      </div>

      <!-- FR-048: the validation panel, matching the backend validator's
           categories. V2: terminal copy; V3: the completion-sink warning. -->
      <section class="validation" data-testid="validation-panel">
        <h3 class="panel-title">validation</h3>
        <ul class="categories">
          <li>gate shape</li>
          <li>required inputs</li>
          <li>reachability</li>
          <li>bounded cycles</li>
          <li>terminal reach — a run ends only rejected, failed or escalated</li>
        </ul>
        <p v-if="edgelessOutPorts.length" class="warn" data-testid="completion-sink-warning">
          completion sink: {{ edgelessOutPorts.slice(0, 3).join(', ') }}{{ edgelessOutPorts.length > 3 ? '…' : '' }}
          — an edgeless non-terminal out-port becomes a completion point
        </p>
        <p v-if="editor.validation" class="issues" data-testid="validation-issues">
          {{ editor.validation.issues.length }} issue(s), {{ editor.errorCount }} error(s)
        </p>
      </section>
    </section>

    <GraphInspector />
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; min-height: 0; }
.palette { width: 180px; overflow: auto; border-right: 1px solid var(--line); padding: 8px; }
.group { margin-bottom: 10px; }
.group-title { margin: 0 0 4px; color: var(--ink-muted); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
.type {
  display: block; width: 100%; text-align: left; margin-bottom: 2px;
  background: var(--ground-2); color: var(--ink-secondary);
  border: 1px solid var(--line); border-radius: 4px;
  padding: 2px 8px; font-family: var(--font-mono); font-size: 11px; cursor: pointer;
}
.type:hover:not(:disabled) { color: var(--ink-primary); border-color: var(--line-strong); }
.type.planned {
  border-style: dashed; color: var(--ink-muted); cursor: not-allowed;
  text-decoration: line-through 1px var(--ink-whisper);
}
.center { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--line); background: var(--ground-0); font-size: 12px; }
.btn { background: var(--ground-3); color: var(--ink-tertiary); border: 1px solid var(--line); border-radius: 4px; padding: 2px 10px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.btn:disabled { color: var(--ink-whisper); cursor: not-allowed; }
.btn.run:not(:disabled) { border-color: var(--status-done); color: var(--status-done); }
.state, .sha { color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; }
.badge { color: var(--status-failed); font-family: var(--font-mono); font-size: 11px; }
.notice { color: var(--status-blocked); font-size: 11px; }
.reason { color: var(--ink-muted); font-size: 11px; }
.spacer { flex: 1; }
.canvas-wrap { flex: 1; position: relative; min-height: 120px; }
.banner { margin: 0; padding: 8px 12px; color: var(--ink-muted); font-size: 12px; }
.validation { border-top: 1px solid var(--line); padding: 8px 12px; background: var(--ground-0); }
.panel-title { margin: 0 0 4px; font-size: 11px; font-family: var(--font-mono); color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.08em; }
.categories { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px 16px; }
.categories li { font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-secondary); }
.warn { margin: 6px 0 0; color: var(--status-blocked); font-size: 11px; }
.issues { margin: 4px 0 0; color: var(--ink-muted); font-family: var(--font-mono); font-size: 10.5px; }
</style>
