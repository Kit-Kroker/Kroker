<script setup lang="ts">
export interface TabItem {
  id: string
  label: string
  count?: number
  disabled?: boolean
}

const props = defineProps<{ tabs: TabItem[]; active: string; label?: string }>()
const emit = defineEmits<{ (e: 'select', id: string): void }>()

function pick(t: TabItem) {
  if (!t.disabled && t.id !== props.active) emit('select', t.id)
}
</script>

<template>
  <nav class="cmp-tab-bar" role="tablist" :aria-label="label">
    <button
      v-for="t in tabs"
      :key="t.id"
      type="button"
      role="tab"
      class="tab"
      :class="{ 'tab-active': t.id === active }"
      :aria-selected="t.id === active"
      :disabled="t.disabled"
      :data-testid="`tab-${t.id}`"
      @click="pick(t)"
    >
      {{ t.label }}<span v-if="t.count" class="badge" data-testid="tab-count">{{ t.count }}</span>
    </button>
  </nav>
</template>

<style scoped>
.cmp-tab-bar { display: flex; align-items: flex-end; gap: var(--space-1); padding: 0 20px; background: var(--ground-shell); border-bottom: 1px solid var(--line); }
.tab { display: inline-flex; align-items: center; gap: var(--space-2); padding: 10px 12px 9px; border: none; border-bottom: 2px solid transparent; background: none; color: var(--ink-secondary); font-family: var(--font-sans); font-size: var(--text-md); font-weight: 500; cursor: pointer; }
.tab:hover:not(:disabled) { color: var(--ink-primary); }
.tab-active { color: var(--ink-primary); border-bottom-color: var(--ink-primary); cursor: default; }
.tab:disabled { color: var(--ink-muted); cursor: not-allowed; }
.tab:focus-visible { outline: 2px solid var(--ink-secondary); outline-offset: -2px; }
.badge { min-width: 18px; padding: 0 5px; border-radius: 9px; background: var(--status-waiting); color: var(--ink-inverse); font-family: var(--font-mono); font-size: var(--text-xs); font-weight: 600; line-height: 18px; text-align: center; }
</style>
