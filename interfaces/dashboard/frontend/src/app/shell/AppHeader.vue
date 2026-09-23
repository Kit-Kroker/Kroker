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
const totalCost = computed(() => money(fleet.totalCost))
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
