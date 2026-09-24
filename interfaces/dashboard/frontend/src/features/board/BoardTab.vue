<script setup lang="ts">
// The Board tab (002, FR-021..FR-024, R-13): rendered inside RunView's
// #board slot by app/RunPage.vue. Owns the board store's lifecycle --
// start on mount, stop on unmount, restart when the run's project changes
// (FR-023). Read-only: the store exposes no write path and this view adds
// none (FR-024). All mapping goes through the pure board.adapter.
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import DetailPane from '@kroker/ui/components/detail_pane/DetailPane.vue'
import DetailSection from '@kroker/ui/components/detail_pane/DetailSection.vue'
import ListRow from '@kroker/ui/components/list_row/ListRow.vue'
import Stat from '@kroker/ui/components/stat/Stat.vue'
import StatusTag from '@kroker/ui/components/status_tag/StatusTag.vue'
import Timeline from '@kroker/ui/components/timeline/Timeline.vue'
import { toCounters, toTaskDetail, toTaskRow, toTimeline, toVersionRows } from './board.adapter'
import type { VersionRow } from './board.adapter'
import { useBoardStore } from './board.store'

const props = defineProps<{ runId: string; projectKey: string | null }>()
const board = useBoardStore()

onMounted(() => board.start({ runId: props.runId, projectKey: props.projectKey }))
onBeforeUnmount(() => board.stop())
watch(
  () => [props.runId, props.projectKey] as const,
  ([runId, projectKey]) => board.start({ runId, projectKey }),
)

const rows = computed(() => board.tasks.map(toTaskRow))
const counters = computed(() => toCounters(board.tasks))
const detail = computed(() => (board.selectedDetail ? toTaskDetail(board.selectedDetail) : null))
const timeline = computed(() => toTimeline(board.selectedEvents ?? []))
const versionRows = computed<VersionRow[]>(() => {
  const out: VersionRow[] = []
  for (const list of Object.values(board.versions)) out.push(...toVersionRows(list, props.runId))
  return out.sort((a, b) => b.id - a.id) // newest surrogate id first, across keys
})
</script>

<template>
  <section data-testid="board-tab" class="board">
    <!-- FR-022/FR-023a: the two permanent banners and the transient line.
         Only these conditions produce a banner; everything else renders. -->
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

      <div class="strip" data-testid="board-counters">
        <Stat v-for="c in counters" :key="c.label" :label="c.label" :value="c.value" :pip="c.pip" />
      </div>

      <div class="cols">
        <div class="list" data-testid="board-task-list">
          <ListRow
            v-for="r in rows"
            :key="r.key"
            :selected="r.key === board.selectedTaskId"
            :dense="true"
            @select="board.select(r.key)"
          >
            <span class="task-id">{{ r.label }}</span>
            <template #meta>
              <StatusTag :kind="r.status.kind" :pulsing="r.status.pulsing" />
              <span v-if="r.diverged" class="meta diverged">diverged</span>
              <span v-if="r.fixAttempts > 0" class="meta">fix ×{{ r.fixAttempts }}</span>
              <span v-if="r.hasError" class="meta error">{{ board.tasks.find((t) => t.task_id === r.key)?.error }}</span>
            </template>
          </ListRow>
        </div>

        <div class="side">
          <div v-if="detail" data-testid="board-detail">
            <DetailPane :eyebrow="detail.eyebrow" :title="detail.title" :fields="detail.fields">
              <DetailSection v-if="detail.evidence.length" label="Evidence">
                <p v-for="e in detail.evidence" :key="e.uri" class="evidence">
                  <span class="kind">{{ e.kind }}</span> {{ e.uri }}
                </p>
              </DetailSection>
              <DetailSection label="Timeline">
                <Timeline :items="timeline">
                  <template #empty>no events recorded for this task.</template>
                </Timeline>
              </DetailSection>
            </DetailPane>
          </div>

          <div class="versions" data-testid="board-versions">
            <DetailSection label="Artifact versions (this run)">
              <li v-for="v in versionRows" :key="`${v.key}-${v.id}`" class="version">
                <span class="vid">{{ v.key }}#{{ v.n }}</span>
                <span class="sha">{{ v.sha256 }}</span>
              </li>
              <p v-if="!versionRows.length" class="none">no versions published by this run.</p>
            </DetailSection>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.board { display: flex; flex-direction: column; flex: 1; min-height: 0; gap: 12px; }
.banner { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.strip { display: flex; flex-wrap: wrap; gap: var(--space-4); padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px; }
.cols { display: flex; gap: 16px; flex: 1; min-height: 0; align-items: flex-start; }
.list { flex: 1 1 55%; display: flex; flex-direction: column; gap: 2px; overflow: auto; min-height: 0; }
.side { flex: 1 1 45%; display: flex; flex-direction: column; gap: 16px; min-width: 0; overflow: auto; min-height: 0; }
.task-id { font-family: var(--font-mono); font-size: 12px; }
.meta { font-family: var(--font-mono); font-size: 11px; color: var(--ink-muted); }
.meta.diverged { color: var(--status-waiting); }
.meta.error { color: var(--status-failed); }
.evidence { margin: 0; font-family: var(--font-mono); font-size: 11px; color: var(--ink-secondary); overflow-wrap: anywhere; }
.evidence .kind { color: var(--ink-muted); }
.version { display: flex; gap: 12px; font-family: var(--font-mono); font-size: 11px; list-style: none; }
.version .sha { color: var(--ink-muted); overflow-wrap: anywhere; }
.none { margin: 0; color: var(--ink-subtle); font-family: var(--font-mono); font-size: 11px; }
</style>
