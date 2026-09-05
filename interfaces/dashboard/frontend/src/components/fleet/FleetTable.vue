<script setup lang="ts">
import { useFleetStore } from '../../stores/fleet'
import FleetRow from './FleetRow.vue'

const fleet = useFleetStore()
</script>

<template>
  <div class="panel">
    <div class="head">
      <span>RUN</span><span>TITLE</span><span>STAGES</span><span>STATUS</span>
      <span>BLOCKER</span><span class="r">COST</span><span class="r">AGE</span>
    </div>
    <FleetRow v-for="r in fleet.runs" :key="r.id" :run="r" />
  </div>
</template>

<style scoped>
.panel {
  border: 1px solid var(--c-1e242f);
  border-radius: 6px;
  overflow: hidden;
  background: var(--c-10141b);
}
.head {
  display: grid;
  grid-template-columns: 170px minmax(140px, 1.4fr) 172px 126px minmax(90px, 1fr) 76px 60px;
  gap: 12px;
  align-items: center;
  padding: 8px 14px;
  background: var(--c-0d1016);
  border-bottom: 1px solid var(--c-1e242f);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--c-5d6675);
}
.r {
  text-align: right;
}
</style>
