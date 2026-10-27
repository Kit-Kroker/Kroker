<script setup lang="ts">
export type ToastKind = 'done' | 'running' | 'waiting' | 'failed' | 'idle'
export interface ToastItem {
  id: string | number
  msg: string
  /** 018 R-10: status kind, mapped to a --status-* token. */
  kind?: ToastKind
}

defineProps<{
  toasts: ToastItem[]
}>()
</script>

<template>
  <div v-if="toasts.length > 0" class="cmp-toasts stack cmp-toasts--bottom-centre">
    <div
      v-for="t in toasts"
      :key="t.id"
      data-testid="toast"
      class="toast"
      :class="t.kind ? `cmp-toast-${t.kind}` : undefined"
    >
      {{ t.msg }}
    </div>
  </div>
</template>

<style scoped>
.stack {
  position: fixed;
  /* 018 v5 (TOASTS-2): the stack sits bottom-centre, not bottom-right. */
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 60;
  pointer-events: none;
}
.toast {
  background: var(--ground-5);
  border: 1px solid var(--line-strong);
  border-left: 3px solid var(--status-done);
  border-radius: 5px;
  padding: 10px 14px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-tertiary);
  box-shadow: var(--shadow-overlay);
  animation: fc-toast 0.18s ease-out;
}
/* 018 R-10: kinds map to status tokens; done is the .toast default. */
.cmp-toast-running { border-left-color: var(--status-running); }
.cmp-toast-waiting { border-left-color: var(--status-waiting); }
.cmp-toast-failed { border-left-color: var(--status-failed); }
.cmp-toast-idle { border-left-color: var(--status-idle); }
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
