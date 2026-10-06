<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../../shared/fleet.store'
import { useInboxStore } from '../inbox.store'
import { useUiStore } from '../ui.store'
import { money } from '../../shared/format'
import AppHeader from '@kroker/ui/components/app_header/AppHeader.vue'

const fleet = useFleetStore()
const inbox = useInboxStore()
const ui = useUiStore()

const inboxCount = computed(() => inbox.items.length)
// 011 R-8 (contract §4): the four honest strings — the priced sum, the sum
// with the excluded count said aloud, "not priced" for a fleet with nothing
// priced, and the em dash when there is nothing to sum. money() runs only on
// a non-null usd; the excluded count is the store's, never re-derived here.
const totalCost = computed(() => {
  if (fleet.runs.length === 0) return '—'
  const { usd, excluded } = fleet.totalCost
  if (usd === null) return 'not priced'
  return excluded > 0 ? `${money(usd)} · ${excluded} not priced` : money(usd)
})
</script>

<template>
  <AppHeader
    :active-count="fleet.activeCount"
    :max-count="50"
    :total-cost="totalCost"
    :inbox-count="inboxCount"
    @start-run="ui.openStart()"
  />
</template>
