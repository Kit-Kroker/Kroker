import type { Run, Status } from '../api/types'
import { STATUS_COLORS } from '../constants'

export interface StatusMeta {
  color: string
  label: string
  anim: string
}

const MAP: Record<Status, StatusMeta> = {
  running: { color: STATUS_COLORS.running, label: 'running', anim: 'fc-pulse 1.8s infinite' },
  blocked: { color: STATUS_COLORS.blocked, label: 'awaiting human', anim: 'fc-pulse 1.4s infinite' },
  failed: { color: STATUS_COLORS.failed, label: 'failed', anim: 'none' },
  done: { color: STATUS_COLORS.done, label: 'done', anim: 'none' },
}

export function statusMetaOf(run: Pick<Run, 'status'>): StatusMeta {
  return MAP[run.status] ?? MAP.running
}
