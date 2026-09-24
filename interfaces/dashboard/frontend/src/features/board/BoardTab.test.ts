// T038 (RED): BoardTab, the board screen (FR-019..FR-024, R-11, R-13,
// data-model §3–§4). BoardTab.vue does not exist yet -- every test here
// fails on that import until T039 lands it. The store is NOT mocked: the
// tests drive it through the './board.api' fake (same vi.hoisted +
// importOriginal pattern as board.store.test.ts, so the pure helpers stay
// real) and settle with fake-timer microtask drains. The poll keeps running
// during a test -- that is fine; only the unmount test freezes its count.
//
// TESTID CONTRACT (T039 builds to this; ported components' own stable
// testids/classes are reused wherever they exist):
//   [data-testid="board-tab"]            the component root
//   [data-testid="board-banner-no-project"]  projectKey null banner; text says "no board"
//   [data-testid="board-banner-not-found"]   project/tasks 404 banner; text says "not found"
//   [data-testid="board-connection-lost"]    transient-failure line; text says "connection lost"
//   [data-testid="board-empty"]              explicit empty line (zero tasks)
//   [data-testid="board-counters"]           the Stat strip; each Stat is `.cmp-stat` (label+value)
//   [data-testid="board-task-list"]          the task list; rows are ListRow `[data-testid="list-row"]`
//   [data-testid="board-detail"]             DetailPane region (`.cmp-detail-pane`, `.title`, `detail-fields`)
//   [data-testid="board-versions"]           version rows, newest surrogate id first, sha text visible
//   row meta text                            a diverged task's row names "diverged"; an errored row shows its error string
//   selection                                the selected ListRow carries ListRow's own `is-selected` class
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
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
vi.mock('./board.api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./board.api')>()),
  boardApi,
}))

import BoardTab from './BoardTab.vue'

const P = 'kroker'
const RUN = 'feature-board'
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
  id, project: P, key, n: 1, run_id, sha256: `s${id}`, uri: `u${id}`, supersedes: null, created_at: AT,
})

const mkTask = (over: Partial<BoardTaskWire> = {}): BoardTaskWire => ({
  project: P, plan_version: 7, task_id: 'T01', run_id: RUN,
  status: 'pending', authoritative_status: 'pending', row_version: 1,
  fix_attempts: 0, error: null, branch: null, updated_at: AT, ...over,
})
const TASKS = [
  mkTask(),
  mkTask({ task_id: 'T02', status: 'in_progress', authoritative_status: 'done', fix_attempts: 2, error: 'boom' }),
  mkTask({ task_id: 'T03', status: 'done', authoritative_status: 'done' }),
  mkTask({ task_id: 'T04', status: 'failed', authoritative_status: 'failed', error: 'late failure' }),
]

const detailOf = (t: BoardTaskWire): TaskDetailWire => ({
  task: t,
  evidence: [{
    id: 'e1', project: P, plan_version: t.plan_version, task_id: t.task_id,
    run_id: t.run_id, kind: 'qa', sha256: 'x', uri: 'file://evidence/qa', created_at: AT,
  }],
})
const EVENTS: BoardEventWire[] = [
  {
    id: 1, project: P, subject: 'task:7:T01', actor: 'dev', authority: 'board',
    from_status: 'pending', to_status: 'in_progress', at: AT, detail: 'picked up',
  },
  {
    id: 2, project: P, subject: 'task:7:T01', actor: 'qa', authority: 'board',
    from_status: 'in_progress', to_status: 'done', at: `${AT}Z`.replace('Z', '5Z'), detail: 'passed',
  },
]

const settle = async () => {
  for (let i = 0; i < 5; i++) await vi.advanceTimersByTimeAsync(0)
}

