<script setup lang="ts">
// 010 T015: the gate kind (contract §3.3, row 2). Reuses the library's
// GateDecision unchanged — the same control the run canvas offers — and
// adapts its one-object payload to the two-argument decide event of
// data-model §2.5 (the same adaptation as RunView.vue:122). The comment
// lives inside GateDecision and survives refreshes because the v-for key
// is the composite key (research R-7).
import GateDecision from '@kroker/ui/components/gate_decision/GateDecision.vue'
import type { GateItem, GateOutcome } from '../../api/types'

defineProps<{ item: GateItem; busy: boolean }>()

const emit = defineEmits<{
  (e: 'decide', outcome: GateOutcome, comment: string): void
}>()
</script>

<template>
  <GateDecision
    :title="`${item.gate} · round ${item.round}`"
    :busy="busy"
    @decide="(d) => emit('decide', d.outcome, d.comment)"
  />
</template>
