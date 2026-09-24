// T033 (RED): the board store state machine, every data-model section 4
// transition (contracts/board-client.md error contract, R-3). The module
// ./board.store does not exist yet -- every test fails on that import until
// T034 lands it. Timing: the store polls via startPoll with its default
// cadence (baseMs 2000, jitter 0.2), so each poll cycle is advanced by
// >= 2500 ms; failures back off 2x per consecutive miss.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { HttpStatusError } from '../../api/errors'
import type {
  ArtifactVersionWire, BoardArtifactWire, BoardEventWire, BoardTaskWire,
  ProjectDetailWire, TaskDetailWire,
} from './board.types'

const boardApi = vi.hoisted(() => ({
  project: vi.fn(),
  versions: vi.fn(),
  tasks: vi.fn(),
  taskDetail: vi.fn(),
  events: vi.fn(),
}))
// Only the singleton is faked; the pure helpers (pickPlanVersion, boardUrls)
// stay real so the plan pin is exercised through its actual logic.
vi.mock('./board.api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./board.api')>()),
  boardApi,
}))

import { useBoardStore } from './board.store'

const P = 'kroker'
const RUN = 'feature-board'
const OTHER = 'feature-other'
const AT = '2026-09-24T10:00:00Z'

const artifact = (key: string): BoardArtifactWire => ({
  project: P, key, status: 'current', current_version: 2,
})
const DETAIL: ProjectDetailWire = {
  key: P, repo: 'git@example:acme/portal',
  artifacts: [artifact('plan'), artifact('requirements'), artifact('architecture')],
  stats: {
    project: P,
    tasks_by_status: { pending: 0, in_progress: 0, done: 0, failed: 0, blocked: 0, quarantined: 0 },
    total_fix_attempts: 0, tasks_with_error: 0, diverged_tasks: 0, event_count: 0,
  },
}
const ver = (id: number, key: string, run_id: string): ArtifactVersionWire => ({
  id, project: P, key, n: 1, run_id, sha256: 's', uri: 'u', supersedes: null, created_at: AT,
})
const PLAN_VERSIONS = [ver(3, 'plan', OTHER), ver(5, 'plan', RUN)]

const mkTask = (over: Partial<BoardTaskWire> = {}): BoardTaskWire => ({
  project: P, plan_version: 7, task_id: 'T01', run_id: RUN,
  status: 'pending', authoritative_status: 'pending', row_version: 1,
  fix_attempts: 0, error: null, branch: null, updated_at: AT, ...over,
})
const TASKS = [mkTask(), mkTask({ task_id: 'T02', status: 'done' })]

const detailOf = (t: BoardTaskWire): TaskDetailWire => ({
  task: t,
  evidence: [{
    id: 'e1', project: P, plan_version: t.plan_version, task_id: t.task_id,
    run_id: t.run_id, kind: 'qa', sha256: 'x', uri: 'u', created_at: AT,
  }],
})
const EVENTS: BoardEventWire[] = [{
  id: 1, project: P, subject: `task:7:T01`, actor: 'dev', authority: 'board',
  from_status: 'pending', to_status: 'in_progress', at: AT, detail: '',
}]

const RUN_ARG = { runId: RUN, projectKey: P }

const flush = () => vi.advanceTimersByTimeAsync(0)
const advance = (ms: number) => vi.advanceTimersByTimeAsync(ms)

