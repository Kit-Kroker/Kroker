// Board wire types (002, data-model section 2): a read-only mirror of
// src/sdlc/board/models.py and board/api.py responses. Datetimes arrive as
// ISO strings. The board transport lives here, feature-local, per R-3.

export type TaskStatus =
  | 'pending'
  | 'in_progress'
  | 'done'
  | 'failed'
  | 'blocked'
  | 'quarantined'

export interface BoardTaskWire {
  project: string
  plan_version: number
  task_id: string
  run_id: string
  status: TaskStatus
  authoritative_status: TaskStatus
  row_version: number
  fix_attempts: number
  error: string | null
  branch: string | null
  updated_at: string
}

export interface TaskEvidenceWire {
  id: string
  project: string
  plan_version: number
  task_id: string
  run_id: string
  kind: string // qa | review | deep_review
  sha256: string
  uri: string
  created_at: string
}

export interface TaskDetailWire {
  task: BoardTaskWire
  evidence: TaskEvidenceWire[]
}

export interface ArtifactVersionWire {
  id: number
  project: string
  key: string
  n: number
  run_id: string
  sha256: string
  uri: string
  supersedes: number | null
  created_at: string
}

export interface BoardArtifactWire {
  project: string
  key: string
  status: string
  current_version: number | null
}

export interface BoardStatsWire {
  project: string
  tasks_by_status: Record<TaskStatus, number>
  total_fix_attempts: number
  tasks_with_error: number
  diverged_tasks: number
  event_count: number
}

export interface ProjectDetailWire {
  key: string
  repo: string
  artifacts: BoardArtifactWire[]
  stats: BoardStatsWire
}

export interface BoardEventWire {
  id: number
  project: string
  subject: string
  actor: string
  authority: string
  from_status: string | null
  to_status: string | null
  at: string
  detail: string
}
