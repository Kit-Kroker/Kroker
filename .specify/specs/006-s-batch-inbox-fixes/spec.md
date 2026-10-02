# Feature Specification: S-batch — six small inbox items

**Feature Branch**: `006-s-batch-inbox-fixes`

**Created**: 2026-10-02

**Status**: Approved at GATE 1 (2026-10-02) — see [GATE 1 rulings](#gate-1-rulings)

**Input**: User description: "S-BATCH of six inbox items (one lean spec); brief at .workspace/tmp/planner-brief-006-s-batch.md"

**Base**: main `817f819`. Every premise below was re-verified in code on that
commit; the inbox files' line numbers have drifted and are corrected in
[Verified premises](#verified-premises).

One ceremony for six unrelated small items. Each item is its own user story,
its own FR group and its own commit set; no item depends on another.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — B1: a failed checkpoint commit is visible (Priority: P1)

An operator watching a run's worker log can tell "no checkpoint because the
round timed out" apart from "no checkpoint because git refused the commit"
(typically an unresolvable committer identity, which silently affects every
attempt in the run and freezes the test-freeze anchor).

**Why this priority**: whole-run condition, zero signal today, and the
downstream drift backstop then measures against a stale baseline.

**Independent Test**: drive the coding-task activity with a commit step that
returns non-zero; assert on the captured log.

**Acceptance Scenarios**:

1. **Given** the staging step succeeded and the checkpoint commit returns
   non-zero, **When** the activity finishes, **Then** exactly one WARNING is
   logged that names the worktree and carries git's stderr (stdout when
   stderr is empty), the result has no checkpoint sha, and nothing is raised.
2. **Given** the checkpoint commit returns zero, **When** the activity
   finishes, **Then** no warning is logged and the checkpoint sha is recorded.

---

### User Story 2 — B2: an unset `$VAR` notify target is visible (Priority: P1)

An operator who routes a gate to `webhook:$SOME_VAR` and forgets to export
the variable learns about it from the log, and from `sdlc doctor` before the
run starts, instead of from a run parked for two days.

**Why this priority**: the shipped policy asset's worked example steers
operators onto exactly this shape; the failure mode is a gate that notifies
nobody.

**Independent Test**: load a routes asset with a `$VAR` target with the
variable unset; assert on the captured log and on the loaded table.

**Acceptance Scenarios**:

1. **Given** a route whose target is `$VAR` and `VAR` is unset or empty,
   **When** routes are loaded, **Then** a WARNING names the route location
   (gate + tier) and the variable name, the route is still dropped, and
   loading still succeeds.
2. **Given** the variable is set, **When** routes are loaded, **Then** no
   warning is logged and the route resolves to the variable's value.
3. *(doctor half)* **Given** a routes
   asset with N `$VAR` targets of which M are unset, **When** `sdlc doctor`
   runs, **Then** the notify-routes check reports WARN naming each of the M
   locations and variables; with M = 0 it reports OK as today.

---

### User Story 3 — B3: the fleet snapshot fixture is regenerable and guarded (Priority: P2)

A developer who changes a dashboard model can regenerate the fleet snapshot
fixture without losing rows, and a fast test fails when the committed
fixture no longer matches what the generator produces.

**Why this priority**: the fixture exists to catch model/TS-mapper drift,
and today regeneration itself destroys data the frontend tests depend on —
so nobody regenerates and drift is silent.

**Independent Test**: run the generator's build step and compare to the
committed fixture, parsed; run the frontend unit tests against the
regenerated file.

**Acceptance Scenarios**:

1. **Given** the fixture as regenerated once by this batch (amendment A1),
   **When** the generator is run again on an unchanged tree, **Then** the
   file is unchanged as parsed data. That one deliberate regeneration keeps
   all seven runs, `closed_marks`, and every R-2 `project_key` state, and
   adds only the model-default keys listed in the plan.
2. **Given** a model change that alters the dumped shape, **When** the fast
   test tier runs, **Then** the freshness test fails and names the fixture.
3. **Given** a CRLF checkout of the fixture, **When** the freshness test
   runs, **Then** it does not false-fail (comparison is on parsed data).
4. **Given** the regenerated fixture, **When** the frontend API tests run,
   **Then** they pass unchanged.

---

### User Story 4 — B4: research-stage gotchas have a living home (Priority: P3)

An agent or developer editing the research slice finds its traps in the
slice's own editing guide rather than in a retired hand page.

**Why this priority**: docs-only; prevents re-learning known traps.

**Independent Test**: read the section; every bullet is traceable to a named
place in the current research code.

**Acceptance Scenarios**:

1. **Given** the research slice's editing guide, **When** a reader opens it,
   **Then** a "Gotchas" section covers fail-and-continue semantics (E-29),
   verifier rules, and budget-enforcement corner cases, each stated as a
   trap with its consequence.
2. **Given** each gotcha, **When** checked against the current code,
   **Then** it is true on main today (not copied from the retired page), and
   it does not restate WHAT-level semantics already in the stage's own doc.

---

### User Story 5 — B5 + B6: two register rows are ready to paste (Priority: P3)

The user, who alone owns the ideas register, finds a finished row draft at
the bottom of each of the two inbox task files and can paste it without
re-deriving the premise.

**Why this priority**: zero code risk; unblocks two long-open inbox items.

**Independent Test**: open the two inbox files; each ends with a "Draft
register row" section whose premise citations resolve on main.

**Acceptance Scenarios**:

1. **Given** the flaky-provider-import inbox task, **When** opened, **Then**
   it ends with a draft row naming the test, why it is load-sensitive, and
   the remedy candidates (measure import cost directly; or mark
   load-sensitive / move to the slow tier).
2. **Given** the lens-outcome-records inbox task, **When** opened, **Then**
   it ends with a draft row stating the corpus cannot distinguish "ran and
   approved" from "never ran" for either lens, with current citations.
3. **Given** the batch is complete, **When** the register file's history is
   inspected, **Then** it has no commit from this batch.

### Edge Cases

- B1: stderr and stdout both empty on a non-zero commit — the warning is
  still emitted (with an empty detail), never suppressed.
- B1: a crew round-1 deadline never reaches this code (crew tasks take a
  different activity), and an empty change set commits successfully — only
  a non-zero commit return warns.
- B2: variable set to an empty string counts as unset (current behaviour).
- B2: both tiers of one gate unset — one warning per dropped route.
- B2: a literal (non-`$`) target and a target-less notifier (`log`) never warn.
- B3: three runs are deliberately key-absent for `project_key` while the
  model would dump an explicit null; the generator must reproduce absence,
  not null, for exactly those runs.
- B3: the committed file is stale beyond the named hand rows (amendment
  A1). No frontend test depends on any of those differences, so the
  generator's shape wins on each; the plan lists every one.

## Requirements *(mandatory)*

### Functional Requirements

**B1 — checkpoint commit warning**

- **FR-001**: A non-zero checkpoint-commit return MUST produce one WARNING
  naming the worktree and carrying git's own error text.
- **FR-002**: The change MUST NOT alter behaviour: no raise, no sha on
  failure, sha recorded on success, no warning on success.

**B2 — notify route drop**

- **FR-003**: Dropping a route because its `$VAR` target is unset MUST
  produce one WARNING naming the route location and the variable.
- **FR-004**: Fail-soft semantics MUST stay: the route is dropped, loading
  succeeds, nothing is POSTed to the literal string.
- **FR-005**: `sdlc doctor`'s notify-routes
  check MUST report WARN listing every unset `$VAR` target found in the raw
  asset, and stay OK when there are none. It MUST NOT change the check's
  severity class or the result for an unloadable asset.

**B3 — fleet snapshot fixture**

- **FR-006**: The fixture generator MUST expose its data construction
  separately from its file write so a test can call it without touching disk.
- **FR-007**: The generator's output MUST contain every row the committed
  fixture carries today — including `graph-run-live`, `graph-run-closed`,
  `closed_marks`, and the R-2 `project_key` states (set on two runs,
  explicit null on two, key-absent on three) — as rows the generator itself
  builds from the real models, plus one commented list of run ids whose
  `project_key` is omitted after the dump. No sidecar file.
- **FR-008**: A fast-tier test MUST fail when the generator's output differs
  from the committed fixture, comparing parsed data.
- **FR-009**: Existing frontend API tests MUST pass without edits to their
  assertions.

**B4 — research gotchas**

- **FR-010**: The research slice's editing guide MUST gain a "Gotchas"
  section covering E-29 fail-and-continue, verifier rules, and
  budget-enforcement corner cases, derived from the current code.
- **FR-011**: The section MUST NOT duplicate WHAT-level clauses of the
  stage's own doc, and no other file changes for B4.

**B5/B6 — register row drafts**

- **FR-012**: Each of the two inbox task files MUST gain an appended "Draft
  register row" section, in the register's existing row style, with
  citations re-verified on main.
- **FR-013**: The register file MUST NOT be edited by this batch.

**Batch-wide**

- **FR-014**: Each tracked-file item (B1–B4) MUST be independently
  committable and revertable; behaviour-changing items (B1, B2, B3) land
  test-first. B5/B6 are working-tree deliverables (amendment A2).
- **FR-015**: The batch MUST NOT edit `src/sdlc/stages/code/step.py`, change
  dependencies, touch retry/budget settings, or edit historical docs.

## Verified premises

Re-checked on main `817f819` (inbox line numbers were stale):

| Item | Premise | Status |
|------|---------|--------|
| B1 | `stages/code/activities.py` checkpoint commit at ~198-203: non-zero return discarded, `git add` above raises | Holds. Module logger is `_log` (inbox snippet says `log`). |
| B2 | `notify/routes.py` `_parse_route` ~83-87 returns None for an unset `$VAR` | Holds. `routes.py` has no logger today; `notifiers.py` uses the `sdlc.notify` logger. |
| B2 doctor | `doctor/checks.py` `check_notify_routes` only reports parse OK / WARN on load error | Holds — no unset-variable detection. |
| B3 | Generator emits 5 runs + 1 inbox row in a single `main()`; committed fixture has 7 runs plus `closed_marks` | Holds, and the drift is wider than the inbox task says — see amendment A1. All hand-row fields (`stage_marks`, `graph_sha`, `project_key`, `closed_marks`) are real model fields. A sibling graph-fixture freshness test already exists as the pattern. |
| B4 | Research `AGENTS.md` has Invariants / Temporal notes / State / Tests, no gotchas | Holds. Retired page recoverable from git history for a topic list only. |
| B5 | Provider-import test asserts wall-clock < 8.0 s around a spawned interpreter | Holds, unchanged (`tests/test_promptfoo_provider.py` ~116-139). |
| B6 | `LensOutcome` landed (C8); reviewer/adversary benchmark records emitted only when the lens runs | Holds post-005. Adversary returns before any record when disabled/agent missing; reviewer record guarded on a non-None report (`review/step.py` ~145 and ~213; matrix empty state ~149). |

## Non-goals

- B2 "related, same shape" findings: delivery-time `EgressDenied` refusal and
  the dashboard chat-config warning — out (GATE 1 did not pull them in).
- B1: any change to checkpoint/anchor behaviour or a fallback baseline.
- B3: codegen for the TS mapper; changing what the frontend tests assert.
- B5/B6: implementing either remedy; editing or creating a register file.
- B4: porting the retired page; edits to the stage's WHAT doc.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A run whose every checkpoint commit fails shows one warning
  per failed attempt in the worker log (today: zero).
- **SC-002**: An operator with an unset notify variable sees the variable's
  name in the log at load time (today: nothing until a gate goes unanswered).
- **SC-003**: After this batch's one deliberate regeneration, regenerating
  the fleet fixture on an unchanged tree produces a zero-line data diff, and
  the frontend API tests pass on the result.
- **SC-004**: A dashboard-model shape change is caught by the fast test tier
  in the same change that introduces it.
- **SC-005**: Every gotcha bullet and every draft-row citation resolves to
  current code when spot-checked by the reviewer (100%).
- **SC-006**: The register file has zero commits and zero working-tree
  changes from this batch; six inbox items can be closed.
- **SC-007**: Full fast tier stays green; 10–14 tasks, each one commit-sized.

## Assumptions

- Warnings use each module's existing logging convention; exact message
  wording is a plan-level detail, the named contents (worktree + git text;
  location + variable) are binding.
- B3's freshness test follows the existing graph-fixture freshness test's
  shape and tier.
- Inbox task files are closed (status flipped) by the orchestrator/user at
  merge, not by the tasks themselves — except the appended draft sections.
- No new spec branch is implied by this document; branch handling is the
  orchestrator's.

## GATE 1 rulings

User rulings relayed by the orchestrator, 2026-10-02. No open questions remain.

- **Q1 (B2 doctor half) — RIDE.** FR-005 is unconditional and lands in this
  batch (~2 tasks). F2 deferred row 13 closes with it.
- **Q2 (B3 mechanism) — TAUGHT ROWS.** The generator builds every hand row
  from the real models, plus one commented omission list of run ids whose
  `project_key` is dropped after the dump (the R-2 absent-path pinning).
  No sidecar.
- **Q3 (B5/B6 register) — DRAFTS STAY IN THE INBOX FILES.** No register
  file and no row id is named; each draft names only a suggested section
  (B5 → "C. Verification and quality"; B6 → "D. Learning and the quality
  cycle"). The crew creates and edits no register file.

## Post-GATE-1 consult amendments

From the advisor (`.workspace/tmp/advisor-006-1.md`) and skeptic
(`.workspace/tmp/skeptic-006-1.md`) consults, each re-checked in code by the
planner. They correct facts; no GATE 1 ruling changes.

- **A1 (B3) — first regeneration is not a zero diff.** Besides the named
  hand rows, the models now emit keys the committed file lacks:
  `stage_marks`/`graph_sha` nulls on non-graph open runs, `graph_sha` null
  on closed rows, `thaw_tests` on decisions, `parent_run_id` on pending
  rows, `open_errors` on the snapshot; and the generator's
  `total_open_runs` says 2 where the file says 3. The frontend mapper reads
  none of the added keys and treats absent and null alike, so the fixture
  is regenerated once, deliberately, and US3 scenario 1 / SC-003 hold from
  that commit on. The `project_key` omission list stays the only pruning
  (it pins the R-2 intent; it is not a test dependency).
- **A2 (B5/B6) — inbox files are git-ignored.** `.workspace/` is ignored,
  so the two draft sections cannot be commits. They are working-tree
  deliverables, verified by the reviewer reading the files. FR-014 and
  SC-006 are worded accordingly.
- **A3 (B1) — visibility is the worker log only.** The warning does not
  appear in the Temporal UI or the dashboard. US1 already scopes itself to
  the worker log; surfacing it elsewhere is out of scope.
- **A4 (B2) — one warning per dropped route per load.** Routes are loaded
  on every notification and by doctor, with no cache; repeated warnings are
  accepted (each is a real missed delivery) and no de-duplication is added.
  The warning names the variable, never a value.
- **A5 (B4) — stale docstrings stay.** Two research docstrings still
  describe the persisted budget counter as not yet built (one as a future
  task, one as "deferred"), although it is implemented. FR-011 holds (no other file
  changes); the Gotchas section warns about them instead.
