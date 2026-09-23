import type { Run } from '../api/types'
import type { StageDot } from '@kroker/ui/components/stage_dots/StageDots.vue'
import { stageStates } from './stageState'

// canonicalStages comes from the catalog store (GET /graphs/catalog), never a
// TS copy (E-76 spec U4). Empty until the catalog loads: StageDots renders no
// marks for an unresolved list (STAGE_DOTS-1.1).
export function toStageDots(
  run: Pick<Run, 'activeStages' | 'status' | 'stageMarks'>,
  canonicalStages: readonly string[],
): StageDot[] {
  const states = stageStates(run, canonicalStages)
  return canonicalStages.map((stage, i) => ({ stage, state: states[i] }))
}
