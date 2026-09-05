<script setup lang="ts">
import { computed } from 'vue'
import { useFleetStore } from '../stores/fleet'
import { useInboxStore } from '../stores/inbox'
import { useUiStore } from '../stores/ui'
import { money } from '../composables/format'
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
