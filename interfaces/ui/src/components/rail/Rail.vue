<script setup lang="ts">
// 018 T024 (data-model §4.2, S3): the v5 run rail — the run-block head
// (title, state, fact rows, budget), call-to-actions, segmented section
// tabs and one section slot per tab. The caller owns the graph and the
// active section; the rail only renders and reports clicks.
export interface RailBudget {
  spent: string
  limit: number | null
  pct: number | null
  note: string
}

export interface RailHead {
  title: string
  state: string
  stateKind: string
  rows: { k: string; v: string }[]
  budget: RailBudget
}

export interface RailTabItem {
  id: string
  label: string
}

export interface RailCall {
  label: string
  kind: string
}

withDefaults(
  defineProps<{
    head: RailHead
    tabs: RailTabItem[]
    active: string
    calls?: RailCall[]
  }>(),
  { calls: () => [] },
)

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'call', index: number): void
}>()
</script>

<template>
  <aside class="cmp-rail" data-testid="rail">
    <div class="head">
      <div class="title" data-testid="rail-title">{{ head.title }}</div>
      <div class="state" :class="`is-${head.stateKind}`" data-testid="rail-state">{{ head.state }}</div>
      <div class="rows" data-testid="rail-rows">
        <div v-for="r in head.rows" :key="r.k" class="row" data-testid="rail-row">
          <span class="k">{{ r.k }}</span>
          <span class="v">{{ r.v }}</span>
        </div>
      </div>
      <div class="budget" data-testid="rail-budget">
        <!-- Only a null limit is "off"; a numeric limit (even 0) draws the bar. -->
        <div v-if="head.budget.limit === null" class="off">off</div>
        <div v-else class="bar" data-testid="rail-budget-bar">
          <div class="fill" :style="{ width: `${Math.min(100, Math.max(0, head.budget.pct ?? 0))}%` }" />
        </div>
        <span class="spent">{{ head.budget.spent }}</span>
        <span class="note">{{ head.budget.note }}</span>
      </div>
    </div>
    <div v-if="calls.length" class="calls">
      <button
        v-for="(c, i) in calls"
        :key="i"
        class="call"
        :class="`is-${c.kind}`"
        data-testid="rail-call"
        @click="emit('call', i)"
      >
        {{ c.label }}
      </button>
    </div>
    <nav class="tabs">
      <button
        v-for="t in tabs"
        :key="t.id"
        class="tab"
        :class="{ 'is-active': t.id === active }"
        data-testid="rail-tab"
        @click="emit('select', t.id)"
      >
        {{ t.label }}
      </button>
    </nav>
    <div class="section"><slot :name="active" /></div>
  </aside>
</template>

<style scoped>
.cmp-rail {
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--ground-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--ink-secondary);
}
.head { display: flex; flex-direction: column; gap: 6px; }
.title { font-weight: 600; color: var(--ink-primary); }
.state { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.06em; color: var(--ink-tertiary); }
.state.is-failed { color: var(--status-failed); }
.state.is-waiting { color: var(--status-waiting); }
.state.is-done { color: var(--status-done); }
.rows { display: flex; flex-direction: column; gap: 2px; }
.row { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 11px; }
.row .k { color: var(--ink-subtle); }
.row .v { color: var(--ink-tertiary); }
.budget { display: flex; flex-direction: column; gap: 3px; border-top: 1px solid var(--line); padding-top: 8px; }
.budget .off { font-family: var(--font-mono); font-size: 11px; color: var(--ink-subtle); }
.budget .bar { height: 4px; border-radius: 2px; background: var(--ground-4); overflow: hidden; }
.budget .bar .fill { height: 100%; background: var(--accent); }
.budget .spent { font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary); }
.budget .note { font-size: 10.5px; color: var(--ink-subtle); }
.calls { display: flex; flex-direction: column; gap: 6px; }
.call { cursor: pointer; text-align: left; padding: 7px 10px; border-radius: 4px; border: 1px solid var(--line-strong); background: var(--ground-3); color: var(--ink-primary); font-family: var(--font-sans); font-size: 12px; }
.call.is-primary { border-color: var(--accent); }
.call.is-danger { color: var(--status-failed); border-color: var(--status-failed); }
.tabs { display: flex; gap: 4px; border-top: 1px solid var(--line); padding-top: 10px; }
.tab { cursor: pointer; padding: 5px 10px; border: none; border-radius: 4px; background: none; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.04em; }
.tab.is-active { background: var(--ground-4); color: var(--ink-primary); }
.section { border-top: 1px solid var(--line); padding-top: 8px; }
</style>
