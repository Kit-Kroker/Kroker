// The board state machine (002, data-model section 4; FR-021..FR-024).
// One startPoll chain per mount: the INITIAL load (steps 1-4) runs inside
// the poll loop until it first succeeds, so a transient failure during
// loading retries with the poll's own backoff instead of leaving an
// unhandled rejection. After the first success only step 3 (tasks) polls,
// plus the selected task's background refresh when its row_version moves.
// 404 is the only permanent failure, and only on steps 1 and 3 (R-3);
// step-2 404 drops the plan pin, step-4 404 skips a key. Read-only (FR-024).
import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import { isNotFound } from '../../api/errors'
import { startPoll } from '../../api/poll'
import { boardApi, pickPlanVersion } from './board.api'
import type {
  ArtifactVersionWire, BoardEventWire, BoardTaskWire, ProjectDetailWire, TaskDetailWire,
} from './board.types'

export type BoardPhase = 'idle' | 'loading' | 'ready' | 'empty' | 'unavailable'
export type BoardReason = 'no_project' | 'not_found' | null

export interface BoardRun {
  runId: string
  projectKey: string | null
}

export const useBoardStore = defineStore('board', () => {
  const phase = ref<BoardPhase>('idle')
  const reason = ref<BoardReason>(null)
  const connectionLost = ref(false)
  const tasks = ref<BoardTaskWire[]>([])
  /** G5d: per artifact key, only THIS run's versions. */
  const versions = ref<Record<string, ArtifactVersionWire[]>>({})
  /** FR-021a: the pinned plan version id, undefined = run published none. */
  const planVersion = ref<number | undefined>(undefined)
  const selectedTaskId = ref<string | null>(null)
  const selectedDetail = shallowRef<TaskDetailWire | null>(null)
  const selectedEvents = ref<BoardEventWire[]>([])

  let cancelPoll: (() => void) | null = null
  let generation = 0
  let loadedOnce = false
  let run: { runId: string; projectKey: string } | null = null
  let selectedRowVersion = 0

  function stop() {
    generation += 1
    cancelPoll?.()
    cancelPoll = null
    loadedOnce = false
    run = null
    selectedRowVersion = 0
    phase.value = 'idle'
    reason.value = null
    connectionLost.value = false
    tasks.value = []
    versions.value = {}
    planVersion.value = undefined
    selectedTaskId.value = null
    selectedDetail.value = null
    selectedEvents.value = []
  }

  function permanentNotFound() {
    phase.value = 'unavailable'
    reason.value = 'not_found'
    cancelPoll?.()
    cancelPoll = null
  }

  /** Steps 1-4. A throw (non-404) bubbles to the poll's backoff; 404 on
   * steps 1/3 is permanent and handled here, never retried. */
  async function loadInitial(signal: AbortSignal): Promise<void> {
    const { runId, projectKey } = run!
    let detail: ProjectDetailWire
    try {
      detail = await boardApi.project(projectKey) // step 1
    } catch (e) {
      if (isNotFound(e)) return permanentNotFound()
      throw e
    }
    if (signal.aborted) return
    let plan: number | undefined
    try {
      const planVersions = await boardApi.versions(projectKey, 'plan') // step 2
      plan = pickPlanVersion(planVersions, runId)?.id
    } catch (e) {
      if (!isNotFound(e)) throw e // a 404 here just drops the pin (step 3 decides)
    }
    if (signal.aborted) return
    let rows: BoardTaskWire[]
    try {
      rows = await boardApi.tasks(projectKey, plan !== undefined ? { runId, plan } : { runId }) // step 3
    } catch (e) {
      if (isNotFound(e)) return permanentNotFound()
      throw e
    }
    const byKey: Record<string, ArtifactVersionWire[]> = {}
    for (const a of detail.artifacts) {
      if (signal.aborted) return
      try {
        const vs = await boardApi.versions(projectKey, a.key) // step 4
        byKey[a.key] = vs.filter((v) => v.run_id === runId)
      } catch (e) {
        if (isNotFound(e)) continue // the key vanished: skip it
        throw e
      }
    }
    if (signal.aborted) return
    planVersion.value = plan
    tasks.value = rows
    versions.value = byKey
    loadedOnce = true
    phase.value = rows.length === 0 ? 'empty' : 'ready'
  }

  /** The poll once loaded: step 3 only. */
  async function pollTasks(signal: AbortSignal): Promise<void> {
    const { runId, projectKey } = run!
    const plan = planVersion.value
    let rows: BoardTaskWire[]
    try {
      rows = await boardApi.tasks(projectKey, plan !== undefined ? { runId, plan } : { runId })
    } catch (e) {
      if (isNotFound(e)) return permanentNotFound()
      throw e
    }
    if (signal.aborted) return
    tasks.value = rows
    phase.value = rows.length === 0 ? 'empty' : 'ready'
    const id = selectedTaskId.value
    const row = id !== null ? rows.find((t) => t.task_id === id) : undefined
    if (id !== null && row && row.row_version !== selectedRowVersion) {
      void refreshSelection(row)
    }
  }

  async function fetchSelection(row: BoardTaskWire): Promise<void> {
    const { projectKey } = run!
    const mine = generation
    const subject = `task:${row.plan_version}:${row.task_id}` // the ROW's plan, not the pin
    const [detail, events] = await Promise.all([
      boardApi.taskDetail(projectKey, row.task_id, planVersion.value),
      boardApi.events(projectKey, subject),
    ])
    // A stop() (or restart) while in flight must not repopulate dead state.
    if (mine !== generation) return
    selectedDetail.value = detail
    selectedEvents.value = events
    selectedRowVersion = detail.task.row_version
  }

  async function refreshSelection(row: BoardTaskWire): Promise<void> {
    try {
      await fetchSelection(row)
    } catch {
      // Background refresh: a miss here never evicts rendered data; the
      // next poll's own reporting covers transient loss.
    }
  }

  async function select(taskId: string): Promise<void> {
    if (!run) return
    const row = tasks.value.find((t) => t.task_id === taskId)
    if (!row) return
    const priorId = selectedTaskId.value
    const priorDetail = selectedDetail.value
    const priorEvents = selectedEvents.value
    selectedTaskId.value = taskId
    try {
      await fetchSelection(row)
    } catch (e) {
      if (isNotFound(e)) {
        // the selected task vanished: clear the selection
        selectedTaskId.value = null
        selectedDetail.value = null
        selectedEvents.value = []
      } else {
        // transient while switching: keep the PRIOR selection data
        selectedTaskId.value = priorId
        selectedDetail.value = priorDetail
        selectedEvents.value = priorEvents
        connectionLost.value = true
      }
    }
  }

  function start(boardRun: BoardRun): void {
    stop()
    const mine = generation
    if (boardRun.projectKey === null) {
      // FR-020a: null is an explicit absent value -- banner, no request.
      phase.value = 'unavailable'
      reason.value = 'no_project'
      return
    }
    run = { runId: boardRun.runId, projectKey: boardRun.projectKey }
    phase.value = 'loading'
    reason.value = null
    connectionLost.value = false
    cancelPoll = startPoll(
      async (signal): Promise<{ kind: 'value'; value: void } | { kind: 'stop' }> => {
        if (mine !== generation) return { kind: 'stop' }
        const dead = (): boolean => phase.value === 'unavailable' as BoardPhase
        if (dead()) return { kind: 'stop' }
        if (!loadedOnce) {
          await loadInitial(signal)
        } else {
          await pollTasks(signal)
        }
        if (mine !== generation || dead()) return { kind: 'stop' }
        return { kind: 'value', value: undefined }
      },
      () => {},
      (failures) => {
        if (mine === generation) connectionLost.value = failures > 0
      },
    )
  }

  return {
    phase, reason, connectionLost, tasks, versions, planVersion,
    selectedTaskId, selectedDetail, selectedEvents,
    start, stop, select,
  }
})
