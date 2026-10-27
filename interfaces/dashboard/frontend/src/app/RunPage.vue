<script setup lang="ts">
// The run page (002, R-13; 018 T032): composition ONLY. It renders the run
// screen's view and fills its typed #board slot with the board screen's
// tab -- the app layer is the one place features/board is reachable from,
// so the cross-screen rule (R6) stays absolute. The Cost tab is retired
// into the rail (S3): RunView renders it; no cost slot exists.
import RunView from '../features/run/RunView.vue'
import BoardTab from '../features/board/BoardTab.vue'

defineProps<{ id: string; tab?: string; rail?: string }>()
</script>

<template>
  <RunView :id="id" :tab="tab" :rail="rail">
    <template #board="{ runId, projectKey }">
      <BoardTab :run-id="runId" :project-key="projectKey" />
    </template>
  </RunView>
</template>
