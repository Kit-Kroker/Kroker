# Research: Decision Inbox (010)

Phase 0 of [plan.md](plan.md). Decisions R-1 to R-12, each with its reason and what was rejected. Base: main `39a07a4`. `F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/src/components/`.

**Sources.** My own reading of the code; advisor consult `.workspace/tmp/advisor-010-1.md`; skeptic pass `.workspace/tmp/skeptic-010-1.md`. Nothing was run. Where the two seats disagreed, the ruling and the reason are stated.

## Verified facts the decisions rest on

| # | Fact | Where |
|---|---|---|
| F1 | The store's `refresh` has no catch. `App.vue` awaits it inside `Promise.all` before it starts the poll, so a failed first read means the poll never starts; later failures are unhandled rejections. | `F/app/inbox.store.ts:12-19`, `F/app/App.vue:15-22` |
| F2 | Every poll already makes two `GET /inbox` requests: `listRuns` and `listInbox` each call `snapshot()`. | `F/api/http.ts:171-186` |
| F3 | The `/inbox` response carries `open_errors`: the open runs whose pending state could not be read. The client maps only `errors`, which also holds closed-run failures. Nothing in `F/` reads `open_errors`. | `src/sdlc/dashboard/fleet.py:69-88`, `F/api/http.ts:155-157` |
| F4 | The only client method returning a `FleetState` is `subscribe`, which nothing calls. On the live provider it opens an `EventSource`. The mock's version hard-codes `errors: []`. | `F/api/http.ts:223-227`, `F/api/mock/index.ts:436-444` |
| F5 | `GateDecision` keeps its comment in a local `ref('')`. It has no `v-model` and emits nothing while the operator types. It trims the comment on emit and does not clear it. | `U/gate_decision/GateDecision.vue:12-21` |
| F6 | `Field` props: `label`, `modelValue`, `placeholder?`, `hint?`, `error?`, `multiline?` (default true), `rows?` (default 4), `disabled?`, `required?`. Emits `update:modelValue`. Never trims or validates. | `U/field/Field.vue` |
| F7 | `Button` props: `variant?` (`primary` \| `secondary` \| `ghost` \| `danger`), `size?` (`md` \| `sm`), `disabled?`, `busy?`, `type?`. Emits `click`, suppressed while disabled or busy. | `U/button/Button.vue` |
| F8 | `CheckRow` props `name`, `kind` (`ABSOLUTE` \| `ADVISORY`), `ok`, `detail?` have the same names and types as `CheckRow` in `F/api/types.ts:65-70`. | `U/check_row/CheckRow.vue` |
| F9 | A reply to a key that is no longer pending, or of the wrong kind, is a 404. A reply that was accepted while another surface won the race is a 200 with `confirmed=False`, which the client reads as success. | `src/sdlc/dashboard/api.py:98-114`, `F/api/http.ts:167` |
| F10 | A retry sent as approve-with-text reaches the fix loop as guidance (`decision.guidance or decision.comments`). An override with empty text is accepted by the backend with the reason "advisory override". | `src/sdlc/stages/code/step.py:925`, `src/sdlc/stages/merge/step.py:527-530` |
| F11 | A live deploy gate has an empty summary, so its `body` is `''`. A live clarify key is whatever id the clarify model wrote; it is not always `q1`. The override and escalation `body` texts are written by the client, not sent by the server. | `src/sdlc/stages/deploy/step.py:162`, `F/api/http.ts:117,131` |
| F12 | The mock removes an item by `id` alone, in all four write methods. Its six seeded keys are distinct, and `createMockApi` has no way to seed others. | `F/api/mock/index.ts:318-320,351,367,383,397` |
| F13 | Mock state is created per page load, so one app-tier test cannot affect another. | `F/api/client.ts:14`, `interfaces/ui/app.pw.ts:46-48` |
| F14 | Screens may import `app/*.store.ts`, `shared/`, `api/`, `@kroker/ui`. `shared/` may not import `app/` or `features/`. `app/` may import anything. | `interfaces/AGENTS.md`, `F/app/boundaries.test.ts` |
| F15 | Pinned by existing tests: `app/inbox.store.ts` exists; `features/inbox/InboxView.vue` exists and the router imports it; `setDraft('q1','hello')` writes `drafts['q1']`; `toggleEdit('q1')` sets `editing['q1']`; `AppHeader.test.ts` assigns `inbox.items` directly. | `F/app/boundaries.test.ts:368,533,658`, `F/app/shell.stores.test.ts:27-33`, `F/app/shell/AppHeader.test.ts:17-27` |
| F16 | The run route is named `run`, path `/runs/:id`, hash history. | `F/app/router.ts:12-14` |

## Decisions

### R-1 — The existing app-layer store owns the list, the per-entry state and the writes

