<script setup lang="ts">
// 018 T032 (S13, screen-local per data-model line 155): the Observe
// inspector. Presentational — RunView owns the mapping (configured model
// from the node's role override or the catalog type's default, answering
// from the run's role). The code node carries the read-only inner loop
// (StepList, FR-017); its step wire arrives with the card slice, so the
// list mounts empty for now.
import StepList from '@kroker/ui/components/step_list/StepList.vue'
import type { StepItem } from '@kroker/ui/components/step_list/StepList.vue'

defineProps<{
  title: string
  configured: string
  answering: string
  isCode: boolean
  steps?: StepItem[]
}>()

const differs = (configured: string, answering: string): boolean =>
  configured !== answering && configured !== 'not measured' && answering !== 'not measured'
</script>

<template>
  <aside class="cmp-run-inspector" data-testid="run-inspector">
    <div class="title">{{ title }}</div>
    <div class="row">
      <span class="k">configured</span>
      <span class="v mono" data-testid="inspector-configured">{{ configured }}</span>
    </div>
    <div class="row">
      <span class="k">answering</span>
      <span class="v mono" data-testid="inspector-answering">{{ answering }}</span>
    </div>
    <div v-if="differs(configured, answering)" class="diff" data-testid="inspector-model-diff">
      the answering model differs from the configured one
    </div>
    <div v-if="isCode" class="loop">
      <div class="loop-title">inner loop</div>
      <StepList :steps="steps ?? []" />
    </div>
  </aside>
</template>

<style scoped>
.cmp-run-inspector {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--ground-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--ink-secondary);
}
.title { font-weight: 600; color: var(--ink-primary); }
.row { display: flex; justify-content: space-between; gap: 8px; }
.row .k { color: var(--ink-subtle); }
.row .v { color: var(--ink-tertiary); }
.mono { font-family: var(--font-mono); font-size: 11px; }
.diff {
  color: var(--status-waiting);
  font-family: var(--font-mono);
  font-size: 11px;
  border-top: 1px solid var(--line);
  padding-top: 6px;
}
.loop { border-top: 1px solid var(--line); padding-top: 6px; }
.loop-title { font-family: var(--font-mono); font-size: 11px; color: var(--ink-subtle); margin-bottom: 4px; }
</style>
