<script setup lang="ts">
export interface NavItem {
  id: string
  label: string
  to: string
  badge?: number
  available: boolean
}
export interface RunSwitchTab {
  label: string
  to: string
  active?: boolean
}
export interface RunSwitch {
  tabs: RunSwitchTab[]
  active: string
  mode?: 'observe' | 'design'
}

defineProps<{
  primary: NavItem[]
  secondary: NavItem[]
  runSwitch?: RunSwitch
  badge?: number
}>()

const emit = defineEmits<{
  (e: 'search'): void
  (e: 'menu'): void
}>()
</script>

<template>
  <header class="cmp-app-header hdr">
    <div class="brand">
      <span class="kmark">K</span><span class="name">Kroker</span>
    </div>
    <nav class="nav">
      <template v-for="item in primary" :key="item.id">
        <RouterLink v-if="item.available" :to="item.to" class="tab" data-testid="nav-item">
          {{ item.label }}<span v-if="item.badge && item.badge > 0" class="nbadge">{{ item.badge }}</span>
        </RouterLink>
      </template>
    </nav>
    <div v-if="runSwitch" data-testid="run-switch" class="runswitch">
      <RouterLink
        v-for="t in runSwitch.tabs"
        :key="t.to"
        :to="t.to"
        class="rtab"
        :class="{ 'tab-active': t.active }"
      >{{ t.label }}</RouterLink>
      <span v-if="runSwitch.mode" class="modes">
        <span class="mode" :class="{ 'mode-on': runSwitch.mode === 'observe' }">Observe</span>
        <span class="mode" :class="{ 'mode-on': runSwitch.mode === 'design' }">Design</span>
      </span>
    </div>
    <nav class="nav nav-secondary">
      <template v-for="item in secondary" :key="item.id">
        <RouterLink v-if="item.available" :to="item.to" class="tab" data-testid="nav-item">
          {{ item.label }}<span v-if="item.badge && item.badge > 0" class="nbadge">{{ item.badge }}</span>
        </RouterLink>
      </template>
    </nav>
    <div class="spacer" />
    <span v-if="badge !== undefined && badge > 0" data-testid="inbox-count" class="badge">{{ badge }}</span>
    <button data-testid="header-search" class="ctl" @click="emit('search')">Search ⌘K</button>
    <button data-testid="header-menu" class="ctl menu" @click="emit('menu')">⋯</button>
  </header>
</template>

<style scoped>
.hdr {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 20px;
  background: var(--ground-raised);
  border-bottom: 1px solid var(--line);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kmark {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 12px;
  color: var(--ink-inverse);
  background: var(--ink-primary);
  border-radius: var(--radius-sm);
}
.name {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: var(--text-md);
  color: var(--ink-primary);
}
.nav {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 100%;
}
.nav-secondary {
  border-left: 1px solid var(--line);
  padding-left: 14px;
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  height: 100%;
  font-family: var(--font-sans);
  font-size: var(--text-md);
  color: var(--ink-muted);
  border-bottom: 2px solid transparent;
  text-decoration: none;
  cursor: pointer;
}
.tab:hover {
  color: var(--ink-primary);
}
.tab-active {
  color: var(--ink-primary);
  border-bottom-color: var(--status-waiting);
}
.nbadge {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--status-waiting);
  color: var(--ink-inverse);
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
}
.runswitch {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 100%;
  padding: 0 10px;
  border-left: 1px solid var(--line);
}
.rtab {
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--ink-muted);
  text-decoration: none;
  border-radius: var(--radius-sm);
}
.rtab:hover {
  color: var(--ink-primary);
}
.modes {
  display: inline-flex;
  gap: 2px;
  margin-left: 8px;
  padding: 2px;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
}
.mode {
  padding: 2px 8px;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--ink-muted);
  border-radius: 3px;
}
.mode-on {
  color: var(--ink-inverse);
  background: var(--ink-primary);
}
.spacer {
  flex: 1;
}
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--status-waiting);
  color: var(--ink-inverse);
  border-radius: 9px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
}
.ctl {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  padding: 6px 10px;
  color: var(--ink-secondary);
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
}
.ctl:hover {
  color: var(--ink-primary);
  border-color: var(--ink-muted);
}
.menu {
  padding: 6px 12px;
}
</style>
