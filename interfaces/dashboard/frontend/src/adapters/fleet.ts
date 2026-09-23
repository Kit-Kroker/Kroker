import type { Run } from '../api/types'
import type { FleetRowProps } from '@kroker/ui/components/fleet_row/FleetRow.vue'
import { statusMetaOf } from '../composables/status'
import { toStageDots } from '../shared/stageStrip.adapter'

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
