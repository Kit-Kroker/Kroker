// Board fixtures (002, contracts/board-client.md mock contract): hand-authored
// from the backend models -- no recorder exists. 'kroker' is the board project
// of the mock run feature-graph-demo; 'ghost-project' 404s; 'kroker-empty' is
// reachable with zero tasks. Artifact versions span the board run AND a
// foreign run so the G5d filter is observable.
import type {
  ArtifactVersionWire, BoardArtifactWire, BoardEventWire, BoardStatsWire,
  BoardTaskWire, ProjectDetailWire, TaskDetailWire,
} from '../board.types'

export const BOARD_RUN = 'feature-graph-demo'
export const EMPTY_RUN = 'feature-empty-board'
const FOREIGN_RUN = 'feature-billing-webhooks'
const PLAN_VERSION = 4102

const at = (h: number, m: number): string => `2026-09-24T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00Z`

const artifact = (key: string, current: number | null): BoardArtifactWire => ({
  project: 'kroker', key, status: 'current', current_version: current,
})

const version = (id: number, key: string, n: number, run: string, hour: number, min: number): ArtifactVersionWire => ({
  id, project: 'kroker', key, n, run_id: run,
  sha256: `sha256-${id.toString().padStart(4, '0')}`,
  uri: `artifacts://${run}/${key}/${n}`,
  supersedes: id > 1 ? id - 1 : null,
  created_at: at(hour, min),
})

export const KROGER_PLAN_VERSIONS: ArtifactVersionWire[] = [
  version(4098, 'plan', 2, FOREIGN_RUN, 7, 5),
  version(4101, 'plan', 1, BOARD_RUN, 8, 10), // an older n, but the run's own
  version(4102, 'plan', 3, FOREIGN_RUN, 8, 40),
  version(4107, 'plan', 4, BOARD_RUN, 9, 15), // the pin: newest id for the run
]

export const KROGER_TASKS: BoardTaskWire[] = [
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T01', run_id: BOARD_RUN, status: 'pending', authoritative_status: 'pending', row_version: 1, fix_attempts: 0, error: null, branch: null, updated_at: at(9, 20) },
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T02', run_id: BOARD_RUN, status: 'in_progress', authoritative_status: 'in_progress', row_version: 6, fix_attempts: 0, error: null, branch: 'task/t02', updated_at: at(10, 2) },
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T03', run_id: BOARD_RUN, status: 'done', authoritative_status: 'done', row_version: 4, fix_attempts: 1, error: null, branch: 'task/t03', updated_at: at(10, 30) },
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T04', run_id: BOARD_RUN, status: 'failed', authoritative_status: 'failed', row_version: 9, fix_attempts: 2, error: 'harness exit 1 after 2 fix attempts', branch: 'task/t04', updated_at: at(11, 5) },
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T05', run_id: BOARD_RUN, status: 'blocked', authoritative_status: 'done', row_version: 7, fix_attempts: 0, error: null, branch: 'task/t05', updated_at: at(11, 40) }, // diverged
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T06', run_id: BOARD_RUN, status: 'quarantined', authoritative_status: 'quarantined', row_version: 3, fix_attempts: 0, error: null, branch: null, updated_at: at(12, 0) },
  { project: 'kroker', plan_version: PLAN_VERSION, task_id: 'T07', run_id: BOARD_RUN, status: 'in_progress', authoritative_status: 'failed', row_version: 8, fix_attempts: 3, error: null, branch: 'task/t07', updated_at: at(12, 10) }, // diverged, fixing
]

const evidence = (id: string, task: string, kind: string): TaskDetailWire['evidence'][number] => ({
  id, project: 'kroker', plan_version: PLAN_VERSION, task_id: task, run_id: BOARD_RUN,
  kind, sha256: `sha256-${id}`, uri: `artifacts://${BOARD_RUN}/evidence/${task}-${kind}.md`,
  created_at: at(12, 15),
})

export const KROGER_EVIDENCE: Record<string, TaskDetailWire['evidence']> = {
  T02: [evidence('ev-t02-qa', 'T02', 'qa')],
  T03: [evidence('ev-t03-review', 'T03', 'review')],
  T04: [evidence('ev-t04-review', 'T04', 'review'), evidence('ev-t04-qa', 'T04', 'qa')],
  T07: [evidence('ev-t07-deep', 'T07', 'deep_review')],
}

const event = (id: number, task: string, from: string | null, to: string, actor: string, hour: number, min: number): BoardEventWire => ({
  id, project: 'kroker', subject: `task:${PLAN_VERSION}:${task}`,
  actor, authority: actor.startsWith('workflow:') ? 'workflow' : 'agent',
  from_status: from, to_status: to, at: at(hour, min),
  detail: `${task}: ${from ?? '—'} → ${to}`,
})

export const KROGER_EVENTS: BoardEventWire[] = [
  event(901, 'T01', null, 'pending', `workflow:${BOARD_RUN}`, 9, 20),
  event(902, 'T02', 'pending', 'in_progress', `workflow:${BOARD_RUN}`, 9, 45),
  event(903, 'T02', 'in_progress', 'failed', `agent:dev`, 10, 1),
  event(904, 'T02', 'failed', 'in_progress', `agent:dev`, 10, 2),
  event(905, 'T03', 'in_progress', 'done', `workflow:${BOARD_RUN}`, 10, 30),
  event(906, 'T05', 'in_progress', 'blocked', `workflow:${BOARD_RUN}`, 11, 40),
]

const stats = (project: string, tasks: BoardTaskWire[]): BoardStatsWire => {
  const by = { pending: 0, in_progress: 0, done: 0, failed: 0, blocked: 0, quarantined: 0 } as Record<string, number>
  for (const t of tasks) by[t.status] += 1
  return {
    project,
    tasks_by_status: by as BoardStatsWire['tasks_by_status'],
    total_fix_attempts: tasks.reduce((s, t) => s + t.fix_attempts, 0),
    tasks_with_error: tasks.filter((t) => t.error !== null).length,
    diverged_tasks: tasks.filter((t) => t.status !== t.authoritative_status).length,
    event_count: KROGER_EVENTS.length,
  }
}

export const KROGER_DETAIL: ProjectDetailWire = {
  key: 'kroker',
  repo: 'git@github.com:acme/kroker',
  artifacts: [
    artifact('plan', 4107),
    artifact('requirements', 4088),
    artifact('architecture', 4095),
  ],
  stats: stats('kroker', KROGER_TASKS),
}

export const KROGER_REQUIREMENTS_VERSIONS: ArtifactVersionWire[] = [
  version(4087, 'requirements', 1, FOREIGN_RUN, 7, 0),
  version(4088, 'requirements', 2, BOARD_RUN, 7, 30),
]

export const KROGER_ARCHITECTURE_VERSIONS: ArtifactVersionWire[] = [
  version(4095, 'architecture', 1, BOARD_RUN, 8, 0),
]

export const EMPTY_DETAIL: ProjectDetailWire = {
  key: 'kroker-empty',
  repo: 'git@github.com:acme/newproj',
  artifacts: [],
  stats: stats('kroker-empty', []),
}
