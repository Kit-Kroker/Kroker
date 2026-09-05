import type { Run } from '../api/types'
import type { FleetRowProps } from '@kroker/ui/components/fleet_row/FleetRow.vue'
import type { StageDot } from '@kroker/ui/components/stage_dots/StageDots.vue'
import { STAGES } from '../constants'
import { statusMetaOf } from '../composables/status'
import { stageStateOf } from '../composables/stageState'

export function toStageDots(run: Pick<Run, 'stageIdx' | 'status'>): StageDot[] {
  return STAGES.map((stage, i) => ({
    stage,
    state: stageStateOf(run, i),
  }))
}

export function toFleetRow(run: Run): FleetRowProps {
  const meta = statusMetaOf(run)
  return {
    id: run.id,
    title: run.title,
    mode: run.mode,
    dots: toStageDots(run),
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
