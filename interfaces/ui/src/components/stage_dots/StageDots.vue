<script setup lang="ts">
import { computed } from 'vue'

export type DotState = 'pending' | 'active' | 'done' | 'blocked' | 'failed' | 'skipped'
export interface StageDot { stage: string; state: DotState }

const STATES: readonly string[] = ['pending', 'active', 'done', 'blocked', 'failed', 'skipped']

const props = defineProps<{ dots: StageDot[] }>()

// STAGE_DOTS-1.2: an unknown state is a product fault, not a default.
const marks = computed(() =>
  props.dots.map((d) => {
    if (!STATES.includes(d.state)) {
      throw new Error(`StageDots: unknown state "${d.state}" for stage "${d.stage}"`)
    }
    return { ...d, title: `${d.stage} · ${d.state}` }
  }),
)
</script>

<template>
  <span class="cmp-stage-dots">
    <span
      v-for="m in marks"
      :key="m.stage"
      data-testid="stage-dot"
      class="cmp-stage-dot"
      :class="`cmp-stage-dot-${m.state}`"
      :title="m.title"
    />
  </span>
</template>

<style scoped>
.cmp-stage-dots { display: flex; gap: 3px; }
.cmp-stage-dot { width: 9px; height: 9px; border-radius: 2px; }
.cmp-stage-dot-pending { background: var(--status-pending); }
.cmp-stage-dot-active { background: var(--status-running); }
.cmp-stage-dot-done { background: var(--status-done); }
.cmp-stage-dot-blocked { background: var(--status-blocked); }
.cmp-stage-dot-failed { background: var(--status-failed); }
.cmp-stage-dot-skipped { background: var(--status-skipped); }
.cmp-stage-dot-active,
.cmp-stage-dot-blocked {
  animation: fc-pulse 1.6s infinite;
}
@keyframes fc-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
</style>
