# Implementation Plan: Decision Inbox (FR-601)

**Branch**: orchestrator's call (spec dir `010-decision-inbox`) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md) | **Base**: main `39a07a4`

**Input**: [spec.md](spec.md) — GATE 1 cleared 2026-10-05 (Q1 = A inbox only, Q2 = A justification mandatory, Q3 = A `human:unknown` accepted). Scope: US1 to US4, FR-001 to FR-015, FR-021, SC-001 to SC-006, SC-008. **Not planned** (not selected at GATE 1): US5, US6, FR-016 to FR-020, SC-007.

**Consults**: advisor `.workspace/tmp/advisor-010-1.md`, skeptic `.workspace/tmp/skeptic-010-1.md`. Their rulings are folded into [research.md](research.md); where they disagreed the ruling is stated there (R-2, R-7).

**Review**: reviewer `.workspace/tmp/reviewer-010-plan-1.md` — VERDICT: approve, 0 blocking, 2 non-blocking, 6 nits. All eight are folded in: EC8 now has a design line and a proof (contract §3.2); the claim that the mock cannot refuse a write is corrected in four places (the 404 path stays at the unit tier because reaching it on the mock is a race with the poll); the `GateDecision` payload, the roles of `Tag` and `Surface`, the `pending` counter, the double banner and the name-check note are written down. Tasks review `.workspace/tmp/reviewer-010-tasks-1.md` — VERDICT: approve, 0 blocking, 0 non-blocking, 7 nits; six folded in (button variants pinned in the contract §3.3; the rest are wording in tasks.md). The seventh, the order of two subsections in data-model.md, is cosmetic and left as is.

**Base note**: verified on main `39a07a4`. Main has since gained `18de7f1` (the `runs/` layout), which changes nothing under `interfaces/`, `README.md`, `ROADMAP.md` or `PRD.md`; T001 re-checks this at branch time.

`F/` = `interfaces/dashboard/frontend/src/`. `U/` = `interfaces/ui/`.

## Summary

Replace the 20-line inbox stub with a working screen. Everything under it exists: the backend routes, the client's four write methods, the mock, and the library controls. The work is one screen folder (a view, an entry frame, four small kind components), an extension of the existing app-layer inbox store (writes, per-entry state, load and error state), one added read method on the client so the screen can say when its list may be incomplete, seven new assembled-console clauses with app-tier tests, and three document corrections. No backend change, no new library component, no change to the run page.

Decisions R-1 to R-12 are in [research.md](research.md). Every name is in [data-model.md](data-model.md). Behaviour, selectors, clause wording and the requirement-to-proof table are in [contracts/inbox-screen.md](contracts/inbox-screen.md). Validation is in [quickstart.md](quickstart.md).

## The two requirements the first attempt tripped on

Both are binding on every task, and each has a mechanical check.

**FR-014 — names.** [data-model.md](data-model.md) is the only source of names. §1 is copied from `F/api/types.ts`; §2 defines every new name once. The first task of the run re-runs the check in data-model §5 against the file and stops on any difference. No task may introduce a name that is not in data-model.md; if one is needed, the executor stops and asks. Convergence is driven by the type checker (`vue-tsc`, the first step of `check_ui.py` after install) and by Vitest, not by re-reading: a task is not done while either is red. The traps table (data-model §1.3) lists the ten substitutions most likely to be made by habit.

**FR-012 — run and key together.** One function, `entryKey`, in `F/shared/entryKey.ts`, is the only way a per-entry key is formed (research R-2). The `v-for` key, `drafts`, `editing`, `inFlight` and `notice` all use it. Review check for every task that touches the store or the view: no map lookup, set membership or `:key` uses `item.id` or `key` alone. Proof: `entryKey.test.ts`, and the two-runs-one-key tests in `inbox.store.test.ts` and `InboxView.test.ts` (contract §6).

## Technical Context

**Language/Version**: TypeScript 5 / Vue 3.4 single-file components (`<script setup lang="ts">`). No Python change.

**Primary Dependencies**: Vue, Pinia, vue-router (hash history), `@kroker/ui` (`GateDecision`, `Field`, `Button`, `CheckRow`, `Tag`, `Surface`). No new dependency.

**Storage**: N/A. All state is in the Pinia store and is lost on reload, by design (PRD FR-604: stateless shells).