const allVersions = (s: ReturnType<typeof useBoardStore>) =>
  Object.values(s.versions as unknown as Record<string, ArtifactVersionWire[]>).flat()

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  vi.resetAllMocks()
  boardApi.project.mockResolvedValue(DETAIL)
  boardApi.versions.mockImplementation(async (_p: string, key: string) => {
    if (key === 'plan') return PLAN_VERSIONS
    if (key === 'requirements') return [ver(2, key, OTHER), ver(6, key, RUN)]
    if (key === 'architecture') return [ver(9, key, RUN)]
    return []
  })
  boardApi.tasks.mockResolvedValue(TASKS)
  boardApi.taskDetail.mockImplementation(async (_p: string, id: string) =>
    detailOf(TASKS.find((t) => t.task_id === id) ?? TASKS[0]))
  boardApi.events.mockResolvedValue(EVENTS)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('start: the permanent failures', () => {
  it('a run with no project key is unavailable(no_project) with no request made', async () => {
    const s = useBoardStore()
    s.start({ runId: RUN, projectKey: null })
    await flush()
    expect(s.phase).toBe('unavailable')
    expect(s.reason).toBe('no_project')
    expect(boardApi.project).not.toHaveBeenCalled()
    expect(boardApi.versions).not.toHaveBeenCalled()
    expect(boardApi.tasks).not.toHaveBeenCalled()
  })

  it('a step-1 (project) 404 is unavailable(not_found)', async () => {
    boardApi.project.mockRejectedValue(new HttpStatusError(404, 'no project'))
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('unavailable')
    expect(s.reason).toBe('not_found')
  })

  it('a step-3 (tasks) 404 with project and plan reachable is unavailable(not_found)', async () => {
    boardApi.tasks.mockRejectedValue(new HttpStatusError(404, 'no current plan'))
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('unavailable')
    expect(s.reason).toBe('not_found')
  })
})

describe('start: the load and its fallbacks', () => {
  it('a step-2 404 continues to step 3 WITHOUT the plan pin', async () => {
    boardApi.versions.mockImplementation(async (_p: string, key: string) => {
      if (key === 'plan') throw new HttpStatusError(404, 'no plan artifact')
      return [ver(6, key, RUN)]
    })
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('ready')
    expect(s.planVersion).toBeUndefined()
    expect(boardApi.tasks).toHaveBeenCalledWith(P, { runId: RUN })
  })

  it('a step-4 404 on one artifact key skips that key; the load completes', async () => {
    boardApi.versions.mockImplementation(async (_p: string, key: string) => {
      if (key === 'architecture') throw new HttpStatusError(404, 'vanished')
      if (key === 'plan') return PLAN_VERSIONS
      return [ver(6, key, RUN)]
    })
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('ready')
    const vs = allVersions(s)
    expect(vs.every((v) => v.key !== 'architecture')).toBe(true) // skipped
    expect(vs.some((v) => v.key === 'requirements' && v.run_id === RUN)).toBe(true)
  })

  it('a transient 500 during loading keeps loading, flags connectionLost, retries to ready', async () => {
    boardApi.tasks.mockRejectedValue(new HttpStatusError(500, 'down'))
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush() // tick 1 fails
    await advance(5000) // tick 2 fails (backoff 4s)
    await advance(9000) // tick 3 fails (backoff 8s)
    expect(s.phase).toBe('loading')
    expect(s.connectionLost).toBe(true)
    boardApi.tasks.mockResolvedValue(TASKS)
    await advance(20000) // the retry lands (backoff 16s)
    expect(s.phase).toBe('ready')
    expect(s.connectionLost).toBe(false)
  })

  it('an ok load with zero tasks ends empty', async () => {
    boardApi.tasks.mockResolvedValue([])
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('empty')
  })

  it('an ok load ends ready: tasks set, versions run-filtered, plan pinned per pickPlanVersion', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('ready')
    expect(s.tasks).toEqual(TASKS)
    expect(s.planVersion).toBe(5) // id 5 is this run's; id 3 (other run) must not win
    const vs = allVersions(s)
    expect(vs.some((v) => v.run_id === RUN)).toBe(true)
    expect(vs.every((v) => v.run_id === RUN)).toBe(true) // the G5d filter held
  })
})

describe('the poll, once loaded', () => {
  it('a non-404 poll failure keeps phase and data, flags connectionLost; recovery clears it', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    expect(s.phase).toBe('ready')
    boardApi.tasks.mockRejectedValue(new HttpStatusError(500, 'down'))
    await advance(2500)
    await advance(5000)
    await advance(9000)
    expect(s.phase).toBe('ready')
    expect(s.connectionLost).toBe(true)
    expect(s.tasks).toEqual(TASKS) // rendered data is kept
    boardApi.tasks.mockResolvedValue(TASKS)
    await advance(20000)
    expect(s.connectionLost).toBe(false)
  })

  it('a poll-time step-3 404 is permanent: unavailable(not_found)', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    boardApi.tasks.mockRejectedValueOnce(new HttpStatusError(404, 'no current plan'))
    await advance(2500)
    expect(s.phase).toBe('unavailable')
    expect(s.reason).toBe('not_found')
  })
})

