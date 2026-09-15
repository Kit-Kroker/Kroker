<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../stores/fleet'
import { useCatalogStore } from '../../stores/catalog'
import FleetTable from '@kroker/ui/components/fleet_table/FleetTable.vue'
import { toFleetRow } from '../../adapters/fleet'

const fleet = useFleetStore()
const catalog = useCatalogStore()
const rows = computed(() => fleet.runs.map((r) => toFleetRow(r, catalog.canonicalStages)))
</script>

<template>
  <FleetTable :rows="rows" />
</template>
