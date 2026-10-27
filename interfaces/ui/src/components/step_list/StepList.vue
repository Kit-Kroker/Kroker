<script setup lang="ts">
// 018 T024 (data-model §4.2, S13): the inner-loop step list — one
// read-only row per step: status pip, name, ref, meta. No control, no
// navigation; the inspector owns everything interactive.
export interface StepItem {
  name: string
  ref: string
  status: import('../graph_canvas/types').CanvasStatus
  meta: string
}

defineProps<{ steps: StepItem[] }>()
</script>

<template>
  <ul class="cmp-step-list">
    <li v-for="(s, i) in steps" :key="`${s.ref}-${i}`" class="row" data-testid="step-row">
      <span class="pip" :class="s.status" data-testid="step-pip" />
      <span class="name">{{ s.name }}</span>
      <span class="ref">{{ s.ref }}</span>
      <span class="meta">{{ s.meta }}</span>
    </li>
  </ul>
</template>

<style scoped>
.cmp-step-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.row { display: grid; grid-template-columns: 10px 1fr auto auto; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 11px; }
.pip { width: 7px; height: 7px; border-radius: 50%; background: var(--ink-subtle); }
.pip.done { background: var(--status-done); }
.pip.running { background: var(--status-running); }
.pip.blocked { background: var(--status-blocked); }
.pip.failed { background: var(--status-failed); }
.pip.stale, .pip.skipped { background: var(--status-skipped); }
.pip.cancelled { background: var(--status-quarantined); }
.name { color: var(--ink-secondary); }
.ref { color: var(--ink-subtle); }
.meta { color: var(--ink-tertiary); }
</style>
