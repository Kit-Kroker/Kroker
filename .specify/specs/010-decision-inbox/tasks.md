# Tasks: Decision Inbox (FR-601)

**Input**: `.specify/specs/010-decision-inbox/` (spec.md, plan.md, research.md, data-model.md, contracts/inbox-screen.md, quickstart.md)

**Tests**: required (spec FR-013; plan "Work order"; contract §6). Each change is preceded by its RED task. A test marked PIN pins behaviour that already exists and is expected to pass on first run; a red PIN is a stop-guard, not a cue to edit source.

**Scope**: US1 to US4 only. US5, US6, FR-016 to FR-020 and SC-007 were not selected at GATE 1 and have no task.

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`. "Contract" = `contracts/inbox-screen.md`. "Names" = `data-model.md`.

## Standing rules for every task

- **Names (FR-014).** `data-model.md` is the only source of names: types, fields, discriminant values, method signatures, store members, props, events, fixed strings. The contract §4 is the only source of test ids. Copy; do not retype from memory. If a name you need is in neither file, stop (SG-1). Read data-model §1.3 (the traps table) before every task that touches a `.vue` or `.ts` file.
- **Keys (FR-012).** A per-entry key is formed only by `entryKey(item)`. No map lookup, set membership or `:key` may use `item.id` or `key` alone. The reviewer checks this on every diff that touches the store or the view.
- **Convergence.** A task is not done while `vue-tsc` or Vitest is red. Run them through `python scripts/check_ui.py`; do not call `npm`, `npx`, `vitest` or `playwright` directly for a gate. One test run per shell call, never two chained.
- **Run environment.** The one the orchestrator names in the exec brief. Node must be present: `check_ui.py` exits 0 with a loud "skipped" when it is not, and a skip is not a pass (SG-6).
- **RED tasks** are written by the qa seat and must be seen failing on the branch for the stated reason before the paired implementation task starts. Their files are committed in the implementation task's commit, so no commit on the branch is red. The reviewer gate still applies to each RED diff on its own.
- **Commit**: subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument. The host shell may be PowerShell 5.1: no heredocs; write every file with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`, before T002.
- **Forbidden paths**: `F/app/App.vue`, `F/app/router.ts`, `F/app/boundaries.test.ts`, `F/app/shell/`, `F/features/run/`, `F/features/fleet/`, `F/features/board/`, `F/features/graphs/`, `F/shared/fleet.store.ts`, `F/shared/fleet.store.test.ts`, `F/api/client.ts`, `F/api/errors.ts`, `F/api/__fixtures__/`, everything under `U/src/` and `U/showcase/`, every Python file, every `AGENTS.md`, `CLAUDE.md`, `package.json` and lock files, earlier `.specify/specs/*`, and the user's uncommitted files in the primary checkout. In `F/api/types.ts` only additions are allowed. In `F/api/mock/index.ts` only the one added method is allowed: the seed and `removeItem` do not change. In `F/api/http.ts` `mapSnapshot` and the existing methods do not change.
- **Styles**: tokens only (`var(--*)` from `U/src/tokens/tokens.css`, pass-three names for new code); no bare hex in a component. Playwright assertions carry no hex and no pixel values.
- Line numbers in the spec set are as of main `39a07a4`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name, test id or rule is needed that the spec set does not define, or the T001 name check differs from data-model §1.
- **SG-2** An edit to a forbidden path appears necessary, or a change to an existing name or signature in `F/api/types.ts`.
- **SG-3** An existing test fails after a change and this file does not name it as an intended edit (only `F/app/shell.stores.test.ts` and `F/app/App.test.ts`, in T007). Do not edit the test to pass.
- **SG-4** A test this file marks RED passes before its implementation task, or a test marked PIN is red.
- **SG-5** `python scripts/check_clauses.py` reports a `CONSOLE-17`…`CONSOLE-23` clause with no test, or a dangling citation, at the end of a phase that added that clause.
- **SG-6** `check_ui.py` reports a skipped step, or a test in a file this feature does not touch times out or fails (known load flake: `.workspace/tasks/2026-10-03-check-ui-wrapper-timeout-flake.md`). Report it; do not "fix" it.
- **SG-7** Any file would exceed 1000 lines, or a new `@kroker/ui` component appears necessary.

