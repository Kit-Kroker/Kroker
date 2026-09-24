// The board transport (002, R-3): feature-local, read-only (FR-024), calling
// the existing board routes under /projects. One BoardApi interface, an http
// factory and a mock factory, selected by the SAME mode rule as api/client
// (API_MODE, the one source -- the two selections can never drift).
import { API_MODE } from '../../api/client'
import { HttpStatusError } from '../../api/errors'
import type {
  ArtifactVersionWire, BoardEventWire, BoardTaskWire, ProjectDetailWire, TaskDetailWire,
} from './board.types'
import {
  EMPTY_DETAIL, EMPTY_RUN, KROGER_ARCHITECTURE_VERSIONS, KROGER_DETAIL, KROGER_EVENTS,
  KROGER_EVIDENCE, KROGER_PLAN_VERSIONS, KROGER_REQUIREMENTS_VERSIONS, KROGER_TASKS,
} from './__fixtures__/board'

export interface BoardApi {
  /** Step 1: project detail (artifact keys, stats). */
  project(p: string): Promise<ProjectDetailWire>
  /** Step 2 (with key 'plan'): plan versions. Step 4 (any key): versions. */
  versions(p: string, key: string): Promise<ArtifactVersionWire[]>
  /** Step 3: the run's tasks, optionally pinned to a plan version. */
  tasks(p: string, q: { runId: string; plan?: number }): Promise<BoardTaskWire[]>
  /** Step 5: one task with its evidence. */
  taskDetail(p: string, taskId: string, plan?: number): Promise<TaskDetailWire>
  /** Step 6: events filtered by subject (`task:<plan_version>:<id>`). */
  events(p: string, subject: string): Promise<BoardEventWire[]>
}

const enc = encodeURIComponent

/** The six step URLs as exact encoded strings (R-11; tested, not guessed). */
export function boardUrls(
  p: string,
  q: { runId?: string; plan?: number; taskId?: string; subject?: string; key?: string } = {},
): { project: string; tasks: string; taskDetail: string; events: string; versions: string } {
  const base = `/projects/${enc(p)}`
  const tasksQ = [
    q.runId !== undefined ? `run_id=${enc(q.runId)}` : null,
    q.plan !== undefined ? `plan=${q.plan}` : null,
  ].filter((s): s is string => s !== null)
  const detailQ = q.plan !== undefined ? `?plan=${q.plan}` : ''
  return {
    project: base,
    tasks: `${base}/tasks${tasksQ.length ? `?${tasksQ.join('&')}` : ''}`,
    taskDetail: `${base}/tasks/${enc(q.taskId ?? '')}${detailQ}`,
    events: q.subject !== undefined ? `${base}/events?subject=${enc(q.subject)}` : `${base}/events`,
    versions: `${base}/artifacts/${enc(q.key ?? '')}`,
  }
}

/**
 * FR-021a: the plan version this run published -- the newest surrogate `id`
 * (never `n`) whose run_id matches. Undefined = the run published none; the
 * caller omits `plan` and lets step 3 (the current plan) decide.
 */
export function pickPlanVersion(versions: ArtifactVersionWire[], runId: string): ArtifactVersionWire | undefined {
  let newest: ArtifactVersionWire | undefined
  for (const v of versions) {
    if (v.run_id !== runId) continue
    if (newest === undefined || v.id > newest.id) newest = v
  }
  return newest
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new HttpStatusError(res.status, `board: ${res.status} ${url}`)
  }
  return (await res.json()) as T
}

export function createHttpBoardApi(base = ''): BoardApi {
  const origin = base.replace(/\/$/, '')
  const u = (p: string, q?: Parameters<typeof boardUrls>[1]) => boardUrls(p, q)
  return {
    project: (p) => getJson(`${origin}${u(p).project}`),
    versions: (p, key) => getJson(`${origin}${u(p, { key }).versions}`),
    tasks: (p, { runId, plan }) => getJson(`${origin}${u(p, { runId, plan }).tasks}`),
    taskDetail: (p, taskId, plan) => getJson(`${origin}${u(p, { taskId, plan }).taskDetail}`),
    events: (p, subject) => getJson(`${origin}${u(p, { subject }).events}`),
  }
}

const VERSIONS_BY_KEY: Record<string, ArtifactVersionWire[]> = {
  plan: KROGER_PLAN_VERSIONS,
  requirements: KROGER_REQUIREMENTS_VERSIONS,
  architecture: KROGER_ARCHITECTURE_VERSIONS,
}

export function createMockBoardApi(): BoardApi {
  return {
    async project(p) {
      if (p === 'kroker') return KROGER_DETAIL
      if (p === 'kroker-empty') return EMPTY_DETAIL
      // Unknown project: the board's own 404 (R-3) -- permanent, not transient.
      throw new HttpStatusError(404, `board: no project ${p}`)
    },
    async versions(p, key) {
      if (p !== 'kroker') throw new HttpStatusError(404, `board: no project ${p}`)
      const list = VERSIONS_BY_KEY[key]
      if (!list) throw new HttpStatusError(404, `board: no artifact ${p}/${key}`)
      return list
    },
    async tasks(p, { runId, plan }) {
      if (p === 'kroker-empty') return []
      if (p !== 'kroker') throw new HttpStatusError(404, `board: no project ${p}`)
      void plan // the mock's single board matches any pin; the run filter is the point
      return KROGER_TASKS.filter((t) => t.run_id === runId)
    },
    async taskDetail(p, taskId) {
      if (p !== 'kroker') throw new HttpStatusError(404, `board: no project ${p}`)
      const task = KROGER_TASKS.find((t) => t.task_id === taskId)
      if (!task) throw new HttpStatusError(404, `board: no task ${taskId}`)
      return { task, evidence: KROGER_EVIDENCE[taskId] ?? [] }
    },
    async events(p, subject) {
      if (p !== 'kroker') throw new HttpStatusError(404, `board: no project ${p}`)
      return KROGER_EVENTS.filter((e) => e.subject === subject)
    },
  }
}

export const boardApi: BoardApi = API_MODE === 'mock' ? createMockBoardApi() : createHttpBoardApi()
export { EMPTY_RUN }
