<script setup lang="ts">
export interface SegmentOption {
  value: string
  label: string
  count?: number
}

const props = defineProps<{ options: SegmentOption[]; modelValue: string; label?: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

function pick(value: string) {
  if (value !== props.modelValue) emit('update:modelValue', value)
}
</script>

<template>
  <div class="cmp-segmented-control" role="radiogroup" :aria-label="label">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      class="segment"
      :class="{ 'is-selected': o.value === modelValue }"
      :aria-checked="o.value === modelValue"
      :data-testid="`segment-${o.value}`"
      @click="pick(o.value)"
    >
      {{ o.label }}<span v-if="o.count !== undefined" class="count">{{ o.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.cmp-segmented-control { display: inline-flex; gap: 2px; padding: 3px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--ground-raised); }
.segment { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border: none; border-radius: 6px; background: transparent; color: var(--ink-secondary); font-family: var(--font-sans); font-size: var(--text-md); font-weight: 500; cursor: pointer; }
.segment:hover:not(.is-selected) { color: var(--ink-primary); }
.segment.is-selected { background: var(--ink-primary); color: var(--ink-inverse); cursor: default; }
.segment:focus-visible { outline: 2px solid var(--ink-secondary); outline-offset: 1px; }
.count { font-family: var(--font-mono); font-size: var(--text-xs); opacity: 0.7; }
</style>
