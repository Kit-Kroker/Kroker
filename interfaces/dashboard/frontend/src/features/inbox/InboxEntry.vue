<script setup lang="ts">
// 010 T009: the entry frame (contract §3.2). What every waiting item shares
// — kind, run link, age, title, body, notice — plus the slot the kind
// component fills. Field names per data-model §1.1.
import { computed } from 'vue'
import { Surface, Tag } from '@kroker/ui'
import type { InboxItem } from '../../api/types'

const props = defineProps<{ item: InboxItem; notice?: string }>()

// data-model §2.6: the fixed kind label per discriminant.
const kindLabel = computed(() => {
  const item = props.item
  switch (item.type) {
    case 'clarify': return 'question'
    case 'gate': return `gate · ${item.gate}`
    case 'override': return 'merge override'
    case 'escalation': return 'escalation'
  }
})
</script>

<template>
  <Surface
    as="article"
    elevation="flat"
    padding="md"
    class="entry"
    data-testid="inbox-entry"
    :data-run-id="item.runId"
    :data-key="item.id"
    :data-type="item.type"
  >
    <div class="meta">
      <Tag tone="neutral" mono data-testid="inbox-entry-kind">{{ kindLabel }}</Tag>
      <RouterLink
        class="run"
        data-testid="inbox-entry-run"
        :to="{ name: 'run', params: { id: item.runId } }"
      >{{ item.runId }}</RouterLink>
      <span class="age" data-testid="inbox-entry-age">{{ item.age }}</span>
    </div>
    <h2 class="title" data-testid="inbox-entry-title">{{ item.title }}</h2>
    <p v-if="item.body" class="body inbox-longtext" data-testid="inbox-entry-body">{{ item.body }}</p>
    <p v-if="notice" class="notice" data-testid="inbox-notice">{{ notice }}</p>
    <slot />
  </Surface>
</template>

<style scoped>
.entry {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.run {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--accent-text);
}
.age {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--ink-subtle);
}
.title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--ink-primary);
}
.body {
  margin: 0;
  color: var(--ink-secondary);
}
.notice {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--status-failed);
}
</style>

<style>
/* EC8 (contract §3.2): the long-text treatment for the four free-text
   blocks (entry body, suggestion, verdict, analysis). Deliberately NOT
   scoped: the kind components that use it are separate components. */
.inbox-longtext {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  max-height: 30vh;
  overflow-y: auto;
}
</style>
