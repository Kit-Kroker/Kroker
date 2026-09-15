<script setup lang="ts">
import { computed, ref } from 'vue'

export type GateDecisionOutcome = 'approve' | 'revise' | 'reject'

const props = withDefaults(defineProps<{ title: string; busy?: boolean; disabled?: boolean }>(), {
  busy: false,
  disabled: false,
})
const emit = defineEmits<{ (e: 'decide', v: { outcome: GateDecisionOutcome; comment: string }): void }>()

const comment = ref('')
const locked = computed(() => props.busy || props.disabled)
// GATE_DECISION-2: a revise must say what to change. A UI affordance only --
// the server accepts an empty revise (E-76 spec E76-OQ-4).
const reviseBlocked = computed(() => locked.value || comment.value.trim() === '')

function decide(outcome: GateDecisionOutcome) {
  if (locked.value || (outcome === 'revise' && reviseBlocked.value)) return
  emit('decide', { outcome, comment: comment.value.trim() })
}
</script>

<template>
  <div class="cmp-gate-decision" :class="{ 'is-busy': busy }" data-testid="gate-decision" @mousedown.stop @keydown.stop>
    <div class="title">{{ title }}</div>
    <textarea
      v-model="comment"
      class="comment"
      data-testid="gate-comment"
      rows="2"
      placeholder="comment (required to revise)"
      :disabled="locked"
    />
    <div class="actions">
      <button data-testid="gate-approve" class="btn approve" :disabled="locked" @click="decide('approve')">approve</button>
      <button data-testid="gate-revise" class="btn revise" :disabled="reviseBlocked" @click="decide('revise')">revise</button>
      <button data-testid="gate-reject" class="btn reject" :disabled="locked" @click="decide('reject')">reject</button>
    </div>
  </div>
</template>

<style scoped>
.cmp-gate-decision { display: flex; flex-direction: column; gap: 6px; padding: 8px; border-top: 1px solid var(--line); background: var(--ground-4); }
.cmp-gate-decision.is-busy { opacity: 0.6; }
.title { color: var(--ink-primary); font-size: 12px; font-weight: 600; }
.comment { resize: vertical; background: var(--ground-2); color: var(--ink-secondary); border: 1px solid var(--line); border-radius: 4px; font-family: var(--font-sans); font-size: 12px; padding: 4px 6px; }
.actions { display: flex; gap: 6px; }
.btn { flex: 1; border: 1px solid var(--line-strong); border-radius: 4px; background: var(--ground-3); color: var(--ink-secondary); font-family: var(--font-mono); font-size: 11px; padding: 3px 0; cursor: pointer; }
.btn:disabled { cursor: not-allowed; color: var(--ink-whisper); }
.approve:not(:disabled) { border-color: var(--status-done); }
.revise:not(:disabled) { border-color: var(--status-blocked); }
.reject:not(:disabled) { border-color: var(--status-failed); }
</style>
