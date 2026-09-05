<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../stores/fleet'
import FleetTable from '@kroker/ui/components/fleet_table/FleetTable.vue'
import type { FleetRowProps } from '@kroker/ui/components/fleet_row/FleetRow.vue'
import { STAGES } from '../../constants'
import { stageStateOf } from '../../composables/stageState'
import { statusMetaOf } from '../../composables/status'
import type { Run } from '../../api/types'

const fleet = useFleetStore()

const toRowProps = (r: Run): FleetRowProps => ({
  id: r.id,
  title: r.title,
  mode: r.mode,
  dots: STAGES.map((stage, i) => ({
    stage,
    state: stageStateOf(r, i),
  })),
  status: {
    kind: r.status,
    label: statusMetaOf(r).label,
    pulsing: r.status === 'running' || r.status === 'blocked',
  },
  blocker: r.blocker,
  cost: r.cost,
  age: r.age,
  href: `/runs/${r.id}`,
})

const rows = computed(() => fleet.runs.map(toRowProps))
</script>

<template>
  <FleetTable :rows="rows" />
</template>
