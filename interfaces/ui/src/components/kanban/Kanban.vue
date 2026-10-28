<script setup lang="ts">
// 018 T052 (S7, V7): the v5 kanban board. Presentational — the caller
// (features/board/kanban.adapter.ts, T053/T054) maps wire tasks to these
// display columns; the optional footer link opens the full Agent Board.
export interface KanbanCard {
  id: string
  title?: string
  tag: string
  tagKind: string
  meta: string
}

export interface KanbanColumn {
  id: string
  title: string
  status: string
  count: number
  cards: KanbanCard[]
}

defineProps<{ columns: KanbanColumn[]; link?: { label: string; to: string } }>()
</script>

<template>
  <div class="cmp-kanban">
    <div class="columns">
      <section
        v-for="c in columns"
        :key="c.id"
        class="column"
        :data-status="c.status"
        data-testid="kanban-column"
      >
        <header class="col-head">
          <span class="col-title">{{ c.title }}</span>
          <span class="col-count">{{ c.count }}</span>
        </header>
        <div class="cards">
          <article v-for="card in c.cards" :key="card.id" class="card" data-testid="kanban-card">
            <div class="card-top">
              <span class="card-id">{{ card.id }}</span>
              <span class="tag" :class="card.tagKind" data-testid="kanban-tag">{{ card.tag }}</span>
            </div>
            <p v-if="card.title" class="card-title">{{ card.title }}</p>
            <p class="card-meta">{{ card.meta }}</p>
          </article>
          <p v-if="c.cards.length === 0" class="col-empty">—</p>
        </div>
      </section>
    </div>
    <RouterLink v-if="link" class="link" data-testid="kanban-link" :to="link.to">
      {{ link.label }}
    </RouterLink>
  </div>
</template>

<style scoped>
.cmp-kanban { display: flex; flex-direction: column; gap: 10px; }
.columns { display: flex; gap: 10px; align-items: stretch; overflow-x: auto; }
.column {
  flex: 1 1 180px; min-width: 170px;
  display: flex; flex-direction: column; gap: 6px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px 10px;
  background: var(--ground-1);
}
.col-head {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  border-bottom: 1px solid var(--line); padding-bottom: 6px;
}
.col-title { font-size: 12px; font-weight: 600; color: var(--ink-primary); }
.col-count {
  font-family: var(--font-mono); font-size: 11px; color: var(--ink-muted);
}
.cards { display: flex; flex-direction: column; gap: 6px; }
.card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 8px;
  background: var(--ground-raised);
  display: flex; flex-direction: column; gap: 3px;
}
.card-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.card-id { font-family: var(--font-mono); font-size: 11px; color: var(--ink-primary); }
.tag {
  font-family: var(--font-mono); font-size: 10px;
  padding: 1px 6px; border-radius: 999px;
  border: 1px solid var(--line-strong);
  color: var(--ink-secondary);
}
.card-title { margin: 0; font-size: 12px; color: var(--ink-primary); }
.card-meta { margin: 0; font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-muted); }
.col-empty { margin: 2px 0; font-family: var(--font-mono); font-size: 11px; color: var(--ink-whisper); }
.link {
  align-self: flex-start;
  color: var(--link); text-decoration: none;
  font-family: var(--font-mono); font-size: 11.5px;
}
.link:hover { text-decoration: underline; }

/* The wire status vocabulary (V7) maps onto the status tokens. */
.tag.pending { color: var(--status-pending); border-color: var(--status-pending); }
.tag.in_progress { color: var(--status-running); border-color: var(--status-running); }
.tag.done { color: var(--status-done); border-color: var(--status-done); }
.tag.failed { color: var(--status-failed); border-color: var(--status-failed); }
.tag.blocked { color: var(--status-blocked); border-color: var(--status-blocked); }
.tag.quarantined { color: var(--status-quarantined); border-color: var(--status-quarantined); }
</style>
