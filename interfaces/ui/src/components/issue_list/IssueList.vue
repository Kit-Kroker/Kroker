<script setup lang="ts">
export interface IssueItem {
  key: string
  severity: 'error' | 'warning'
  message: string
  targetLabel: string
  /** Canvas key to focus; null for a graph-level issue. */
  focusKey: string | null
}

defineProps<{ items: IssueItem[] }>()
const emit = defineEmits<{ (e: 'focus', key: string): void }>()
</script>

<template>
  <div class="cmp-issue-list" data-testid="issue-list">
    <p v-if="items.length === 0" class="none" data-testid="issues-none">no issues</p>
    <ul v-else>
      <li
        v-for="item in items"
        :key="item.key"
        class="issue"
        :class="`cmp-issue-${item.severity}`"
        data-testid="issue"
      >
        <button v-if="item.focusKey" class="target" @click="emit('focus', item.focusKey)">{{ item.targetLabel }}</button>
        <span v-else class="target graph">{{ item.targetLabel }}</span>
        <span class="message">{{ item.message }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cmp-issue-list { padding: 8px 10px; background: var(--ground-2); border-top: 1px solid var(--line); font-size: 12px; overflow: auto; }
.none { margin: 0; color: var(--ink-subtle); }
ul { margin: 0; padding: 0; list-style: none; }
.issue { display: flex; gap: 8px; padding: 2px 0; color: var(--ink-secondary); }
.target { background: none; border: none; padding: 0; color: var(--link); font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.target.graph { color: var(--ink-faint); cursor: default; }
.cmp-issue-error .message { color: var(--status-failed); }
.cmp-issue-warning .message { color: var(--status-blocked); }
</style>
