<script setup lang="ts">
export type TagTone = 'neutral' | 'strong'
withDefaults(defineProps<{ tone?: TagTone; mono?: boolean }>(), { tone: 'neutral', mono: false })
</script>

<template>
  <span class="cmp-tag" :class="[`cmp-tag-${tone}`, { 'is-mono': mono }]"><slot /></span>
</template>

<style scoped>
.cmp-tag { display: inline-flex; align-items: center; padding: 1px 7px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); font-family: var(--font-sans); font-size: var(--text-xs); font-weight: 500; line-height: 1.5; white-space: nowrap; color: var(--ink-secondary); }
.cmp-tag-strong { background: var(--ink-primary); border-color: var(--ink-primary); color: var(--ink-inverse); }
.cmp-tag.is-mono { font-family: var(--font-mono); font-size: 10px; padding: 1px 5px; border-color: var(--line); }
</style>