## Phase order

| Phase | Purpose | Story | Plan step | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | known-green start, name check | — | 0 | 1 |
| 2 Foundation | key, client method, store | all | 1 to 3 | 3 |
| 3 The list | see everything waiting | US1 | 4, 5, 6 | 1 |
| 4 Clarify | answer a question | US2 | 4, 5, 6 | 1 |
| 5 Gates | decide a gate | US3 | 4, 5, 6 | 1 |
| 6 Override and escalation | resolve the two rarer kinds | US4 | 4, 5, 6 | 1 |
| 7 Close-out | empty state end to end, documents, gates | US1, all | 6 to 8 | 3 |

T022 is the one story-labelled task outside phases 3 to 6: it proves US1's acceptance scenario 4 but needs all four kinds built.

---

## Phase 1: Setup and baseline (no source edits)

- [x] T001 Create branch `010-decision-inbox` from current main in the worktree the orchestrator names. The spec set was verified on `39a07a4`; main has since gained `18de7f1`, which touches nothing under `interfaces/`, `README.md` or `ROADMAP.md`. Confirm with `git diff --stat 39a07a4 HEAD -- interfaces README.md ROADMAP.md` that this is still so for the commit you branch from (SG-1 if it prints anything). Run `python scripts/check_ui.py` once and `python scripts/check_clauses.py` once. Run the name check of data-model §5 against `interfaces/dashboard/frontend/src/api/types.ts` and compare with data-model §1 (SG-1 on any difference). Record in `.specify/specs/010-decision-inbox/baseline.md`: the base sha, each `check_ui.py` step's result, the Vitest pass counts for both workspaces, the Playwright pass count, any pre-existing failure, the `check_clauses.py` summary, the name-check outcome, and the line counts of `F/app/inbox.store.ts`, `F/api/http.ts`, `F/api/mock/index.ts`, `U/app.md` and `U/app.pw.ts`. Commit (spec set + baseline).

**Checkpoint**: baseline.md holds a fully green `check_ui.py`; `git diff 39a07a4 --stat -- interfaces` is empty. The base sha recorded in baseline.md is the one later tasks diff against.

---

## Phase 2: Foundation (blocks every story)

**Purpose**: the composite key, the one added client method, and the store rules. No markup yet.

### The key (plan step 1; research R-2)

- [x] T002 RED: create `interfaces/dashboard/frontend/src/shared/entryKey.test.ts` with three tests of `entryKey` from `./entryKey`: (1) two items with different `runId` and the same `id` (`'architecture#1'`) give different keys; (2) the pair `{runId:'a:b', id:'c'}` and `{runId:'a', id:'b:c'}` give different keys; (3) the same `runId` and `id` give the same key on two calls, and extra fields on the object do not change it. Fails because the module does not exist.
- [x] T003 Create `interfaces/dashboard/frontend/src/shared/entryKey.ts` exactly as data-model §2.3 (one exported function, no imports). T002 goes green. Commit T002 + T003.

### The client method (plan step 2; research R-5; contract §1)

