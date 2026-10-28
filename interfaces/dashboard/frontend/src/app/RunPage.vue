<script setup lang="ts">
// The run page (002, R-13; 018 T032): composition ONLY. It renders the run
// screen's view and fills its typed #board slot with the board screen's
// tab -- the app layer is the one place features/board is reachable from,
// so the cross-screen rule (R6) stays absolute. The Cost tab is retired
// into the rail (S3): RunView renders it; no cost slot exists.
import { watch } from 'vue'
import RunView from '../features/run/RunView.vue'
import BoardTab from '../features/board/BoardTab.vue'
import { usePrefsStore } from './prefs.store'

const props = defineProps<{ id: string; tab?: string; rail?: string }>()

// 018 T050 (S16/CONSOLE-53): opening a run makes it the run in context —
// the fleet's Open-run label and the header commands follow it.
const prefs = usePrefsStore()
watch(
  () => props.id,
  (id) => {
    prefs.runInContext = id
  },
  { immediate: true },
)
</script>

<template>
  <RunView :id="id" :tab="tab" :rail="rail">
    <template #board="{ runId, projectKey }">
      <BoardTab :run-id="runId" :project-key="projectKey" />
    </template>
  </RunView>
</template>
