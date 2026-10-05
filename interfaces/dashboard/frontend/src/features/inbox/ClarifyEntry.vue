<script setup lang="ts">
// 010 T012: the clarify kind (contract §3.3, row 1). Stateless: the draft
// and the edit flag live in the store, keyed by entryKey; this component
// only renders and re-emits. R-12: a suggestion that is empty after
// trimming counts as no suggestion.
import { computed } from 'vue'
import { Button, Field } from '@kroker/ui'
import type { ClarifyItem } from '../../api/types'

const props = defineProps<{
  item: ClarifyItem
  busy: boolean
  draft: string
  editing: boolean
}>()

const emit = defineEmits<{
  (e: 'answer', text: string): void
  (e: 'update:draft', v: string): void
  (e: 'toggle-edit'): void
}>()

const hasSuggestion = computed(() => props.item.suggestion.trim() !== '')
const showField = computed(() => props.editing || !hasSuggestion.value)
const canSend = computed(() => props.draft.trim() !== '')
</script>

<template>
  <div class="clarify">
    <p v-if="hasSuggestion" class="suggestion inbox-longtext" data-testid="inbox-suggestion">{{ item.suggestion }}</p>
    <div v-if="hasSuggestion" class="actions">
      <Button
        variant="primary"
        size="sm"
        :disabled="busy"
        data-testid="inbox-accept"
        @click="emit('answer', item.suggestion.trim())"
      >Accept suggestion</Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="busy"
        data-testid="inbox-edit"
        @click="emit('toggle-edit')"
      >{{ editing ? 'Hide my own answer' : 'Write my own answer' }}</Button>
    </div>
    <Field
      v-if="showField"
      label="Answer"
      :model-value="draft"
      :disabled="busy"
      @update:model-value="(v) => emit('update:draft', v)"
    />
    <div v-if="showField" class="actions">
      <Button
        variant="primary"
        size="sm"
        :disabled="busy || !canSend"
        data-testid="inbox-send"
        @click="emit('answer', draft.trim())"
      >Send</Button>
    </div>
  </div>
</template>

<style scoped>
.clarify {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.suggestion {
  margin: 0;
  color: var(--ink-secondary);
}
.actions {
  display: flex;
  gap: var(--space-2);
}
</style>
