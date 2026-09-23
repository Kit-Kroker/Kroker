<script setup lang="ts">
// The inspector (E-76 spec §8.3): a schema_form over the SERVED GraphNode /
// GraphEdge schema. Nothing here names a RoleConfig or GateConfig field.
import { computed, ref, watch } from 'vue'
import SchemaForm from '@kroker/ui/components/schema_form/SchemaForm.vue'
import { useCatalogStore } from '../../shared/catalog.store'
import { useGraphEditorStore } from '../../stores/graphEditor'
import type { EdgeWire, NodeWire } from '../../api/graph-types'

const catalog = useCatalogStore()
const editor = useGraphEditorStore()

const target = computed(() =>
  editor.selectedNode
    ? { kind: 'node' as const, value: editor.selectedNode.node as unknown as Record<string, unknown> }
    : editor.selectedEdge
      ? { kind: 'edge' as const, value: editor.selectedEdge.edge as unknown as Record<string, unknown> }
      : null,
)
const schema = computed(() => {
  if (!catalog.catalog || !target.value) return null
  return target.value.kind === 'node' ? catalog.catalog.schemas.GraphNode : catalog.catalog.schemas.GraphEdge
})

const draft = ref<Record<string, unknown> | null>(null)
const dirty = ref(false)
watch(target, (t) => { draft.value = t ? { ...t.value } : null; dirty.value = false }, { immediate: true })

function onUpdate(v: Record<string, unknown>) {
  draft.value = v
  dirty.value = true
}
async function apply() {
  if (!draft.value) return
  await editor.applyInspector(draft.value as unknown as NodeWire | EdgeWire)
  if (editor.inspectorErrors.length === 0) dirty.value = false
}
</script>

<template>
  <aside class="inspector" data-testid="graph-inspector">
    <p v-if="!target" class="hint">select a node or an edge</p>
    <template v-else-if="schema && draft">
      <header class="bar">
        <span class="what">{{ target.kind }}</span>
        <button class="apply" data-testid="inspector-apply" :disabled="!dirty || editor.applying" @click="apply">apply</button>
      </header>
      <SchemaForm
        :schema="schema"
        :value="target.value"
        :errors="editor.inspectorErrors"
        :readonly-paths="target.kind === 'node' ? ['type'] : []"
        :readonly="editor.applying"
        @update="onUpdate"
      />
    </template>
  </aside>
</template>

<style scoped>
.inspector { width: 320px; overflow: auto; background: var(--ground-2); border-left: 1px solid var(--line); }
.hint { padding: 12px; color: var(--ink-subtle); font-size: 12px; }
.bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border-bottom: 1px solid var(--line); }
.what { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; }
.apply { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 4px; padding: 3px 12px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.apply:disabled { background: var(--ground-4); color: var(--ink-whisper); cursor: not-allowed; }
</style>
