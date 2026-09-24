// T029 (RED): the board transport contract (contracts/board-client.md steps
// 1-6, FR-021, G4/G5). The module ./board.api does not exist yet -- every
// test here fails on that import until T030 lands it. URL shapes are
// asserted as exact encoded strings, so any correct encoding satisfies them
// and any guess-the-default or missing encodeURIComponent fails.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { boardUrls, pickPlanVersion, createHttpBoardApi, createMockBoardApi } from './board.api'
import { HttpStatusError, isNotFound } from '../../api/errors'

const enc = encodeURIComponent

describe('boardUrls (steps 1-6)', () => {
  it('URL-encodes the project key into the project path (step 1)', () => {
    expect(boardUrls('team kroker').project).toBe(`/projects/${enc('team kroker')}`)
  })

  it('builds the tasks URL with an encoded run_id and the pinned plan (step 3)', () => {
    expect(boardUrls('kroker', { runId: 'feature x', plan: 7 }).tasks).toBe(
      `/projects/kroker/tasks?run_id=${enc('feature x')}&plan=7`,
    )
  })

  it('omits the plan query when no plan version is pinned (step-2 404 fallback)', () => {
    expect(boardUrls('kroker', { runId: 'r1' }).tasks).toBe('/projects/kroker/tasks?run_id=r1')
  })

  it('builds the task detail URL with an encoded task id and optional plan (step 5)', () => {
    expect(boardUrls('kroker', { taskId: 'T07#1', plan: 7 }).taskDetail).toBe(
      `/projects/kroker/tasks/${enc('T07#1')}?plan=7`,
    )
  })

  it('builds the events URL with the subject encoded, colons included (step 6)', () => {
    expect(boardUrls('kroker', { subject: 'task:42:T07#1' }).events).toBe(
      `/projects/kroker/events?subject=${enc('task:42:T07#1')}`,
    )
  })

  it('builds the per-key versions URL (step 4)', () => {
    expect(boardUrls('team kroker', { key: 'graph yaml' }).versions).toBe(
      `/projects/${enc('team kroker')}/artifacts/${enc('graph yaml')}`,
    )
  })
})

describe('pickPlanVersion (FR-021a)', () => {
  const v = (id: number, n: number, run_id: string) => ({ id, n, run_id })

  it('picks the newest id with a matching run_id, not the biggest n', () => {
    expect(pickPlanVersion([v(5, 9, 'r1'), v(8, 2, 'r1')], 'r1')?.id).toBe(8)
  })

  it('ignores a wrong-run version even with a much bigger n', () => {
    expect(pickPlanVersion([v(10, 1, 'r1'), v(4, 99, 'r2')], 'r1')?.id).toBe(10)
  })

  it('returns undefined when no version belongs to the run', () => {
    expect(pickPlanVersion([v(4, 1, 'r2')], 'r1')).toBeUndefined()
  })
})

describe('createHttpBoardApi error classification', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('rejects with an HttpStatusError a 404 registers as (isNotFound true)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('gone', { status: 404 })))
    const api = createHttpBoardApi('')
    const e = await api.tasks('kroker', { runId: 'r1' }).catch((x: unknown) => x)
    expect(e).toBeInstanceOf(HttpStatusError)
    expect(isNotFound(e)).toBe(true)
  })

  it('rejects on a 500 too, but isNotFound is false (transient, FR-023a)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })))
    const api = createHttpBoardApi('')
    const e = await api.tasks('kroker', { runId: 'r1' }).catch((x: unknown) => x)
    expect(e).toBeInstanceOf(HttpStatusError)
    expect(isNotFound(e)).toBe(false)
  })

  it('requests the built step-3 URL from the given base', async () => {
    const fetchMock = vi.fn(async () => new Response('[]', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const api = createHttpBoardApi('')
    await api.tasks('kroker', { runId: 'r1' })
    expect(fetchMock).toHaveBeenCalledWith('/projects/kroker/tasks?run_id=r1')
  })
})

