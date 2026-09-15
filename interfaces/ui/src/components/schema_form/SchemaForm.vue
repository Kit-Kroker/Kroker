<script setup lang="ts">
// A generic form over a served JSON Schema (E-76 spec §8.3, U8). The caller
// owns the schema (pydantic model_json_schema() from the backend), the value
// and what applying it means; the form knows JSON Schema, not Kroker models.
import { computed, ref, watch } from 'vue'
import SchemaField from './SchemaField.vue'
import { classify, setPath, type Path, type Schema } from './schema'

export interface SchemaFormError {
  /** Dot path inside the value, e.g. "gate.policy"; '' for the whole value. */
  path: string
  msg: string
}

const props = withDefaults(
  defineProps<{
    schema: Schema
    value: Record<string, unknown>
    errors?: SchemaFormError[]
    readonly?: boolean
    readonlyPaths?: string[]
  }>(),
  { errors: () => [], readonly: false, readonlyPaths: () => [] },
)
const emit = defineEmits<{ (e: 'update', value: Record<string, unknown>): void }>()

const defs = computed(() => (props.schema.$defs ?? {}) as Record<string, Schema>)
const root = computed(() => classify(props.schema, defs.value))
const properties = computed(() => (root.value.kind === 'object' ? root.value.properties : []))
const errorMap = computed(() => Object.fromEntries(props.errors.map((e) => [e.path, e.msg])))
const formError = computed(() => errorMap.value[''] ?? null)

// `base` is the value as supplied; the draft accumulates touched paths only.
const draft = ref<Record<string, unknown>>(JSON.parse(JSON.stringify(props.value)))
watch(() => props.value, (v) => { draft.value = JSON.parse(JSON.stringify(v)) })

function onSet(path: Path, next: unknown) {
  if (props.readonly || props.readonlyPaths.includes(path.join('.'))) return
  draft.value = setPath(draft.value, path, next, props.value)
  emit('update', draft.value)
}
</script>

<template>
  <form class="cmp-schema-form" data-testid="schema-form" @submit.prevent>
    <p v-if="formError" class="err" data-testid="form-error">{{ formError }}</p>
    <SchemaField
      v-for="p in properties"
      :key="p.name"
      :name="p.name"
      :field="p.field"
      :path="[p.name]"
      :value="draft[p.name]"
      :errors="errorMap"
      :readonly-paths="readonlyPaths"
      :readonly="readonly"
      @set="onSet"
    />
  </form>
</template>

<style scoped>
.cmp-schema-form { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; font-size: 12px; }
.err { margin: 0 0 6px; color: var(--status-failed); }
</style>
