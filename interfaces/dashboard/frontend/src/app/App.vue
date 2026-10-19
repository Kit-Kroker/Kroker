<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useFleetStore } from '../shared/fleet.store'
import { useInboxStore } from './inbox.store'
import { useCatalogStore } from '../shared/catalog.store'
import AppHeader from './shell/AppHeader.vue'
import Toasts from './shell/Toasts.vue'
import StartRunModal from './shell/StartRunModal.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
const catalog = useCatalogStore()
let pollId: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  // T5: a failed first read must not stop the poll. Every store owns its
  // error state (catalog.load, inbox.refresh, and fleet.refresh never
  // reject), so the first refreshes run fire-and-forget and the interval
  // starts unconditionally.
  void catalog.load()
  void fleet.refresh()
  void inbox.refresh()
  pollId = setInterval(() => {
    if (document.visibilityState === 'visible') {
      void fleet.refresh()
      void inbox.refresh()
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
