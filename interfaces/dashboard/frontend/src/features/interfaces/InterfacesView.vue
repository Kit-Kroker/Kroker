<script setup lang="ts">
// 018 T079 (S12, FR-050/FR-051): the v5 Interfaces screen. The harness
// containment matrix on the library CheckMatrix - the view adds nothing
// the wire does not carry.
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'
import { mapInterfaces } from '../../api/http-read'
import type { InterfaceMatrix } from '../../api/read-types'
import { CheckMatrix } from '@kroker/ui'

const matrix = ref<InterfaceMatrix | null>(null)
const failed = ref(false)

onMounted(async () => {
  try {
    matrix.value = mapInterfaces((await api.getInterfaces()) as never)
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <section class="if page" data-testid="if-view">
    <header class="head">
      <h1>Interfaces</h1>
      <p class="desc">Harness containment, per adapter declaration and the shipped policy.</p>
    </header>

    <div v-if="failed" class="empty">interfaces read failed — retry in a moment</div>
    <div v-else-if="!matrix" class="empty">loading.</div>
    <CheckMatrix v-else :columns="matrix.columns" :rows="matrix.rows" :facts="matrix.facts" />
  </section>
</template>

<style scoped>
.if { display: flex; flex-direction: column; gap: 16px; }
.head h1 { font: 600 15px/1.2 var(--font-sans); color: var(--ink-primary); margin: 0; }
.desc { font: 12px/1.4 var(--font-mono); color: var(--ink-muted); margin: 4px 0 0; }
.empty { color: var(--ink-muted); font: 12.5px/1.5 var(--font-sans); }
</style>