**Testing**: `python scripts/check_ui.py` is the only entry point for JavaScript checks (install → typecheck ×2 → builds → vitest-dashboard → ds-bundle → vitest-ui → playwright). `python scripts/check_clauses.py` (always exits 0; read the output). `python scripts/check_file_size.py`. Unit tests sit beside their module (Vitest + `@vue/test-utils`, jsdom, the client faked with `vi.mock` of `api/client` and `vi.hoisted`, as `F/features/run/RunView.test.ts:16-22` does with the specifier `'../../api/client'`). App-tier tests are in `U/app.pw.ts` against the dashboard built with `VITE_API=mock` on port 4174.

**Target Platform**: browser SPA served by the dashboard backend. Developer host is Windows (PowerShell 5.1 / Git Bash); see Execution notes.

**Project Type**: web application; this feature touches the front-end package and the two contract files of the design-system package.

**Performance Goals**: none new. Requests per poll stay at two (research R-5).

**Constraints**: cross-screen imports banned and screens reachable only through the app layer (`F/app/boundaries.test.ts`); 1000-line ceiling; tokens only, no bare hex in component styles; no hex or pixel values in Playwright assertions; clause ids with underscores and same-line citations; `F/api/types.ts` existing names and signatures frozen.

**Scale/Scope**: 10 new files, 11 modified files, 3 documents. Each new file is expected to be well under 200 lines.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles), so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md`, `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`. Checked after design:

| Rule | Status |
|---|---|
| Screens import only `app/*.store.ts`, `shared/`, `api/`, `@kroker/ui`; never another screen | Holds. `features/inbox/` imports `app/inbox.store.ts`, `shared/entryKey.ts`, `api/types.ts`, `@kroker/ui`. |
| `shared/` never imports `app/` or `features/` | Holds. `entryKey.ts` imports nothing. |
| `ui/` never imports `dashboard/` | Holds. No library source file changes. |
| New library component ⇒ five files + showcase registry | Not triggered. No new library component (R-3). |
| New shipped surface ⇒ `CONSOLE-N` clauses + `app.pw.ts` coverage | Planned: CONSOLE-17 to CONSOLE-23. |
| 1000-line ceiling | Holds. Largest touched file is `F/app/boundaries.test.ts` (736), which is not edited; `F/api/mock/index.ts` (459) gains about 6 lines. |
| Tokens only; no hex in Playwright | Planned; reviewer checks per task. |

No violation, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/010-decision-inbox/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   inbox-screen.md
├── checklists/  requirements.md (+ plan.md, tasks.md from the reviewer)
└── tasks.md     (/speckit-tasks)
```

### Source Code (after the feature)

```text
interfaces/dashboard/frontend/src/
├── api/
│   ├── types.ts             M  + UnreadableRun, InboxState, DashboardApi.getInboxState (additive)
│   ├── http.ts              M  + mapInboxState, getInboxState
│   ├── http.test.ts         M  + mapInboxState cases
│   └── mock/
│       ├── index.ts         M  + getInboxState
│       └── index.test.ts    M  + getInboxState case
├── shared/
│   ├── entryKey.ts          N
│   └── entryKey.test.ts     N
├── app/
│   ├── inbox.store.ts       M  writes, per-entry state, load state (R-1, R-4, R-6)
│   ├── inbox.store.test.ts  N  the store rules (contract §2)
│   ├── shell.stores.test.ts M  api fake gains getInboxState (intentional, SC-008)
│   └── App.test.ts          M  api fake gains getInboxState (intentional, SC-008)
└── features/inbox/
    ├── InboxView.vue        M  stub → screen
    ├── InboxView.test.ts    N
    ├── InboxEntry.vue       N  frame
    ├── ClarifyEntry.vue     N
    ├── GateEntry.vue        N
    ├── OverrideEntry.vue    N
    ├── EscalationEntry.vue  N
    └── entries.test.ts      N  the four kind components and the frame

interfaces/ui/
├── app.md                   M  + CONSOLE-17..23, one sentence in Failure modes
└── app.pw.ts                M  + one or more tests per new clause

README.md                                   M  (FR-021)
interfaces/dashboard/frontend/README.md     M  (FR-021)
ROADMAP.md                                  M  (FR-021)
```

**Structure Decision**: the existing by-screen layout. The screen's files live in `F/features/inbox/`; state that the header also reads stays in `F/app/inbox.store.ts`; the one helper both need is in `F/shared/`.

**Not touched** (research R-11): `F/app/App.vue`, `F/app/router.ts`, `F/app/boundaries.test.ts`, `F/app/shell/*`, `F/features/run/*`, `F/shared/fleet.store.ts`, `F/shared/fleet.store.test.ts`, the mock's seed and `removeItem`, every file under `U/src/`, every Python file, every `AGENTS.md`.

## Design in brief

Full detail is in the contract; this is the shape.

1. **Client** (contract §1). `getInboxState()` returns the items and the unreadable runs from one snapshot. Live: a new mapper reads `open_errors`. Mock: items plus an empty list.
2. **Key** (R-2). `entryKey(item)` = `JSON.stringify([item.runId, item.id])`.
3. **Store** (contract §2). `refresh` never rejects and applies a result only if it started later than the last one applied. Four actions with the client's parameter lists; each guards against a double send, calls the client, then refreshes. An entry stays unavailable until a refresh that started after its write finished. A 404 leaves the notice `already decided elsewhere`; any other failure leaves `failed: …` and frees the entry with its text intact.
4. **Screen** (contract §3). Three states plus the list, an "incomplete" banner, a frame that renders what every entry shares, and four stateless kind components built from library controls.
5. **Contract and tests** (contract §5, §6). Seven clauses at the app tier for what the mock can produce; unit tests for what it cannot (R-10).

## Work order

Tasks are generated by `/speckit-tasks`; this is the order and the reason for it. Each step ends with `vue-tsc` and Vitest green.

| Step | What | Why here |
|---|---|---|
| 0 | Baseline: run the gates on the base; run the data-model §5 name check. | Known-green start; FR-014. |
| 1 | `entryKey` + its test. | No dependencies; everything else imports it. |
| 2 | Client: types (additive), `mapInboxState`, `getInboxState` in both providers, their tests. | The store needs it. After this step `vue-tsc` proves both providers implement the widened interface. |
| 3 | Store: tests first (contract §2.3), then the implementation; update the two existing api fakes. | The screen needs it. The store rules are the riskiest logic, so they land before any markup. |
| 4 | Kind components and frame: tests first, then the five files. | Stateless, typed per variant; independent of each other. |
| 5 | `InboxView`: tests first, then the view. US1 is complete here; US2 to US4 follow from wiring. | Needs steps 1, 3, 4. |
| 6 | `app.md` clauses and `app.pw.ts` tests. | Needs the built screen. |
| 7 | Documents (FR-021). | Describe what is on the branch. |
| 8 | Full gates; quickstart walk. | Done means [quickstart.md](quickstart.md) §1 is green and §2 was walked. |

US1 (see the list) is usable after step 5 with only the frame; US2, US3 and US4 are each one kind component plus its wiring and its clause, and can be delivered and reviewed one at a time.

## Existing tests changed on purpose (SC-008)

| File | Change | Why |
|---|---|---|
| `F/app/shell.stores.test.ts` | the `vi.mock` api fake gains `getInboxState: vi.fn(async () => ({ items: [{ id: 'q1', runId: 'r1', type: 'clarify' }], unreadable: [] }))`; the "refresh loads items" assertion is unchanged | the store now calls `getInboxState` (R-5) |
| `F/app/App.test.ts` | the api fake gains `getInboxState: vi.fn(async () => ({ items: [], unreadable: [] }))` | same |

`listInbox` stays in both fakes. No other existing test is edited. `F/shared/fleet.store.test.ts` lists `listInbox` in its fake but the fleet store never calls it; leave it. `F/app/shell/AppHeader.test.ts` assigns `items` directly and is unaffected. `F/api/mock/index.test.ts` "6 inbox items" is unaffected. CONSOLE-1 to CONSOLE-16 and their tests are not edited.

## Document changes (FR-021)

| File | Now | Change to |
|---|---|---|
| `README.md` ~176 | "…and a decision-inbox placeholder." | the decision inbox: it lists everything waiting on a person across runs and lets the operator answer questions, decide gates, override or send back a merge, and retry or quarantine an escalated task. Gates and Cost stay "not built yet". |
| `README.md` ~194 ("Bind to localhost") | says `X-Actor` is self-asserted | add: the dashboard sends no `X-Actor`, so a decision taken there is recorded as `human:unknown`; closing that is PRD FR-1004 (GATE 1, Q3 = A). |
| `interfaces/dashboard/frontend/README.md` ~37-38 | "Plan 1 … / Plan 2 (follow-up): decision inbox cards + run-detail panels." | current status: fleet, run page (Graph and Board tabs), graph editor and decision inbox are built; the run page's Gates and Cost tabs are not. |
| `ROADMAP.md` ~314 (FR-601) | "the run-detail (spine) and inbox views are not built" | what is on main after this lands: inbox built (010); the run page exists as a tab host with Graph and Board; Gates and Cost tabs not built. Keep it `[ ]` ⚠️ unless the user rules otherwise at GATE 2, because the tabs are open. |
| `ROADMAP.md` ~300 (FR-305) | "no surface lists everything awaiting a human" | stale: the CLI `inbox` verb (E-8) and, after this lands, the dashboard inbox both do. |
| `ROADMAP.md` ~316-318 (FR-603) | "missing cross-run `inbox` (FR-305)" | stale (spec N7): the verb is live. |
| `ROADMAP.md` line 6 | "Last verified" | prepend the date of the change and what was re-checked. |

Line numbers are from the base; the executor finds each passage by its text. Whether FR-305 and FR-603 flip to `[x]` is a roadmap status call: the plan proposes `[x]` for both and flags it for GATE 2. `interfaces/AGENTS.md` already lists the inbox screen and needs no change. Documents describe main, so these edits ride the branch and become true at merge.

## Risks

| Risk | Mitigation |
|---|---|
| Name drift again | data-model.md as the single source; step-0 check; type checker gate per task; traps table; reviewer checks names against data-model.md on every diff. |
| The release rule (R-4) is subtle | Written as pseudocode in the contract; six named unit tests written before the code, with controllable promises. |
| `check_ui.py` under container load times out in jsdom-heavy tests | Known (`.workspace/tasks/2026-10-03-check-ui-wrapper-timeout-flake.md`). A timeout in a file this feature does not touch is reported to the orchestrator, not "fixed". |
| The all-six app-tier test (CONSOLE-22) is slow | The mock delays each call 120 to 300 ms; six writes plus refreshes is a few seconds. Use Playwright's auto-waiting assertions, no fixed sleeps. |
| Adding `getInboxState` is read as breaking FR-014 | It is additive and flagged for GATE 2 (R-5). If the user rejects it, FR-011's unreadable-runs sentence needs a spec amendment; nothing else in the plan depends on `unreadable`. |
| Node missing in the run environment | `check_ui.py` then skips and exits 0. A skip is not a pass; the executor reports it and stops. |

## Follow-ups filed (`.workspace/tasks/`)

- `2026-10-05-mock-inbox-removes-by-key-alone.md` — the mock's `removeItem` (R-9).
- `2026-10-05-fleet-refresh-failure-stops-the-poll.md` — the fleet store has the defect this plan fixes in the inbox store (R-6).
- `2026-10-05-gate-comment-lost-on-leaving-inbox.md` — `GateDecision` keeps its comment internally (R-7); also a home for the "thaw tests" option (spec A5).

## Items for GATE 2

1. **`getInboxState` is added to the client contract** (R-5). Additive; needed for FR-011.
2. **A gate comment in progress is lost on leaving the inbox page** (R-7). Accepted limitation; follow-up filed.
3. **An entry the server still lists after a write becomes usable again** (R-4), rather than staying locked.
4. **Roadmap status**: FR-305 and FR-603 proposed `[x]`; FR-601 stays `[ ]` ⚠️ while the Gates and Cost tabs are open.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind (no `Co-Authored-By:`, no `Claude-Session:`), even where a template prints one.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs (the host shell may be PowerShell 5.1). Every file is written with the Write tool.
- Never chain two test runs in one shell call. `addopts` already carries `-q`; do not add another.
- Tests first: for steps 1 to 6 the failing test lands before the code that satisfies it, in the same commit as the code (no red commits on the branch).
- The reviewer gate is per task and blocking: no task N+1 commit before the reviewer has answered on task N's diff.
- `AGENTS.md` files are not edited by this plan.

## Complexity Tracking

No constitution or repository-rule violation to justify.
