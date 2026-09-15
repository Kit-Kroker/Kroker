import type { Run } from '../api/types'
import type { DotState } from '@kroker/ui/components/stage_dots/StageDots.vue'

export type StageState = DotState

// The strip keyed by NAME over the served canonical list (E-76 spec §9.1).
// No index ever crosses the API: the old stageIdx computed in one stage list
// and rendered in another (a live run at clarify lit `architecture`).
// Names already reported: a product fault is logged once per name (§9.1),
// not on every recomputation of the strip.
const reported = new Set<string>()

export function stageStates(
  run: Pick<Run, 'activeStages' | 'status'>,
  canonicalStages: readonly string[],
): StageState[] {
  const positions: number[] = []
  for (const name of run.activeStages) {
    const i = canonicalStages.indexOf(name)
    if (i < 0) {
      // A product fault, never silently mapped (spec §9.1 rule 3).
      if (!reported.has(name)) {
        reported.add(name)
        console.error(`stage strip: "${name}" is not a canonical stage`)
      }
      continue
    }
    positions.push(i)
  }
  if (positions.length === 0) return canonicalStages.map(() => 'pending')
  const lowest = Math.min(...positions)
  const activeMark: StageState =
    run.status === 'blocked' ? 'blocked'
      : run.status === 'failed' ? 'failed'
        : run.status === 'done' ? 'done'
          : 'active'
  return canonicalStages.map((_, i) =>
    positions.includes(i) ? activeMark : i < lowest ? 'done' : 'pending',
  )
}