// T029 companion (RED): every fixture scenario the mock contract requires
// (contracts/board-client.md), against the not-yet-existing
// createMockBoardApi(). Project keys come from the four board mock runs
// api/mock/index.ts already seeds: 'kroker' (feature-graph-demo),
// 'ghost-project' (404) and 'kroker-empty' (empty state). Asserts are on
// values a hand-authored fixture naturally pins -- counts, ids, statuses --
// never full deep-equals.
describe('createMockBoardApi (mock contract)', () => {
  const BOARD_RUN = 'feature-graph-demo'

  it("kroker's detail lists its artifacts, plan among them (step 1)", async () => {
    const api = createMockBoardApi()
    const d = await api.project('kroker')
    expect(d.key).toBe('kroker')
    expect(d.artifacts.some((a) => a.key === 'plan')).toBe(true)
  })

  it('plan versions span the board run and another run (G5d filter observable, step 2)', async () => {
    const api = createMockBoardApi()
    const versions = await api.versions('kroker', 'plan')
    expect(versions.some((v) => v.run_id === BOARD_RUN)).toBe(true)
    expect(versions.some((v) => v.run_id !== BOARD_RUN)).toBe(true)
  })

  it('tasks for the board run cover every TaskStatus, incl diverged, error and fix-attempt variety (step 3)', async () => {
    const api = createMockBoardApi()
    const tasks = await api.tasks('kroker', { runId: BOARD_RUN })
    expect(tasks.length).toBeGreaterThan(0)
    expect(tasks.every((t) => t.run_id === BOARD_RUN)).toBe(true) // the run filter is honored
    const statuses = new Set(tasks.map((t) => t.status))
    for (const s of ['pending', 'in_progress', 'done', 'failed', 'blocked', 'quarantined'] as const) {
      expect(statuses.has(s)).toBe(true)
    }
    expect(tasks.some((t) => t.status !== t.authoritative_status)).toBe(true) // diverged
    expect(tasks.some((t) => t.error !== null)).toBe(true)
    const fixAttempts = new Set(tasks.map((t) => t.fix_attempts > 0))
    expect(fixAttempts.has(true)).toBe(true)
    expect(fixAttempts.has(false)).toBe(true)
  })

  it('task detail returns the task and evidence of every kind (step 5)', async () => {
    const api = createMockBoardApi()
    const tasks = await api.tasks('kroker', { runId: BOARD_RUN })
    const kinds = new Set<string>()
    for (const t of tasks) {
      const d = await api.taskDetail('kroker', t.task_id)
      expect(d.task.task_id).toBe(t.task_id)
      for (const e of d.evidence) kinds.add(e.kind)
    }
    for (const kind of ['qa', 'review', 'deep_review']) {
      expect(kinds.has(kind)).toBe(true)
    }
  })

  it('events answer for at least one task subject (step 6)', async () => {
    const api = createMockBoardApi()
    const tasks = await api.tasks('kroker', { runId: BOARD_RUN })
    let withEvents = 0
    for (const t of tasks) {
      const events = await api.events('kroker', `task:${t.plan_version}:${t.task_id}`)
      if (events.length > 0) withEvents += 1
    }
    expect(withEvents).toBeGreaterThanOrEqual(1)
  })

  it('every artifact key has versions, and some key shows a foreign run (step 4)', async () => {
    const api = createMockBoardApi()
    const d = await api.project('kroker')
    expect(d.artifacts.length).toBeGreaterThan(0)
    let foreignRunVisible = false
    for (const a of d.artifacts) {
      const versions = await api.versions('kroker', a.key)
      expect(versions.length).toBeGreaterThan(0)
      if (versions.some((v) => v.run_id !== BOARD_RUN)) foreignRunVisible = true
    }
    expect(foreignRunVisible).toBe(true)
  })

  it("ghost-project answers 404 on the project detail (isNotFound true)", async () => {
    const api = createMockBoardApi()
    const e = await api.project('ghost-project').catch((x: unknown) => x)
    expect(isNotFound(e)).toBe(true)
  })

  it('kroker-empty resolves with an empty tasks list (empty state)', async () => {
    const api = createMockBoardApi()
    const d = await api.project('kroker-empty')
    expect(d.key).toBe('kroker-empty')
    await expect(api.tasks('kroker-empty', { runId: 'feature-empty-board' })).resolves.toEqual([])
  })
})
