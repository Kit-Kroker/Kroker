<script setup lang="ts"></script>

<template>
  <main data-testid="inbox-view" data-screen-label="Decision inbox" class="view">
    <div class="hint">Decision inbox — implemented in Plan 2.</div>
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
