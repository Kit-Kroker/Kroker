# Contract: the inbox screen, its store and its client method (010)

Phase 1 of [plan.md](plan.md). Names are defined in [data-model.md](../data-model.md) and are used here exactly. `F/` = `interfaces/dashboard/frontend/src/`.

## 1. Client method `getInboxState`

- Returns `InboxState`: `items` and `unreadable` taken from **one** snapshot.
- Live provider: `mapInboxState(await json('/inbox'))`. `items` are produced by the same per-item mapping `mapSnapshot` uses, in the same order. `unreadable` is `snap.open_errors ?? []` mapped to `{ runId, error }`. A payload with no `open_errors` gives `[]`.
- Mock: after its usual delay, `{ items: <a copy of its inbox>, unreadable: [] }`.
- `listInbox`, `mapSnapshot`, `FleetState` and `subscribe` are not changed.

## 2. Store behaviour (`useInboxStore`)

Private state: `startSeq` (refreshes started), `appliedSeq` (start number of the newest applied result), `settledAt` (`entryKey` → `startSeq` when that entry's write finished), `pending` (refreshes in progress; `loading` is `pending > 0`).

### 2.1 `refresh()`

```text
mine = ++startSeq; pending = pending + 1
try   r = await api.getInboxState()
catch e: loadError = String(e); return            // items, unreadable, inFlight, drafts untouched
finally: pending = pending − 1                     // on every exit, success or failure
if mine <= appliedSeq: return                      // an older overlapping read; drop it
appliedSeq = mine
items = r.items; unreadable = r.unreadable; loadError = null; loaded = true
for each key in settledAt with mine > settledAt[key]:
    remove key from inFlight and from settledAt
remove from drafts, editing and notice every key that is neither listed in items nor in inFlight
```

`refresh` never rejects.

### 2.2 The four actions

Each action computes `k = entryKey({ runId, id: key })` and runs:

```text
if inFlight has k: return                          // checked before any await
inFlight = inFlight + k; delete notice[k]
try
    await api.<same-named method>(runId, key, …)
    settledAt[k] = startSeq; await refresh()
catch e
    if isNotFound(e): notice[k] = 'already decided elsewhere'; settledAt[k] = startSeq; await refresh()
    else:             notice[k] = 'failed: ' + String(e); inFlight = inFlight − k
```

Actions never reject. They do not clear `drafts`; a draft goes when its entry goes (§2.1 last line).

### 2.3 Guarantees and the requirement each one serves

| Guarantee | Serves |
|---|---|
| `items.length` is the only count; the header reads the same ref | FR-002 |
| a second call for an entry in flight sends nothing | FR-010, EC5 |
| a read that started before a write finished can neither re-enable nor remove that entry | FR-008, FR-010 |
| after a 404 the entry stays, unavailable, with its notice, until a later refresh | FR-009, EC2 |
| after another failure the entry is usable again and its draft is intact | FR-009, EC3 |
| a failed refresh changes nothing but `loadError` | FR-011, EC9 |
| a refresh never clears the draft of a listed entry | FR-012, EC4, SC-005 |
| two runs sharing a key have separate drafts, flags and notices | FR-012, EC1, SC-004 |

## 3. Screen behaviour (`InboxView.vue`)

### 3.1 States (FR-011)

Exactly one of the first three, or the list:

| Condition | Shown | Test id |
|---|---|---|
| `!loaded && !loadError` | `loading…` | `inbox-loading` |
| `!loaded && loadError` | `The inbox could not be loaded.` | `inbox-load-error` |
| `loaded && items.length === 0 && unreadable.length === 0 && !loadError` | `Nothing is waiting.` | `inbox-empty` |
| otherwise | the list (possibly empty), with the banner below when it applies | — |

Banner `inbox-incomplete`, above the list, when `loaded` and (`unreadable.length > 0` or `loadError`):

- `unreadable.length > 0`: `This list may be incomplete: the pending state of N run(s) could not be read.` followed by the run ids.
- `loadError`: `The inbox could not be refreshed; showing the last known list.`

When both hold (the last refresh failed and the last applied result had unreadable runs), the banner shows both lines, the `loadError` line first.

With zero items and a banner, `inbox-empty` is **not** shown.

A heading row shows `Decision inbox` and the count `N waiting` (`inbox-count-line`), where N is `items.length`.

### 3.2 Entry frame (`InboxEntry.vue`) — FR-003

Root: `<Surface as="article" elevation="flat" padding="md">` carrying `data-testid="inbox-entry"`, `data-run-id`, `data-key` (the item's `id`), `data-type` (the item's `type`). Contents, in order: kind label (`inbox-entry-kind`, a `<Tag tone="neutral" mono>`), run link (`inbox-entry-run`, text = `runId`, `<RouterLink :to="{ name: 'run', params: { id: item.runId } }">`), age (`inbox-entry-age`), title (`inbox-entry-title`), body (`inbox-entry-body`, only when `body` is non-empty), notice (`inbox-notice`, only when present), then the slot.

**Long text (EC8).** The four free-text blocks (`inbox-entry-body`, `inbox-suggestion`, `inbox-verdict`, `inbox-analysis`) each carry the class `inbox-longtext`. That class wraps long words and lines, keeps line breaks, and limits the block's height with its own vertical scroll, so a long text never pushes the entry's actions off the screen or widens the page. Proof: `entries.test.ts` asserts the class on all four blocks (jsdom cannot measure layout), and the quickstart walk checks it by eye on the escalation entry, whose seeded analysis is the longest text in the mock.

### 3.3 Kind components

| Component | Shows | Actions (test id → event) |
|---|---|---|
| `ClarifyEntry` | the suggestion (`inbox-suggestion`) when non-empty after trimming; a `Field` labelled `Answer` when `editing` is true or there is no suggestion | `inbox-accept` → `answer(item.suggestion.trim())`, only with a suggestion; `inbox-edit` → `toggle-edit`, only with a suggestion; `inbox-send` → `answer(draft.trim())`, unavailable while the trimmed draft is empty |
| `GateEntry` | `GateDecision` with the title from the name table and `:busy` | `GateDecision` emits `decide` with ONE object `{ outcome, comment }`; `GateEntry` re-emits it as two arguments, `decide(d.outcome, d.comment)` (the same adaptation as `F/features/run/RunView.vue:122`) |
| `OverrideEntry` | the verdict (`inbox-verdict`) when non-empty; one `CheckRow` per check, bound with `v-bind="check"`; a `Field` labelled `Justification`, `required` | `inbox-override` → `resolve(true, draft.trim())`, unavailable while the trimmed draft is empty; `inbox-send-back` → `resolve(false, draft.trim())` |
| `EscalationEntry` | the analysis (`inbox-analysis`) when non-empty; a `Field` labelled `Guidance` | `inbox-retry` → `resolve(true, draft.trim())`; `inbox-quarantine` → `resolve(false, draft.trim())` |

`Button` props for the new actions (all `size="sm"`): `inbox-accept`, `inbox-send`, `inbox-override` and `inbox-retry` are `variant="primary"`; `inbox-edit` and `inbox-send-back` are `variant="secondary"`; `inbox-quarantine` is `variant="danger"`. The test id goes on the `Button` and falls through to its root `<button>`.

While `busy`, every action and field of that entry is unavailable. Kind components keep no state of their own (except `GateDecision`'s internal comment, research R-7).

### 3.4 Wiring in `InboxView`

For each `item` with `k = entryKey(item)`: `:key="k"`, `busy = inFlight.has(k)`, `draft = drafts[k] ?? ''`, `editing = editing[k] ?? false`, `notice = notice[k]`.

| Event | Call |
|---|---|
| `update:draft(v)` | `setDraft(k, v)` |
| `toggle-edit` | if `drafts[k]` is empty, `setDraft(k, item.suggestion)`; then `toggleEdit(k)` |
| clarify `answer(text)` | `answerClarify(item.runId, item.id, text)` |
| gate `decide(outcome, comment)` | `decideGate(item.runId, item.id, outcome, comment)` |
| override `resolve(approve, text)` | `overrideMerge(item.runId, item.id, approve, text)` |
| escalation `resolve(retry, guidance)` | `resolveEscalation(item.runId, item.id, retry, guidance)` |

The view does not start its own poll and does not call `refresh` on mount: `App.vue` already loads and polls the store.

## 4. Test ids (complete list)

Existing: `inbox-view`. From library components: `gate-decision`, `gate-comment`, `gate-approve`, `gate-revise`, `gate-reject`, `field-control`, `field-error`, `field-hint`, `check-row`.

New: `inbox-loading`, `inbox-load-error`, `inbox-empty`, `inbox-incomplete`, `inbox-count-line`, `inbox-entry`, `inbox-entry-kind`, `inbox-entry-run`, `inbox-entry-age`, `inbox-entry-title`, `inbox-entry-body`, `inbox-notice`, `inbox-suggestion`, `inbox-accept`, `inbox-edit`, `inbox-send`, `inbox-verdict`, `inbox-override`, `inbox-send-back`, `inbox-analysis`, `inbox-retry`, `inbox-quarantine`.

One new CSS class is part of the contract: `inbox-longtext` (§3.2).

App-tier locators are scoped to `[data-testid="inbox-view"]`, because `gate-decision` also appears on the run page. An entry is located by `[data-testid="inbox-entry"][data-run-id="…"][data-key="…"]`.

## 5. New assembled-console clauses (`interfaces/ui/app.md`)

Appended after CONSOLE-16. Wording to use:

- **CONSOLE-17** — The inbox renders one entry per item the provider reports as waiting, each showing its kind, its run, its age and its title; the number of entries equals the header's inbox badge; and an entry's run link opens that run's page. [FR-601, FR-305]
- **CONSOLE-18** — On a clarify entry, accepting the suggestion sends it with that one action; a typed answer is sent only when it is not blank. Either way the entry leaves the list and the badge drops by one. [FR-601]
- **CONSOLE-19** — On a gate entry, approve and reject send at once and revise is unavailable until a comment is entered; a decided entry leaves the list. [FR-601, FR-301/302]
- **CONSOLE-20** — A merge override entry shows the verdict and one check row per check; override is unavailable until a justification is entered, and send-back is not; a resolved entry leaves the list. [FR-601, FR-304]
- **CONSOLE-21** — An escalation entry shows the analysis; retry and quarantine each resolve it, with or without guidance, and the entry leaves the list. [FR-601]
- **CONSOLE-22** — When every waiting item has been resolved the inbox shows its explicit empty state and the header shows no inbox badge. [FR-601]
- **CONSOLE-23** — A gate decided in the inbox is no longer offered for decision on that run's canvas. [FR-601, FR-302]

Clause to user story: CONSOLE-17 → US1; CONSOLE-18 → US2; CONSOLE-19 and CONSOLE-23 → US3; CONSOLE-20 and CONSOLE-21 → US4; CONSOLE-22 → US1 (acceptance scenario 4), which needs all four kinds built and so lands last.

The "Failure modes" paragraph of `app.md` gains one sentence: the inbox's load-failure, incomplete-list and already-decided states are pinned at the unit tier (`inbox.store.test.ts`, `InboxView.test.ts`): the mock provider cannot fail a read or report an unreadable run, and it refuses a write only in the few seconds between a decision taken on another screen and the next poll, which a test cannot hit reliably.

## 6. Requirement → proof

| Requirement | App tier (`app.pw.ts`) | Unit tier (Vitest) |
|---|---|---|
| FR-001, FR-002, FR-003 | CONSOLE-17 | `InboxView.test.ts` (order preserved, fields, empty body omitted) |
| FR-004 | CONSOLE-18 | `entries.test.ts` (no suggestion → no accept; blank answer not sent; whitespace suggestion) |
| FR-005 | CONSOLE-19 | `entries.test.ts` (decide re-emitted with outcome and comment) |
| FR-006 | CONSOLE-20 | `entries.test.ts` (override blocked on blank; send-back allowed blank; boolean argument) |
| FR-007 | CONSOLE-21 | `entries.test.ts` (retry = true, quarantine = false; blank guidance allowed) |
| FR-008 | CONSOLE-18 to CONSOLE-23 | `inbox.store.test.ts` (stale read after a write) |
| FR-009 | — (the mock refuses only inside a race with the 5 s poll; not deterministic, research R-10) | `inbox.store.test.ts` (404 path; other-failure path), `InboxView.test.ts` (notice shown) |
| EC8 | — | `entries.test.ts` (`inbox-longtext` on the four text blocks); quickstart §2 by eye |
| FR-010 | — | `inbox.store.test.ts` (double call sends once), `InboxView.test.ts` (busy entry only) |
| FR-011 | CONSOLE-22 (empty state) | `InboxView.test.ts` (loading, load error, incomplete with and without items), `http.test.ts` (`mapInboxState`) |
| FR-012 | — (mock keys are distinct) | `entryKey.test.ts`, `inbox.store.test.ts`, `InboxView.test.ts` (two runs, one key; text survives two refreshes; gate comments stay separate) |
| FR-013 | the seven clauses above | — |
| FR-014 | — | `vue-tsc` (typecheck step of `check_ui.py`); data-model §5 check |
| FR-015 | — | `boundaries.test.ts` (unchanged, must stay green); `check_file_size.py` |
| FR-021 | — | review of the three documents |
