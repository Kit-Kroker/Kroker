<script setup lang="ts">
defineProps<{ label: string }>()
</script>

<template>
  <section class="cmp-detail-section">
    <div class="bar">
      <h3 class="label">{{ label }}</h3>
      <span class="spacer" />
      <slot name="action" />
    </div>
    <slot />
  </section>
</template>

<style scoped>
.cmp-detail-section { display: flex; flex-direction: column; gap: var(--space-2); }
.bar { display: flex; align-items: center; gap: var(--space-3); }
.label { margin: 0; font-family: var(--font-sans); font-size: var(--text-xs); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-secondary); }
.spacer { flex: 1; }
</style>
