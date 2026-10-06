<script setup lang="ts">
// The run page (002, R-13): composition ONLY. It renders the run screen's
// view and fills its typed #board and #cost slots with the board and cost
// screens' tabs -- the app layer is the one place features/board and
// features/cost are reachable from, so the cross-screen rule (R6) stays
// absolute with no exceptions.
import RunView from '../features/run/RunView.vue'
import BoardTab from '../features/board/BoardTab.vue'
import CostTab from '../features/cost/CostTab.vue'

defineProps<{ id: string; tab?: string }>()
</script>

<template>
  <RunView :id="id" :tab="tab">
    <template #board="{ runId, projectKey }">
      <BoardTab :run-id="runId" :project-key="projectKey" />
    </template>
    <template #cost="{ runId }">
      <CostTab :run-id="runId" />
    </template>
  </RunView>
</template>
