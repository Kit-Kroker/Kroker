<script setup lang="ts">
// 010 T018: the merge-override kind (contract §3.3, row 3). Stateless: the
// justification draft lives in the store, keyed by entryKey. An override
// needs a non-empty trimmed justification (GATE 1, Q2 = A); a send-back may
// carry empty text. Override and send-back share this one draft.
import { computed } from 'vue'
import { Button, CheckRow, Field } from '@kroker/ui'
import type { OverrideItem } from '../../api/types'

const props = defineProps<{
  item: OverrideItem
  busy: boolean
  draft: string
}>()

const emit = defineEmits<{
  (e: 'resolve', approve: boolean, text: string): void
  (e: 'update:draft', v: string): void
}>()

const canOverride = computed(() => props.draft.trim() !== '')
</script>

<template>
  <div class="override">
    <p v-if="item.verdict" class="verdict inbox-longtext" data-testid="inbox-verdict">{{ item.verdict }}</p>
    <ul class="checks">
      <li v-for="check in item.checks" :key="check.name" class="check">
        <CheckRow v-bind="check" />
      </li>
    </ul>
    <Field
      label="Justification"
      :model-value="draft"
      required
      :disabled="busy"
      @update:model-value="(v) => emit('update:draft', v)"
    />
    <div class="actions">
      <Button
        variant="primary"
        size="sm"
        :disabled="busy || !canOverride"
        data-testid="inbox-override"
        @click="emit('resolve', true, draft.trim())"
      >Override</Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="busy"
        data-testid="inbox-send-back"
        @click="emit('resolve', false, draft.trim())"
      >Send back</Button>
    </div>
  </div>
</template>

<style scoped>
.override {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.verdict {
  margin: 0;
  color: var(--ink-secondary);
}
.checks {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.actions {
  display: flex;
  gap: var(--space-2);
}
</style>
