<script setup lang="ts">
// 018 T072 (S10, FR-052): the v5 Compare screen. Arms × graphs with SC
// and $/case, the description line from the wire, and the rework heatmap
// on the library component. An unavailable root renders the empty state
// naming the root - never invented rows.
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'
import { mapCompare } from '../../api/http-read'
import type { Compare } from '../../api/read-types'
import { Heatmap } from '@kroker/ui'

const compare = ref<Compare | null>(null)
const failed = ref(false)

const short = (sha: string) => sha.slice(0, 12)

onMounted(async () => {
  try {
    // Idempotent map: raw wire or an already-mapped shape both land.
    compare.value = mapCompare((await api.getCompare()) as never)
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <section class="cmp page">
    <header class="head">
      <h1>Compare</h1>
      <p v-if="compare?.description" data-testid="cmp-desc" class="desc">{{ compare.description }}</p>
    </header>

    <div v-if="failed" class="empty">compare read failed — retry in a moment</div>

    <div
      v-else-if="compare && !compare.available"
      data-testid="cmp-empty"
      class="empty"
    >
      No benchmark runs under {{ compare.root }}. Run the benchmarks and come back.
    </div>

    <template v-else-if="compare">
      <table class="arms">
        <thead>
          <tr>
            <th>arm</th>
            <th v-for="g in compare.graphs" :key="g">{{ short(g) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="arm in compare.arms" :key="arm.name" data-testid="cmp-row">
            <td class="arm">
              <span class="name">{{ arm.name }}</span>
              <span class="note">{{ arm.note ?? `${arm.harness} × ${arm.model}` }}</span>
            </td>
            <td v-for="cell in arm.cells" :key="cell.graph" class="cell">
              <span class="sc">SC {{ cell.sc === null ? 'not measured' : cell.sc.toFixed(1) }}</span>
              <span class="cost">{{ cell.costPerCase === null ? 'not measured' : `$${cell.costPerCase.toFixed(2)}/case` }}</span>
            </td>
          </tr>
        </tbody>
      </table>

      <h2 class="sub">Rework by canonical stage</h2>
      <div data-testid="cmp-heat" class="heat">
        <Heatmap :columns="compare.heatColumns" :rows="compare.heatRows" />
      </div>
    </template>
  </section>
</template>

<style scoped>
.cmp { display: flex; flex-direction: column; gap: 16px; }
.head h1 { font: 600 15px/1.2 var(--font-sans); color: var(--ink-primary); margin: 0; }
.desc { font: 12px/1.4 var(--font-mono); color: var(--ink-muted); margin: 4px 0 0; }
.empty { color: var(--ink-muted); font: 12.5px/1.5 var(--font-sans); }
.arms { width: 100%; border-collapse: collapse; font: 12px/1.4 var(--font-mono); }
.arms th {
  text-align: left; color: var(--ink-muted); font-weight: 500; font-size: 10.5px;
  letter-spacing: 0.04em; padding: 4px 10px; border-bottom: 1px solid var(--line);
}
.arm { padding: 8px 10px 8px 0; }
.name { display: block; color: var(--ink-primary); }
.note { display: block; color: var(--ink-muted); font-size: 10.5px; }
.cell { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
.sc { display: block; }
.cost { display: block; color: var(--ink-muted); }
.sub { font: 500 12px/1.2 var(--font-sans); color: var(--ink-secondary); margin: 8px 0 0; }
</style>
