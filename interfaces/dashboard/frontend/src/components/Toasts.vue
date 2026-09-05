<script setup lang="ts">
import { useUiStore } from '../stores/ui'
import Toasts from '@kroker/ui/components/toasts/Toasts.vue'

const ui = useUiStore()
</script>

<template>
  <Toasts :toasts="ui.toasts" />
</template>
