<script setup lang="ts">
import { computed, ref, watch } from 'vue'

// 018 data-model §4.2: the ⌘K palette. Pure display — the app owns the
// command list and runs them; the palette filters, highlights and closes.
export interface PaletteCommand {
  id: string
  label: string
  hint?: string
}

const props = defineProps<{
  open: boolean
  commands: PaletteCommand[]
}>()

const emit = defineEmits<{
  run: [id: string]
  close: []
}>()

const query = ref('')
const highlighted = ref(0)

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.commands
  return props.commands.filter((c) => c.label.toLowerCase().includes(q))
})

// A new filter re-ranks the list: the highlight resets to the first match.
watch(query, () => {
  highlighted.value = 0
})
watch(
  () => props.open,
  (open) => {
    if (open) {
      query.value = ''
      highlighted.value = 0
    }
  },
)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
    return
  }
  if (e.key === 'ArrowDown') {
    // Clamp at the ends: the highlight never leaves the list.
    highlighted.value = Math.min(highlighted.value + 1, visible.value.length - 1)
    e.preventDefault()
    return
  }
  if (e.key === 'ArrowUp') {
    highlighted.value = Math.max(highlighted.value - 1, 0)
    e.preventDefault()
    return
  }
  if (e.key === 'Enter') {
    const cmd = visible.value[highlighted.value]
    if (cmd) emit('run', cmd.id)
  }
}
</script>

<template>
  <div v-if="open" data-testid="palette-backdrop" class="cmp-command-palette backdrop" @click="emit('close')">
    <div class="card" @click.stop>
      <input
        data-testid="palette-input"
        class="input"
        type="text"
        placeholder="Type a command…"
        :value="query"
        @input="query = ($event.target as HTMLInputElement).value"
        @keydown="onKey"
      />
      <div class="list" role="listbox">
        <div
          v-for="(c, i) in visible"
          :key="c.id"
          data-testid="palette-command"
          role="option"
          :aria-selected="i === highlighted"
          class="cmd"
          :class="{ 'cmd-on': i === highlighted }"
          @click="emit('run', c.id)"
        >
          <span class="cmd-label">{{ c.label }}</span>
          <span v-if="c.hint" class="cmd-hint">{{ c.hint }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
  z-index: 70;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 14vh;
}
.card {
  width: 480px;
  max-width: calc(100vw - 48px);
  background: var(--ground-5);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  box-shadow: var(--shadow-overlay);
  overflow: hidden;
}
.input {
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--line);
  color: var(--ink-secondary);
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 12px 14px;
  outline: none;
}
.list {
  max-height: 320px;
  overflow: auto;
}
.cmd {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
}
.cmd-on {
  background: var(--ground-raised);
  color: var(--ink-primary);
}
.cmd-label {
  color: inherit;
}
.cmd-hint {
  color: var(--ink-dim);
  flex: none;
}
</style>
