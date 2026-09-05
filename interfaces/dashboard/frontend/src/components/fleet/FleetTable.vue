<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../stores/fleet'
import FleetTable from '@kroker/ui/components/fleet_table/FleetTable.vue'
import { toFleetRow } from '../../adapters/fleet'

const fleet = useFleetStore()
const rows = computed(() => fleet.runs.map(toFleetRow))
</script>

<template>
  <FleetTable :rows="rows" />
</template>
