<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useFleetStore } from '../shared/fleet.store'
import { useInboxStore } from './inbox.store'
import { useCatalogStore } from '../shared/catalog.store'
import { usePrefsStore } from './prefs.store'
import { money } from '../shared/format'
import AppHeader from './shell/AppHeader.vue'
import Toasts from './shell/Toasts.vue'
import StartRunModal from './shell/StartRunModal.vue'
import FooterBar from '@kroker/ui/components/footer_bar/FooterBar.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
const catalog = useCatalogStore()
const prefs = usePrefsStore()
let pollId: ReturnType<typeof setInterval> | null = null

// 018 T012 (CONSOLE-27's new home): the footer's fleet total — priced runs
// only, the excluded counted aloud, "not priced" when nothing is priced,
// the em dash when there is nothing to sum (011's honest-spend contract).
const footerTotal = computed(() => {
  if (fleet.runs.length === 0) return '—'
  const { usd, excluded } = fleet.totalCost
  if (usd === null) return 'not priced'
  return excluded > 0 ? `${money(usd)} · ${excluded} not priced` : money(usd)
})

// 018 R-10/S4: the app owns the active theme (tokens.md); the library
// never sets it. 'dark' is the unstyled default, so it REMOVES the
// attribute — including a stale one left by an earlier page.
watch(
  () => prefs.theme,
  (theme) => {
    if (theme === 'light') document.documentElement.dataset.theme = 'light'
    else delete document.documentElement.dataset.theme
  },
  { immediate: true },
)

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
    <FooterBar :left="footerTotal" right="⌘K commands" />
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
