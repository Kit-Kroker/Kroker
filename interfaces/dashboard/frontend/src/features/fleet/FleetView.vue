<script setup lang="ts">
// 018 T049 (S6): the v5 Fleet view — the table's rows come from the fleet
// store and the fleet-summary read (one request per poll, App.vue refreshes
// both), with prefs.runInContext marking the Open-run row. The three honest
// states and the stale banner keep their rules.
import { computed } from 'vue'
import { useFleetStore } from '../../shared/fleet.store'
import { useFleetSummaryStore } from '../../shared/fleetSummary.store'
import { usePrefsStore } from '../../app/prefs.store'
import FleetTable from './FleetTable.vue'
import { fleetRows } from './fleet.adapter'

const fleet = useFleetStore()
const summary = useFleetSummaryStore()
const prefs = usePrefsStore()

const rows = computed(() => fleetRows(fleet.runs, summary.byRun, prefs.runInContext))
</script>

<template>
  <main data-testid="fleet-view" data-screen-label="Fleet" class="view">
    <div class="head-row">
      <h1 class="title">Fleet</h1>
      <span class="summary">{{ fleet.runs.length }} runs</span>
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
      <FleetTable :rows="rows" :run-in-context="prefs.runInContext" />
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
.summary {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-subtle);
}
.state {
  color: var(--ink-subtle);
  font-family: var(--font-mono);
  font-size: 12px;
}
.incomplete {
  border: 1px solid var(--status-blocked);
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 12px;
}
.incomplete .line {
  margin: 0;
  font-size: 12px;
  color: var(--ink-secondary);
}
</style>
