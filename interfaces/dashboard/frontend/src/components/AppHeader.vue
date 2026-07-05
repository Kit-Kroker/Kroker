<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../stores/fleet'
import { useInboxStore } from '../stores/inbox'
import { useUiStore } from '../stores/ui'
import { money } from '../composables/format'

const fleet = useFleetStore()
const inbox = useInboxStore()
const ui = useUiStore()

const inboxCount = computed(() => inbox.items.length)
const hasInbox = computed(() => inboxCount.value > 0)
const totalCost = computed(() => money(fleet.totalCost))
</script>

<template>
  <header class="hdr">
    <div class="brand">
      <span class="mark">SDLC·FACTORY</span>
      <span class="sub">temporal · ai-sdlc queue</span>
    </div>
    <nav class="tabs">
      <RouterLink to="/" class="tab" active-class="tab-active">FLEET</RouterLink>
      <RouterLink to="/inbox" class="tab" active-class="tab-active">
        INBOX
        <span v-if="hasInbox" data-testid="inbox-count" class="badge">{{ inboxCount }}</span>
      </RouterLink>
    </nav>
    <div class="spacer" />
    <div class="stats">
      <span>runs <b>{{ fleet.activeCount }}</b>/50</span>
      <span>spend today <b>{{ totalCost }}</b></span>
      <button data-testid="start-btn" class="start" @click="ui.openStart()">+ START RUN</button>
    </div>
  </header>
</template>

<style scoped>
.hdr {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: #090b0f;
  border-bottom: 1px solid #1e242f;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.mark {
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.08em;
  color: #e8edf5;
}
.sub {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10.5px;
  color: #4d5665;
}
.tabs {
  display: flex;
  gap: 4px;
  height: 100%;
}
.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  height: 100%;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #7d8697;
  border-bottom: 2px solid transparent;
  text-decoration: none;
  cursor: pointer;
}
.tab:hover {
  color: #e8edf5;
}
.tab-active {
  color: #e8edf5;
  border-bottom-color: #e0b050;
}
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e0b050;
  color: #1a1405;
  border-radius: 9px;
  font-size: 10.5px;
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.stats {
  display: flex;
  align-items: center;
  gap: 18px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: #7d8697;
}
.stats b {
  color: #d9dfe9;
}
.start {
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 14px;
  background: #e0b050;
  color: #1a1405;
  border: none;
  border-radius: 4px;
}
.start:hover {
  background: #ecc06a;
}
</style>
