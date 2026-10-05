# Data Model and Name Table: Decision Inbox (010)

Phase 1 of [plan.md](plan.md). **This file is the single source of names for the implementation (FR-014).** Section 1 was copied from `interfaces/dashboard/frontend/src/api/types.ts` on main `39a07a4`. Before writing any file, the executor re-runs the check in §5 and stops if it differs.

`F/` = `interfaces/dashboard/frontend/src/`.

## 1. Existing names — frozen, copied from `F/api/types.ts`

### 1.1 Item variants (`types.ts:43-100`)

Common to all four: `id: string`, `runId: string`, `round: number`, `age: string`, `type`, `title: string`, `body: string`.

| Type name | `type` value | Extra fields |
|---|---|---|
| `ClarifyItem` | `'clarify'` | `suggestion: string` |
| `GateItem` | `'gate'` | `gate: string` |
| `OverrideItem` | `'override'` | `gate: 'merge'`, `verdict: string`, `checks: CheckRow[]` |
| `EscalationItem` | `'escalation'` | `analysis: string` |

`InboxItem = ClarifyItem | GateItem | OverrideItem | EscalationItem`.

`CheckRow`: `name: string`, `kind: 'ABSOLUTE' | 'ADVISORY'`, `ok: boolean`, `detail: string`.

`GateOutcome = 'approve' | 'revise' | 'reject'`.

### 1.2 Client methods used (`types.ts:118-122`)

| Method | Signature | Meaning of the third argument |
|---|---|---|
| `listInbox` | `(): Promise<InboxItem[]>` | — (kept; no longer called by the store, see §2) |
| `answerClarify` | `(runId: string, key: string, answer: string): Promise<void>` | the answer text |
| `decideGate` | `(runId: string, key: string, outcome: GateOutcome, comment: string): Promise<void>` | a `GateOutcome` |
| `overrideMerge` | `(runId: string, key: string, approve: boolean, justification: string): Promise<void>` | `true` = override, `false` = send back |
| `resolveEscalation` | `(runId: string, key: string, retry: boolean, guidance: string): Promise<void>` | `true` = retry, `false` = quarantine |

The `key` argument is the item's `id`.

### 1.4 Library components used (`interfaces/ui/src/components/`, copied from the files)

| Component | Props | Emits |
|---|---|---|
| `GateDecision` | `title: string`, `busy?: boolean`, `disabled?: boolean` | `decide` with ONE object: `{ outcome: 'approve' \| 'revise' \| 'reject'; comment: string }` (comment already trimmed) |
| `Field` | `label: string`, `modelValue: string`, `placeholder?`, `hint?`, `error?`, `multiline?` (default `true`), `rows?` (default `4`), `disabled?`, `required?` | `update:modelValue(v: string)` |
| `Button` | `variant?: 'primary' \| 'secondary' \| 'ghost' \| 'danger'`, `size?: 'md' \| 'sm'`, `disabled?`, `busy?`, `type?` | `click` (not emitted while disabled or busy) |
| `CheckRow` | `name: string`, `kind: 'ABSOLUTE' \| 'ADVISORY'`, `ok: boolean`, `detail?: string` | — |
| `Tag` | `tone?: 'neutral' \| 'strong'`, `mono?: boolean` | — (default slot) |
| `Surface` | `elevation?: 'flat' \| 'overlay'`, `padding?: 'none' \| 'sm' \| 'md'`, `as?: string` | — (default slot) |

`GateDecision` is imported from `@kroker/ui/components/gate_decision/GateDecision.vue` (it is not in the barrel; `F/features/run/RunView.vue:15` does the same). The other five are imported from the `@kroker/ui` barrel. Where each is used: contract §3.2 and §3.3.

### 1.3 Traps — the names an executor is most likely to get wrong

| Wrong | Right | Why |
|---|---|---|
| `item.key` | `item.id` | the wire calls it `key`; the client type calls it `id` |
| `item.run_id` | `item.runId` | camelCase on the client |
| `item.kind` | `item.type` | `kind` is the wire's word, and also a field of `CheckRow` |
| `type === 'merge'` | `type === 'override'` | `'merge'` is the value of `OverrideItem.gate` |
| `type === 'stage_gate'` | `type === 'gate'` | wire value vs client value |
| `item.suggested_answer`, `item.suggestedAnswer` | `item.suggestion` | |
| `check.passed` | `check.ok` | |
| `check.classification` | `check.kind` (UPPERCASE values) | |
| `overrideMerge(runId, key, 'approve', text)` | `overrideMerge(runId, key, true, text)` | boolean, not an outcome |
| `resolveEscalation(runId, key, 'reject', text)` | `resolveEscalation(runId, key, false, text)` | boolean, not an outcome |

## 2. New names — added by this feature, used exactly as written here

### 2.1 Added to `F/api/types.ts` (additive only)

```ts
export interface UnreadableRun {
  runId: string
  error: string
}

export interface InboxState {
  items: InboxItem[]
  unreadable: UnreadableRun[]
}
```

and one member added to `DashboardApi`, directly after `listInbox`:

```ts
getInboxState(): Promise<InboxState>
```

| Name | Meaning |
|---|---|
| `listInbox` | existing: the items only. Kept for its existing tests. **The store does not call it.** |
| `getInboxState` | new: the items and the unreadable runs from one snapshot. **The store calls this.** |

### 2.2 Added to `F/api/http.ts`

`export function mapInboxState(snap: any, now: Date = new Date()): InboxState` — items by the same loop `mapSnapshot` uses; `unreadable` from `snap.open_errors ?? []`, each `{ runId: e.run_id, error: e.error }`.

