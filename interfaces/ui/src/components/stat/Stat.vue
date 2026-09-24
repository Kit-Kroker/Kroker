<script setup lang="ts">
import { computed } from 'vue'
import StatusPip from '../status_pip/StatusPip.vue'

const props = defineProps<{ label: string; value: string | number | null | undefined; pip?: string }>()
const shown = computed(() => (props.value === null || props.value === undefined || props.value === '' ? '—' : String(props.value)))
</script>

<template>
  <div class="cmp-stat">
    <span class="label"><StatusPip v-if="pip" :kind="pip" />{{ label }}</span>
    <span class="value" data-testid="stat-value">{{ shown }}</span>
  </div>
</template>

<style scoped>
.cmp-stat { display: flex; flex-direction: column; gap: 2px; font-family: var(--font-sans); }
.label { display: flex; align-items: center; gap: 6px; font-size: var(--text-xs); color: var(--ink-secondary); }
.value { font-family: var(--font-mono); font-size: var(--text-lg); font-weight: 500; color: var(--ink-primary); }
</style>
