<script setup lang="ts">
import { useUiStore } from '../stores/ui'
import { useFleetStore } from '../stores/fleet'
import StartRunModal, { type StartRunPayload } from '@kroker/ui/components/start_run_modal/StartRunModal.vue'

const ui = useUiStore()
const fleet = useFleetStore()

async function onSubmit(payload: StartRunPayload) {
  const r = await fleet.startRun({
    title: payload.title,
    description: '',
    repo: payload.repo,
    mode: payload.mode,
  })
  ui.toast(`Run started — ${r.id}`, '#5b9dd9')
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
    @submit="onSubmit"
    @invalid="onInvalid"
    @close="ui.closeStart()"
  />
</template>
