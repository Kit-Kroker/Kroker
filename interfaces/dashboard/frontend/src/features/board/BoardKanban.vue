<script setup lang="ts">
// 018 T054 (S7, V7; FR-023): the run's Board tab is the v5 kanban over the
// same board store — identical lifecycle (start on mount, stop on unmount,
// restart when the run's project changes), the same banners and the same
// empty state as the full board. The footer link opens the full Agent
// Board at /runs/:id/board. Read-only (FR-024).
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import Kanban from '@kroker/ui/components/kanban/Kanban.vue'
import { kanbanOf } from './kanban.adapter'
import { useBoardStore } from './board.store'

const props = defineProps<{ runId: string; projectKey: string | null }>()
const board = useBoardStore()

onMounted(() => board.start({ runId: props.runId, projectKey: props.projectKey }))
onBeforeUnmount(() => board.stop())
watch(
  () => [props.runId, props.projectKey] as const,
  ([runId, projectKey]) => board.start({ runId, projectKey }),
)

const columns = computed(() => kanbanOf(board.tasks))
</script>

<template>
  <section data-testid="board-kanban" class="kanban-tab">
    <!-- The store's banners and empty state, reused verbatim (T054). -->
    <p v-if="board.reason === 'no_project'" class="banner" data-testid="board-banner-no-project">
      no board for this run — the run's project is unknown.
    </p>
    <p v-else-if="board.reason === 'not_found'" class="banner" data-testid="board-banner-not-found">
      board not found for this project — it may not exist or has no current plan.
    </p>
    <p v-if="board.connectionLost" class="banner" data-testid="board-connection-lost">connection lost — retrying</p>

    <template v-if="board.phase === 'ready' || board.phase === 'empty'">
      <div v-if="board.phase === 'empty'" class="banner" data-testid="board-empty">
        no board tasks for this run yet.
      </div>
      <Kanban
        v-else
        :columns="columns"
        :link="{ label: 'Open full Agent Board →', to: `/runs/${runId}/board` }"
      />
    </template>
  </section>
</template>

<style scoped>
.kanban-tab { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 12px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
</style>
