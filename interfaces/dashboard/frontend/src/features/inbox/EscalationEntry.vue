<script setup lang="ts">
// 010 T019: the escalation kind (contract §3.3, row 4). Stateless: the
// guidance draft lives in the store, keyed by entryKey. Retry sends
// resolve(true, guidance); quarantine sends resolve(false, guidance);
// guidance is optional for both.
import { Button, Field } from '@kroker/ui'
import type { EscalationItem } from '../../api/types'

defineProps<{
  item: EscalationItem
  busy: boolean
  draft: string
}>()

const emit = defineEmits<{
  (e: 'resolve', retry: boolean, guidance: string): void
  (e: 'update:draft', v: string): void
}>()
</script>

<template>
  <div class="escalation">
    <p v-if="item.analysis" class="analysis inbox-longtext" data-testid="inbox-analysis">{{ item.analysis }}</p>
    <Field
      label="Guidance"
      :model-value="draft"
      :disabled="busy"
      @update:model-value="(v) => emit('update:draft', v)"
    />
    <div class="actions">
      <Button
        variant="primary"
        size="sm"
        :disabled="busy"
        data-testid="inbox-retry"
        @click="emit('resolve', true, draft.trim())"
      >Retry with guidance</Button>
      <Button
        variant="danger"
        size="sm"
        :disabled="busy"
        data-testid="inbox-quarantine"
        @click="emit('resolve', false, draft.trim())"
      >Quarantine</Button>
    </div>
  </div>
</template>

<style scoped>
.escalation {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.analysis {
  margin: 0;
  color: var(--ink-secondary);
}
.actions {
  display: flex;
  gap: var(--space-2);
}
</style>
