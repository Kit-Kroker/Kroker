<script setup lang="ts">
export interface DetailField {
  k: string
  v: string | number | null | undefined
  mono?: boolean
}

withDefaults(defineProps<{ eyebrow?: string; title: string; fields?: DetailField[] }>(), { fields: () => [] })

// DETAIL_PANE-2: an absent value reads as an em dash, never as a blank cell.
const show = (v: DetailField['v']) => (v === null || v === undefined || v === '' ? '—' : String(v))
</script>

<template>
  <section class="cmp-detail-pane">
    <header class="head">
      <div v-if="eyebrow || $slots.badges" class="eyebrow">
        <span v-if="eyebrow" class="eyebrow-text">{{ eyebrow }}</span>
        <slot name="badges" />
      </div>
      <h2 class="title">{{ title }}</h2>
      <slot name="meta" />
    </header>
    <dl v-if="fields.length" class="fields" data-testid="detail-fields">
      <template v-for="f in fields" :key="f.k">
        <dt class="k">{{ f.k }}</dt>
        <dd class="v" :class="{ 'is-mono': f.mono !== false }" data-testid="detail-value">{{ show(f.v) }}</dd>
      </template>
    </dl>
    <slot />
  </section>
</template>

<style scoped>
.cmp-detail-pane { display: flex; flex-direction: column; gap: 20px; padding: 20px; color: var(--ink-primary); font-family: var(--font-sans); }
.head { display: flex; flex-direction: column; gap: var(--space-2); }
.eyebrow { display: flex; align-items: center; gap: var(--space-2); }
.eyebrow-text { font-family: var(--font-mono); font-size: var(--text-md); color: var(--ink-secondary); }
.title { margin: 0; font-size: var(--text-xl); font-weight: 600; line-height: 1.3; text-wrap: pretty; }
.fields { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: var(--space-2) var(--space-3); margin: 0; font-size: var(--text-sm); }
.k { color: var(--ink-secondary); }
.v { margin: 0; overflow-wrap: anywhere; }
.v.is-mono { font-family: var(--font-mono); }
</style>
