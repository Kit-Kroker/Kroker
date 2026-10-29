<script setup lang="ts">
// 018 T070 (S10, FR-052): Compare's "Rework by canonical_stage" heatmap.
// Presentational — the compare read maps into these display shapes; the
// intensity rides a token scale (a --heat-* step via color-mix), never a
// literal colour.
export interface HeatCell {
  state: 'value' | 'low_n' | 'blank'
  value: number | null
  n: number
}

defineProps<{
  columns: string[]
  rows: { name: string; cells: HeatCell[] }[]
}>()

/** The heat step for a value: 0..1 clamped onto five token steps. */
function stepOf(cell: HeatCell): number {
  if (cell.state === 'blank' || cell.value === null) return 0
  const v = Math.max(0, Math.min(1, cell.value))
  return Math.min(5, 1 + Math.floor(v * 5))
}
</script>

<template>
  <div class="cmp-heatmap" data-testid="heatmap">
    <div class="grid" :style="{ '--cols': columns.length }">
      <span class="corner" />
      <span
        v-for="c in columns"
        :key="c"
        class="col"
        data-testid="heat-column"
      >{{ c }}</span>
      <div v-for="row in rows" :key="row.name" class="row" data-testid="heat-row">
        <span class="row-name">{{ row.name }}</span>
        <span
          v-for="(cell, i) in row.cells"
          :key="i"
          class="cell"
          :class="[`heat-scale-${cell.state === 'blank' ? 0 : stepOf(cell)}`, { 'low-n': cell.state === 'low_n' }]"
          data-testid="heat-cell"
          :title="cell.state === 'blank' ? '' : `${cell.state === 'low_n' ? 'low n · ' : ''}n=${cell.n}`"
        >{{ cell.state === 'value' && cell.value !== null ? cell.value.toFixed(2) : '' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cmp-heatmap { overflow-x: auto; }
.grid {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(var(--cols), minmax(52px, 1fr));
  gap: 2px;
  font-size: 11.5px;
}
.col {
  font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-muted);
  padding: 3px 6px; letter-spacing: 0.04em;
}
.corner { }
.row {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(220px, 1fr) repeat(var(--cols), minmax(52px, 1fr));
  gap: 2px;
}
.row-name {
  font-family: var(--font-mono); font-size: 11px; color: var(--ink-secondary);
  padding: 4px 8px 4px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cell {
  font-family: var(--font-mono); font-size: 11px;
  padding: 4px 6px; border-radius: 4px; text-align: center;
  color: var(--ink-secondary);
  border: 1px solid var(--line);
}
/* The token scale: five steps over the heat token, muted for low n. */
.cell.heat-scale-1 { background: color-mix(in srgb, var(--status-waiting) 12%, transparent); }
.cell.heat-scale-2 { background: color-mix(in srgb, var(--status-waiting) 26%, transparent); }
.cell.heat-scale-3 { background: color-mix(in srgb, var(--status-waiting) 42%, transparent); }
.cell.heat-scale-4 { background: color-mix(in srgb, var(--status-waiting) 60%, transparent); }
.cell.heat-scale-5 { background: color-mix(in srgb, var(--status-waiting) 80%, transparent); color: var(--ink-primary); }
.cell.heat-scale-0 { background: transparent; border-style: dashed; }
</style>
