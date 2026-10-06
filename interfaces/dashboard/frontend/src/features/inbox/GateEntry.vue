<script setup lang="ts">
// 010 T015: the gate kind (contract §3.3, row 2). Reuses the library's
// GateDecision unchanged — the same control the run canvas offers — and
// adapts its one-object payload to the two-argument decide event of
// data-model §2.5 (the same adaptation as RunView.vue:122). The comment
// lives inside GateDecision and survives refreshes because the v-for key
// is the composite key (research R-7).
// 011 R-9 (FR-008): a budget gate says what approving grants — one more
// increment of the same amount — read from the run's own live numbers
// (current limit + budget); an unknown run row omits the amount. The
// decide event is untouched.
import { computed } from 'vue'
import GateDecision from '@kroker/ui/components/gate_decision/GateDecision.vue'
import { useFleetStore } from '../../shared/fleet.store'
import { money } from '../../shared/format'
import type { GateItem, GateOutcome } from '../../api/types'

const props = defineProps<{ item: GateItem; busy: boolean }>()

const emit = defineEmits<{
  (e: 'decide', outcome: GateOutcome, comment: string): void
}>()

// The store is reached lazily, inside the computed: only a budget gate
// needs the run row, and the entry must stay mountable without a pinia
// (the non-budget tests mount it exactly that way).
const budgetNote = computed(() => {
  if (props.item.gate !== 'budget') return null
  const run = useFleetStore().getOrLoad(props.item.runId)
  if (!run || run.budget === null || run.budgetThreshold === null) {
    return 'Approve raises the limit and the run continues. Any other decision ends the run.'
  }
  const raised = money(run.budgetThreshold + run.budget)
  return `Approve raises the limit to ${raised} and the run continues. Any other decision ends the run.`
})
</script>

<template>
  <div class="gate-entry">
    <GateDecision
      :title="`${item.gate} · round ${item.round}`"
      :busy="busy"
      @decide="(d) => emit('decide', d.outcome, d.comment)"
    />
    <p v-if="budgetNote" data-testid="gate-budget-note" class="note">{{ budgetNote }}</p>
  </div>
</template>

<style scoped>
.note {
  margin: 6px 0 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-subtle);
}
</style>
