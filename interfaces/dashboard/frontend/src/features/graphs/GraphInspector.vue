<script setup lang="ts">
// The v5 Design inspector (018 T063, S15/S9): an edge edits its
// max_traversals (round-tripping through the parse); a node offers delete
// and renders its PipelineConfig knobs READ-ONLY with the configured
// values — no write route exists and B5 forbids one. The schema-form
// node-field corners are retired with S15.
import { computed, ref, watch } from 'vue'
import { useGraphEditorStore } from './graphEditor.store'
import type { EdgeWire } from '../../api/graph-types'

const editor = useGraphEditorStore()

const node = computed(() => editor.selectedNode?.node ?? null)
const edge = computed(() => editor.selectedEdge?.edge ?? null)

// The edge draft: max_traversals as a string; '' = unset (the field drops).
const maxTraversals = ref('')
watch(edge, (e) => {
  maxTraversals.value = e?.max_traversals != null ? String(e.max_traversals) : ''
}, { immediate: true })

async function applyEdge() {
  if (!edge.value) return
  const raw = String(maxTraversals.value ?? '').trim()
  const n = raw === '' ? undefined : Number(raw)
  const next: EdgeWire = { ...edge.value, max_traversals: n }
  await editor.applyInspector(next)
}

function deleteNode() {
  if (editor.selection) editor.remove('node', editor.selection)
}

// S9: the node's PipelineConfig knobs, read-only with the configured
// values. Everything visible comes from the node itself.
const knobs = computed<{ k: string; v: string }[]>(() => {
  const n = node.value
  if (!n?.gate) return []
  const rows: { k: string; v: string }[] = []
  for (const key of ['policy', 'threshold', 'on_timeout']) {
    const v = (n.gate as Record<string, unknown>)[key]
    if (v !== undefined) rows.push({ k: key, v: String(v) })
  }
  return rows
})

const nodeType = computed(() => node.value?.type ?? '')
const errorsByPath = computed(() => {
  const map = new Map<string, string>()
  for (const e of editor.inspectorErrors) map.set(e.path, e.msg)
  return map
})
</script>

<template>
  <aside class="inspector" data-testid="graph-inspector">
    <p v-if="!node && !edge" class="hint">select a node or an edge</p>

    <template v-else-if="edge">
      <header class="bar">
        <span class="what">edge</span>
        <button
          class="apply"
          data-testid="inspector-apply"
          :disabled="editor.applying"
          @click="applyEdge"
        >apply</button>
      </header>
      <div class="body">
        <p class="path mono">
          {{ edge.source }}.{{ edge.source_port }} → {{ edge.target }}.{{ edge.target_port }}
        </p>
        <label class="field">
          <span class="k">max_traversals</span>
        <input
          v-model="maxTraversals"
          class="v"
          type="number"
          min="1"
          data-testid="inspector-max-traversals"
          :disabled="editor.applying"
        >
        </label>
        <p v-if="errorsByPath.get('max_traversals')" class="err">{{ errorsByPath.get('max_traversals') }}</p>
      </div>
    </template>

    <template v-else-if="node">
      <header class="bar">
        <span class="what">node</span>
        <button
          class="danger"
          data-testid="inspector-delete"
          :disabled="editor.applying"
          @click="deleteNode"
        >delete</button>
      </header>
      <div class="body">
        <p class="path mono">{{ node.id }} <span class="dim">· {{ nodeType }}</span></p>
        <div
          v-for="knob in knobs"
          :key="knob.k"
          class="knob"
          data-testid="inspector-knob"
          :data-k="knob.k"
        >
          <span class="k">{{ knob.k }}</span>
          <span class="v mono">{{ knob.v }}</span>
        </div>
        <p v-if="!knobs.length" class="hint">no PipelineConfig knobs on this node.</p>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.inspector { width: 320px; overflow: auto; background: var(--ground-2); border-left: 1px solid var(--line); }
.hint { padding: 12px; color: var(--ink-subtle); font-size: 12px; }
.bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-bottom: 1px solid var(--line); }
.what { color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; }
.body { padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.path { margin: 0; font-size: 11.5px; color: var(--ink-primary); overflow-wrap: anywhere; }
.dim { color: var(--ink-muted); }
.mono { font-family: var(--font-mono); }
.field, .knob { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.field .k, .knob .k { font-family: var(--font-mono); font-size: 11px; color: var(--ink-muted); }
.field .v, .knob .v {
  font-family: var(--font-mono); font-size: 11px; color: var(--ink-secondary);
  background: var(--ground-raised); border: 1px solid var(--line); border-radius: 4px;
  padding: 3px 6px; width: 140px;
}
.knob .v { color: var(--ink-muted); }
.apply { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 4px; padding: 3px 12px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.apply:disabled { background: var(--ground-4); color: var(--ink-whisper); cursor: not-allowed; }
.danger { background: none; border: 1px solid var(--status-failed); color: var(--status-failed); border-radius: 4px; padding: 3px 10px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.err { margin: 0; color: var(--status-failed); font-size: 11px; }
</style>
