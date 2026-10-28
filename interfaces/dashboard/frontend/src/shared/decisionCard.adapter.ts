import type {
  ClarifyItem, DashboardApi, EscalationItem, GateItem, InboxItem, OverrideItem,
} from '../api/types'
import type { CardAction, CardField, CardText } from '@kroker/ui/components/decision_card/DecisionCard.vue'

// 018 T038/T039 (R-3's table, data-model §5): one decision-card mapping for
// every inbox kind. The card kind is derived from fields already on the
// wire — no backend change. Every action maps to exactly one client call;
// the task card routes through decideTaskGate (never the generic gate), so
// the main-branch retry defect (retry posting 'approve') is not carried
// forward.

export interface DecisionCardModel {
  card: {
    kicker: string
    schema: string
    title: string
    where: string
    fields: CardField[]
    text?: CardText
    actions: CardAction[]
    foot: string
  }
  timeout: string | null
  call: (api: DashboardApi, actId: string, text: string, thawTests?: boolean) => Promise<void>
}

type Act = (api: DashboardApi, text: string, thawTests: boolean) => Promise<void>

const action = (
  id: string, label: string, title: string, variant: string, needsText = false, act: Act,
): { a: CardAction; act: Act } => ({
  a: { id, label, title, variant, needsText },
  act,
})

export function decisionCardOf(item: InboxItem, timeouts?: Record<string, string>): DecisionCardModel {
  const base = {
    kicker: `${'gate' in item && item.gate ? item.gate : item.type} r${item.round}`,
    title: item.title,
    where: `${item.runId} · round ${item.round}`,
    fields: [] as CardField[],
  }
  const entries: { a: CardAction; act: Act }[] = []
  let schema = 'gate'
  let text: CardText | undefined
  let foot = `opened ${item.age} ago`

  if (item.type === 'clarify') {
    const c = item as ClarifyItem
    schema = 'clarify'
    base.kicker = `clarify r${c.round}`
    if (c.suggestion) {
      entries.push(action('accept', 'Accept suggestion', `send the suggested answer`, 'default', false,
        // Acceptance is the one-action send: the empty answer with the
        // suggestion present; typed text never leaks into accept.
        (api) => api.answerClarify(c.runId, c.id, '')))
    }
    text = { label: 'Answer', hint: 'one line, plain text', value: '', required: true }
    entries.push(action('answer', 'Send answer', 'send the typed answer', 'primary', true,
      (api, t) => api.answerClarify(c.runId, c.id, t)))
    if (c.body) base.fields.push({ k: 'Why', v: c.body })
  } else if (item.type === 'override') {
    const o = item as OverrideItem
    schema = 'override'
    if (o.verdict) base.fields.push({ k: 'Verdict', v: o.verdict, mono: true })
    for (const check of o.checks) {
      base.fields.push({ k: check.name, v: check.ok ? 'pass' : check.detail || 'fail', mono: true })
    }
    text = { label: 'Justification', hint: 'why this override is safe', value: '', required: true }
    entries.push(action('override', 'Override', 'merge under an audited human override', 'primary', true,
      (api, t) => api.overrideMerge(o.runId, o.id, true, t)))
    entries.push(action('send-back', 'Send back', 'return the work without merging', 'default', false,
      (api, t) => api.overrideMerge(o.runId, o.id, false, t)))
  } else if (item.type === 'escalation') {
    const e = item as EscalationItem
    schema = 'escalation'
    base.kicker = `task r${e.round}`
    if (e.analysis) base.fields.push({ k: 'Analysis', v: e.analysis })
    text = { label: 'Guidance', hint: 'what the retry should try', value: '', required: true }
    entries.push(action('approve', 'Accept as done', 'accept as done', 'default', false,
      (api, _t, thaw) => api.decideTaskGate(e.runId, e.id, 'approve', '', thaw)))
    entries.push(action('revise', 'retry', 'retry the task with this guidance', 'primary', true,
      (api, t, thaw) => api.decideTaskGate(e.runId, e.id, 'revise', t, thaw)))
    entries.push(action('reject', 'Quarantine', 'quarantine; the build ends failed:quarantined-tasks after the wave', 'danger', false,
      (api, _t, thaw) => api.decideTaskGate(e.runId, e.id, 'reject', '', thaw)))
  } else {
    const g = item as GateItem
    schema = 'gate'
    if (g.body) base.fields.push({ k: 'Summary', v: g.body })
    if (g.gate === 'tool_approval') {
      // V4 (E-17): Approve / Deny only — a halt is not offered; the timeout
      // rule is the foot.
      foot = 'a timeout counts as not approved'
      entries.push(action('approve', 'Approve', 'run the step', 'default', false,
        (api, t) => api.decideGate(g.runId, g.id, 'approve', t)))
      entries.push(action('reject', 'Deny', 'skip the step', 'danger', false,
        (api, t) => api.decideGate(g.runId, g.id, 'reject', t)))
    } else if (g.gate === 'budget') {
      // V6 (CONSOLE-29's copy): the consequences are priced into the titles.
      entries.push(action('approve', 'Approve', 'one more increment', 'default', false,
        (api, t) => api.decideGate(g.runId, g.id, 'approve', t)))
      entries.push(action('reject', 'Reject', 'ends the run rejected:budget', 'danger', false,
        (api, t) => api.decideGate(g.runId, g.id, 'reject', t)))
    } else {
      text = { label: 'Comment', hint: 'required for revise', value: '', required: false }
      entries.push(action('approve', 'Approve', 'grant this increment', 'default', false,
        (api, t) => api.decideGate(g.runId, g.id, 'approve', t)))
      entries.push(action('revise', 'Revise', 'send the work back for another round', 'primary', true,
        (api, t) => api.decideGate(g.runId, g.id, 'revise', t)))
      entries.push(action('reject', 'Reject', 'end the round with a rejection', 'danger', false,
        (api, t) => api.decideGate(g.runId, g.id, 'reject', t)))
    }
  }

  const byId = new Map(entries.map(({ a, act }) => [a.id, act]))
  return {
    card: { ...base, schema, text, actions: entries.map(({ a }) => a), foot },
    timeout: timeouts?.[item.type === 'gate' ? (item as GateItem).gate : item.type] ?? null,
    call: async (api, actId, text, thawTests = false) => {
      const act = byId.get(actId)
      await act?.(api, text, thawTests)
    },
  }
}
