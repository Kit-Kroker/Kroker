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
</style>
