<script setup lang="ts">
// 018 data-model §4.2: the ⋯ display menu. Pure display — the app owns
// the toggle state; the menu shows labels, descriptions and checks.
export interface ToggleItem {
  id: string
  label: string
  desc?: string
  on: boolean
}

defineProps<{
  items: ToggleItem[]
}>()

const emit = defineEmits<{
  toggle: [id: string]
}>()
</script>

<template>
  <div class="cmp-toggle-menu menu">
    <button
      v-for="item in items"
      :key="item.id"
      data-testid="toggle-item"
      type="button"
      class="item"
      :class="{ 'item-on': item.on }"
      @click="emit('toggle', item.id)"
    >
      <span class="texts">
        <span class="label">{{ item.label }}</span>
        <span v-if="item.desc" class="desc">{{ item.desc }}</span>
      </span>
      <span v-if="item.on" data-testid="toggle-check" class="check">✓</span>
    </button>
  </div>
</template>

<style scoped>
.menu {
  min-width: 220px;
  background: var(--ground-5);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  box-shadow: var(--shadow-overlay);
  padding: 4px;
  display: flex;
  flex-direction: column;
}
.item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  background: none;
  border: none;
  text-align: left;
  padding: 8px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
}
.item:hover {
  background: var(--ground-raised);
}
.texts {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.label {
  font-size: 12px;
  color: var(--ink-primary);
}
.desc {
  font-size: 10.5px;
  color: var(--ink-dim);
}
.check {
  font-size: 12px;
  color: var(--status-done);
}
</style>
