<script setup lang="ts">
import { ref, watch } from 'vue'
import type { Field, Path } from './schema'

const props = defineProps<{
  name: string
  field: Field
  path: Path
  value: unknown
  errors: Record<string, string>
  readonlyPaths: string[]
  readonly: boolean
}>()
const emit = defineEmits<{ (e: 'set', path: Path, value: unknown): void }>()

const key = (p: Path) => p.join('.')
const isReadonly = () => props.readonly || props.readonlyPaths.includes(key(props.path))
const placeholder = () =>
  'default' in props.field && props.field.default !== undefined && props.field.default !== null
    ? String(props.field.default)
    : ''

function onText(ev: Event) {
  const v = (ev.target as HTMLInputElement | HTMLTextAreaElement).value
  emit('set', props.path, v === '' ? undefined : v)
}
function onNumber(ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const n = Number(raw)
  emit('set', props.path, raw === '' || !Number.isFinite(n) ? undefined : n)
}
function onBool(ev: Event) {
  emit('set', props.path, (ev.target as HTMLInputElement).checked)
}
function onEnum(ev: Event) {
  const v = (ev.target as HTMLSelectElement).value
  emit('set', props.path, v === '' ? undefined : v)
}
function onLines(ev: Event) {
  const lines = (ev.target as HTMLTextAreaElement).value.split('\n').filter((l) => l !== '')
  emit('set', props.path, lines.length ? lines : undefined)
}

// JSON snippet fallback (U8 as amended): parsed on blur; bad JSON stays local.
const snippet = ref(props.value === undefined ? '' : JSON.stringify(props.value, null, 2))
const snippetError = ref<string | null>(null)
watch(() => props.value, (v) => { snippet.value = v === undefined ? '' : JSON.stringify(v, null, 2) })
function onSnippetBlur() {
  if (snippet.value.trim() === '') { snippetError.value = null; emit('set', props.path, undefined); return }
  try {
    const parsed = JSON.parse(snippet.value)
    snippetError.value = null
    emit('set', props.path, parsed)
  } catch (e) {
    snippetError.value = `not JSON: ${(e as Error).message}`
  }
}
const str = (v: unknown) => (v === undefined || v === null ? '' : String(v))
</script>

<template>
  <fieldset v-if="field.kind === 'object'" class="group" :data-path="key(path)">
    <legend>{{ name }}</legend>
    <SchemaField
      v-for="p in field.properties"
      :key="p.name"
      :name="p.name"
      :field="p.field"
      :path="[...path, p.name]"
      :value="value && typeof value === 'object' ? (value as Record<string, unknown>)[p.name] : undefined"
      :errors="errors"
      :readonly-paths="readonlyPaths"
      :readonly="readonly"
      @set="(p2, v) => emit('set', p2, v)"
    />
    <p v-if="errors[key(path)]" class="err" data-testid="field-error">{{ errors[key(path)] }}</p>
  </fieldset>

  <label v-else class="row" :data-path="key(path)" data-testid="schema-field" :data-kind="field.kind">
    <span class="name">{{ name }}</span>
    <textarea
      v-if="field.kind === 'string'"
      class="input" rows="1" :value="str(value)" :placeholder="placeholder()" :readonly="isReadonly()"
      @input="onText"
    />
    <input
      v-else-if="field.kind === 'number' || field.kind === 'integer'"
      class="input" type="number" :step="field.kind === 'integer' ? 1 : 'any'"
      :min="field.minimum ?? field.exclusiveMinimum" :max="field.maximum ?? field.exclusiveMaximum"
      :value="str(value)" :placeholder="placeholder()" :readonly="isReadonly()"
      @change="onNumber"
    />
    <input
      v-else-if="field.kind === 'boolean'"
      type="checkbox" :checked="value === true" :disabled="isReadonly()"
      @change="onBool"
    />
    <select
      v-else-if="field.kind === 'enum'"
      class="input" :value="str(value)" :disabled="isReadonly()"
      @change="onEnum"
    >
      <option value="">{{ placeholder() ? `(default: ${placeholder()})` : '(unset)' }}</option>
      <option v-for="v in field.values" :key="v" :value="v">{{ v }}</option>
    </select>
    <textarea
      v-else-if="field.kind === 'string-array'"
      class="input" rows="2" placeholder="one per line"
      :value="Array.isArray(value) ? value.join('\n') : ''" :readonly="isReadonly()"
      @change="onLines"
    />
    <template v-else>
      <textarea
        v-model="snippet" class="input snippet" rows="3" data-testid="schema-fallback" :readonly="isReadonly()"
        @blur="onSnippetBlur"
      />
      <span v-if="snippetError" class="err">{{ snippetError }}</span>
    </template>
    <span v-if="errors[key(path)]" class="err" data-testid="field-error">{{ errors[key(path)] }}</span>
  </label>
</template>

<style scoped>
.group { margin: 6px 0; padding: 6px 8px; border: 1px solid var(--line); border-radius: 4px; }
legend { padding: 0 4px; color: var(--ink-faint); font-family: var(--font-mono); font-size: 11px; }
.row { display: grid; grid-template-columns: 110px 1fr; gap: 4px 8px; align-items: center; padding: 2px 0; }
.name { color: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; overflow: hidden; text-overflow: ellipsis; }
.input { width: 100%; box-sizing: border-box; background: var(--ground-2); color: var(--ink-secondary); border: 1px solid var(--line); border-radius: 4px; font-family: var(--font-mono); font-size: 12px; padding: 2px 4px; field-sizing: content; resize: vertical; }
.snippet { min-height: 48px; }
.err { grid-column: 2; color: var(--status-failed); font-size: 11px; }
</style>
