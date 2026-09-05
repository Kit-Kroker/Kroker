<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../stores/fleet'
import FleetTable from '../components/fleet/FleetTable.vue'

const fleet = useFleetStore()
const summary = computed(() => `${fleet.runs.length} runs · ${fleet.blockedCount} blocked on humans`)
</script>

<template>
  <main data-testid="fleet-view" data-screen-label="Fleet" class="view">
    <div class="head-row">
      <h1 class="title">Fleet</h1>
      <span class="summary">{{ summary }}</span>
    </div>
    <FleetTable />
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 40px;
}
.head-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 0 0 14px;
}
.title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--c-e8edf5);
}
.summary {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--c-5d6675);
}
</style>
