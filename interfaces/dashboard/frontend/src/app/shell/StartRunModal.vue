<script setup lang="ts">
import { useUiStore } from '../ui.store'
import { useFleetStore } from '../../shared/fleet.store'
import StartRunModal, { type StartRunPayload } from '@kroker/ui/components/start_run_modal/StartRunModal.vue'

const ui = useUiStore()
const fleet = useFleetStore()

async function onSubmit(payload: StartRunPayload) {
  // 011 US2: the library emits trimmed text; the wire wants a number or
  // nothing. The library already blocked what cannot stand, so the empty
  // string is the only "no budget" case here.
  const budget = payload.budget === '' ? null : Number(payload.budget)
  const r = await fleet.startRun({
    title: payload.title,
    description: '',
    repo: payload.repo,
    mode: payload.mode,
    budget,
  })
  ui.toast(`Run started — ${r.id}`, '#5b9dd9')
  // FR-009: when a budget was given the server says what it counts.
  if (r.budgetNotice) ui.toast(r.budgetNotice, '#e0b050')
  ui.resetStartForm()
  ui.closeStart()
}

function onInvalid() {
  ui.toast('Title required', '#e0b050')
}
</script>

<template>
  <StartRunModal
    :open="ui.startOpen"
    :initial-title="ui.startTitle"
    :initial-repo="ui.startRepo"
    :initial-mode="ui.startMode"
    :initial-budget="ui.startBudget"
    @submit="onSubmit"
    @invalid="onInvalid"
    @close="ui.closeStart()"
  />
</template>
