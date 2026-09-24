<script setup lang="ts">
// The run page (002, R-13): composition ONLY. It renders the run screen's
// view and fills its typed #board slot with the board screen's tab --
// the app layer is the one place features/board is reachable from, so the
// cross-screen rule (R6) stays absolute with no exceptions.
import RunView from '../features/run/RunView.vue'
import BoardTab from '../features/board/BoardTab.vue'

defineProps<{ id: string; tab?: string }>()
</script>

<template>
  <RunView :id="id" :tab="tab">
    <template #board="{ runId, projectKey }">
      <BoardTab :run-id="runId" :project-key="projectKey" />
    </template>
  </RunView>
</template>
