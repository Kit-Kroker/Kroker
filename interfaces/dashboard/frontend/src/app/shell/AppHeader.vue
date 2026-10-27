<script setup lang="ts">
import { computed } from 'vue'
import { navManifest } from '../nav'
import { useFleetStore } from '../../shared/fleet.store'
import { useInboxStore } from '../inbox.store'
import { usePrefsStore } from '../prefs.store'
import { useUiStore } from '../ui.store'
import AppHeader from '@kroker/ui/components/app_header/AppHeader.vue'
import type { NavItem } from '@kroker/ui/components/app_header/AppHeader.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
const prefs = usePrefsStore()
const ui = useUiStore()

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
      @search="emit('search')"
      @menu="emit('menu')"
    />
    <!-- R-1: the Start-run button stays in the shell until slice 6 (T066). -->
    <button data-testid="start-btn" class="start" @click="ui.openStart()">+ START RUN</button>
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
.start {
  flex: none;
  align-self: center;
  margin-right: 12px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 14px;
  background: var(--status-waiting);
  color: var(--ink-inverse);
  border: none;
  border-radius: 4px;
}
.start:hover {
  background: var(--ink-secondary);
}
</style>