**Decision**: extend `F/app/inbox.store.ts`. No second store.

**Rationale**: the rule that releases a busy entry is evaluated when a refresh lands (R-4), so the list and the in-flight set must be one module's state. With one list, the header badge and the screen cannot disagree (FR-002). F14 allows the screen to import it; F15 pins its location.

**Rejected**: a `features/inbox/inbox.store.ts` for writes. It would have to watch or copy the app store's list.

### R-2 — The composite key is `JSON.stringify([runId, id])`, in `shared/entryKey.ts`

**Decision**: one pure function `entryKey(item: { runId: string; id: string }): string`. It is the `v-for` key and the key of `drafts`, `editing`, `inFlight` and `notice`. `setDraft` and `toggleEdit` keep their signatures; callers pass `entryKey(item)`.

**Rationale**: run ids are Temporal workflow ids and item keys are free-form (`#` already occurs). No separator can be proved absent from both. Encoding the pair as JSON is collision-free for any two strings and needs no escaping rule. `shared/` is importable by both the store and the screen (F14). The existing store test stays valid because the store does not interpret the key (F15).

**Rejected**: `runId + ':' + id` (skeptic): `('a:b','c')` and `('a','b:c')` collide. An overloaded `setDraft(runId, id, value)` (skeptic): changes a pinned signature for no gain. Putting the helper in `api/types.ts` (frozen by FR-014) or in the store file (a screen would import a store to get a helper).

**Consequence**: the key is not readable in the DOM. No `data-testid` embeds it; entries carry `data-run-id` and `data-key` instead.

### R-3 — No new `@kroker/ui` component; one frame and four kind components in the screen folder

**Decision**: `F/features/inbox/` holds `InboxView.vue` (states and list), `InboxEntry.vue` (the frame: kind, run link, age, title, body, notice, slot) and `ClarifyEntry.vue`, `GateEntry.vue`, `OverrideEntry.vue`, `EscalationEntry.vue`. Each kind component is typed with its own variant from `F/api/types.ts`. `InboxView` chooses with a `v-if` / `v-else-if` chain on `item.type`, so the type checker narrows the prop. Kind components hold no state: draft text comes in as a prop and goes out as an event.

**Rationale**: F5 to F8 show the library already has every control. Not adding a library component keeps the five-file rule and the showcase registry out of this feature. FR-003 is written once, in the frame. Four small typed files mean a wrong field name fails in one file at type-check time, which is the defence against the drift that sank the first attempt.

**Rejected**: one component with four branches (a rename breaks all four at once). A library "inbox card" (it would need domain types, which the library must not import). `<component :is>` (loses narrowing).

### R-4 — One rule for when a busy entry is released

**Decision**: the store counts refreshes as they start. A refresh result is applied only if it started later than the last one applied. When a write succeeds, or is refused with a 404, the store records the current start count against that entry and then refreshes. An entry is released by the first applied refresh that started after that record. The full rule is in [contracts/inbox-screen.md](contracts/inbox-screen.md) §2.

**Rationale**: a poll that started before a write can land after it and put the decided entry back with live controls. Recording the count when the write *finishes*, not when it starts, covers a read the server answered before applying the write. Success and 404 share one path, so no separate lost-race set is needed. The same check also fixes two overlapping polls landing out of order, which can happen today.

**Judgement call, recorded**: on release, an entry the server still lists becomes usable again. `runGraph.store.ts` instead keeps a key busy until it is unlisted. The inbox has no push state, so an entry the server relists would otherwise be stuck until a page reload. The cost is a possible second send on a still-listed item; the server answers that with a 404, which FR-009 already handles. This also covers F9's `confirmed=False` case.

**Rejected**: removing the entry locally on success (it still needs a guard against a stale refresh, so it is this rule plus extra state).

### R-5 — FR-011 is met by one added client method, `getInboxState`

**Decision**: add to `F/api/types.ts`, without changing anything already there:

```ts
export interface UnreadableRun { runId: string; error: string }
export interface InboxState { items: InboxItem[]; unreadable: UnreadableRun[] }
// in DashboardApi:
getInboxState(): Promise<InboxState>
```

The live provider builds it with a new exported mapper `mapInboxState(snap, now)` that reads `open_errors` (F3). The mock returns its items and an empty `unreadable`. The store calls `getInboxState()` **instead of** `listInbox()`.

**Rationale**: FR-011 needs the unreadable runs and the items from the *same* snapshot; two calls could pair six items from one snapshot with "no unreadable runs" from another. Replacing the store's call keeps the request count at two per poll (F2). FR-014 forbids changing existing names and signatures; it does not forbid adding. `listInbox`, `mapSnapshot` and `FleetState` are untouched.

