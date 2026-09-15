<script setup lang="ts">
// Edit mode at /graphs (E-76 spec §8). `?from=run:<id>` opens a run's graph
// as a COPY; `?sha=<sha>` loads a saved graph (when the server declares load).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import GraphCanvas from '@kroker/ui/components/graph_canvas/GraphCanvas.vue'
import NodePalette from '@kroker/ui/components/node_palette/NodePalette.vue'
import IssueList from '@kroker/ui/components/issue_list/IssueList.vue'
import YamlPane from '@kroker/ui/components/yaml_pane/YamlPane.vue'
import type { PortRef } from '@kroker/ui/components/graph_canvas/types'
import GraphInspector from '../components/graph/GraphInspector.vue'
import { useCatalogStore } from '../stores/catalog'
import { useGraphEditorStore } from '../stores/graphEditor'
import { locLabel, nodeKeys, toCanvas } from '../adapters/graph'

const route = useRoute()
const catalog = useCatalogStore()
const editor = useGraphEditorStore()
const tab = ref<'canvas' | 'yaml'>('canvas')

onMounted(async () => {
  await catalog.load()
  const from = route.query.from
  const sha = route.query.sha
  if (typeof from === 'string' && from.startsWith('run:') && catalog.can('run_graph')) await editor.openRunCopy(from.slice(4))
  else if (typeof sha === 'string' && catalog.can('load')) await editor.loadSha(sha)
})

// U5: text that fails the shape parse lives in the YAML pane.
watch(() => editor.state, (s) => { if (s === 'text_broken') tab.value = 'yaml' })
watch(tab, (t) => { if (t === 'yaml') void editor.openYaml() })

const model = computed(() =>
  editor.working
    ? toCanvas(editor.working, {
        typeOf: catalog.typeOf,
        issues: editor.validation?.issues,
        backEdges: editor.validation?.back_edges,
      })
    : null,
)
const paletteItems = computed(() => catalog.nodeTypes.map((t) => ({ type: t.type, kind: t.kind, stage: t.canonical_stage })))
const yamlErrors = computed(() =>
  editor.yamlErrors.map((e) => ({ path: locLabel(e.loc), message: e.msg, line: e.line, column: e.column })),
)

function typeOfKey(key: string): string | undefined {
  const g = editor.working
  if (!g) return undefined
  const i = nodeKeys(g).indexOf(key)
  return i < 0 ? undefined : g.nodes[i].type
}
// GRAPH_CANVAS-6: the only drag-time rule, Python's table served as data.
function connectable(from: PortRef, to: PortRef): boolean {
  const s = typeOfKey(from.node)
  const t = typeOfKey(to.node)
  return !!s && !!t && catalog.connectable(s, from.port, t, to.port)
}

const saveHint = computed(() =>
  catalog.can('save') ? '' : `Saving arrives with E-77${catalog.can('validate') ? '' : '; validation with E-73'}.`,
)
</script>

<template>
  <main data-testid="graph-editor-view" data-screen-label="Graph editor" class="view">
    <NodePalette :items="paletteItems" :disabled="editor.canvasLocked" @pick="(t) => editor.addNode(t, 40, 40)" />
    <section class="center">
      <header class="toolbar">
        <div class="tabs">
          <button class="tab" :class="{ on: tab === 'canvas' }" data-testid="tab-canvas" @click="tab = 'canvas'">canvas</button>
          <button class="tab" :class="{ on: tab === 'yaml' }" data-testid="tab-yaml" @click="tab = 'yaml'">yaml</button>
        </div>
        <button class="btn" data-testid="editor-new" @click="editor.newGraph()">new</button>
        <button class="btn" data-testid="editor-tidy" :disabled="editor.canvasLocked" @click="editor.tidy()">tidy</button>
        <span class="state" data-testid="editor-state" :data-state="editor.state">{{ editor.state }}</span>
        <span v-if="editor.sha" class="sha" data-testid="editor-sha">{{ editor.sha.slice(0, 12) }}</span>
        <span v-if="editor.validation && !editor.runnable" class="badge" data-testid="not-runnable">not runnable · {{ editor.errorCount }}</span>
        <span v-if="editor.notice" class="notice" data-testid="editor-notice">{{ editor.notice }}</span>
        <span class="spacer" />
        <span v-if="saveHint" class="hint">{{ saveHint }}</span>
        <button class="btn save" data-testid="editor-save" :disabled="!catalog.can('save') || editor.state !== 'graph_loaded'" @click="editor.save()">save</button>
      </header>

      <div v-show="tab === 'canvas'" class="canvas-wrap">
        <p v-if="editor.state === 'text_broken'" class="banner" data-testid="canvas-disabled">
          the text does not parse — fix it in the yaml tab
        </p>
        <p v-else-if="editor.state === 'empty'" class="banner">paste YAML in the yaml tab, or start a new graph</p>
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
          @drop-type="(d) => editor.addNode(d.type, d.x, d.y)"
          @layout-failed="(msg) => (editor.notice = `layout failed: ${msg}`)"
        />
      </div>
      <YamlPane
        v-if="tab === 'yaml'"
        class="yaml"
        :text="editor.yamlText"
        :errors="yamlErrors"
        :dirty="editor.yamlDirty"
        :busy="editor.applying"
        :max-bytes="catalog.catalog?.max_graph_bytes ?? null"
        @update:text="editor.setYamlText"
        @apply="editor.applyText()"
      />
      <IssueList v-if="model && model.issues.length" :items="model.issues" @focus="editor.select" />
    </section>
    <GraphInspector />
  </main>
</template>

<style scoped>
.view { flex: 1; display: flex; min-height: 0; }
.center { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.toolbar { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--line); background: var(--ground-0); font-size: 12px; }
.tabs { display: flex; gap: 2px; }
.tab, .btn { background: var(--ground-3); color: var(--ink-tertiary); border: 1px solid var(--line); border-radius: 4px; padding: 2px 10px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.tab.on { border-color: var(--accent); color: var(--ink-primary); }
.btn:disabled { color: var(--ink-whisper); cursor: not-allowed; }
.state, .sha { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; }
.badge { color: var(--status-failed); font-family: var(--font-mono); font-size: 11px; }
.notice { color: var(--status-blocked); font-size: 11px; }
.hint { color: var(--ink-subtle); font-size: 11px; }
.spacer { flex: 1; }
.canvas-wrap { flex: 1; position: relative; min-height: 0; }
.banner { margin: 0; padding: 8px 12px; color: var(--ink-muted); font-size: 12px; }
.yaml { flex: 1; min-height: 0; }
</style>
