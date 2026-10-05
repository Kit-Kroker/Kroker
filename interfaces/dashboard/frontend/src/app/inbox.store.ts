import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { isNotFound } from '../api/errors'
import type { GateOutcome, InboxItem, UnreadableRun } from '../api/types'
import { entryKey } from '../shared/entryKey'

// 010 (contract §2). The list, the per-entry state and the writes are one
// module's state so the header badge and the screen cannot disagree (FR-002)
// and the release rule below is evaluated where the refresh lands (R-1, R-4).
export const useInboxStore = defineStore('inbox', () => {
  const items = ref<InboxItem[]>([])
  const drafts = ref<Record<string, string>>({})
  const editing = ref<Record<string, boolean>>({})
  const unreadable = ref<UnreadableRun[]>([])
  const loaded = ref(false)
  const loadError = ref<string | null>(null)
  // Replaced, never mutated, so reactivity and identity stay honest.
  const inFlight = ref<Set<string>>(new Set())
  const notice = ref<Record<string, string>>({})

  // R-4: a refresh result is applied only if it started later than the last
  // one applied; an entry whose write finished at startSeq n is released by
  // the first APPLIED refresh that started after n. settledAt is private.
  let startSeq = 0
  let appliedSeq = 0
  const settledAt = new Map<string, number>()
  const pending = ref(0)
  const loading = computed(() => pending.value > 0)

  async function refresh(): Promise<void> {
    const mine = ++startSeq
    pending.value += 1
    let r: Awaited<ReturnType<typeof api.getInboxState>>
    try {
      r = await api.getInboxState()
    } catch (e) {
      // FR-011/EC9: the last known list stays; nothing else moves.
      loadError.value = String(e)
      return
    } finally {
      pending.value -= 1
    }
    if (mine <= appliedSeq) return // an older overlapping read; drop it
    appliedSeq = mine
    items.value = r.items
    unreadable.value = r.unreadable
    loadError.value = null
    loaded.value = true
    let flying = inFlight.value
    for (const [k, at] of settledAt) {
      if (mine > at) {
        settledAt.delete(k)
        if (flying === inFlight.value) flying = new Set(inFlight.value)
        flying.delete(k)
      }
    }
    inFlight.value = flying
    // FR-012/EC4: per-entry state survives a refresh only while the entry
    // is listed or still in flight.
    const live = (k: string) =>
      r.items.some((i) => entryKey(i) === k) || inFlight.value.has(k)
    const prune = <T>(m: Record<string, T>): Record<string, T> => {
      const next: Record<string, T> = {}
      for (const [k, v] of Object.entries(m)) if (live(k)) next[k] = v
      return next
    }
    drafts.value = prune(drafts.value)
    editing.value = prune(editing.value)
    notice.value = prune(notice.value)
  }

  // One path for all four actions (contract §2.2). Actions never reject and
  // never clear drafts; a draft goes when its entry goes.
  async function send(k: string, run: () => Promise<void>): Promise<void> {
    if (inFlight.value.has(k)) return // checked before any await (EC5)
    inFlight.value = new Set(inFlight.value).add(k)
    if (notice.value[k] !== undefined) {
      const cleared = { ...notice.value }
      delete cleared[k]
      notice.value = cleared
    }
    try {
      await run()
      settledAt.set(k, startSeq)
      await refresh()
    } catch (e) {
      if (isNotFound(e)) {
        // FR-009/EC2: decided elsewhere; the entry leaves at the refresh
        // this starts, and until then it stays unavailable with its notice.
        notice.value = { ...notice.value, [k]: 'already decided elsewhere' }
        settledAt.set(k, startSeq)
        await refresh()
      } else {
        // FR-009/EC3: usable again at once, draft intact.
        notice.value = { ...notice.value, [k]: `failed: ${String(e)}` }
        const next = new Set(inFlight.value)
        next.delete(k)
        inFlight.value = next
      }
    }
  }

  async function answerClarify(
    runId: string, key: string, answer: string,
  ): Promise<void> {
    await send(entryKey({ runId, id: key }), () =>
      api.answerClarify(runId, key, answer))
  }

  async function decideGate(
    runId: string, key: string, outcome: GateOutcome, comment: string,
  ): Promise<void> {
    await send(entryKey({ runId, id: key }), () =>
      api.decideGate(runId, key, outcome, comment))
  }

  async function overrideMerge(
    runId: string, key: string, approve: boolean, justification: string,
  ): Promise<void> {
    await send(entryKey({ runId, id: key }), () =>
      api.overrideMerge(runId, key, approve, justification))
  }

  async function resolveEscalation(
    runId: string, key: string, retry: boolean, guidance: string,
  ): Promise<void> {
    await send(entryKey({ runId, id: key }), () =>
      api.resolveEscalation(runId, key, retry, guidance))
  }

  function setDraft(id: string, v: string) {
    drafts.value[id] = v
  }
  function toggleEdit(id: string) {
    editing.value[id] = !editing.value[id]
  }

  return {
    items, drafts, editing, loading, refresh, setDraft, toggleEdit,
    loaded, loadError, unreadable, inFlight, notice,
    answerClarify, decideGate, overrideMerge, resolveEscalation,
  }
})
