<script setup lang="ts">
const props = withDefaults(defineProps<{ selected?: boolean; disabled?: boolean; dense?: boolean }>(), {
  selected: false,
  disabled: false,
  dense: false,
})
const emit = defineEmits<{ (e: 'select'): void }>()

function press() {
  if (!props.disabled) emit('select')
}
</script>

<template>
  <button
    type="button"
    class="cmp-list-row"
    :class="{ 'is-selected': selected, 'is-dense': dense }"
    :aria-current="selected ? 'true' : undefined"
    :disabled="disabled"
    data-testid="list-row"
    @click="press"
  >
    <span v-if="$slots.leading" class="leading"><slot name="leading" /></span>
    <span class="main"><slot /></span>
    <span v-if="$slots.meta" class="meta"><slot name="meta" /></span>
  </button>
</template>

<style scoped>
.cmp-list-row { width: 100%; display: flex; align-items: center; gap: var(--space-3); padding: 9px 10px; border: none; border-radius: var(--radius-md); background: transparent; color: var(--ink-primary); font-family: var(--font-sans); font-size: var(--text-md); text-align: left; cursor: pointer; }
.cmp-list-row.is-dense { padding: 6px 10px; }
.cmp-list-row:hover:not(:disabled) { background: var(--ground-raised); }
.cmp-list-row.is-selected { background: var(--ground-raised); box-shadow: inset 0 0 0 1px var(--line-strong); }
.cmp-list-row:disabled { cursor: default; color: var(--ink-muted); }
.cmp-list-row:focus-visible { outline: 2px solid var(--ink-secondary); outline-offset: -2px; }
.leading { flex: none; display: flex; align-items: center; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
.meta { flex: none; display: flex; align-items: center; gap: var(--space-2); font-family: var(--font-mono); font-size: var(--text-xs); color: var(--ink-muted); }
</style>
