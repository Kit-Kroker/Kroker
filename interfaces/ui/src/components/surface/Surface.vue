<script setup lang="ts">
export type SurfaceElevation = 'flat' | 'overlay'
export type SurfacePadding = 'none' | 'sm' | 'md'

withDefaults(defineProps<{ elevation?: SurfaceElevation; padding?: SurfacePadding; as?: string }>(), {
  elevation: 'flat',
  padding: 'md',
  as: 'div',
})
</script>

<template>
  <component :is="as" class="cmp-surface" :class="[`cmp-surface-${elevation}`, `cmp-surface-pad-${padding}`]">
    <slot />
  </component>
</template>

<style scoped>
.cmp-surface { background: var(--ground-raised); border: 1px solid var(--line); color: var(--ink-primary); }
.cmp-surface-flat { border-radius: var(--radius-md); }
.cmp-surface-overlay { border-radius: var(--radius-lg); box-shadow: var(--shadow-overlay); }
.cmp-surface-pad-none { padding: 0; }
.cmp-surface-pad-sm { padding: 6px; }
.cmp-surface-pad-md { padding: var(--space-3) var(--space-4); }
</style>