describe('stop and selection', () => {
  it('stop() returns to idle, clears the selection, and ends the poll', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(s.selectedTaskId).toBe('T01')
    const calls = boardApi.tasks.mock.calls.length
    s.stop()
    expect(s.phase).toBe('idle')
    expect(s.selectedTaskId).toBeNull()
    await advance(10000)
    expect(boardApi.tasks.mock.calls.length).toBe(calls) // the poll really stopped
  })

  it('select fetches detail (with the pinned plan) and events (subject from the task row)', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(boardApi.taskDetail).toHaveBeenCalledWith(P, 'T01', 5)
    expect(boardApi.events).toHaveBeenCalledWith(P, 'task:7:T01') // task.plan_version, not the pin
    expect(s.selectedDetail?.task.task_id).toBe('T01')
    expect(s.selectedEvents).toHaveLength(1)
  })

  it('a 404 on the selected detail clears the selection', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    boardApi.taskDetail.mockRejectedValueOnce(new HttpStatusError(404, 'vanished'))
    s.select('T01')
    await flush()
    expect(s.selectedTaskId).toBeNull()
  })

  it('a poll that bumps the selected task row_version refreshes its detail', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(boardApi.taskDetail).toHaveBeenCalledTimes(1)
    boardApi.tasks.mockResolvedValue([
      mkTask({ row_version: 2, status: 'in_progress' }),
      TASKS[1],
    ])
    await advance(2500)
    expect(boardApi.taskDetail).toHaveBeenCalledTimes(2)
  })
})

// T033 companion (RED): the three non-transition contracts' uncovered
// edges -- stop() clearing the selection DATA (the poll-stop itself is
// pinned above), the events half of the selection failure modes, and the
// row_version refresh's negative case plus its events half.

describe('stop(): the selection data', () => {
  it('clears selectedDetail and selectedEvents, not just the id', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(s.selectedDetail).toBeTruthy() // something to clear
    s.stop()
    expect(s.phase).toBe('idle')
    expect(s.selectedTaskId).toBeNull()
    expect(s.selectedDetail == null).toBe(true)
    expect((s.selectedEvents ?? []).length).toBe(0)
  })
})

describe('selection failure modes (chaos half)', () => {
  it('a 404 on the selected EVENTS also clears the selection', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(s.selectedTaskId).toBe('T01')
    boardApi.events.mockRejectedValueOnce(new HttpStatusError(404, 'vanished'))
    s.select('T01')
    await flush()
    expect(s.selectedTaskId).toBeNull()
  })

  it('a non-404 failure while switching selection keeps the PRIOR task selected', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(s.selectedTaskId).toBe('T01')
    boardApi.taskDetail.mockRejectedValueOnce(new HttpStatusError(500, 'down'))
    s.select('T02')
    await flush()
    // "keep prior selection data": the failed switch leaves everything as it was
    expect(s.selectedTaskId).toBe('T01')
    expect(s.selectedDetail?.task.task_id).toBe('T01')
    expect(s.connectionLost).toBe(true)
  })
})

describe('selected-task refresh (row_version, chaos half)', () => {
  it('an unchanged row_version does NOT refetch detail or events', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    const details = boardApi.taskDetail.mock.calls.length
    const eventCalls = boardApi.events.mock.calls.length
    boardApi.tasks.mockResolvedValue(TASKS) // same rows, same row_version
    await advance(2500)
    expect(boardApi.taskDetail.mock.calls.length).toBe(details)
    expect(boardApi.events.mock.calls.length).toBe(eventCalls)
  })

  it('a changed row_version refetches BOTH detail and events in the background', async () => {
    const s = useBoardStore()
    s.start(RUN_ARG)
    await flush()
    s.select('T01')
    await flush()
    expect(boardApi.taskDetail).toHaveBeenCalledTimes(1)
    expect(boardApi.events).toHaveBeenCalledTimes(1)
    boardApi.tasks.mockResolvedValue([
      mkTask({ row_version: 2, status: 'in_progress' }),
      TASKS[1],
    ])
    await advance(2500)
    expect(boardApi.taskDetail).toHaveBeenCalledTimes(2)
    expect(boardApi.events).toHaveBeenCalledTimes(2)
  })
})
