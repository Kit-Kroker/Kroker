<script setup lang="ts">
import { computed } from 'vue'
import type { Run } from '../../api/types'
import { statusMetaOf } from '../../composables/status'
import { money } from '../../composables/format'
import { STAGES } from '../../constants'
import { stageStateOf } from '../../composables/stageState'
import StageDots from '@kroker/ui/components/stage_dots/StageDots.vue'
import StatusPip from '@kroker/ui/components/status_pip/StatusPip.vue'

const props = defineProps<{ run: Run }>()
const meta = computed(() => statusMetaOf(props.run))
const dots = computed(() =>
  STAGES.map((stage, i) => ({
    stage,
    state: stageStateOf(props.run, i),
  })),
)
</script>

<template>
  <RouterLink :to="`/runs/${run.id}`" data-testid="fleet-row" class="row">
    <span class="id">{{ run.id }}</span>
    <span class="title">
      <span class="title-text">{{ run.title }}</span>
      <span class="mode">{{ run.mode }}</span>
    </span>
    <StageDots :dots="dots" />
    <span class="status" :style="{ color: meta.color }">
      <StatusPip :kind="run.status" :pulsing="run.status === 'running' || run.status === 'blocked'" />
      {{ meta.label }}
    </span>
    <span class="blocker">{{ run.blocker || '—' }}</span>
    <span class="cost">{{ run.cost == null ? '—' : money(run.cost) }}</span>
    <span class="age">{{ run.age }}</span>
  </RouterLink>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 170px minmax(140px, 1.4fr) 172px 126px minmax(90px, 1fr) 76px 60px;
  gap: 12px;
  align-items: center;
  padding: 11px 14px;
  border-bottom: 1px solid var(--c-171c25);
  cursor: pointer;
  text-decoration: none;
  color: inherit;
}
.row:hover {
  background: var(--c-151a23);
}
.id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--c-9db4d8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-c8cfdb);
}
.mode {
  flex: none;
  font-family: var(--font-mono);
  font-size: 9.5px;
  padding: 2px 6px;
  border: 1px solid var(--c-2a3140);
  border-radius: 3px;
  color: var(--c-7d8697);
}
.status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.blocker {
  font-size: 11px;
  color: var(--c-8a93a5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cost {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--c-c8cfdb);
}
.age {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--c-5d6675);
}
</style>
