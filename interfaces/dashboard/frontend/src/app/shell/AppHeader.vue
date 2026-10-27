<script setup lang="ts">
import { computed } from 'vue'
import { useInboxStore } from '../inbox.store'
import { useUiStore } from '../ui.store'
import AppHeader from '@kroker/ui/components/app_header/AppHeader.vue'
import type { NavItem } from '@kroker/ui/components/app_header/AppHeader.vue'

const inbox = useInboxStore()
const ui = useUiStore()

// 018 T010: interim inline manifest; nav.ts replaces it in T012.
const primary = computed<NavItem[]>(() => [
  { id: 'fleet', label: 'Fleet', to: '/', available: true },
  { id: 'inbox', label: 'Inbox', to: '/inbox', available: true },
])
const secondary: NavItem[] = [
  { id: 'graphs', label: 'Graphs', to: '/graphs', available: true },
  { id: 'compare', label: 'Compare', to: '/compare', available: false },
  { id: 'interfaces', label: 'Interfaces', to: '/interfaces', available: false },
]
</script>

<template>
  <div class="shell-header">
    <AppHeader :primary="primary" :secondary="secondary" :badge="inbox.items.length" @search="ui.openStart()" />
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