- [x] T004 RED: add to `interfaces/dashboard/frontend/src/api/http.test.ts` a `describe('mapInboxState')` with: (1) on the existing fixture `./__fixtures__/fleet-snapshot.json`, `items` deep-equals `mapSnapshot(snapshot, NOW).inbox` and `unreadable` is `[]`; (2) on a copy of the fixture with `open_errors: [{ run_id: 'r9', error: 'boom' }]`, `unreadable` is `[{ runId: 'r9', error: 'boom' }]`; (3) on a copy with the `open_errors` key deleted, `unreadable` is `[]`; (4) on a copy to which the test adds one `errors` entry (`{ run_id: 'rc', error: 'summary failed' }`; the fixture's own `errors` is empty) while `open_errors` stays empty, `unreadable` is `[]` (closed-run failures are not unreadable runs). Add to `interfaces/dashboard/frontend/src/api/mock/index.test.ts` one test: `getInboxState()` returns six `items` equal to `listInbox()` and `unreadable` `[]`. All fail (missing export / missing method). The existing "seeds 10 runs and 6 inbox items" test is a PIN and stays untouched.
- [x] T005 In `interfaces/dashboard/frontend/src/api/types.ts` add `UnreadableRun`, `InboxState` and the `getInboxState` member directly after `listInbox`, exactly as data-model §2.1 (additions only). In `interfaces/dashboard/frontend/src/api/http.ts` add the exported `mapInboxState` (data-model §2.2; reuse `mapPending`; do not edit `mapSnapshot`) and `getInboxState` in the object `createHttpApi` returns, placed after `listInbox`. In `interfaces/dashboard/frontend/src/api/mock/index.ts` add `getInboxState` after `listInbox` (contract §1). `vue-tsc` proves both providers implement the widened interface. T004 goes green. Commit T004 + T005.

### The store (plan step 3; research R-1, R-4, R-6, R-8; contract §2)

- [x] T006 RED: create `interfaces/dashboard/frontend/src/app/inbox.store.test.ts`. Fake `../api/client` with `vi.hoisted` + `vi.mock` (pattern: `F/features/run/RunView.test.ts:16-22`), providing `getInboxState`, `answerClarify`, `decideGate`, `overrideMerge`, `resolveEscalation` as `vi.fn()` whose promises the test resolves or rejects by hand; build rejections with `HttpStatusError` from `../api/errors`. Tests, named for the contract §2.3 guarantees: (1) `refresh` applies `items` and `unreadable`, sets `loaded`, clears `loadError`; (2) a rejected read sets `loadError`, leaves `items`/`unreadable`/`loaded` as they were, and `refresh()` resolves (does not reject); (3) two overlapping refreshes that land in reverse order: the older result is dropped; (4) `loading` is true while any refresh is in progress and false after both of two overlapping ones finish; (5) each of the four actions calls the same-named client method with exactly the arguments it was given (assert the boolean third argument for `overrideMerge` and `resolveEscalation`); (6) a second call for the same run and key while the first is in flight sends nothing; (7) stale read: a refresh started before a write finishes and landing after it neither removes the entry from `inFlight` nor is its list allowed to free the entry, and the entry is released by the refresh the action itself starts; (8) 404: `notice[k]` is `already decided elsewhere`, the entry stays in `inFlight` until the next later-started refresh, then leaves `inFlight`; (9) other failure: `notice[k]` starts with `failed: `, the entry leaves `inFlight` at once, `drafts[k]` is unchanged, the action resolves; (10) a failed refresh while an entry is settled leaves it in `inFlight`; (11) after a write, an entry the server still lists is released and usable, with its draft; (12) on an applied refresh, `drafts`/`editing`/`notice` for keys neither listed nor in flight are removed, and those of listed keys are kept; (13) two runs sharing `id` `'q1'`: `setDraft(entryKey(a), 'x')` leaves `drafts[entryKey(b)]` undefined, and `answerClarify` for run A puts only A's key in `inFlight`; (14) PIN: `setDraft('q1','hello')` writes `drafts['q1']` and `toggleEdit('q1')` sets `editing['q1']` (the existing signatures). Tests 1 to 13 fail; 14 passes.
- [x] T007 Rewrite `interfaces/dashboard/frontend/src/app/inbox.store.ts` to the contract §2 and data-model §2.4: keep store id `'inbox'`, `items` as a plain writable ref, `drafts`, `editing`, `setDraft`, `toggleEdit` unchanged; `refresh` calls `api.getInboxState()` (not `listInbox`) and never rejects; `loading` derived from the in-progress count; add `loaded`, `loadError`, `unreadable`, `inFlight` (replaced, never mutated), `notice` and the four actions, all routed through one private send helper that implements §2.2. Imports: `../api/client`, `../api/errors` (`isNotFound`), `../api/types`, `../shared/entryKey`. Then the two intended edits to existing tests (plan, "Existing tests changed on purpose"): in `interfaces/dashboard/frontend/src/app/shell.stores.test.ts` and `interfaces/dashboard/frontend/src/app/App.test.ts` add `getInboxState` to the api fake with the values given there; change nothing else in either file. T006 goes green; every pre-existing test stays green (SG-3). Commit T006 + T007.

**Checkpoint**: `check_ui.py` green. The header badge still shows 6 on the mock build (CONSOLE-2 passes). The inbox route still shows the stub.

---

## Phase 3: User Story 1 — see everything that is waiting (P1) 🎯 MVP

**Goal**: the inbox lists every waiting item with kind, run link, age, title and body; its count equals the badge; loading, load-failure, incomplete and empty states are honest (FR-001, FR-002, FR-003, FR-011, FR-012).

**Independent test**: Vitest files `InboxView.test.ts` and `entries.test.ts`; app tier CONSOLE-17.

- [x] T008 [US1] RED: create `interfaces/dashboard/frontend/src/features/inbox/entries.test.ts` with a `describe('InboxEntry')`: mounted with a `GateItem` literal and a `RouterLink` stub (pattern: `RunView.test.ts:24`), the root carries `data-testid="inbox-entry"`, `data-run-id`, `data-key`, `data-type`; kind label, age, title and body render under their test ids; the kind label for each of the four `type` values is the fixed string of data-model §2.6; the run link's `to` is `{ name: 'run', params: { id: item.runId } }`; an empty `body` renders no `inbox-entry-body`; `notice` renders `inbox-notice` only when given; the body carries the class `inbox-longtext`; slot content renders after the notice. Create `interfaces/dashboard/frontend/src/features/inbox/InboxView.test.ts`: mount with a real Pinia and the store seeded directly (assign `items`, `loaded`, `loadError`, `unreadable`); tests for contract §3.1: (1) not loaded, no error → `inbox-loading` only; (2) not loaded, error → `inbox-load-error` only, no `inbox-empty`; (3) loaded, no items, nothing unreadable → `inbox-empty`; (4) loaded with items → one `inbox-entry` per item in the given order, and `inbox-count-line` reads `N waiting`; (5) loaded, zero items, one unreadable run → `inbox-incomplete` naming the run id, and no `inbox-empty`; (6) loaded with items and `loadError` → `inbox-incomplete` with the could-not-refresh line and the list still shown; (7) both conditions → both lines, the could-not-refresh line first; (8) two items with different `runId` and the same `id` render two entries with different `data-run-id`. All fail (components missing / stub).
- [x] T009 [US1] Create `interfaces/dashboard/frontend/src/features/inbox/InboxEntry.vue` (contract §3.2; names §2.5 and §2.6; `Surface` and `Tag` as specified; the `inbox-longtext` class defined here in a second, unscoped `<style>` block, because the kind components that use it are separate components; everything else in the file is `<style scoped>`). Replace the stub in `interfaces/dashboard/frontend/src/features/inbox/InboxView.vue` with the heading row, the states and banner of contract §3.1, and the list: `v-for` over `inbox.items` with `:key="entryKey(item)"`, rendering `InboxEntry` with `:item` and `:notice`. Keep `data-testid="inbox-view"` and `data-screen-label="Decision inbox"` on the root. No kind component yet: the slot is empty. No poll and no `refresh` on mount (contract §3.4). T008 goes green.
- [x] T010 [US1] In `interfaces/ui/app.md` append clause `### CONSOLE-17` after CONSOLE-16 with the wording of contract §5. In `interfaces/ui/app.pw.ts` add one test citing `// clause: CONSOLE-17` on the test line: go to `/#/inbox`; expect six `[data-testid="inbox-view"] [data-testid="inbox-entry"]`; the header `inbox-count` reads `6`; the entry `[data-run-id="feature-add-sso"][data-key="q1"]` shows non-empty kind, age and title; clicking its `inbox-entry-run` link shows `[data-testid="run-view"]`. Run `check_ui.py`, then `check_clauses.py` (SG-5). Commit T008 + T009 + T010.

**Checkpoint**: US1 works on its own. The header tab and every canvas "pending — inbox" link land on a working list (SC-006). Entries show no actions yet.

---

## Phase 4: User Story 2 — answer a clarifying question (P1)

**Goal**: one-action accept of a suggestion; a typed answer; nothing blank is sent (FR-004).

**Independent test**: `entries.test.ts` (`ClarifyEntry`), `InboxView.test.ts` (clarify wiring); app tier CONSOLE-18.

- [x] T011 [US2] RED: in `interfaces/dashboard/frontend/src/features/inbox/entries.test.ts` add `describe('ClarifyEntry')`: (1) with a suggestion: `inbox-suggestion` (class `inbox-longtext`), `inbox-accept` and `inbox-edit` render, and no `field-control` while `editing` is false; (2) clicking `inbox-accept` emits `answer` once with the trimmed suggestion; (3) with `editing` true the `Field` labelled `Answer` shows `draft`; typing emits `update:draft`; (4) `inbox-send` is disabled while `draft.trim()` is empty and emits `answer(draft.trim())` otherwise; (5) a suggestion that is empty or only whitespace: no `inbox-suggestion`, no `inbox-accept`, no `inbox-edit`, and the field is shown; (6) clicking `inbox-edit` emits `toggle-edit`; (7) with `busy` true every button and the field are disabled and nothing is emitted. In `interfaces/dashboard/frontend/src/features/inbox/InboxView.test.ts` add, with the store's actions spied: (9) `answer` from a clarify entry calls `answerClarify(item.runId, item.id, text)`; (10) `toggle-edit` with an empty draft copies the suggestion into `drafts[entryKey(item)]` and sets `editing`; with a non-empty draft it leaves the draft; (11) an entry whose key is in `inFlight` gets `busy`, and a second entry does not; (12) two clarify items with different `runId` and the same `id`: typing in one leaves the other's field empty, and sending calls `answerClarify` with that item's `runId` and its own text; (13) text typed in a clarify field is still shown after `items` is replaced twice with fresh equal objects (SC-005). All fail.
- [x] T012 [US2] Create `interfaces/dashboard/frontend/src/features/inbox/ClarifyEntry.vue` (contract §3.3 row 1; props and events from data-model §2.5; `Field` and `Button` from `@kroker/ui`; no local state). In `interfaces/dashboard/frontend/src/features/inbox/InboxView.vue` render it inside the entry slot under `v-if="item.type === 'clarify'"` with the wiring of contract §3.4. T011 goes green.
- [x] T013 [US2] In `interfaces/ui/app.md` append `### CONSOLE-18` (contract §5). In `interfaces/ui/app.pw.ts` add one test citing `// clause: CONSOLE-18`: on `/#/inbox`, click `inbox-accept` on `[data-run-id="feature-add-sso"][data-key="q1"]`; that entry is gone and the header `inbox-count` reads `5`; on `[data-key="q2"]` click `inbox-edit`, expect `inbox-send` enabled, clear the field and expect `inbox-send` disabled, fill a new answer, click `inbox-send`; the entry is gone and the badge reads `4`. Run `check_ui.py`, then `check_clauses.py`. Commit T011 + T012 + T013.

**Checkpoint**: US1 and US2 work. Gate, override and escalation entries still show no actions.

---

## Phase 5: User Story 3 — decide a gate from the inbox (P1)

**Goal**: approve, revise (comment required) and reject from the inbox; the canvas agrees afterwards (FR-005; research R-7).

**Independent test**: `entries.test.ts` (`GateEntry`), `InboxView.test.ts` (gate wiring); app tier CONSOLE-19 and CONSOLE-23.

- [x] T014 [US3] RED: in `interfaces/dashboard/frontend/src/features/inbox/entries.test.ts` add `describe('GateEntry')`: (1) renders one `gate-decision` whose title is the fixed string of data-model §2.6 for the item; (2) clicking `gate-approve` emits `decide` with TWO arguments `('approve', '')`; (3) with a typed comment, `gate-revise` emits `decide('revise', <trimmed comment>)`; (4) `gate-revise` is disabled with an empty comment; (5) with `busy` true all three buttons are disabled. In `interfaces/dashboard/frontend/src/features/inbox/InboxView.test.ts` add: (14) `decide` from a gate entry calls `decideGate(item.runId, item.id, outcome, comment)`; (15) two gate items with different `runId` and the same `id` `'architecture#1'`: type a different comment in each `gate-comment`, replace `items` twice with fresh equal objects, click revise on the second; `decideGate` is called once with the second run's id and the second comment, and the first entry's comment is unchanged (FR-012 for gates, SC-004, SC-005). All fail.
- [x] T015 [US3] Create `interfaces/dashboard/frontend/src/features/inbox/GateEntry.vue` (contract §3.3 row 2: wraps `GateDecision` imported from `@kroker/ui/components/gate_decision/GateDecision.vue`, adapts its one-object payload to two arguments). In `interfaces/dashboard/frontend/src/features/inbox/InboxView.vue` add the `v-else-if="item.type === 'gate'"` branch with the wiring of contract §3.4. T014 goes green.
- [x] T016 [US3] In `interfaces/ui/app.md` append `### CONSOLE-19` and `### CONSOLE-23` (contract §5; file order of clauses is 17, 18, 19, then later 20, 21, 22, 23 — insert so the numbers stay ascending). In `interfaces/ui/app.pw.ts` add: one test citing `// clause: CONSOLE-19`: on `/#/inbox`, in entry `[data-run-id="feature-usage-metering"][data-key="g2"]` expect `gate-revise` disabled, fill `gate-comment`, expect it enabled, click it, the entry is gone and the badge reads `5`; then in `[data-run-id="feature-graph-demo"]` click `gate-reject` and the entry is gone. One test citing `// clause: CONSOLE-23`: on `/#/inbox`, click `gate-approve` in the `feature-graph-demo` entry, wait for it to leave, go to `/#/runs/feature-graph-demo`, expect zero `[data-testid="run-view"] [data-testid="gate-decision"]`. Scope every inbox locator to `[data-testid="inbox-view"]`. Run `check_ui.py`, then `check_clauses.py`. Commit T014 + T015 + T016.

**Checkpoint**: US1 to US3 work. CONSOLE-5 (deciding on the canvas) still passes unchanged.

---

## Phase 6: User Story 4 — merge override and escalated task (P2)

**Goal**: see the checks and verdict, override with a mandatory justification or send back; see the analysis, retry with guidance or quarantine (FR-006, FR-007; GATE 1 Q2 = A).

**Independent test**: `entries.test.ts` (`OverrideEntry`, `EscalationEntry`), `InboxView.test.ts` (their wiring); app tier CONSOLE-20 and CONSOLE-21.

- [x] T017 [US4] RED: in `interfaces/dashboard/frontend/src/features/inbox/entries.test.ts` add `describe('OverrideEntry')`: (1) one `check-row` per item check, in order, and `inbox-verdict` (class `inbox-longtext`) with the verdict; an empty verdict renders no `inbox-verdict`; (2) `inbox-override` is disabled while `draft.trim()` is empty; `inbox-send-back` is enabled; (3) with a draft, `inbox-override` emits `resolve(true, draft.trim())`; (4) `inbox-send-back` emits `resolve(false, draft.trim())`, including with an empty draft (`resolve(false, '')`); (5) typing in the `Field` labelled `Justification` emits `update:draft`; (6) `busy` disables both buttons and the field. Add `describe('EscalationEntry')`: (1) `inbox-analysis` (class `inbox-longtext`) shows the analysis; empty analysis renders none; (2) `inbox-retry` emits `resolve(true, draft.trim())` and `inbox-quarantine` emits `resolve(false, draft.trim())`, both also with an empty draft; (3) typing in the `Field` labelled `Guidance` emits `update:draft`; (4) `busy` disables both buttons and the field. In `interfaces/dashboard/frontend/src/features/inbox/InboxView.test.ts` add: (16) override `resolve(approve, text)` calls `overrideMerge(item.runId, item.id, approve, text)` for both `true` and `false`; (17) escalation `resolve(retry, guidance)` calls `resolveEscalation(item.runId, item.id, retry, guidance)` for both; (18) a notice set in the store for an entry's key is shown on that entry only. All fail.
- [x] T018 [P] [US4] Create `interfaces/dashboard/frontend/src/features/inbox/OverrideEntry.vue` (contract §3.3 row 3; `CheckRow` bound with `v-bind="check"`; `Field` with `required`; no local state).
- [x] T019 [P] [US4] Create `interfaces/dashboard/frontend/src/features/inbox/EscalationEntry.vue` (contract §3.3 row 4; no local state).
- [x] T020 [US4] In `interfaces/dashboard/frontend/src/features/inbox/InboxView.vue` add the `v-else-if="item.type === 'override'"` and `v-else-if="item.type === 'escalation'"` branches with the wiring of contract §3.4. The chain now covers all four values of `type`. T017 goes green.
- [x] T021 [US4] In `interfaces/ui/app.md` insert `### CONSOLE-20` and `### CONSOLE-21` (contract §5) between CONSOLE-19 and CONSOLE-23. In `interfaces/ui/app.pw.ts` add: one test citing `// clause: CONSOLE-20`: in entry `[data-run-id="feature-billing-webhooks"][data-key="g1"]` expect six `check-row`, a non-empty `inbox-verdict`, `inbox-override` disabled and `inbox-send-back` enabled; fill the field; `inbox-override` enabled; click it; the entry is gone and the badge reads `5`. Two tests citing `// clause: CONSOLE-21` (each on a fresh page): in entry `[data-run-id="fix-rate-limit-retry"][data-key="e1"]` a non-empty `inbox-analysis`; (a) fill guidance and click `inbox-retry`; (b) click `inbox-quarantine` with no guidance; in both the entry is gone. Run `check_ui.py`, then `check_clauses.py`. Commit T017 to T021.

**Checkpoint**: all four kinds can be resolved from the dashboard (SC-001).

---

## Phase 7: Close-out

- [x] T022 [US1] In `interfaces/ui/app.md` append `### CONSOLE-22` (contract §5, between 21 and 23) and add to the "Failure modes" paragraph the sentence given in contract §5. In `interfaces/ui/app.pw.ts` add one test citing `// clause: CONSOLE-22`: on `/#/inbox`, resolve all six seeded entries one after another (accept `q1`; accept `q2`; approve `g2`; approve the `feature-graph-demo` gate; override `g1` with a justification; quarantine `e1`), asserting after each that the entry count and the header badge both dropped by one (SC-002: seven observations including the first); at the end `inbox-empty` is visible, there are zero `inbox-entry`, and the header has zero `inbox-count`. Auto-waiting assertions only, no fixed sleeps. Run `check_ui.py`, then `check_clauses.py`: no `clause with no test: CONSOLE-17`…`CONSOLE-23` line and no dangling citation. Commit.
- [x] T023 Documents (FR-021; plan "Document changes"): edit `README.md` (the dashboard paragraph, and the unnamed-decision sentence in the "Bind to localhost" paragraph: GATE 1 Q3 = A), `interfaces/dashboard/frontend/README.md` (the Status section), and `ROADMAP.md` (FR-601, FR-305, FR-603 passages and the "Last verified" cell), each as that table says. The FR-305 and FR-603 checkbox flips follow the GATE 2 ruling; without one, change the text only and leave the boxes. Do not edit any `AGENTS.md`. Commit.
- [x] T024 Final verification, one command per call: `python scripts/check_ui.py`; `python scripts/check_clauses.py`; `python scripts/check_file_size.py`. Walk quickstart.md §2 on `VITE_API=mock npm run dev`, including the EC8 row. Confirm with `git diff <base sha from baseline.md> --stat` that no forbidden path changed and that `F/api/types.ts` shows additions only. Record every result, the final test counts against baseline.md, and the quickstart walk in `.specify/specs/010-decision-inbox/verification.md`. Commit.

**Checkpoint**: every gate green; the seven new clauses covered; CONSOLE-1 to CONSOLE-16 unchanged and passing (SC-008).

---

## Dependencies and execution order

- Phase 1 → Phase 2 → Phases 3 to 6 → Phase 7. Inside Phase 2: T002/T003, then T004/T005, then T006/T007 (the store imports both).
- **US1 (Phase 3)** depends only on Phase 2. It creates `InboxView.vue`, `InboxEntry.vue` and the two test files that later phases extend.
- **US2, US3, US4** each depend on Phase 3 (the frame and the view). They do not depend on each other in behaviour, but they all edit `InboxView.vue`, `InboxView.test.ts`, `entries.test.ts`, `U/app.md` and `U/app.pw.ts`, so they run one after another in the order 4, 5, 6. Any one of them can be dropped or deferred without breaking the others: the `v-if` chain simply has fewer branches.
- **T022** needs all four kinds (it resolves every seeded item).
- **Parallel**: only T018 and T019 (two new files, no shared edits). Everything else touches a file an adjacent task touches.

### Requirement coverage

| Requirement | Tasks |
|---|---|
| FR-001, FR-002, FR-003 | T008, T009, T010, T022 |
| FR-004 | T011, T012, T013 |
| FR-005 | T014, T015, T016 |
| FR-006 | T017, T018, T020, T021 |
| FR-007 | T017, T019, T020, T021 |
| FR-008 | T006, T007, T013, T016, T021, T022. The run page half is CONSOLE-23. The fleet view half has no test of its own: it rests on the fleet poll, which this feature does not touch. |
| FR-009, FR-010 | T006, T007, T011 (busy), T017 (notice) |
| FR-011 | T004, T005, T006, T007, T008, T009, T022 |
| FR-012 | T002, T003, T006, T007, T008, T011, T014 |
| FR-013 | T010, T013, T016, T021, T022 |
| FR-014 | T001 (name check), every task (standing rule), T024 (types diff) |
| FR-015 | standing rules; T024 |
| FR-021 | T023 |
| EC1 to EC9 | EC1 T011/T014; EC2, EC3, EC5 T006; EC4 T011/T014; EC6, EC9 T008; EC7 T008/T011/T017; EC8 T008/T011/T017/T024 |
| SC-001 to SC-006, SC-008 | SC-001 T021/T022; SC-002 T022; SC-003 T013; SC-004 T011/T014; SC-005 T011/T014; SC-006 T010; SC-008 T024 |

## Implementation strategy

**MVP**: Phases 1 to 3. After T010 the inbox is an honest read-only list: the badge, the header tab and the canvas links all land on real content. Stop and validate there.

**Increments**: Phase 4 adds answers, Phase 5 adds gates, Phase 6 adds the two rarer kinds. Each ends with its own clause green and one commit, and each can be demonstrated on the mock build.

**One implementer**: the tasks are written for a single executor with a qa seat writing the RED tasks. Parallel staffing gains nothing here because the stories share five files.
