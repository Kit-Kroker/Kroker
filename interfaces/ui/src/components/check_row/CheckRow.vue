<script setup lang="ts">
export type CheckKind = 'ABSOLUTE' | 'ADVISORY'
defineProps<{ name: string; kind: CheckKind; ok: boolean; detail?: string }>()
</script>

<template>
  <div
    class="cmp-check-row"
    :class="[ok ? 'is-ok' : 'is-failing', `cmp-check-row-${kind.toLowerCase()}`]"
    data-testid="check-row"
  >
    <span class="mark" role="img" :aria-label="ok ? 'passed' : 'failed'">{{ ok ? '✓' : '✕' }}</span>
    <span class="body">
      <span class="name">{{ name }}</span>
      <span v-if="detail" class="detail">{{ detail }}</span>
    </span>
    <span class="kind">{{ kind }}</span>
  </div>
</template>

<style scoped>
.cmp-check-row { display: grid; grid-template-columns: 14px minmax(0, 1fr) auto; gap: 10px; align-items: start; padding: var(--space-2) 10px; border-radius: var(--radius-md); font-family: var(--font-sans); }
.mark { font-size: var(--text-sm); line-height: 18px; }
.is-ok .mark { color: var(--status-done); }
.is-failing .mark { color: var(--status-failed); }
.is-failing.cmp-check-row-absolute { background: var(--status-failed-tint); }
.is-failing.cmp-check-row-advisory { background: var(--status-idle-tint); }
.body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-family: var(--font-mono); font-size: var(--text-sm); color: var(--ink-primary); }
.detail { font-size: var(--text-sm); line-height: 1.45; color: var(--ink-secondary); text-wrap: pretty; }
.kind { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.04em; line-height: 18px; color: var(--ink-muted); }
.cmp-check-row-absolute .kind { color: var(--ink-primary); }
</style>
