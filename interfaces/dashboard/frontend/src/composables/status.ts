import type { Run, Status } from '../api/types'

export interface StatusMeta {
  color: string
  label: string
  anim: string
}

const MAP: Record<Status, StatusMeta> = {
  running: { color: 'var(--status-running)', label: 'running', anim: 'fc-pulse 1.8s infinite' },
  blocked: { color: 'var(--status-blocked)', label: 'awaiting human', anim: 'fc-pulse 1.4s infinite' },
  failed: { color: 'var(--status-failed)', label: 'failed', anim: 'none' },
  done: { color: 'var(--status-done)', label: 'done', anim: 'none' },
}

export function statusMetaOf(run: Pick<Run, 'status'>): StatusMeta {
  return MAP[run.status] ?? MAP.running
}
