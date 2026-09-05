<script setup lang="ts">
import StageDots, { type StageDot } from '../stage_dots/StageDots.vue'
import StatusPip from '../status_pip/StatusPip.vue'

export interface FleetRowStatus {
  kind: string
  label: string
  pulsing?: boolean
}

export interface FleetRowProps {
  id: string
  title: string
  mode: string
  dots: StageDot[]
  status: FleetRowStatus
  blocker?: string | null
  cost?: number | null
  age: string
  href: string
}

defineProps<FleetRowProps>()

const formatCost = (cost: number | null | undefined) => {
  if (cost == null) return '—'
  return `$${cost.toFixed(2)}`
}
</script>

<template>
  <RouterLink :to="href" data-testid="fleet-row" class="cmp-fleet-row">
    <span class="cmp-fleet-row-id">{{ id }}</span>
    <span class="cmp-fleet-row-title">
      <span class="cmp-fleet-row-title-text">{{ title }}</span>
      <span class="cmp-fleet-row-mode">{{ mode }}</span>
    </span>
    <StageDots :dots="dots" />
    <span class="cmp-fleet-row-status" :style="{ color: `var(--status-${status.kind})` }">
      <StatusPip :kind="status.kind" :pulsing="status.pulsing" />
      {{ status.label }}
    </span>
    <span class="cmp-fleet-row-blocker">{{ blocker || '—' }}</span>
    <span class="cmp-fleet-row-cost">{{ formatCost(cost) }}</span>
    <span class="cmp-fleet-row-age">{{ age }}</span>
  </RouterLink>
</template>

<style scoped>
.cmp-fleet-row {
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
.cmp-fleet-row:hover {
  background: var(--c-151a23);
}
.cmp-fleet-row-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--c-9db4d8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmp-fleet-row-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.cmp-fleet-row-title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-c8cfdb);
}
.cmp-fleet-row-mode {
  flex: none;
  font-family: var(--font-mono);
  font-size: 9.5px;
  padding: 2px 6px;
  border: 1px solid var(--c-2a3140);
  border-radius: 3px;
  color: var(--c-7d8697);
}
.cmp-fleet-row-status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.cmp-fleet-row-blocker {
  font-size: 11px;
  color: var(--c-8a93a5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmp-fleet-row-cost {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--c-c8cfdb);
}
.cmp-fleet-row-age {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--c-5d6675);
}
</style>
