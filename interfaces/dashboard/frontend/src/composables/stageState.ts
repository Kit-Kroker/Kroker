import type { Run } from '../api/types'

export type StageState = 'done' | 'active' | 'blocked' | 'failed' | 'skipped' | 'pending'

export function stageStateOf(
  run: Pick<Run, 'stageIdx' | 'status' | 'skipCtx'>,
  i: number,
): StageState {
  if (i === 2 && run.skipCtx) return 'skipped'
  if (i < run.stageIdx) return 'done'
  if (i === run.stageIdx) {
    if (run.status === 'blocked') return 'blocked'
    if (run.status === 'failed') return 'failed'
    if (run.status === 'done') return 'done'
    return 'active'
  }
  return 'pending'
}
