<script setup lang="ts">
// 018 T077 (S12, FR-050/FR-051): the Interfaces matrix. Presentational —
// the interfaces read maps into these display shapes. Cell marks are the
// state itself (data-state); the planned row dims; facts carry severity.
export type CellState = 'yes' | 'no' | 'partial' | 'not_measured' | 'planned'

export interface MatrixCell {
  state: CellState
  text: string
}

defineProps<{
  columns: { key: string; name: string; ref: string }[]
  rows: { harness: string; sub: string; planned: boolean; cells: MatrixCell[] }[]
  facts: { who: string; severity: 'warn' | 'error'; text: string }[]
}>()
</script>

<template>
  <div class="cmp-check-matrix" data-testid="check-matrix">
    <table class="matrix">
      <thead>
        <tr>
          <th class="lead">harness</th>
          <th v-for="c in columns" :key="c.key" data-testid="matrix-column" class="col">
            <span class="name">{{ c.name }}</span>
            <span class="ref">{{ c.ref }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.harness"
          data-testid="matrix-row"
          :class="{ planned: row.planned }"
        >
          <td class="lead">
            <span class="harness">{{ row.harness }}</span>
            <span v-if="row.sub" class="sub">{{ row.sub }}</span>
          </td>
          <td
            v-for="(cell, i) in row.cells"
            :key="i"
            data-testid="matrix-cell"
            :data-state="cell.state"
            :class="`mark-${cell.state}`"
          >
            <span class="glyph" aria-hidden="true" />
            <span v-if="cell.text" class="text">{{ cell.text }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <ul v-if="facts.length" class="facts">
      <li
        v-for="f in facts"
        :key="`${f.who}-${f.text}`"
        data-testid="matrix-fact"
        :data-severity="f.severity"
        :class="`sev-${f.severity}`"
      >
        <span class="who">{{ f.who }}</span>
        <span class="text">{{ f.text }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cmp-check-matrix { display: flex; flex-direction: column; gap: 12px; }
.matrix { width: 100%; border-collapse: collapse; font: 12px/1.4 var(--font-mono); }
th.lead, td.lead { text-align: left; padding: 6px 10px 6px 0; }
th.col {
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line);
  vertical-align: bottom;
}
th.col .name { display: block; font: 500 12px/1.3 var(--font-sans); color: var(--ink-primary); }
th.col .ref { display: block; font: 10.5px/1.3 var(--font-mono); color: var(--ink-muted); }
td.lead .harness { display: block; color: var(--ink-primary); }
td.lead .sub { display: block; color: var(--ink-muted); font-size: 10.5px; }
td[data-testid="matrix-cell"] { padding: 6px 10px; border-bottom: 1px solid var(--line); }
.glyph { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.text { color: var(--ink-secondary); }
/* Marks over the status tokens — no literals (TOKENS-2). */
.mark-yes .glyph { background: var(--status-ok); }
.mark-no .glyph { background: var(--status-failed); }
.mark-partial .glyph { background: var(--status-waiting); }
.mark-not_measured .glyph { border: 1px solid var(--ink-muted); background: transparent; }
.mark-planned .glyph { border: 1px dashed var(--ink-muted); background: transparent; }
tr.planned .harness, tr.planned .sub, tr.planned .text { opacity: 0.55; }
.facts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.facts li { font: 11.5px/1.5 var(--font-mono); padding: 4px 8px; border-radius: 4px; }
.sev-warn { border-left: 2px solid var(--status-waiting); background: var(--ground-2); }
.sev-error { border-left: 2px solid var(--status-failed); background: var(--ground-2); }
.facts .who { color: var(--ink-primary); margin-right: 6px; }
.facts .text { color: var(--ink-secondary); }
</style>
