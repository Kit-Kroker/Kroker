<script setup lang="ts">
import { computed } from 'vue'

export interface YamlPaneError {
  /** A readable path into the document, e.g. "nodes[3].id"; '' for the whole text. */
  path: string
  message: string
  line: number | null
  column: number | null
}

const props = withDefaults(
  defineProps<{
    text: string
    errors?: YamlPaneError[]
    dirty?: boolean
    busy?: boolean
    /** Refuse to apply above this many UTF-8 bytes (the server's cap). */
    maxBytes?: number | null
  }>(),
  { errors: () => [], dirty: false, busy: false, maxBytes: null },
)

const emit = defineEmits<{
  (e: 'update:text', text: string): void
  (e: 'apply'): void
}>()

const bytes = computed(() => new TextEncoder().encode(props.text).length)
const tooLarge = computed(() => props.maxBytes !== null && bytes.value > props.maxBytes)
const applyDisabled = computed(() => props.busy || !props.dirty || tooLarge.value)

function onInput(ev: Event) {
  emit('update:text', (ev.target as HTMLTextAreaElement).value)
}
function onApply() {
  if (!applyDisabled.value) emit('apply')
}
const where = (e: YamlPaneError) =>
  [e.line !== null ? `line ${e.line}${e.column !== null ? `:${e.column}` : ''}` : '', e.path].filter(Boolean).join(' · ')
</script>

<template>
  <section class="cmp-yaml-pane" data-testid="yaml-pane">
    <header class="bar">
      <span class="notice">canonical YAML — comments, key order and default values are not kept across canvas edits</span>
      <span v-if="tooLarge" class="too-large" data-testid="yaml-too-large">{{ bytes }} bytes exceeds {{ maxBytes }}</span>
      <button class="apply" data-testid="yaml-apply" :disabled="applyDisabled" @click="onApply">apply</button>
    </header>
    <textarea
      class="text"
      data-testid="yaml-text"
      spellcheck="false"
      :value="text"
      :readonly="busy"
      @input="onInput"
    />
    <ul v-if="errors.length" class="errors" data-testid="yaml-errors">
      <li v-for="(e, i) in errors" :key="i" class="error" data-testid="yaml-error">
        <span v-if="where(e)" class="where">{{ where(e) }}</span>
        <span class="message">{{ e.message }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cmp-yaml-pane { display: flex; flex-direction: column; height: 100%; background: var(--ground-2); }
.bar { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-bottom: 1px solid var(--line); }
.notice { flex: 1; color: var(--ink-subtle); font-size: 11px; }
.too-large { color: var(--status-failed); font-family: var(--font-mono); font-size: 11px; }
.apply { background: var(--accent); color: var(--accent-ink); border: none; border-radius: 4px; padding: 3px 12px; font-family: var(--font-mono); font-size: 11px; cursor: pointer; }
.apply:disabled { background: var(--ground-4); color: var(--ink-whisper); cursor: not-allowed; }
.text { flex: 1; min-height: 240px; resize: none; border: none; padding: 10px; background: var(--ground-1); color: var(--ink-secondary); font-family: var(--font-mono); font-size: 12px; line-height: 1.5; outline: none; }
.errors { margin: 0; padding: 6px 10px; list-style: none; border-top: 1px solid var(--line); max-height: 30%; overflow: auto; }
.error { display: flex; gap: 8px; padding: 2px 0; font-size: 12px; }
.where { color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; white-space: nowrap; }
.message { color: var(--status-failed); white-space: pre-wrap; }
</style>
