<script setup lang="ts">
import { computed } from 'vue'
import type { Run } from '../../api/types'
import { statusMetaOf } from '../../composables/status'
import { money } from '../../composables/format'
import StageDots from './StageDots.vue'

const props = defineProps<{ run: Run }>()
const meta = computed(() => statusMetaOf(props.run))
</script>

<template>
  <RouterLink :to="`/runs/${run.id}`" data-testid="fleet-row" class="row">
    <span class="id">{{ run.id }}</span>
    <span class="title">
      <span class="title-text">{{ run.title }}</span>
      <span class="mode">{{ run.mode }}</span>
    </span>
    <StageDots :run="run" />
    <span class="status" :style="{ color: meta.color }">
      <span class="pip" :style="{ background: meta.color, animation: meta.anim }" />
      {{ meta.label }}
    </span>
    <span class="blocker">{{ run.blocker || '—' }}</span>
    <span class="cost">{{ money(run.cost) }}</span>
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
  border-bottom: 1px solid #171c25;
  cursor: pointer;
  text-decoration: none;
  color: inherit;
}
.row:hover {
  background: #151a23;
}
.id {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  color: #9db4d8;
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
  color: #c8cfdb;
}
.mode {
  flex: none;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9.5px;
  padding: 2px 6px;
  border: 1px solid #2a3140;
  border-radius: 3px;
  color: #7d8697;
}
.status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
}
.pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.blocker {
  font-size: 11px;
  color: #8a93a5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cost {
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: #c8cfdb;
}
.age {
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #5d6675;
}
</style>
