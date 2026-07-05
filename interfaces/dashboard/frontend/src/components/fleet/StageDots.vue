<script setup lang="ts">
import { computed } from 'vue'
import type { Run } from '../../api/types'
import { STAGES, STATUS_COLORS } from '../../constants'
import { stageStateOf } from '../../composables/stageState'

const props = defineProps<{ run: Run }>()

interface Dot {
  title: string
  bg: string
  anim: string
}

const dots = computed<Dot[]>(() =>
  STAGES.map((name, i) => {
    const st = stageStateOf(props.run, i)
    const c =
      st === 'done' ? STATUS_COLORS.done
      : st === 'active' ? STATUS_COLORS.running
      : st === 'blocked' ? STATUS_COLORS.blocked
      : st === 'failed' ? STATUS_COLORS.failed
      : st === 'skipped' ? STATUS_COLORS.skipped
      : STATUS_COLORS.pending
    return {
      title: `${i} ${name} · ${st}`,
      bg: c,
      anim: st === 'active' || st === 'blocked' ? 'fc-pulse 1.6s infinite' : 'none',
    }
  }),
)
</script>

<template>
  <span class="dots">
    <span
      v-for="(d, i) in dots"
      :key="i"
      data-testid="stage-dot"
      class="dot"
      :title="d.title"
      :style="{ background: d.bg, animation: d.anim }"
    />
  </span>
</template>

<style scoped>
.dots {
  display: flex;
  gap: 3px;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}
</style>
