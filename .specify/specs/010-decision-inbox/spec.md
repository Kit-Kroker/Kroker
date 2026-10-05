# Feature Specification: Decision Inbox (FR-601, the unfinished interface)

**Feature Branch**: `010-decision-inbox` (spec directory only; no branch is cut until exec)

**Created**: 2026-10-05

**Status**: Approved (2026-10-05). GATE 1 cleared: Q1 = A, Q2 = A, Q3 = A (see [GATE 1 rulings](#gate-1-rulings)). Scope is US1 to US4. Items marked *not selected* are kept as the record of the fork and are not to be planned.

**Input**: TASK BRIEF "item 5: the unfinished interface (FR-601)", relayed by the orchestrator on 2026-10-05.

**Base**: main `39a07a4`.

## Context and verified findings

Kroker stops a run and waits for a person at five kinds of point: a clarifying question, an architecture or plan approval, a merge that needs an override, a deploy approval, and a task the fix loop could not close. The dashboard is meant to be where a person sees everything that is waiting and acts on it (PRD FR-601, FR-305). Today the dashboard counts those items in its header and links to a screen that says "implemented in Plan 2".

Every claim in the brief was checked by reading the code on main `39a07a4`. Nothing was run. `F/` = `interfaces/dashboard/frontend/src/`.

| # | Claim (from the brief) | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | The Inbox screen is a stub | **True.** `F/features/inbox/InboxView.vue` is 20 lines and renders one hint line. The route (`F/app/router.ts:11`) and the header tab (`interfaces/ui/src/components/app_header/AppHeader.vue:39`) point at it. | US1. |
| V2 | The header badge counts items that have no screen | **True.** `F/app/shell/AppHeader.vue:13` reads `inbox.items.length`; `F/app/App.vue:16-22` refreshes the inbox store at start and every 5 s while the page is visible. | FR-002, SC-002. |
| V3 | Gates and Cost run-page tabs are disabled placeholders | **True.** `F/features/run/RunView.vue:66-67`, by ruling G7 of spec 002. `interfaces/ui/app.md` CONSOLE-10 pins `?tab=cost` as a disabled value. | Q1 option (b). |
| V4 | Backend is live | **True.** `GET /inbox`, `POST /runs/{id}/answer`, `POST /runs/{id}/decide` (`src/sdlc/dashboard/api.py:131,170,178`). A reply to a key that is no longer pending, or of the wrong kind, is a 404 (`:101-110`). | FR-009. No backend work in options (a) or (c). |
| V5 | The client maps the snapshot to four item variants and implements every write | **True.** `F/api/http.ts:105-139` and `:188-202`; the variants are `ClarifyItem`, `GateItem`, `OverrideItem`, `EscalationItem` (`F/api/types.ts:43-100`). A merge override is sent as approve or revise; an escalation as approve (retry) or reject (quarantine). | FR-003 to FR-007. The screen offers exactly these choices. |
| V6 | The mock seeds a full inbox | **True.** Six items across five runs, at least one of each variant (`F/api/mock/index.ts:220-293`). | The app-tier tests can cover every variant on the mock. |
| V7 | The stores exist | **True.** `F/app/inbox.store.ts` holds `items`, `drafts`, `editing`, `loading`, `refresh`, `setDraft`, `toggleEdit`. | See N2: its draft keys are not unique. |
| V8 | `GateDecision` and `CheckRow` exist in `@kroker/ui` | **True.** `gate_decision/GateDecision.vue` (approve / revise / reject; revise needs a comment) and `check_row/`. A `field/` component also exists. | FR-004, FR-005. Whether new library components are needed is a plan question. |
| V9 | The app-tier contract is `interfaces/ui/app.md` + `app.pw.ts` | **True.** Clauses CONSOLE-1 to CONSOLE-16 exist; the next free number is 17. | FR-013. |
| V10 | A first attempt was reverted | **True** by the working tree: `F/features/inbox/` holds only the stub. | FR-014. |

**Additional findings (not in the brief).**

- **N1 — the run page can already decide a gate.** On a run that executes as a graph, a pending gate shows approve / revise / reject on its canvas node, and deciding it clears the control (`RunView.vue:118-123`, CONSOLE-5). The same canvas sends every clarify and escalation item to `/inbox` (`:124-130`), which is the stub. So today the dashboard handles architecture, plan and deploy gates on graph runs, and nothing else: no clarify answers, no merge overrides, no escalations, and nothing at all for a run that predates graph execution.
- **N2 — an item's key is unique only within its run.** The client's own comment says two runs can both be waiting on the same key (`http.ts:174-176`); `architecture#1` is the key of the first architecture gate of every graph run. The inbox store keys its drafts by item key alone (`inbox.store.ts:21-26`). With two such runs open, a draft typed for one would appear on the other. The mock's keys happen to be distinct, so no test shows this.
- **N3 — a per-run Gates tab would have no history to show.** The live client sets every run's decision list to empty (`http.ts:99`); the snapshot does not carry past decisions. Only the mock fills them. A Gates tab built on live data could list that run's pending items and nothing more, which is the inbox filtered to one run. Showing past decisions needs a new backend read.
- **N4 — decisions made in the dashboard are recorded without a name.** The backend records the `X-Actor` header as the decider and defaults it to `human:unknown` (`api.py:174,182`). The dashboard client sends no such header. This is already true of gate decisions made on the canvas. PRD FR-1004 names this gap and owns closing it.
- **N5 — the dashboard cannot ask for a test thaw.** The backend and the CLI accept a "thaw tests" flag on a revise (`api.py:64`, `src/sdlc/cli.py:148`). The client's `decideGate` has no such parameter.
- **N6 — a run whose pending state could not be read is invisible to the inbox.** The snapshot reports such runs separately (`FleetState.errors`, `types.ts:112`), but the client's inbox read returns the items only (`http.ts:186`).
- **N7 — the CLI already covers every decision.** `inbox`, `answer`, `approve`, `revise`, `reject` are live (`src/sdlc/cli.py:136-225`), and `README.md:36-45,118-125` shows them. `README.md:176-178` already says the inbox is a placeholder and that Gates and Cost are not built. `ROADMAP.md:316` still says the cross-run `inbox` verb is missing, which is stale.

## Scope options (Q1)

| Option | What ships | What stays | Cost and risk |
|---|---|---|---|
| **(a) Inbox only** | US1 to US4. | Gates and Cost tabs stay disabled (G7 stands). | Front end only. One screen, no backend change. |
| **(b) Inbox + Gates tab** | US1 to US5. | Cost tab stays disabled. | Everything in (a), plus a tab that on live data repeats the inbox for one run (N3). A history view needs a backend read that does not exist; that is a second feature. |
| **(c) CLI is the decision surface** | US6 only. | Inbox stub, Gates and Cost. | Smallest. But the header badge and the canvas links keep pointing at a screen that does nothing, so "build nothing" is not quite available: the stub and the stale roadmap line have to change to be honest. |

**Ruled at GATE 1: (a).** Options (b) and (c) are not selected.

**Recommended (as asked): (a).** The gap is not gates on graph runs, which the canvas already handles (N1). It is the three things that have no dashboard surface at all, and the fact that the dashboard advertises them. Option (b) adds a tab with nothing of its own to show until the backend can serve history. Option (c) leaves the product's central feature out of its own console while everything beneath the screen is already built.

## User Scenarios & Testing *(mandatory)*

US1 to US4 are the scope (GATE 1, Q1 = A). US5 (option (b)) and US6 (option (c)) are **not selected**; they are kept as the record of the fork.

### User Story 1 - See everything that is waiting, across all runs (Priority: P1)

An operator opens the inbox and sees one entry for each item waiting on a person, across every run: what kind of item it is, which run it belongs to, how long it has waited, and the text they need in order to decide. The number of entries is the number in the header badge.

**Why this priority**: Without the list there is nothing to act on. It is also the smallest slice that stops the header from pointing at an empty page.

**Independent Test**: With the mock provider, open the inbox and count one entry per seeded item, each showing its kind, its run and its age; compare the count with the header badge.

**Acceptance Scenarios**:

1. **Given** six items waiting across five runs, **When** the operator opens the inbox, **Then** six entries are shown and the header badge reads 6.
2. **Given** an entry, **When** the operator reads it, **Then** it shows the item's kind, its run, its age, its title and its body text.
3. **Given** an entry, **When** the operator follows its run link, **Then** that run's page opens.
4. **Given** nothing is waiting, **When** the operator opens the inbox, **Then** an explicit "nothing is waiting" state is shown and the header shows no badge.
5. **Given** the inbox is open, **When** a new item starts waiting, **Then** it appears without a page reload.

---

### User Story 2 - Answer a clarifying question (Priority: P1)

An operator reads a clarifying question, sees why it matters and the suggested answer, and either accepts the suggestion with one action or writes their own answer and sends it.

**Why this priority**: Clarifying questions come first in every run and have no dashboard surface today. One-click accept is named in FR-601 and in US-1's acceptance criterion.

**Independent Test**: With the mock provider, accept the suggestion on one question and send a typed answer on another; both entries leave the list and the badge drops by two.

**Acceptance Scenarios**:

1. **Given** a question with a suggested answer, **When** the operator accepts the suggestion, **Then** the suggestion is sent as the answer with that single action and the entry leaves the list.
2. **Given** a question, **When** the operator writes their own answer and sends it, **Then** that text is sent and the entry leaves the list.
3. **Given** a question with no suggested answer, **When** the operator reads it, **Then** no accept action is offered.
4. **Given** an empty answer, **When** the operator tries to send it, **Then** nothing is sent.

---

### User Story 3 - Decide a gate from the inbox (Priority: P1)

An operator reads what an architecture, plan or deploy gate is asking them to approve, and approves it, sends it back with comments, or rejects it.

**Why this priority**: This is the product's main human checkpoint. Today it is reachable only from the canvas of a graph run (N1), one run at a time.

**Independent Test**: With the mock provider, approve one gate and send another back with a comment; both entries leave the list and each run's status changes accordingly.

**Acceptance Scenarios**:

1. **Given** a pending gate, **When** the operator approves it, **Then** the decision is sent and the entry leaves the list.
2. **Given** a pending gate, **When** the operator sends it back with a comment, **Then** the decision and the comment are sent and the entry leaves the list.
3. **Given** a pending gate and no comment, **When** the operator tries to send it back, **Then** nothing is sent.
4. **Given** a pending gate, **When** the operator rejects it, **Then** the decision is sent and the entry leaves the list.
5. **Given** a gate decided from the inbox, **When** the operator opens that run's page, **Then** the canvas no longer offers a decision for it.

---

### User Story 4 - Resolve a merge override and an escalated task (Priority: P2)

For a merge that needs an override, the operator sees the verdict and every check with its class (absolute or advisory), its result and its detail, then either overrides with a written justification or sends the work back. For a task the fix loop could not close, the operator sees the analysis and either retries with guidance or quarantines the task.

**Why this priority**: These are rarer than questions and gates, but neither has any dashboard surface today, and both stop a run until someone acts.

**Independent Test**: With the mock provider, override the seeded merge item with a justification and retry the seeded escalation with guidance; both entries leave the list.

**Acceptance Scenarios**:

1. **Given** a merge override item, **When** the operator reads it, **Then** every check is shown with its class, its pass or fail result and its detail, and the verdict text is shown.
2. **Given** a merge override item and a justification, **When** the operator overrides, **Then** the override and the justification are sent and the entry leaves the list.
3. **Given** a merge override item, **When** the operator sends the work back, **Then** a revise is sent with any text they wrote.
4. **Given** an escalated task, **When** the operator retries with guidance, **Then** the retry and the guidance are sent and the entry leaves the list.
5. **Given** an escalated task, **When** the operator quarantines it, **Then** the quarantine is sent and the entry leaves the list.

---

### User Story 5 - See one run's pending decisions on its own page (NOT SELECTED at GATE 1; was P3, option (b) only)

An operator on a run's page opens the Gates tab and sees that run's waiting items, with the same actions the inbox offers.

**Why this priority**: It repeats US1 to US4 for one run. It adds nothing that the inbox and the canvas do not already give (N3).

**Independent Test**: With the mock provider, open a run with a pending gate, select Gates, and decide the gate there.

**Acceptance Scenarios**:

1. **Given** a run with waiting items, **When** the operator opens its Gates tab, **Then** exactly that run's items are shown.
2. **Given** a run with nothing waiting, **When** the operator opens its Gates tab, **Then** an explicit empty state is shown.
3. **Given** the Gates tab is open, **When** the operator copies the page address and reopens it, **Then** the Gates tab is open again.
4. **Given** the Cost tab, **When** the operator looks at the tab bar, **Then** Cost is still disabled.

---

### User Story 6 - Be told plainly that decisions are taken in the CLI (NOT SELECTED at GATE 1; was P1, option (c) only)

An operator who opens the inbox, or follows a "pending" link from a run, is told that decisions are taken in the CLI and is shown the commands. The project's documents say the same.

**Why this priority**: Under option (c) this is the whole feature: the console stops implying a screen that does not exist.

**Independent Test**: Open the inbox and read the commands; read the README and the roadmap and find the same statement.

**Acceptance Scenarios**:

1. **Given** the inbox route, **When** the operator opens it, **Then** it states that decisions are taken in the CLI and lists the commands to list, answer, approve, revise and reject.
2. **Given** the roadmap and the README, **When** a reader looks up the dashboard's decision surface, **Then** both say the CLI is the alpha's decision surface and that the inbox screen is deferred.

---

### Edge Cases

- **EC1 — two runs waiting on the same key.** Text typed for one must never appear on, or be sent for, the other (N2).
- **EC2 — the item was decided somewhere else first.** The CLI, the canvas or a chat surface can win the race. The operator is told it was already decided, the entry leaves the list at the next refresh, and nothing is recorded twice.
- **EC3 — the send fails for another reason.** The operator sees that it failed, the entry stays, its controls work again, and what they typed is still there.
- **EC4 — a refresh arrives while the operator is typing.** The list refreshes every few seconds. Text in progress, and which entry is being edited, survive it.
- **EC5 — a second click while a send is in flight.** One action sends at most one decision.
- **EC6 — a run whose pending state could not be read.** The inbox must not show "nothing is waiting" as if it were certain (N6). See FR-011.
- **EC7 — an item with empty optional text** (no suggestion, no verdict, no analysis, an empty body). The entry still renders and offers only the actions that make sense.
- **EC8 — long text.** A long body, verdict or analysis stays readable and does not push the actions out of reach.
- **EC9 — the provider cannot be reached when the inbox opens.** The operator sees that the list could not be loaded, not an empty inbox.

## Requirements *(mandatory)*

### Functional Requirements

FR-001 to FR-015 and FR-021 are the scope (GATE 1, Q1 = A). FR-016 to FR-020 are **not selected** and MUST NOT be planned; they are kept as the record of the fork. The Gates and Cost tabs stay disabled (ruling G7 of spec 002 stands), so CONSOLE-10 is unchanged.

- **FR-001**: The inbox MUST show one entry for every item the provider reports as waiting, across all runs, in the order the provider gives them.
- **FR-002**: The number of entries MUST equal the header badge count at all times, including after an action.
- **FR-003**: Every entry MUST show the item's kind, its run, its age, its title and its body, and MUST link to that run's page.
- **FR-004**: A clarify entry MUST show the suggested answer when there is one, offer a single action that sends the suggestion as the answer, and let the operator write and send a different answer. An empty answer MUST NOT be sent.
- **FR-005**: A gate entry MUST offer approve, revise and reject. A revise MUST NOT be sent without a comment.
- **FR-006**: A merge override entry MUST show the verdict and every check with its class, result and detail, and MUST offer override and send-back. An override MUST NOT be sent without a non-empty justification (GATE 1, Q2 = A). This is a rule of the screen only: the backend and the CLI are unchanged. A send-back may carry empty text.
- **FR-007**: An escalation entry MUST show the analysis and MUST offer retry-with-guidance and quarantine. Guidance is optional.
- **FR-008**: After a successful action the entry MUST leave the list without a page reload, and the fleet view and the affected run's page MUST reflect the change at their next refresh.
- **FR-009**: When an action is refused because the item is no longer pending, the operator MUST be told it was already decided elsewhere, and the entry MUST leave the list at the next refresh. When an action fails for any other reason, the operator MUST be told it failed, the entry MUST stay, and its controls MUST work again.
- **FR-010**: While an action on an entry is in flight, that entry's actions MUST be unavailable, and a repeated click MUST NOT send a second decision. Other entries MUST stay usable.
- **FR-011**: The inbox MUST distinguish three states: nothing is waiting; the list could not be loaded; items are shown. If the provider reports runs whose pending state could not be read, the inbox MUST say so rather than present the list as complete.
- **FR-012**: Everything the screen keeps per entry (text in progress, edit state, in-flight state, list identity) MUST be keyed by run and item key together, never by item key alone. A periodic refresh MUST NOT discard text in progress.
- **FR-013**: Every shipped behaviour of the screen MUST be stated as new numbered clauses in the assembled-console contract (from CONSOLE-17) and covered by app-tier tests against the mock provider. Existing clauses CONSOLE-1 to CONSOLE-16 MUST keep passing unchanged.
- **FR-014**: The delivery MUST use the data names already defined by the dashboard's client contract (`F/api/types.ts`) exactly as written there, and MUST NOT change that contract's existing names or method signatures. The plan MUST list every name it uses, copied from the file, before any file is written.
- **FR-015**: The screen MUST respect the repository's standing front-end rules: screens are reachable only through the app layer and do not import each other; no file exceeds 1000 lines; colours come from design tokens only; any new shared component follows the library's five-file rule and is registered in the showcase.
- **FR-016** *(not selected; b only)*: The run page's Gates tab MUST be enabled and MUST show exactly that run's waiting items with the same actions as the inbox. The tab MUST be reflected in the page address like the Board tab. The run screen MUST receive this content from the app layer, not by importing the inbox screen.
- **FR-017** *(not selected; b only)*: The Gates tab MUST show an explicit empty state when the run has nothing waiting, and MUST NOT present past decisions.
- **FR-018** *(not selected; b only)*: The Cost tab MUST stay disabled with no content.
- **FR-019** *(not selected; c only)*: The inbox route MUST state that decisions are taken in the CLI and show the commands for listing, answering, approving, revising and rejecting.
- **FR-020** *(not selected; c only)*: No new decision controls are added to the dashboard.
- **FR-021**: The roadmap entry for FR-601, the README's dashboard paragraph and the dashboard front end's README MUST describe what is on main once this lands. The README MUST state that decisions sent from the dashboard are recorded without the operator's name (as `human:unknown`) and that PRD FR-1004 owns closing that gap (GATE 1, Q3 = A). The roadmap's stale statement that the CLI lacks a cross-run inbox verb (N7) MUST be corrected.

### Key Entities

- **Inbox item**: one thing waiting on a person. It belongs to one run and has a key that is unique only within that run, a round, an age, a title and a body. It is one of four kinds.
- **Clarify item**: a question, why it matters, and an optional suggested answer. Resolved by a text answer.
- **Gate item**: a named gate (architecture, plan, deploy) and a summary of what is being approved. Resolved by approve, revise or reject, with an optional comment.
- **Merge override item**: a verdict and a list of checks, each absolute or advisory, passed or failed, with a detail line. Resolved by an override or a send-back, with text.
- **Escalation item**: a task the fix loop could not close, with an analysis. Resolved by retry or quarantine, with optional guidance.
- **Run**: the pipeline execution an item belongs to. The inbox reads its identity only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

SC-001 to SC-006 and SC-008 are the scope. SC-007 is **not selected**.

- **SC-001**: An operator can resolve every kind of waiting item (question, gate, merge override, escalated task) from the dashboard without using the CLI. Four of four kinds, demonstrated on the mock provider.
- **SC-002**: The header badge and the number of inbox entries agree before and after each of the six seeded items is resolved (seven observations, zero mismatches).
- **SC-003**: Accepting a suggested answer takes one action from the moment the entry is visible.
- **SC-004**: With two runs waiting on the same key, text typed for one run is sent for that run only, in every repetition of the test.
- **SC-005**: Text an operator is typing is still present after at least two automatic refreshes.
- **SC-006**: No link or badge in the dashboard leads to a placeholder for decisions: the header tab and every "pending" link on a run's canvas land on a working list.
- **SC-007** *(not selected; c only)*: A reader of the inbox route, the README or the roadmap finds, in each, the statement that the CLI is the decision surface and the commands to use. Three of three.
- **SC-008**: Every pre-existing dashboard check passes unchanged apart from the tests the plan names as intentionally updated.

## Assumptions

These are defaults taken where the brief was silent. GATE 1 cleared the spec without overruling any of them.

- **A1 — order.** Entries appear in the provider's order. No sorting, filtering or grouping in this feature. The age is served as display text and cannot be sorted on.
- **A2 — no confirmation step.** Reject, quarantine and override send on one action, as the canvas does today. A decision cannot be undone from any surface.
- **A3 — the choices offered are the client's existing ones.** A merge override offers override and send-back, not reject. An escalation offers retry and quarantine, not revise (V5).
- **A4 — refresh.** The inbox keeps the existing five-second refresh while the page is visible. No push channel is added.
- **A5 — test thaw stays in the CLI.** The dashboard does not gain the "thaw tests" option on revise (N5). Adding it would change the client contract that FR-014 freezes. Named as a follow-up.
- **A6 — both providers.** The screen works against the mock and the live provider through the same client contract; app-tier tests run on the mock.
- **A7 — no backend change.**
- **A8 — the canvas keeps its gate control.** Deciding a gate on a run's canvas (CONSOLE-5) is unchanged; the inbox is a second place to do it, and the first decision wins (PRD FR-302).
- **A9 — documents.** Edits to any `AGENTS.md` need the orchestrator's approval and are proposed in the plan, not assumed.

## Out of scope and follow-ups

- The Cost tab and the Gates tab on the run page (US5, FR-016 to FR-018).
- Turning the inbox route into a pointer to the CLI (US6, FR-019, FR-020, SC-007).
- A history of past decisions per run. It needs a backend read that does not exist (N3).
- Real operator identity and authorisation (PRD FR-1004). Dashboard decisions stay recorded as `human:unknown` for the alpha (Q3 = A).
- The "thaw tests" option on revise (A5).
- Sorting, filtering, grouping, keyboard shortcuts, notifications.
- The MCP surface (FR-602).

## GATE 1 rulings

Cleared by the user on 2026-10-05, relayed by the orchestrator.

| Q | Ruling | Effect on this spec |
|---|---|---|
| Q1 | **A — inbox only** | Scope is US1 to US4, FR-001 to FR-015, FR-021, SC-001 to SC-006, SC-008. US5, US6, FR-016 to FR-020 and SC-007 are not selected and must not be planned. |
| Q2 | **A — justification mandatory in the dashboard** | FR-006 resolved: an override needs non-empty text. Screen rule only; backend and CLI unchanged. |
| Q3 | **A — `human:unknown` accepted for the alpha** | No change to the client's write path. FR-021 requires the README to say so. The gap stays with PRD FR-1004. |

Standing reminder from the gate: FR-012 (state keyed by run and key together) and FR-014 (every name copied from `F/api/types.ts` into the plan before any file is written) are the two requirements the reverted first attempt tripped on. The plan must keep both load-bearing.

## Open Questions — GATE 1 (as asked)

### Q1 — Scope

**Context**: "Scope options" above. FR-601 asks for a "decision inbox with one-click accept-suggestion, approve/reject with comments".

**What we need to know**: which surface is the alpha's?

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **(a) Inbox only** (recommended) | US1 to US4. Front end only. Gates and Cost stay disabled; G7 stands. Closes the three kinds with no dashboard surface (N1). |
| B | (b) Inbox + Gates tab | US1 to US5. The tab repeats the inbox for one run until a history read exists (N3). CONSOLE-10 changes. More surface for the same capability. |
| C | (c) CLI is the decision surface | US6 only. The inbox route becomes a pointer to the CLI; the header badge keeps counting items the console cannot act on. FR-601 stays partial. |

### Q2 — Is a justification mandatory to override a merge?

**Context**: FR-006. PRD FR-304: "Advisory-check overrides SHALL be recorded as audited decisions." The backend accepts an override with no text.

**What we need to know**: may the dashboard send an override with an empty justification?

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **Mandatory in the dashboard** (recommended) | The override action is unavailable until text is entered, as revise is today. A rule of the screen only; the backend and the CLI are unchanged. |
| B | Optional | Matches the backend. An audited override can be recorded with no reason. |

### Q3 — Decisions recorded without a name

**Context**: N4. PRD US-2: "approval is recorded with identity + timestamp". Every decision sent from the dashboard is recorded as `human:unknown`. The canvas already behaves this way. The inbox would be the first dashboard surface for merge overrides.

**What we need to know**: is that acceptable for the alpha?

| Option | Answer | Implications |
|--------|--------|--------------|
| A | **Accept for the alpha and say so in the README** (recommended) | No change to the client. The gap stays with FR-1004, which already owns it. |
| B | Let the operator set a display name that is sent with every decision | A new setting, kept in the browser and self-asserted (not authentication). Touches the client's write path, so it also applies to canvas decisions. |
| C | Do not ship merge overrides in the dashboard until identity exists | US4's merge half moves out of scope; overrides stay in the CLI. |
