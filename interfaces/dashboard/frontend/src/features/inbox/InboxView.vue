<script setup lang="ts">
// 010 T009: the decision-inbox screen (contract §3.1). Three honest states
// plus the list; App.vue already loads and polls the store, so this view
// starts no poll and calls no refresh (contract §3.4).
import { useInboxStore } from '../../app/inbox.store'
import { entryKey } from '../../shared/entryKey'
import InboxEntry from './InboxEntry.vue'

const inbox = useInboxStore()
</script>

<template>
  <main data-testid="inbox-view" data-screen-label="Decision inbox" class="view">
    <header class="head">
      <h1 class="heading">Decision inbox</h1>
      <span class="count" data-testid="inbox-count-line">{{ inbox.items.length }} waiting</span>
    </header>

    <div v-if="!inbox.loaded && !inbox.loadError" class="state" data-testid="inbox-loading">loading…</div>
    <div
      v-else-if="!inbox.loaded && inbox.loadError"
      class="state"
      data-testid="inbox-load-error"
    >The inbox could not be loaded.</div>
    <div
      v-else-if="inbox.loaded && inbox.items.length === 0 && inbox.unreadable.length === 0 && !inbox.loadError"
      class="state"
      data-testid="inbox-empty"
    >Nothing is waiting.</div>

    <template v-else>
      <!-- FR-011: with a banner up, "nothing is waiting" would be a lie. -->
      <div
        v-if="inbox.loaded && (inbox.unreadable.length > 0 || inbox.loadError)"
        class="incomplete"
        data-testid="inbox-incomplete"
      >
        <p v-if="inbox.loadError" class="line">The inbox could not be refreshed; showing the last known list.</p>
        <p v-if="inbox.unreadable.length > 0" class="line">
          This list may be incomplete: the pending state of
          {{ inbox.unreadable.length }} run(s) could not be read.
          {{ inbox.unreadable.map((r) => r.runId).join(' ') }}
        </p>
      </div>

      <div class="entries">
        <InboxEntry
          v-for="item in inbox.items"
          :key="entryKey(item)"
          :item="item"
          :notice="inbox.notice[entryKey(item)]"
        />
      </div>
    </template>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 60px;
}
.head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.heading {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--ink-primary);
}
.count {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--ink-subtle);
}
.state {
  color: var(--ink-subtle);
  font-family: var(--font-mono);
  font-size: 12px;
}
.incomplete {
  border: 1px solid var(--status-blocked);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
}
.line {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--ink-secondary);
}
.entries {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
</style>
