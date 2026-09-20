import type { Run } from '../api/types'
import type { FleetRowProps } from '@kroker/ui/components/fleet_row/FleetRow.vue'
import type { StageDot } from '@kroker/ui/components/stage_dots/StageDots.vue'
import { statusMetaOf } from '../composables/status'
import { stageStates } from '../composables/stageState'

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

export function toFleetRow(run: Run, canonicalStages: readonly string[]): FleetRowProps {
  const meta = statusMetaOf(run)
  return {
    id: run.id,
    title: run.title,
    mode: run.mode,
    dots: toStageDots(run, canonicalStages),
    status: {
      kind: run.status,
      label: meta.label,
      pulsing: run.status === 'running' || run.status === 'blocked',
    },
    blocker: run.blocker,
    cost: run.cost,
    age: run.age,
    href: `/runs/${run.id}`,
  }
}
