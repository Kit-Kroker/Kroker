<script setup lang="ts">
// 018 T059 (S8, FR-044): the Graphs catalog card. Presentational — the
// Graphs view maps the shipped-graphs read to these props and turns `act`
// into navigation (Open in Design). A value with no source renders
// 'not measured', never null or undefined.
export interface CatalogCount {
  label: string
  n: number
}

defineProps<{
  kicker: string
  name: string
  sha: string
  description: string | null
  when: string | null
  counts: CatalogCount[]
  action: { label: string }
}>()

defineEmits<{ act: [] }>()
</script>

<template>
  <article class="cmp-catalog-card">
    <p class="kicker" data-testid="catalog-kicker">{{ kicker }}</p>
    <h3 class="name" data-testid="catalog-name">{{ name }}</h3>
    <p class="sha mono" data-testid="catalog-sha" :title="sha">{{ sha.slice(0, 12) }}…</p>
    <p class="description" data-testid="catalog-description">
      {{ description ?? 'not measured' }}
    </p>
    <p class="when" data-testid="catalog-when">{{ when ?? 'not measured' }}</p>
    <div class="counts">
      <span v-for="c in counts" :key="c.label" class="count" data-testid="catalog-count">
        <span class="n">{{ c.n }}</span> {{ c.label }}
      </span>
    </div>
    <button type="button" class="action" data-testid="catalog-action" @click="$emit('act')">
      {{ action.label }}
    </button>
  </article>
</template>

<style scoped>
.cmp-catalog-card {
  display: flex; flex-direction: column; gap: 6px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--ground-1);
  min-width: 220px;
}
.kicker { margin: 0; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em; color: var(--ink-muted); }
.name { margin: 0; font-size: 14px; font-weight: 600; color: var(--ink-primary); }
.mono { font-family: var(--font-mono); }
.sha { margin: 0; font-size: 10.5px; color: var(--ink-muted); overflow: hidden; text-overflow: ellipsis; }
.description { margin: 0; font-size: 12px; color: var(--ink-secondary); }
.when { margin: 0; font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-muted); }
.counts { display: flex; gap: 12px; margin-top: 2px; }
.count { font-family: var(--font-mono); font-size: 11px; color: var(--ink-muted); }
.count .n { color: var(--ink-primary); }
.action {
  align-self: flex-start; margin-top: 6px;
  border: 1px solid var(--line-strong); border-radius: 6px;
  background: var(--ground-raised); color: var(--ink-primary);
  font-family: var(--font-mono); font-size: 11.5px;
  padding: 4px 10px; cursor: pointer;
}
.action:hover { border-color: var(--link); color: var(--link); }
</style>
