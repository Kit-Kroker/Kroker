<script setup lang="ts">
export interface AppHeaderProps {
  activeCount?: number
  maxCount?: number
  totalCost?: string
  inboxCount?: number
  activeTab?: 'fleet' | 'inbox' | string
}

withDefaults(defineProps<AppHeaderProps>(), {
  activeCount: 0,
  maxCount: 50,
  totalCost: '$0.00',
  inboxCount: 0,
  activeTab: 'fleet',
})

const emit = defineEmits<{
  (e: 'start-run'): void
}>()
</script>

<template>
  <header class="cmp-app-header hdr">
    <div class="brand">
      <span class="mark">SDLC·FACTORY</span>
      <span class="sub">temporal · ai-sdlc queue</span>
    </div>
    <nav class="tabs">
      <RouterLink
        to="/"
        class="tab"
        :class="{ 'tab-active': activeTab === 'fleet' }"
        active-class="tab-active"
      >
        FLEET
      </RouterLink>
      <RouterLink
        to="/inbox"
        class="tab"
        :class="{ 'tab-active': activeTab === 'inbox' }"
        active-class="tab-active"
      >
        INBOX
        <span v-if="inboxCount > 0" data-testid="inbox-count" class="badge">{{ inboxCount }}</span>
      </RouterLink>
    </nav>
    <div class="spacer" />
    <div class="stats">
      <span>runs <b>{{ activeCount }}</b>/{{ maxCount }}</span>
      <span>spend today <b>{{ totalCost }}</b></span>
      <button data-testid="start-btn" class="start" @click="emit('start-run')">+ START RUN</button>
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
  background: var(--c-090b0f);
  border-bottom: 1px solid var(--c-1e242f);
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.mark {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.08em;
  color: var(--c-e8edf5);
}
.sub {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--c-4d5665);
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
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--c-7d8697);
  border-bottom: 2px solid transparent;
  text-decoration: none;
  cursor: pointer;
}
.tab:hover {
  color: var(--c-e8edf5);
}
.tab-active {
  color: var(--c-e8edf5);
  border-bottom-color: var(--status-blocked);
}
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--status-blocked);
  color: var(--c-1a1405);
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
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--c-7d8697);
}
.stats b {
  color: var(--c-d9dfe9);
}
.start {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 7px 14px;
  background: var(--status-blocked);
  color: var(--c-1a1405);
  border: none;
  border-radius: 4px;
}
.start:hover {
  background: var(--c-ecc06a);
}
</style>
