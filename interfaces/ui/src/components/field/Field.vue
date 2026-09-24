<script lang="ts">
// Vue ^3.4 has no useId(); a module counter gives each instance a stable id.
let seq = 0
</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{ label: string; modelValue: string; placeholder?: string; hint?: string; error?: string; multiline?: boolean; rows?: number; disabled?: boolean; required?: boolean }>(),
  { multiline: true, rows: 4, disabled: false, required: false },
)
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const id = `cmp-field-${++seq}`
const noteId = `${id}-note`
const invalid = computed(() => !!props.error)
const note = computed(() => props.error || props.hint || '')

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement | HTMLTextAreaElement).value)
}
</script>

<template>
  <div class="cmp-field" :class="{ 'is-invalid': invalid, 'is-disabled': disabled }">
    <div class="bar">
      <label class="label" :for="id">{{ label }}<span v-if="required" class="req" aria-hidden="true"> *</span></label>
      <span class="spacer" />
      <slot name="action" />
    </div>
    <textarea
      v-if="multiline"
      :id="id"
      class="control"
      :value="modelValue"
      :rows="rows"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-invalid="invalid"
      :aria-describedby="note ? noteId : undefined"
      data-testid="field-control"
      @input="onInput"
    />
    <input
      v-else
      :id="id"
      class="control"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :required="required"
      :aria-invalid="invalid"
      :aria-describedby="note ? noteId : undefined"
      data-testid="field-control"
      @input="onInput"
    />
    <span v-if="error" :id="noteId" class="note error" role="alert" data-testid="field-error">{{ error }}</span>
    <span v-else-if="hint" :id="noteId" class="note" data-testid="field-hint">{{ hint }}</span>
  </div>
</template>

<style scoped>
.cmp-field { display: flex; flex-direction: column; gap: var(--space-2); }
.bar { display: flex; align-items: center; gap: var(--space-2); }
.label { font-family: var(--font-sans); font-size: var(--text-md); font-weight: 500; color: var(--ink-primary); }
.req { color: var(--ink-muted); }
.spacer { flex: 1; }
.control { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-md); background: var(--ground-canvas); color: var(--ink-primary); font-family: var(--font-sans); font-size: var(--text-md); line-height: 1.5; resize: vertical; }
.control::placeholder { color: var(--ink-muted); }
.control:focus { outline: none; border-color: var(--ink-secondary); }
.is-invalid .control { border-color: var(--status-failed); }
.control:disabled { opacity: 0.5; cursor: not-allowed; }
.note { font-family: var(--font-sans); font-size: var(--text-sm); color: var(--ink-muted); line-height: 1.45; }
.note.error { color: var(--status-failed); }
</style>
