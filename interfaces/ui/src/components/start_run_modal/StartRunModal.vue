<script setup lang="ts">
import { ref, computed, watch } from 'vue'

export type ProjectMode = 'brownfield' | 'greenfield'

export interface StartRunPayload {
  title: string
  repo: string
  mode: ProjectMode
}

const props = withDefaults(
  defineProps<{
    open: boolean
    initialTitle?: string
    initialRepo?: string
    initialMode?: ProjectMode
  }>(),
  {
    open: false,
    initialTitle: '',
    initialRepo: '',
    initialMode: 'brownfield',
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

watch(
  () => [props.open, props.initialTitle, props.initialRepo, props.initialMode],
  ([isOpen]) => {
    if (isOpen) {
      title.value = props.initialTitle
      repo.value = props.initialRepo
      mode.value = props.initialMode
    }
  },
)

const canSubmit = computed(() => title.value.trim().length > 0)

function handleSubmit() {
  if (!canSubmit.value) {
    emit('invalid')
    return
  }
  emit('submit', {
    title: title.value.trim(),
    repo: repo.value.trim(),
    mode: mode.value,
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
  background: var(--c-10141b);
  border: 1px solid var(--c-2a3140);
  border-radius: 8px;
  padding: 22px 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.title {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.08em;
  font-weight: 600;
  color: var(--c-e8edf5);
  margin-bottom: 18px;
}
.lbl {
  display: block;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--c-5d6675);
  margin-bottom: 6px;
}
.inp {
  width: 100%;
  background: var(--c-0d1016);
  border: 1px solid var(--c-2a3140);
  border-radius: 5px;
  color: var(--c-d9dfe9);
  font-size: 12.5px;
  padding: 9px 12px;
  margin-bottom: 14px;
  font-family: var(--font-sans);
}
.mono {
  font-family: var(--font-mono);
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
  background: var(--c-0d1016);
  color: var(--c-7d8697);
  border: 1px solid var(--c-2a3140);
}
.mode.on {
  background: var(--c-2a2310);
  color: var(--status-blocked);
  border-color: var(--c-574a2c);
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
  color: var(--c-8a93a5);
  border: 1px solid var(--c-2a3140);
  border-radius: 4px;
}
.ghost:hover {
  color: var(--c-d9dfe9);
}
.go {
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  padding: 8px 16px;
  background: var(--status-blocked);
  color: var(--c-1a1405);
  border: none;
  border-radius: 4px;
}
.go:hover:not(:disabled) {
  background: var(--c-ecc06a);
}
.go:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
