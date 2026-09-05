<script setup lang="ts">
defineProps<{ kind: string; pulsing?: boolean }>()
</script>

<template>
  <span class="cmp-status-pip" :class="[`cmp-status-pip-${kind}`, { 'is-pulsing': pulsing }]" />
</template>

<style scoped>
.cmp-status-pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.cmp-status-pip.is-pulsing {
  animation: fc-pulse 1.6s infinite;
}
@keyframes fc-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
</style>
