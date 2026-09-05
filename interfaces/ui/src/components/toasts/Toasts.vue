<script setup lang="ts">
export interface ToastItem {
  id: string | number
  msg: string
  color?: string
}

defineProps<{
  toasts: ToastItem[]
}>()
</script>

<template>
  <div v-if="toasts.length > 0" class="cmp-toasts stack">
    <div
      v-for="t in toasts"
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
  background: var(--c-161c26);
  border: 1px solid var(--c-2a3140);
  border-left: 3px solid var(--status-done);
  border-radius: 5px;
  padding: 10px 14px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--c-c8cfdb);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: fc-toast 0.18s ease-out;
}
@keyframes fc-toast {
  from {
    transform: translateY(8px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
</style>
