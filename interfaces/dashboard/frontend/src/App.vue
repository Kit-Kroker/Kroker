<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useFleetStore } from './stores/fleet'
import { useInboxStore } from './stores/inbox'
import AppHeader from './components/AppHeader.vue'
import Toasts from './components/Toasts.vue'
import StartRunModal from './components/StartRunModal.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
let pollId: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([fleet.refresh(), inbox.refresh()])
  pollId = setInterval(() => {
    if (document.visibilityState === 'visible') {
      fleet.refresh()
      inbox.refresh()
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollId) clearInterval(pollId)
})
</script>

<template>
  <div class="console">
    <AppHeader />
    <RouterView />
    <Toasts />
    <StartRunModal />
  </div>
</template>

<style scoped>
.console {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ground-1);
  color: var(--ink-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  overflow: hidden;
}
</style>
