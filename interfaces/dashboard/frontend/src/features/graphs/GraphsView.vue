<script setup lang="ts">
// 018 T061 (S8, FR-044/FR-045): the v5 Graphs screen — the catalog of
// shipped graphs as cards, and the one PipelineConfig panel (three checks,
// five sections). The card's action opens the graph in Design at
// /graphs/<sha> (the route lands with T063; the navigation is the
// contract). Null values read 'not measured', never null.
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import CatalogCard from '@kroker/ui/components/catalog_card/CatalogCard.vue'
import { api } from '../../api/client'
import type { ShippedGraphs } from '../../api/read-types'

const router = useRouter()
const shipped = ref<ShippedGraphs | null>(null)
const failed = ref(false)

onMounted(async () => {
  try {
    shipped.value = await api.getShippedGraphs()
  } catch {
    failed.value = true
  }
})

function openInDesign(sha: string) {
  void router.push(`/graphs/${sha}`)
}
</script>

<template>
  <main data-testid="graphs-view" data-screen-label="Graphs" class="view">
    <div class="head-row">
      <h1 class="title">Graphs</h1>
      <span v-if="shipped" class="summary">{{ shipped.graphs.length }} shipped</span>
    </div>

    <div v-if="failed" class="state" data-testid="graphs-load-error">The graphs could not be loaded.</div>
    <div v-else-if="!shipped" class="state" data-testid="graphs-loading">loading…</div>

    <template v-else>
      <div class="cards">
        <CatalogCard
          v-for="g in shipped.graphs"
          :key="g.sha"
          kicker="shipped graph"
          :name="g.name"
          :sha="g.sha"
          :description="g.description"
          :when="g.when"
          :counts="g.counts"
          :action="{ label: 'Open in Design' }"
          @act="openInDesign(g.sha)"
        />
      </div>

      <section class="panel" data-testid="config-panel">
        <h2 class="panel-title">PipelineConfig</h2>
        <ul class="checks">
          <li
            v-for="c in shipped.checks"
            :key="c.name"
            class="check"
            data-testid="config-check"
            :data-state="c.state"
          >
            <span class="check-name">{{ c.name }}</span>
            <span class="check-text">{{ c.text }}</span>
          </li>
        </ul>
        <div class="sections">
          <section
            v-for="s in shipped.sections"
            :key="s.title"
            class="section"
            data-testid="config-section"
          >
            <h3 class="section-title" data-testid="config-section-title">{{ s.title }}</h3>
            <p class="section-note">{{ s.note }}</p>
            <div v-for="row in s.rows" :key="row.k" class="row" data-testid="config-row">
              <span class="k">{{ row.k }}</span>
              <span class="v">{{ row.v ?? 'not measured' }}</span>
            </div>
          </section>
        </div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.view { flex: 1; overflow: auto; padding: 20px 20px 40px; }
.head-row { display: flex; align-items: baseline; gap: 12px; margin: 0 0 14px; }
.title { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink-primary); }
.summary { font-family: var(--font-mono); font-size: 11px; color: var(--ink-muted); }
.state { color: var(--ink-muted); font-family: var(--font-mono); font-size: 12px; }
.cards { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 20px; }

.panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px 16px;
  max-width: 640px;
  background: var(--ground-1);
}
.panel-title { margin: 0 0 10px; font-size: 13px; font-weight: 600; color: var(--ink-primary); }
.checks { list-style: none; margin: 0 0 14px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.check { display: flex; gap: 10px; align-items: baseline; }
.check-name { font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary); min-width: 150px; }
.check-text { font-size: 11.5px; color: var(--ink-secondary); }
.check[data-state='fail'] .check-name { color: var(--status-failed); }
.check[data-state='off'] .check-name { color: var(--ink-muted); }
.check[data-state='pass'] .check-name::before { content: '✓ '; color: var(--status-done); }

.sections { display: flex; flex-direction: column; gap: 14px; }
.section { border-top: 1px solid var(--line); padding-top: 10px; }
.section-title { margin: 0 0 2px; font-size: 12px; font-weight: 600; color: var(--ink-primary); }
.section-note { margin: 0 0 8px; font-size: 11px; color: var(--ink-muted); }
.row { display: flex; gap: 12px; font-size: 11.5px; padding: 1px 0; }
.row .k { font-family: var(--font-mono); color: var(--ink-muted); min-width: 220px; }
.row .v { color: var(--ink-secondary); }
</style>