**Rejected**: `subscribe` (F4: mixed error list, an untested transport, mock hard-codes empty). A second method called beside `listInbox` (a third request, and skew). Narrowing FR-011 (not needed; this is cheap).

**Flag for GATE 2**: this is the one place the plan adds to the client contract. It is additive and both seats accept it, but it is the user's contract.

### R-6 — `refresh` never rejects, and the store knows whether it has ever loaded

**Decision**: `refresh` catches a failed read, records `loadError`, and keeps the last known list. A `loaded` flag becomes true at the first applied result.

**Rationale**: F1. Without `loaded`, the first paint shows "nothing is waiting" because the store starts empty. Nothing relies on `refresh` throwing (skeptic L6).

**Out of scope**: `fleet.store.ts` has the same shape. It is filed as an inbox task, not changed here.

### R-7 — Gate entries reuse `GateDecision`; its comment stays inside the component

**Decision**: `GateEntry.vue` wraps `GateDecision` unchanged.

**Rationale**: it already carries the three actions, the revise-needs-a-comment rule and the busy lock, with its own contract clauses, and it is the control the run canvas uses for the same decision. Its comment survives a refresh because the component instance survives, and it is distinct per entry because the `v-for` key is the composite key. That meets FR-012, SC-004 and SC-005 for gates, and a unit test proves it with two runs on the same key.

**Rejected**: rebuilding the gate entry from `Field` + `Button` so the comment lives in the store (skeptic). It would duplicate a rule the library already owns and tests, and give the same decision two different controls on two screens.

**Stated limitation**: a gate comment in progress is lost if the operator leaves the inbox page. Text for the other three kinds is in the store and survives. Recorded as a follow-up, not fixed here, because fixing it means changing a library component.

### R-8 — A persistent notice on the entry, not a toast

**Decision**: failures and "already decided elsewhere" are shown on the entry itself, from `notice[entryKey]`. No toast.

**Rationale**: toasts disappear after 3.8 s. An entry refused with a 404 stays on screen, disabled, until the next refresh; the operator needs the reason to stay with it.

### R-9 — The mock is not changed beyond the added method

**Decision**: add `getInboxState` to the mock. Do not change `removeItem` and do not add a seeded item.

**Rationale**: F12. Fixing `removeItem` touches five places and no test could fail without it, because the mock cannot hold two runs on one key. An unpinned change is how the first attempt drifted. A seventh item would break the "6 inbox items" pin and CONSOLE-2's badge. SC-004 is proved at the unit tier with the real store and a fake client. The mock defect is filed as an inbox task.

### R-10 — Which test tier proves what

**Decision**: the app tier (Playwright on the mock build) proves what the mock can produce: the list, the badge count, the four kinds of action, the empty state after all six are resolved, the run link, and the canvas no longer offering a gate decided in the inbox. The unit tier (Vitest) proves what it cannot: load failure, unreadable runs, the 404 path, the stale-refresh race, two runs on one key, and text surviving refreshes.

**Rationale**: the mock does not use `fetch` and has no hook to fail a read or report an unreadable run. It *can* refuse a write: every write method throws a 404 when the item is no longer pending (`F/api/mock/index.ts:350,366,382,396`). But the only way to reach that from the screen is to decide an item elsewhere (the run canvas) and then act on the same inbox entry before the 5 s poll removes it. A test of that would pass or fail on timing, so the 404 path is proved at the unit tier with a fake client instead. FR-013 asks for app-tier coverage of shipped behaviour "against the mock provider"; it cannot ask for what that provider cannot do. The split is listed clause by clause in the contract §6 so that it is not read as a gap.

### R-11 — What does not change

- The canvas's "pending — inbox" link stays `to="/inbox"` with no query. Focusing one entry is a new routing contract and is not in scope.
- Entries are rendered in the order given. No sort (assumption A1).
- No change to `App.vue`, `router.ts`, `RunView.vue`, `AppHeader.vue`, `boundaries.test.ts`, the mock's seed, or any `@kroker/ui` file other than `app.md` and `app.pw.ts`.
- The badge counts items only. Unreadable runs are not entries (FR-002).

### R-12 — Text rules

- Every text sent is trimmed. `GateDecision` already trims.
- Accept sends `item.suggestion.trim()`. A suggestion that is empty after trimming counts as no suggestion: no accept action, and the answer field is shown directly (EC7).
- Opening the answer field copies the suggestion into the draft only if the draft is empty.
- An override needs a non-empty trimmed justification (Q2 = A). A send-back, a retry and a quarantine may carry empty text. Override and send-back share one draft per entry.
- Item ids are opaque. Nothing parses or slices them (F11).
- An empty `body`, `verdict` or `analysis` renders nothing, not an empty box (F11, EC7).

## Open items

None blocking. Three follow-ups are filed in `.workspace/tasks/` (see plan.md, "Follow-ups filed").
