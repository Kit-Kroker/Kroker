<script setup lang="ts">
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'md' | 'sm'

const props = withDefaults(
  defineProps<{ variant?: ButtonVariant; size?: ButtonSize; disabled?: boolean; busy?: boolean; type?: 'button' | 'submit' }>(),
  { variant: 'secondary', size: 'md', disabled: false, busy: false, type: 'button' },
)
const emit = defineEmits<{ (e: 'click', ev: MouseEvent): void }>()

function onClick(ev: MouseEvent) {
  if (props.disabled || props.busy) return
  emit('click', ev)
}
</script>

<template>
  <button
    :type="type"
    class="cmp-button"
    :class="[`cmp-button-${variant}`, `cmp-button-${size}`, { 'is-busy': busy }]"
    :disabled="disabled || busy"
    :aria-busy="busy || undefined"
    @click="onClick"
  >
    <slot />
  </button>
</template>

<style scoped>
.cmp-button { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid transparent; border-radius: var(--radius-md); font-family: var(--font-sans); font-weight: 500; line-height: 1.3; white-space: nowrap; cursor: pointer; }
.cmp-button-md { padding: 7px 14px; font-size: var(--text-md); }
.cmp-button-sm { padding: 3px 10px; font-size: var(--text-sm); border-radius: var(--radius-sm); }
.cmp-button-primary { background: var(--ink-primary); border-color: var(--ink-primary); color: var(--ink-inverse); }
.cmp-button-primary:hover:not(:disabled) { background: var(--ink-secondary); border-color: var(--ink-secondary); }
.cmp-button-secondary { background: var(--ground-raised); border-color: var(--line-strong); color: var(--ink-primary); }
.cmp-button-secondary:hover:not(:disabled) { border-color: var(--ink-muted); }
.cmp-button-ghost { background: transparent; color: var(--ink-secondary); }
.cmp-button-ghost:hover:not(:disabled) { background: var(--ground-raised); color: var(--ink-primary); }
.cmp-button-danger { background: transparent; border-color: var(--line-strong); color: var(--status-failed); }
.cmp-button-danger:hover:not(:disabled) { background: var(--status-failed-tint); }
.cmp-button:disabled { cursor: not-allowed; opacity: 0.5; }
.cmp-button.is-busy { cursor: progress; }
.cmp-button:focus-visible { outline: 2px solid var(--ink-secondary); outline-offset: 2px; }
</style>
