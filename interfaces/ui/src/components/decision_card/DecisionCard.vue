<script setup lang="ts">
// 018 T034/T035 (data-model §4.2, S14): the v5 decision card shell — one
// card for every kind (R-3). Presentational: the caller maps InboxItem or
// pending ref to these props and turns act(id, text) into a client call.
// Each action's consequence title renders as VISIBLE text before the click
// (never a tooltip): a decision is taken with its consequence in view.
import { ref, watch } from 'vue'

export interface CardField {
  k: string
  v: string
  mono?: boolean
}

export interface CardText {
  label: string
  hint: string
  value: string
  required: boolean
}

export interface CardAction {
  id: string
  label: string
  title: string
  variant: string
  needsText?: boolean
}

const props = withDefaults(
  defineProps<{
    kicker: string
    schema: string
    title: string
    where: string
    fields: CardField[]
    text?: CardText
    actions: CardAction[]
    foot: string
    busy?: boolean
  }>(),
  { busy: false },
)

const emit = defineEmits<{ (e: 'act', id: string, text: string): void }>()

const draft = ref(props.text?.value ?? '')
watch(
  () => props.text,
  (t) => { draft.value = t?.value ?? '' },
)

function gated(a: CardAction): boolean {
  return a.needsText === true && draft.value.trim() === ''
}
function disabled(a: CardAction): boolean {
  return props.busy || gated(a)
}
function act(a: CardAction): void {
  if (disabled(a)) return
  emit('act', a.id, draft.value)
}
</script>

<template>
  <article class="cmp-decision-card" data-testid="decision-card">
    <header class="head">
      <span class="kicker" data-testid="card-kicker">{{ kicker }}</span>
      <span class="schema" data-testid="card-schema">{{ schema }}</span>
    </header>
    <h3 class="title" data-testid="card-title">{{ title }}</h3>
    <p class="where" data-testid="card-where">{{ where }}</p>
    <dl class="fields">
      <div v-for="f in fields" :key="f.k" class="field" data-testid="card-field">
        <dt class="k">{{ f.k }}</dt>
        <dd class="v" :class="{ mono: f.mono }">{{ f.v }}</dd>
      </div>
    </dl>
    <label v-if="text" class="text-block">
      <span class="text-label">{{ text.label }}<span v-if="text.required" class="req"> · required</span></span>
      <textarea
        class="text"
        data-testid="card-text"
        :aria-label="text.label"
        :placeholder="text.hint"
        :disabled="busy"
        v-model="draft"
      />
    </label>
    <div class="actions">
      <div v-for="a in actions" :key="a.id" class="action">
        <button
          class="btn"
          :class="`is-${a.variant}`"
          data-testid="card-action"
          :disabled="disabled(a)"
          @click="act(a)"
        >{{ a.label }}</button>
        <span class="action-title" data-testid="action-title">{{ a.title }}</span>
      </div>
    </div>
    <footer class="foot" data-testid="card-foot">{{ foot }}</footer>
  </article>
</template>

<style scoped>
.cmp-decision-card {
  width: 380px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--ground-2);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 14px;
  box-shadow: var(--shadow-overlay);
  font-family: var(--font-sans);
  font-size: 12.5px;
  color: var(--ink-secondary);
}
.head { display: flex; align-items: center; gap: 8px; }
.kicker { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.08em; color: var(--ink-subtle); }
.schema {
  font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-tertiary);
  border: 1px solid var(--line); border-radius: 4px; padding: 1px 6px;
}
.title { margin: 0; font-size: 14px; font-weight: 600; color: var(--ink-primary); }
.where { margin: 0; font-family: var(--font-mono); font-size: 11px; color: var(--ink-subtle); }
.fields { margin: 0; display: flex; flex-direction: column; gap: 2px; }
.field { display: flex; justify-content: space-between; gap: 10px; }
.field .k { color: var(--ink-subtle); }
.field .v { margin: 0; color: var(--ink-tertiary); }
.field .v.mono { font-family: var(--font-mono); font-size: 11px; }
.text-block { display: flex; flex-direction: column; gap: 4px; }
.text-label { font-size: 11px; color: var(--ink-subtle); }
.req { color: var(--status-waiting); }
.text {
  font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-primary);
  background: var(--ground-3); border: 1px solid var(--line); border-radius: 4px;
  padding: 6px 8px; min-height: 56px; resize: vertical;
}
.actions { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--line); padding-top: 8px; }
.action { display: flex; align-items: baseline; gap: 8px; }
.btn {
  cursor: pointer; font-family: var(--font-sans); font-size: 12px;
  padding: 6px 12px; border-radius: 4px;
  background: var(--ground-3); color: var(--ink-primary); border: 1px solid var(--line-strong);
}
.btn.is-primary { border-color: var(--accent); }
.btn.is-danger { color: var(--status-failed); border-color: var(--status-failed); }
.btn:disabled { cursor: not-allowed; color: var(--ink-subtle); border-color: var(--line); }
.action-title { font-size: 11px; color: var(--ink-subtle); }
.foot { font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-subtle); border-top: 1px solid var(--line); padding-top: 6px; }
</style>
