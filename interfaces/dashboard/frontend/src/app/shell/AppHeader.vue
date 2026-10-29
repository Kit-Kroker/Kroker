<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { designAvailable, navManifest } from '../nav'
import { useFleetStore } from '../../shared/fleet.store'
import { useFleetSummaryStore } from '../../shared/fleetSummary.store'
import { useInboxStore } from '../inbox.store'
import { usePrefsStore } from '../prefs.store'
import AppHeader from '@kroker/ui/components/app_header/AppHeader.vue'
import type { NavItem, RunSwitch } from '@kroker/ui/components/app_header/AppHeader.vue'

const route = useRoute()
const fleet = useFleetStore()
const summary = useFleetSummaryStore()
const inbox = useInboxStore()
const prefs = usePrefsStore()

// 018 T012: the manifest's static primary entries with the run entry
// rebuilt from live state. A fresh array every render — the exported
// manifest is never mutated (fleet state must not leak across mounts).
const runEntry = computed<NavItem>(() => {
  const pinned = prefs.runInContext
  if (pinned) return { id: 'run', label: pinned, to: `/runs/${pinned}`, available: true }
  const newest = fleet.runs[0]
  if (newest) return { id: 'run', label: newest.id, to: `/runs/${newest.id}`, available: true }
  return { id: 'run', label: 'No runs', to: '/runs', available: false }
})

const primary = computed<NavItem[]>(() =>
  navManifest.slice(0, 3).map((item) => (item.id === 'run' ? runEntry.value : item)),
)
const secondary = navManifest.slice(3)

// 018 T063: the Observe/Design switch — only when Design is available and
// a run is in context with a pinned graph sha. Observe returns to the run;
// Design opens the pinned sha with the run copy loaded.
const runSwitch = computed<RunSwitch | null>(() => {
  if (!designAvailable) return null
  const runId = prefs.runInContext ?? fleet.runs[0]?.id ?? null
  if (!runId) return null
  const sha = summary.byRun[runId]?.graphSha ?? null
  // Mounted without a router in some tests: absent route reads Observe.
  const mode = (route?.path ?? '').startsWith('/graphs') ? 'design' : 'observe'
  return {
    tabs: [
      { label: 'Observe', to: `/runs/${runId}`, active: mode === 'observe' },
      {
        label: 'Design',
        to: sha ? `/graphs/${sha}?from=run:${runId}` : '/graphs',
        active: mode === 'design',
      },
    ],
    active: runId,
    mode,
  }
})

// 018 T019 (S11): the header's Search opens the command palette and ⋯ the
// session menu; the shell only re-emits, App.vue owns both.
const emit = defineEmits<{ search: []; menu: [] }>()
</script>

<template>
  <div class="shell-header">
    <AppHeader
      :primary="primary"
      :secondary="secondary"
      :badge="inbox.items.length"
      :run-switch="runSwitch ?? undefined"
      @search="emit('search')"
      @menu="emit('menu')"
    />
    <!-- 018 T065 (R-1 ends): the header Start button is gone — runs start
         from Design's "Run this version" (the same start form). -->
  </div>
</template>

<style scoped>
.shell-header {
  display: flex;
  align-items: stretch;
}
.shell-header > :first-child {
  flex: 1;
  min-width: 0;
}
</style>
