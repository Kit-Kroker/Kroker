<script setup lang="ts">
import FleetRow, { type FleetRowProps } from '../fleet_row/FleetRow.vue'

defineProps<{
  rows: FleetRowProps[]
}>()
</script>

<template>
  <div class="cmp-fleet-table">
    <div class="cmp-fleet-table-head">
      <span>RUN</span><span>TITLE</span><span>STAGES</span><span>STATUS</span>
      <span>BLOCKER</span><span class="r">COST</span><span class="r">AGE</span>
    </div>
    <div v-if="rows.length === 0" class="cmp-fleet-table-empty" data-testid="fleet-empty">
      No runs in fleet
    </div>
    <FleetRow v-else v-for="r in rows" :key="r.id" v-bind="r" />
  </div>
</template>

<style scoped>
.cmp-fleet-table {
  border: 1px solid var(--c-1e242f);
  border-radius: 6px;
  overflow: hidden;
  background: var(--c-10141b);
}
.cmp-fleet-table-head {
  display: grid;
  grid-template-columns: 170px minmax(140px, 1.4fr) 172px 126px minmax(90px, 1fr) 76px 60px;
  gap: 12px;
  align-items: center;
  padding: 8px 14px;
  background: var(--c-0d1016);
  border-bottom: 1px solid var(--c-1e242f);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--c-5d6675);
}
.cmp-fleet-table-empty {
  padding: 32px 14px;
  text-align: center;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--c-5d6675);
}
.r {
  text-align: right;
}
</style>
