<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../shared/fleet.store'
import FleetTable from './FleetTable.vue'

const fleet = useFleetStore()
const summary = computed(() => `${fleet.runs.length} runs · ${fleet.blockedCount} blocked on humans`)
</script>

<template>
  <main data-testid="fleet-view" data-screen-label="Fleet" class="view">
    <div class="head-row">
      <h1 class="title">Fleet</h1>
      <span class="summary">{{ summary }}</span>
    </div>
    <!-- T5 (010 inbox pattern): three honest states before the table. -->
    <div v-if="!fleet.loaded && !fleet.loadError" class="state" data-testid="fleet-loading">loading…</div>
    <div
      v-else-if="!fleet.loaded && fleet.loadError"
      class="state"
      data-testid="fleet-load-error"
    >The fleet could not be loaded.</div>
    <template v-else>
      <!-- A stale banner must not lie that the list is current. -->
      <div
        v-if="fleet.loadError"
        class="incomplete"
        data-testid="fleet-incomplete"
      >
        <p class="line">The fleet could not be refreshed; showing the last known list.</p>
      </div>
      <FleetTable />
    </template>
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
  color: var(--ink-primary);
}
.state {
  color: var(--ink-subtle);
  font-family: var(--font-mono);
  font-size: 12px;
}
.incomplete {
  border: 1px solid var(--status-blocked);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
}
.incomplete .line {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--ink-secondary);
}
.summary {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-subtle);
}
</style>