### 2.3 New module `F/shared/entryKey.ts`

`export function entryKey(item: { runId: string; id: string }): string` — returns `JSON.stringify([item.runId, item.id])`.

### 2.4 Store `useInboxStore` (`F/app/inbox.store.ts`, store id `'inbox'`)

| Member | Type | Status | Meaning |
|---|---|---|---|
| `items` | `Ref<InboxItem[]>` | existing, unchanged | the list, in provider order; plain writable ref |
| `drafts` | `Ref<Record<string, string>>` | existing | text in progress, keyed by `entryKey` |
| `editing` | `Ref<Record<string, boolean>>` | existing | answer field open, keyed by `entryKey` |
| `loading` | read-only boolean | existing name | true while at least one refresh is in progress |
| `refresh` | `(): Promise<void>` | existing name | never rejects |
| `setDraft` | `(id: string, v: string): void` | existing, unchanged | callers pass `entryKey(item)` |
| `toggleEdit` | `(id: string): void` | existing, unchanged | callers pass `entryKey(item)` |
| `loaded` | `Ref<boolean>` | new | a result has been applied at least once |
| `loadError` | `Ref<string \| null>` | new | the last refresh failed; cleared by the next applied result |
| `unreadable` | `Ref<UnreadableRun[]>` | new | open runs whose pending state could not be read |
| `inFlight` | `Ref<Set<string>>` | new | entries with an action in flight, by `entryKey`; replaced, never mutated |
| `notice` | `Ref<Record<string, string>>` | new | message shown on an entry, by `entryKey` |
| `answerClarify` | `(runId: string, key: string, answer: string): Promise<void>` | new | same parameters as the client method |
| `decideGate` | `(runId: string, key: string, outcome: GateOutcome, comment: string): Promise<void>` | new | same |
| `overrideMerge` | `(runId: string, key: string, approve: boolean, justification: string): Promise<void>` | new | same |
| `resolveEscalation` | `(runId: string, key: string, retry: boolean, guidance: string): Promise<void>` | new | same |

The four store actions never reject. Behaviour: [contracts/inbox-screen.md](contracts/inbox-screen.md) §2.

### 2.5 Screen components (`F/features/inbox/`)

| File | Props | Emits |
|---|---|---|
| `InboxView.vue` | none (route component) | none |
| `InboxEntry.vue` | `item: InboxItem`, `notice?: string` | none; default slot |
| `ClarifyEntry.vue` | `item: ClarifyItem`, `busy: boolean`, `draft: string`, `editing: boolean` | `answer(text: string)`, `update:draft(v: string)`, `toggle-edit()` |
| `GateEntry.vue` | `item: GateItem`, `busy: boolean` | `decide(outcome: GateOutcome, comment: string)` |
| `OverrideEntry.vue` | `item: OverrideItem`, `busy: boolean`, `draft: string` | `resolve(approve: boolean, text: string)`, `update:draft(v: string)` |
| `EscalationEntry.vue` | `item: EscalationItem`, `busy: boolean`, `draft: string` | `resolve(retry: boolean, guidance: string)`, `update:draft(v: string)` |

### 2.6 Fixed strings

| Where | Text |
|---|---|
| notice, 404 | `already decided elsewhere` |
| notice, other failure | `failed: ` followed by `String(e)` |
| kind label, clarify | `question` |
| kind label, gate | `gate · ` followed by `item.gate` |
| kind label, override | `merge override` |
| kind label, escalation | `escalation` |
| `GateDecision` title | `item.gate`, then ` · round `, then `item.round` |

Test ids and the state texts are in the contract §4.

## 3. Entities and rules

| Entity | Identity | Rules |
|---|---|---|
| Inbox item | `(runId, id)` — `id` is unique only within its run | rendered in provider order; `id` is opaque |
| Entry state | `entryKey(item)` | draft, edit flag, in-flight flag and notice exist only while the item is listed or in flight |
| Unreadable run | `runId` | not an entry; not counted in the badge |

Validation (screen rules only; the backend accepts all of these):

| Action | Rule |
|---|---|
| send a typed answer | trimmed draft is non-empty |
| accept a suggestion | offered only when `suggestion.trim()` is non-empty |
| revise a gate | comment non-empty (`GateDecision` enforces) |
| override a merge | trimmed draft is non-empty (GATE 1, Q2 = A) |
| send back, retry, quarantine, approve, reject | text optional |

## 4. Entry state transitions

```text
idle ──action──▶ in flight ──success──▶ settled ──next later refresh──▶ gone (unlisted)
                     │                     ▲                         └▶ idle (still listed)
                     ├──404───────────────┘   (notice: already decided elsewhere)
                     └──other failure──▶ idle (notice: failed: …; draft kept)
```

"Settled" entries are still in `inFlight`: visible, controls unavailable.

## 5. Name check the executor runs first (FR-014)

Run from the repository root before writing any file, and compare with §1:

```text
Grep  pattern: "^export (interface|type) |^  (id|runId|round|age|type|gate|title|body|suggestion|verdict|checks|analysis|name|kind|ok|detail):"
      path:    interfaces/dashboard/frontend/src/api/types.ts   (lines 1-100)
Grep  pattern: "listInbox|answerClarify|decideGate|overrideMerge|resolveEscalation"
      path:    interfaces/dashboard/frontend/src/api/types.ts
```

The patterns also print names this feature does not use (`Status`, `Run`, `Decision`, the graph methods and so on). That is expected: check only that every name in §1 appears exactly as written.

If any name, value or signature in §1 differs from the file, stop and report to the orchestrator. Do not adapt the plan silently.
