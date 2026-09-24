<script setup lang="ts">
import { computed } from 'vue'
import StatusPip from '../status_pip/StatusPip.vue'

const props = withDefaults(defineProps<{ kind: string; label?: string; mono?: boolean; pulsing?: boolean }>(), {
  mono: false,
  pulsing: false,
})

// STATUS_TAG-2: 'in_progress' -> 'In progress'. The caller passes label to override.
const text = computed(() => {
  if (props.label) return props.label
  const s = props.kind.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
})
</script>

<template>
  <span class="cmp-status-tag" :class="[`cmp-status-tag-${kind}`, { 'is-mono': mono }]">
    <StatusPip :kind="kind" :pulsing="pulsing" />
    <span class="label">{{ text }}</span>
  </span>
</template>

<style scoped>
.cmp-status-tag { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: var(--radius-sm); font-family: var(--font-sans); font-size: var(--text-sm); font-weight: 500; white-space: nowrap; background: var(--status-idle-tint); color: var(--ink-secondary); }
.cmp-status-tag.is-mono { font-family: var(--font-mono); font-size: var(--text-xs); letter-spacing: 0.04em; text-transform: uppercase; }
.cmp-status-tag :deep(.cmp-status-pip) { width: 6px; height: 6px; }
.cmp-status-tag-running, .cmp-status-tag-in_progress { background: var(--status-running-tint); color: var(--status-running); }
.cmp-status-tag-blocked, .cmp-status-tag-waiting { background: var(--status-waiting-tint); color: var(--status-waiting); }
.cmp-status-tag-failed, .cmp-status-tag-quarantined { background: var(--status-failed-tint); color: var(--status-failed); }
.cmp-status-tag-done { background: var(--status-done-tint); color: var(--status-done); }
</style>
