<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useFleetStore } from '../shared/fleet.store'
import { useFleetSummaryStore } from '../shared/fleetSummary.store'
import { useInboxStore } from './inbox.store'
import { useCatalogStore } from '../shared/catalog.store'
import { usePrefsStore } from './prefs.store'
import { money } from '../shared/format'
import { commandsOf } from './commands'
import { api } from '../api/client'
import AppHeader from './shell/AppHeader.vue'
import Toasts from './shell/Toasts.vue'
import StartRunModal from './shell/StartRunModal.vue'
import FooterBar from '@kroker/ui/components/footer_bar/FooterBar.vue'
import CommandPalette from '@kroker/ui/components/command_palette/CommandPalette.vue'
import ToggleMenu from '@kroker/ui/components/toggle_menu/ToggleMenu.vue'

const fleet = useFleetStore()
const fleetSummary = useFleetSummaryStore()
const inbox = useInboxStore()
const catalog = useCatalogStore()
const prefs = usePrefsStore()
const router = useRouter()
const route = useRoute()
let pollId: ReturnType<typeof setInterval> | null = null

// 018 T063: the shipped graphs the palette's Design commands target.
const shippedGraphs = ref<{ name: string; sha: string }[]>([])

// 018 T019 (S11): the ⌘K palette and the ⋯ session menu. Both are shell
// state, closed by Escape and by their own backdrops.
const paletteOpen = ref(false)
const menuOpen = ref(false)

function openPalette(): void {
  menuOpen.value = false
  paletteOpen.value = true
}

// The run in context, the same source the header's run entry uses
// (T012): pinned first, else the newest fleet run.
const runInContext = computed(() => prefs.runInContext ?? fleet.runs[0]?.id ?? null)

// 018 T063: live palette state — the mode from the route, the shipped
// graph names from the read.
const designMode = computed(() => route.path.startsWith('/graphs'))
const graphNames = ref<string[]>([])

const commands = computed(() =>
  commandsOf({
    run: runInContext.value
      ? {
          id: runInContext.value,
          pending: inbox.items
            .filter((i) => i.runId === runInContext.value)
            .map((i) => ({ id: i.id, title: i.title })),
        }
      : null,
    inboxCount: inbox.items.length,
    mode: designMode.value ? 'design' : 'observe',
    graphs: graphNames.value,
  }),
)

function runCommand(id: string): void {
  paletteOpen.value = false
  if (id === 'open-inbox' || id.startsWith('review-')) void router.push('/inbox')
  else if (id === 'open-fleet') void router.push('/')
  else if (id === 'open-run-board' && runInContext.value) {
    void router.push(`/runs/${runInContext.value}`)
  } else if (id === 'switch-mode') {
    // The Observe/Design switch: to the run, or to its pinned graph.
    if (designMode.value && runInContext.value) void router.push(`/runs/${runInContext.value}`)
    else if (runInContext.value) {
      const sha = fleetSummary.byRun[runInContext.value]?.graphSha
      if (sha) void router.push(`/graphs/${sha}?from=run:${runInContext.value}`)
    }
  } else if (id.startsWith('design-')) {
    const name = id.slice('design-'.length)
    const sha = shippedGraphs.value.find((g) => g.name === name)?.sha
    if (sha) void router.push(`/graphs/${sha}`)
  } else if (id === 'validate-graph' || id === 'fit-graph') {
    // The validation panel lives on Design; fit is a canvas control there.
    if (runInContext.value) {
      const sha = fleetSummary.byRun[runInContext.value]?.graphSha
      if (sha) void router.push(`/graphs/${sha}?from=run:${runInContext.value}`)
    }
  } else if (id === 'compare') {
    void router.push('/compare')
  } else if (id === 'interfaces') {
    void router.push('/interfaces')
  }
}

// The four session toggles (data-model §5), labels shared with the
// library's toggle_menu 'session' profile.
const toggles = computed(() => [
  { id: 'payloads', label: 'Payloads', desc: 'show edge payloads on the canvas', on: prefs.payloadsEverywhere },
  { id: 'terminals', label: 'Terminals', desc: 'mark terminal stages on the canvas', on: prefs.terminalsEverywhere },
  { id: 'grid', label: 'Grid', desc: 'show the dot grid behind the canvas', on: prefs.grid },
  { id: 'theme', label: 'Light theme', desc: 'light surfaces, same tokens', on: prefs.theme === 'light' },
])

function onToggle(id: string): void {
  if (id === 'payloads') prefs.payloadsEverywhere = !prefs.payloadsEverywhere
  else if (id === 'terminals') prefs.terminalsEverywhere = !prefs.terminalsEverywhere
  else if (id === 'grid') prefs.grid = !prefs.grid
  else if (id === 'theme') prefs.theme = prefs.theme === 'light' ? 'dark' : 'light'
}

// 018 T019: global ⌘K / Ctrl+K toggles the palette; Escape closes both.
function onKeydown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    if (paletteOpen.value) paletteOpen.value = false
    else openPalette()
  } else if (e.key === 'Escape') {
    paletteOpen.value = false
    menuOpen.value = false
  }
}

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
  window.addEventListener('keydown', onKeydown)
  // T5: a failed first read must not stop the poll. Every store owns its
  // error state (catalog.load, inbox.refresh, and fleet.refresh never
  // reject), so the first refreshes run fire-and-forget and the interval
  // starts unconditionally.
  void catalog.load()
  void fleet.refresh()
  void fleetSummary.refresh()
  void inbox.refresh()
  // 018 T063: the shipped graph names for the palette's Design commands.
  void api.getShippedGraphs().then((s) => {
    shippedGraphs.value = s.graphs.map((g) => ({ name: g.name, sha: g.sha }))
    graphNames.value = s.graphs.map((g) => g.name)
  }).catch(() => {})
  pollId = setInterval(() => {
    if (document.visibilityState === 'visible') {
      void fleet.refresh()
      void fleetSummary.refresh()
      void inbox.refresh()
    }
  }, 5000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (pollId) clearInterval(pollId)
})
</script>

<template>
  <div class="console">
    <AppHeader @search="openPalette" @menu="menuOpen = !menuOpen" />
    <RouterView />
    <Toasts />
    <StartRunModal />
    <FooterBar :left="footerTotal" right="⌘K commands" />
    <CommandPalette :open="paletteOpen" :commands="commands" @run="runCommand" @close="paletteOpen = false" />
    <div v-if="menuOpen" class="menu-layer">
      <div class="menu-catch" data-testid="menu-catch" @click="menuOpen = false" />
      <div class="menu-panel">
        <ToggleMenu :items="toggles" @toggle="onToggle" />
      </div>
    </div>
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

.menu-layer {
  position: fixed;
  inset: 0;
  z-index: 60;
}

.menu-catch {
  position: absolute;
  inset: 0;
}

.menu-panel {
  position: absolute;
  top: 54px;
  right: 140px;
  width: 280px;
  background: var(--ground-3);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  box-shadow: var(--shadow-overlay);
  padding: 8px;
}
</style>
