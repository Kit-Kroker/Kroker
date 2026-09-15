<script setup lang="ts">
import { computed } from 'vue'

export interface PaletteItem {
  type: string
  kind: 'stage' | 'gate'
  stage: string | null
}

const props = withDefaults(defineProps<{ items: PaletteItem[]; disabled?: boolean }>(), { disabled: false })
const emit = defineEmits<{ (e: 'pick', type: string): void }>()

// Supplied order within each kind (the catalog serves types sorted).
const groups = computed(() =>
  (['stage', 'gate'] as const)
    .map((kind) => ({ kind, items: props.items.filter((i) => i.kind === kind) }))
    .filter((g) => g.items.length > 0),
)

function onDragStart(ev: DragEvent, type: string) {
  if (props.disabled) {
    ev.preventDefault()
    return
  }
  ev.dataTransfer?.setData('application/x-kroker-node-type', type)
}

function onPick(type: string) {
  if (!props.disabled) emit('pick', type)
}
</script>

<template>
  <aside class="cmp-node-palette" data-testid="node-palette">
    <p v-if="groups.length === 0" class="empty" data-testid="palette-empty">no node types</p>
    <section v-for="g in groups" :key="g.kind">
      <h4 class="group">{{ g.kind === 'stage' ? 'STAGES' : 'GATES' }}</h4>
      <button
        v-for="item in g.items"
        :key="item.type"
        class="item"
        data-testid="palette-item"
        :data-type="item.type"
        :disabled="disabled"
        draggable="true"
        @dragstart="onDragStart($event, item.type)"
        @click="onPick(item.type)"
      >
        <span class="type">{{ item.type }}</span>
        <span class="stage">{{ item.stage ?? 'unknown' }}</span>
      </button>
    </section>
  </aside>
</template>

<style scoped>
.cmp-node-palette { display: flex; flex-direction: column; gap: 10px; padding: 10px; width: 180px; background: var(--ground-2); border-right: 1px solid var(--line); overflow: auto; }
.empty { color: var(--ink-subtle); font-size: 12px; }
.group { margin: 0 0 4px; color: var(--ink-faint); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; }
.item { display: flex; flex-direction: column; align-items: flex-start; width: 100%; margin-bottom: 4px; padding: 4px 6px; background: var(--ground-3); border: 1px solid var(--line); border-radius: 4px; color: var(--ink-secondary); cursor: grab; }
.item:disabled { cursor: not-allowed; color: var(--ink-whisper); }
.type { font-family: var(--font-mono); font-size: 12px; }
.stage { color: var(--ink-subtle); font-size: 10px; }
</style>
