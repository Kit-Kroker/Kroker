<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <div class="stack">
    <div
      v-for="t in ui.toasts"
      :key="t.id"
      data-testid="toast"
      class="toast"
      :style="{ borderLeftColor: t.color }"
    >
      {{ t.msg }}
    </div>
  </div>
</template>

<style scoped>
.stack {
  position: fixed;
  right: 18px;
  bottom: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 60;
  pointer-events: none;
}
.toast {
  background: #161c26;
  border: 1px solid #2a3140;
  border-left: 3px solid #4fae7f;
  border-radius: 5px;
  padding: 10px 14px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  color: #c8cfdb;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: fc-toast 0.18s ease-out;
}
</style>
