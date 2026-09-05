<script setup lang="ts">
defineProps<{ id: string }>()
</script>

<template>
  <main data-testid="run-view" data-screen-label="Run detail" class="view">
    <div class="hint">Run detail for {{ id }} — implemented in Plan 2.</div>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 60px;
}
.hint {
  color: var(--c-5d6675);
  font-family: var(--font-mono);
  font-size: 12px;
}
</style>
