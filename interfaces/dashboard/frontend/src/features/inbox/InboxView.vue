<script setup lang="ts">
// 018 T040/T041 (R-3, S14): the v5 decision inbox — a list of rows (kind,
// age, title, where) and one DecisionCard for the selection, mirrored in
// ?item=. The store rules (in-flight, notices, drafts, load states) are
// unchanged; the card's actions route through the store's own methods so
// every guarantee (run-and-key scoping, 404 notice, failure release,
// refresh-after-write) keeps holding.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DecisionCard from '@kroker/ui/components/decision_card/DecisionCard.vue'
import type { InboxItem } from '../../api/types'
import type { DashboardApi } from '../../api/types'
import { useInboxStore } from '../../app/inbox.store'
import { entryKey } from '../../shared/entryKey'
import { decisionCardOf } from '../../shared/decisionCard.adapter'

const inbox = useInboxStore()
const route = useRoute()
const router = useRouter()

const KIND_LABEL: Record<InboxItem['type'], string> = {
  clarify: 'clarify',
  gate: 'gate',
  override: 'override',
  escalation: 'escalation',
}

// ?item= mirrors the selection (replace, never push).
const selectedKey = ref<string | null>((route?.query.item as string) ?? null)
watch(
  () => route?.query.item,
  (item) => { selectedKey.value = typeof item === 'string' ? item : null },
)
function select(key: string): void {
  const next = selectedKey.value === key ? null : key
  selectedKey.value = next
  const current = router?.currentRoute.value
  if (!current) return
  void router.replace({ query: { ...current.query, item: next ?? undefined } })
}

const selected = computed(() => inbox.items.find((i) => entryKey(i) === selectedKey.value) ?? null)
const selectedKeyOf = () => (selected.value ? entryKey(selected.value) : '')
const model = computed(() => (selected.value ? decisionCardOf(selected.value) : null))

// R-12: opening a clarify card seeds the empty draft with the suggestion —
// the card's initial value reads the store draft, a typed draft wins.
const cardText = computed(() => {
  if (!model.value?.card.text || !selected.value) return undefined
  const seeded = selected.value.type === 'clarify' ? selected.value.suggestion : ''
  return { ...model.value.card.text, value: inbox.drafts[selectedKeyOf()] ?? seeded ?? '' }
})

// The card's actions route through the STORE's methods (never the raw api):
// the store owns in-flight, notices and the refresh-after-write.
const storeAsApi = {
  answerClarify: (r: string, k: string, a: string) => inbox.answerClarify(r, k, a),
  decideGate: (r: string, k: string, o: 'approve' | 'reject' | 'revise', c: string) => inbox.decideGate(r, k, o, c),
  overrideMerge: (r: string, k: string, a: boolean, j: string) => inbox.overrideMerge(r, k, a, j),
  decideTaskGate: (r: string, k: string, o: 'approve' | 'reject' | 'revise', g: string, t: boolean) =>
    inbox.decideTaskGate(r, k, o, g, t),
} as unknown as DashboardApi

async function onAct(actId: string, text: string): Promise<void> {
  if (!selected.value || !model.value) return
  const key = selectedKeyOf()
  try {
    await model.value.call(storeAsApi, actId, text, false)
  } catch (e) {
    // The store's send() owns this in the real flow; a throwing action
    // (a spy in tests, a future bug in prod) must still surface here.
    inbox.notice = { ...inbox.notice, [key]: `failed: ${String(e)}` }
  }
}
</script>

<template>
  <main data-testid="inbox-view" data-screen-label="Decision inbox" class="view">
    <header class="head">
      <h1 class="heading">Decision inbox</h1>
      <span class="count" data-testid="inbox-count-line">{{ inbox.items.length }} waiting</span>
    </header>

    <div v-if="!inbox.loaded && !inbox.loadError" class="state" data-testid="inbox-loading">loading…</div>
    <div
      v-else-if="!inbox.loaded && inbox.loadError"
      class="state"
      data-testid="inbox-load-error"
    >The inbox could not be loaded.</div>
    <div
      v-else-if="inbox.loaded && inbox.items.length === 0 && inbox.unreadable.length === 0 && !inbox.loadError"
      class="state"
      data-testid="inbox-empty"
    >Nothing waiting on you</div>

    <template v-else>
      <!-- FR-011: with a banner up, "nothing is waiting" would be a lie. -->
      <div
        v-if="inbox.loaded && (inbox.unreadable.length > 0 || inbox.loadError)"
        class="incomplete"
        data-testid="inbox-incomplete"
      >
        <p v-if="inbox.loadError" class="line">The inbox could not be refreshed; showing the last known list.</p>
        <p v-if="inbox.loadError || inbox.unreadable.length > 0" class="line">
          This list may be incomplete: the pending state of
          {{ inbox.unreadable.length }} run(s) could not be read.
          {{ inbox.unreadable.map((r) => r.runId).join(' ') }}
        </p>
      </div>

      <div class="cols">
        <div class="list">
          <button
            v-for="item in inbox.items"
            :key="entryKey(item)"
            class="row"
            data-testid="inbox-row"
            :data-key="entryKey(item)"
            :class="{ 'is-selected': entryKey(item) === selectedKey }"
            @click="select(entryKey(item))"
          >
            <span class="kind">{{ KIND_LABEL[item.type] }}</span>
            <span class="title">{{ item.title }}</span>
            <span class="where">{{ item.runId }} · {{ item.age }}</span>
          </button>
        </div>
        <div v-if="model && selected" class="pane" data-testid="inbox-card">
          <RouterLink
            class="run-ref"
            data-testid="card-run-link"
            :to="`/runs/${selected.runId}`"
          >{{ selected.runId }}</RouterLink>
          <p v-if="inbox.notice[selectedKeyOf()]" class="notice" data-testid="inbox-notice">
            {{ inbox.notice[selectedKeyOf()] }}
          </p>
          <DecisionCard
            v-bind="model.card"
            :text="cardText"
            :busy="inbox.inFlight.has(selectedKeyOf())"
            @act="(id, text) => onAct(id, text)"
          />
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.view {
  flex: 1;
  overflow: auto;
  padding: 20px 20px 60px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.head { display: flex; align-items: baseline; gap: 12px; }
.heading { margin: 0; font-size: 15px; font-weight: 600; color: var(--ink-primary); }
.count { font-family: var(--font-mono); font-size: 11px; color: var(--ink-subtle); }
.state { color: var(--ink-subtle); font-family: var(--font-mono); font-size: 12px; }
.incomplete { border: 1px solid var(--status-blocked); border-radius: 6px; padding: 6px 10px; }
.line { margin: 0; font-size: 12px; color: var(--ink-secondary); }
.cols { display: flex; gap: 16px; align-items: flex-start; }
.list { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0; }
.row {
  display: grid; grid-template-columns: 70px 1fr auto; gap: 10px; align-items: baseline;
  text-align: left; cursor: pointer;
  background: var(--ground-2); border: 1px solid var(--line); border-radius: 6px;
  padding: 8px 10px; font-family: var(--font-sans); font-size: 12.5px; color: var(--ink-secondary);
}
.row.is-selected { border-color: var(--accent); }
.kind { font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-subtle); }
.title { color: var(--ink-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.where { font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-subtle); }
.pane { display: flex; flex-direction: column; gap: 8px; }
.run-ref { font-family: var(--font-mono); font-size: 11px; color: var(--link); }
.notice { margin: 0; font-family: var(--font-mono); font-size: 11px; color: var(--status-waiting); }
</style>
