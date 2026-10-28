<script setup lang="ts">
// 018 T049 (S6/S16): the v5 Fleet table — Run, Graph, Arm, Outcome,
// Where/reason, revise traversals, Cost, Elapsed, Open. The stage strip is
// retired (CONSOLE-3); the open label is the row's single action.
import type { FleetRowV5 } from './fleet.adapter'

defineProps<{ rows: FleetRowV5[]; runInContext?: string | null }>()
</script>

<template>
  <div class="fleet-table" data-testid="fleet-table">
    <div class="thead row" aria-hidden="true">
      <span class="col col-run">Run</span>
      <span class="col col-graph">Graph</span>
      <span class="col col-arm">Arm</span>
      <span class="col col-outcome">Outcome</span>
      <span class="col col-where">Where</span>
      <span class="col col-traversals">Revise</span>
      <span class="col col-cost">Cost</span>
      <span class="col col-elapsed">Elapsed</span>
      <span class="col col-open" />
    </div>
    <div
      v-for="r in rows"
      :key="r.runId"
      class="row body"
      data-testid="fleet-row"
      :class="{ 'is-context': r.runId === runInContext }"
    >
      <span class="col col-run">
        <RouterLink class="run" :to="`/runs/${r.runId}`">{{ r.title }}</RouterLink>
      </span>
      <span class="col col-graph">{{ r.graph }}</span>
      <span class="col col-arm">{{ r.arm }}</span>
      <span class="col col-outcome" :class="{ 'is-final': r.outcome !== 'running' && r.outcome !== '—' }">{{ r.outcome }}</span>
      <span class="col col-where">{{ r.where }}</span>
      <span class="col col-traversals">{{ r.traversals }}</span>
      <span class="col col-cost">{{ r.cost }}</span>
      <span class="col col-elapsed">{{ r.elapsed }}</span>
      <span class="col col-open">
        <RouterLink class="open" data-testid="fleet-open" :to="`/runs/${r.runId}`">{{ r.openLabel }}</RouterLink>
      </span>
    </div>
    <div v-if="rows.length === 0" class="empty" data-testid="fleet-empty">No runs yet.</div>
  </div>
</template>

<style scoped>
.fleet-table { display: flex; flex-direction: column; gap: 2px; font-size: 12.5px; }
.row {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) 1.1fr 1.4fr 1.2fr 1.2fr 0.7fr 0.8fr 0.8fr 0.8fr;
  gap: 10px; align-items: baseline;
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
}
.thead { color: var(--ink-subtle); font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.06em; border-bottom: 1px solid var(--line-strong); }
.body:hover { background: var(--ground-2); }
.is-context { background: var(--ground-2); }
.col { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.col-run .run { color: var(--ink-primary); text-decoration: none; }
.col-run .run:hover { text-decoration: underline; }
.col-graph, .col-arm, .col-traversals, .col-elapsed { font-family: var(--font-mono); font-size: 11px; color: var(--ink-tertiary); }
.col-outcome { font-family: var(--font-mono); font-size: 11px; color: var(--ink-secondary); }
.col-outcome.is-final { color: var(--ink-subtle); }
.col-cost { font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary); }
.open {
  color: var(--link); text-decoration: none; font-family: var(--font-mono); font-size: 11px;
}
.open:hover { text-decoration: underline; }
.empty { color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; padding: 14px 0; }
</style>
