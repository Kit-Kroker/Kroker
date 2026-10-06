<script setup lang="ts">
import { ref, computed, watch } from 'vue'

export type ProjectMode = 'brownfield' | 'greenfield'

export interface StartRunPayload {
  title: string
  repo: string
  mode: ProjectMode
  // 011 US2: trimmed text; '' = no budget. The caller converts and owns
  // the server round-trip (the component only blocks what cannot stand).
  budget: string
}

const props = withDefaults(
  defineProps<{
    open: boolean
    initialTitle?: string
    initialRepo?: string
    initialMode?: ProjectMode
    initialBudget?: string
  }>(),
  {
    open: false,
    initialTitle: '',
    initialRepo: '',
    initialMode: 'brownfield',
    initialBudget: '',
  },
)

const emit = defineEmits<{
  (e: 'submit', payload: StartRunPayload): void
  (e: 'close'): void
  (e: 'invalid'): void
}>()

const title = ref(props.initialTitle)
const repo = ref(props.initialRepo)
const mode = ref<ProjectMode>(props.initialMode)
const budget = ref(props.initialBudget)

watch(
  () => [props.open, props.initialTitle, props.initialRepo, props.initialMode, props.initialBudget],
  ([isOpen]) => {
    if (isOpen) {
      title.value = props.initialTitle
      repo.value = props.initialRepo
      mode.value = props.initialMode
      budget.value = props.initialBudget
    }
  },
)

// 011 (START_RUN_MODAL-3): the field is optional; non-empty and not a
// number greater than 0 blocks submission with the server's own messages
// (zero is its own case — omit the field). The server stays the authority.
const budgetError = computed(() => {
  const raw = budget.value.trim()
  if (raw === '') return ''
  const n = Number(raw)
  if (Number.isNaN(n)) return 'budget must be a number greater than 0'
  if (n === 0) return 'budget must be greater than 0; omit it to run without a budget'
  if (n < 0) return 'budget must be a number greater than 0'
  return ''
})

const canSubmit = computed(() => title.value.trim().length > 0 && budgetError.value === '')

function handleSubmit() {
  if (!canSubmit.value) {
    emit('invalid')
    return
  }
  emit('submit', {
    title: title.value.trim(),
    repo: repo.value.trim(),
    mode: mode.value,
    budget: budget.value.trim(),
  })
}
</script>

<template>
  <div
    v-if="open"
    data-testid="backdrop"
    class="cmp-start-run-modal backdrop"
    @click="emit('close')"
  >
    <div data-testid="modal-card" class="card" @click.stop>
      <div class="title">START RUN</div>

      <label class="lbl">FEATURE TITLE</label>
      <input
        v-model="title"
        data-testid="start-title-input"
        class="inp"
        placeholder="Add SSO to customer portal"
      />

      <label class="lbl">REPO URL</label>
      <input
        v-model="repo"
        data-testid="start-repo-input"
        class="inp mono"
        placeholder="git@github.com:org/repo"
      />

      <label class="lbl">MODE</label>
      <div class="modes">
        <button
          type="button"
          class="mode"
          :class="{ on: mode === 'brownfield' }"
          @click="mode = 'brownfield'"
        >
          brownfield
        </button>
        <button
          type="button"
          class="mode"
          :class="{ on: mode === 'greenfield' }"
          @click="mode = 'greenfield'"
        >
          greenfield
        </button>
      </div>

      <label class="lbl">BUDGET (USD)</label>
      <input
        v-model="budget"
        data-testid="start-budget-input"
        class="inp mono"
        placeholder="optional; crossing it raises the budget gate"
      />
      <p v-if="budgetError" data-testid="start-budget-error" class="err">{{ budgetError }}</p>

      <div class="actions">
        <button type="button" class="ghost" @click="emit('close')">CANCEL</button>
        <button
          type="button"
          data-testid="submit"
          class="go"
          :disabled="!canSubmit"
          @click="handleSubmit"
        >
          START
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(5, 7, 10, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.card {
  width: 480px;
  background: var(--ground-3);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 22px 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.title {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: var(--ink-primary);
  margin-bottom: 18px;
}
.lbl {
  display: block;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--ink-subtle);
  margin-bottom: 6px;
}
.inp {
  width: 100%;
  background: var(--ground-2);
  border: 1px solid var(--line-strong);
  border-radius: 5px;
  color: var(--ink-secondary);
  font-size: 12.5px;
  padding: 9px 12px;
  margin-bottom: 14px;
  font-family: var(--font-sans);
}
.mono {
  font-family: var(--font-mono);
}
.err {
  margin: -8px 0 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--status-failed);
}
.modes {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.mode {
  cursor: pointer;
  flex: 1;
  font-family: var(--font-mono);
  font-size: 11.5px;
  padding: 8px 0;
  border-radius: 4px;
  background: var(--ground-2);
  color: var(--ink-faint);
  border: 1px solid var(--line-strong);
}
.mode.on {
  background: var(--accent-tint-surface);
  color: var(--status-blocked);
  border-color: var(--accent-tint-border);
}
.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.ghost {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  padding: 8px 16px;
  background: none;
  color: var(--ink-muted);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
}
.ghost:hover {
  color: var(--ink-secondary);
}
.go {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 8px 16px;
  background: var(--status-blocked);
  color: var(--accent-ink);
  border: none;
  border-radius: 4px;
}
.go:hover:not(:disabled) {
  background: var(--accent-hover);
}
.go:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
