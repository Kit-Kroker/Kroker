<script setup lang="ts">
defineProps<{
  left?: string
  right?: string
}>()
</script>

<template>
  <footer class="cmp-footer-bar bar">
    <span class="side">{{ left }}</span>
    <span class="side">{{ right }}</span>
  </footer>
</template>

<style scoped>
.bar {
  flex: none;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--ground-raised);
  border-top: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--ink-muted);
}
</style>
