<script setup lang="ts">
import StatusPip from '../status_pip/StatusPip.vue'

export interface TimelineItem {
  id: string | number
  to: string
  from?: string
  /** status kind for the mark; defaults to `to` */
  kind?: string
  detail?: string
  at: string
  actor?: string
}

defineProps<{ items: TimelineItem[] }>()
</script>

<template>
  <ol v-if="items.length" class="cmp-timeline">
    <li v-for="it in items" :key="it.id" class="entry" data-testid="timeline-entry">
      <span class="rail"><StatusPip :kind="it.kind ?? it.to" /><span class="line" /></span>
      <span class="body">
        <span class="move"><template v-if="it.from"><span class="from">{{ it.from }}</span> → </template><span class="to">{{ it.to }}</span></span>
        <span v-if="it.detail" class="detail" data-testid="timeline-detail">{{ it.detail }}</span>
        <span class="when">{{ it.at }}<template v-if="it.actor"> · {{ it.actor }}</template></span>
      </span>
    </li>
  </ol>
  <div v-else class="cmp-timeline-empty"><slot name="empty" /></div>
</template>

<style scoped>
.cmp-timeline { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; font-family: var(--font-sans); }
.entry { display: grid; grid-template-columns: 14px minmax(0, 1fr); gap: 10px; }
.rail { display: flex; flex-direction: column; align-items: center; padding-top: 5px; }
.line { flex: 1; width: 1px; margin-top: 4px; background: var(--line); }
.entry:last-child .line { display: none; }
.body { display: flex; flex-direction: column; gap: 2px; padding-bottom: var(--space-3); min-width: 0; }
.move { font-size: var(--text-sm); color: var(--ink-primary); }
.from { color: var(--ink-secondary); }
.to { font-weight: 500; }
.detail { font-size: var(--text-sm); color: var(--ink-secondary); text-wrap: pretty; }
.when { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--ink-muted); }
.cmp-timeline-empty { font-size: var(--text-sm); color: var(--ink-muted); }
</style>