const mountBoard = async (projectKey: string | null = P) => {
  const w = mount(BoardTab, { props: { runId: RUN, projectKey } })
  await settle()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
  vi.resetAllMocks()
  boardApi.project.mockResolvedValue(DETAIL)
  boardApi.versions.mockImplementation(async (_p: string, key: string) => {
    if (key === 'plan') return [ver(3, key, 'feature-other'), ver(5, key, RUN)]
    if (key === 'requirements') return [ver(6, key, RUN)]
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

describe('BoardTab lifecycle', () => {
  it('mounting starts the store; unmounting stops the poll for good', async () => {
    const w = await mountBoard()
    expect(boardApi.project).toHaveBeenCalledWith(P)
    expect(boardApi.tasks).toHaveBeenCalled()
    w.unmount()
    await settle()
    await vi.advanceTimersByTimeAsync(30000)
    const projectCalls = boardApi.project.mock.calls.length
    const taskCalls = boardApi.tasks.mock.calls.length
    await vi.advanceTimersByTimeAsync(30000)
    expect(boardApi.project.mock.calls.length).toBe(projectCalls)
    expect(boardApi.tasks.mock.calls.length).toBe(taskCalls)
  })

  it('a projectKey change restarts against the new key', async () => {
    const w = await mountBoard()
    expect(boardApi.project).toHaveBeenCalledWith(P)
    await w.setProps({ projectKey: 'kroker2' })
    await settle()
    expect(boardApi.project).toHaveBeenCalledWith('kroker2')
    // the mock's plan versions pin id 5 for RUN, so step 3 carries the pin
    expect(boardApi.tasks).toHaveBeenCalledWith('kroker2', { runId: RUN, plan: 5 })
  })
})

describe('the task list', () => {
  it('renders one ListRow per task, label = task id, with status tags', async () => {
    const w = await mountBoard()
    const rows = w.findAll('[data-testid="board-task-list"] [data-testid="list-row"]')
    expect(rows).toHaveLength(TASKS.length)
    for (const t of TASKS) {
      expect(rows.find((r) => r.text().includes(t.task_id)), t.task_id).toBeDefined()
    }
    expect(w.find('[data-testid="board-task-list"] .cmp-status-tag-in_progress').exists()).toBe(true)
  })

  it('a diverged task and an errored task are distinguishable in their row text', async () => {
    const w = await mountBoard()
    const rows = w.findAll('[data-testid="board-task-list"] [data-testid="list-row"]')
    const diverged = rows.find((r) => r.text().includes('T02'))!
    expect(diverged).toBeDefined()
    expect(diverged.text()).toContain('diverged')
    expect(diverged.text()).toContain('boom') // the error string is visible
    const errored = rows.find((r) => r.text().includes('T04'))!
    expect(errored.text()).toContain('late failure')
    const clean = rows.find((r) => r.text().includes('T03'))!
    expect(clean.text()).not.toContain('diverged')
  })
})

describe('selection', () => {
  it('clicking a row shows DetailPane fields, an evidence section and a timeline', async () => {
    const w = await mountBoard()
    await w.findAll('[data-testid="list-row"]').find((r) => r.text().includes('T01'))!.trigger('click')
    await settle()
    const pane = w.find('[data-testid="board-detail"]')
    expect(pane.exists()).toBe(true)
    expect(pane.find('.title').text()).toBe('T01')
    expect(pane.findAll('[data-testid="detail-fields"] [data-testid="detail-value"]').length).toBeGreaterThan(0)
    const sections = pane.findAll('.cmp-detail-section')
    expect(sections.some((s) => s.find('.label').text().toLowerCase().includes('evidence'))).toBe(true)
    expect(pane.text()).toContain('file://evidence/qa')
    expect(w.findAll('[data-testid="timeline-entry"]').length).toBe(EVENTS.length)
    const selected = w.findAll('[data-testid="list-row"]').find((r) => r.text().includes('T01'))!
    expect(selected.classes()).toContain('is-selected')
  })
})

describe('versions and counters', () => {
  it('renders this run\'s versions newest-surrogate-id first', async () => {
    const w = await mountBoard()
    const rows = w.findAll('[data-testid="board-versions"] [data-testid="list-row"], [data-testid="board-versions"] li')
    expect(rows.length).toBe(3) // s5 (plan), s6 (requirements), s9 (architecture)
    expect(w.find('[data-testid="board-versions"]').text()).toContain('s9')
    expect(w.find('[data-testid="board-versions"]').text()).toContain('s5')
  })

  it("the counter strip is all 'this run' with per-status counts", async () => {
    const w = await mountBoard()
    const strip = w.find('[data-testid="board-counters"]')
    expect(strip.exists()).toBe(true)
    expect(strip.text()).toContain('this run')
    const stats = strip.findAll('.cmp-stat')
    expect(stats.length).toBeGreaterThan(0)
    const statValue = (labelPart: string) =>
      stats.find((s) => s.text().toLowerCase().includes(labelPart))
        ?.find('[data-testid="stat-value"]').text()
    expect(statValue('pending')).toBe('1')
    expect(statValue('in progress')).toBe('1')
    expect(statValue('done')).toBe('1')
    expect(statValue('failed')).toBe('1')
    expect(statValue('fix attempts')).toBe('2') // T02 only
    expect(statValue('error')).toBe('2') // T02, T04
    expect(statValue('diverged')).toBe('1') // T02
  })
})

describe('the banners and the empty state (FR-022, FR-023a, SC-006)', () => {
  it('projectKey null shows the no-project banner and makes no request', async () => {
    const w = await mountBoard(null)
    const banner = w.find('[data-testid="board-banner-no-project"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('no board')
    expect(boardApi.project).not.toHaveBeenCalled()
  })

  it('a project 404 shows the not-found banner', async () => {
    boardApi.project.mockRejectedValue(new HttpStatusError(404, 'board: no project'))
    const w = await mountBoard()
    const banner = w.find('[data-testid="board-banner-not-found"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('not found')
  })

  it('zero tasks shows the explicit empty line and zeroed counters', async () => {
    boardApi.tasks.mockResolvedValue([])
    const w = await mountBoard()
    expect(w.find('[data-testid="board-empty"]').exists()).toBe(true)
    for (const stat of w.findAll('[data-testid="board-counters"] .cmp-stat')) {
      expect(stat.find('[data-testid="stat-value"]').text()).toBe('0')
    }
  })

  it('a transient failure shows connection lost; recovery clears it', async () => {
    const w = await mountBoard()
    expect(w.find('[data-testid="board-connection-lost"]').exists()).toBe(false)
    boardApi.tasks.mockRejectedValue(new HttpStatusError(500, 'down'))
    // worst-case jittered cadence: poll1 <=2.4s, poll2 <=7.2s, poll3 <=16.8s
    // (the 3rd consecutive miss reports connectionLost)
    await vi.advanceTimersByTimeAsync(5000) // poll 1-2 fail
    await vi.advanceTimersByTimeAsync(20000) // poll 3 fails -> onFailures(3)
    await settle()
    const lost = w.find('[data-testid="board-connection-lost"]')
    expect(lost.exists()).toBe(true)
    expect(lost.text()).toContain('connection lost')
    boardApi.tasks.mockResolvedValue(TASKS)
    await vi.advanceTimersByTimeAsync(20000) // the retry lands
    await settle()
    expect(w.find('[data-testid="board-connection-lost"]').exists()).toBe(false)
  })
})
