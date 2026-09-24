<script setup lang="ts">
const props = withDefaults(defineProps<{ label: string; count?: number; selected?: boolean; disabled?: boolean }>(), {
  selected: false,
  disabled: false,
})
const emit = defineEmits<{ (e: 'select'): void }>()

function press() {
  if (!props.disabled) emit('select')
}
</script>

<template>
  <button
    type="button"
    class="cmp-filter-chip"
    :class="{ 'is-selected': selected }"
    :aria-pressed="selected"
    :disabled="disabled"
    data-testid="filter-chip"
    @click="press"
  >
    {{ label }}<span v-if="count !== undefined" class="count">{{ count }}</span>
  </button>
</template>

<style scoped>
.cmp-filter-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border: 1px solid var(--line); border-radius: var(--radius-sm); background: transparent; color: var(--ink-secondary); font-family: var(--font-sans); font-size: var(--text-sm); cursor: pointer; }
.cmp-filter-chip:hover:not(:disabled) { color: var(--ink-primary); }
.cmp-filter-chip.is-selected { background: var(--ground-raised); border-color: var(--line-strong); color: var(--ink-primary); }
.cmp-filter-chip:disabled { cursor: not-allowed; opacity: 0.5; }
.cmp-filter-chip:focus-visible { outline: 2px solid var(--ink-secondary); outline-offset: 1px; }
.count { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--ink-muted); }
</style>
