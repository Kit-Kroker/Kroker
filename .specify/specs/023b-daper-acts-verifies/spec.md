# Feature Specification: Round 023b — DAPER maintenance loop: acts and verifies

**Feature Branch**: none (spec-only phase; this round writes under `.specify/specs/023b-daper-acts-verifies/` only)

**Created**: 2026-11-15

**Status**: GATE 1 cleared (owner, 2026-11-15); advisor/skeptic folded; plan + tasks reviewer-approved (pass 1 each, gaps folded); GATE 2 cleared (owner, 2026-11-15; record at end) — ready for exec.

**Input**: Orchestrator TASK BRIEF, 2026-11-15: "round 023b, the second half of DAPER (E-14): acts and verifies." 023a is landed, verified and integrated (HEAD `f576d2f7`). Binding GATE 2 rulings (2026-11-14) apply: rollback execution and deploy liveness are deferred past P4; confidence threshold 0.8 stands; build probes stay behind the explicit-enable flag; no paid live cycle without the owner's word.

**Authority**: `.specify/specs/023-daper-maintenance-loop/spec.md` (Part B, GATE 2 record), its `verification.md`, and `ARCHITECTURE.md` §7. 023b does not re-open 023a's settled decisions; it builds only what 023a explicitly deferred to 023b.

---

## Part A — Scope and round boundary

### A.1 What 023b is

023a made the loop **plan and gate, and never act**. 023b adds the second half of the DAPER cycle: **Execute** and **Report**.

- **Execute.** An approved `code_fix` action starts a seeded brownfield factory child run, asynchronously, under a deterministic id. The loop never patches code itself.
- **Report.** Each child's branch is re-detected on a verification branch built from the pinned commit. A clean, collected result marks the incident `verified`. Closure needs a later default-branch Detect that no longer reports the identity. A dirty result reopens the incident, boundedly, and then escalates it.
- **Bounds.** Per-cycle and per-project caps limit repair execution. Terminal incidents are retained to memory (FR-401, FR-403).

### A.2 Hypotheses from the brief, checked against the repo

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | 023a is landed and verified, so 023b may start | **Confirmed, with one caveat.** 023a's `verification.md` is "complete". SC-007 (the paid live cycle) was **deferred to the owner**, so 023a's proof is fixture-tier only. 023b must not claim live evidence it lacks | `.specify/specs/023-daper-maintenance-loop/verification.md` (status line, SC-007 row) |
| H2 | Code fixes can reuse an existing seeded-child path | **Partly.** `workflows/tidyup.py` already starts `execute_pipeline_child(...)` with `seeded_work_for(...)`, `_fix_gates()` and `_default_fix_cfg()`, and builds a composite verification branch via `build_verification_branch` with a `gating=False` re-triage (`tidyup.py:192, 228, 319-345`). **But** `seeded_work_for` is written for MECHANICAL findings only ("change nothing else"). Judgement repairs need a new deterministic builder (023a preview; `tidyup/backlog.py:63`). **And** `execute_pipeline_child` awaits the child's final result (`workflows/pipeline_child.py:49`), which is right for tidyup and wrong for a loop that must not block. 023b needs a non-blocking start variant (advisor D1) | `src/sdlc/workflows/tidyup.py`, `src/sdlc/tidyup/backlog.py:63-75` |
| H3 | Repair execution can read off the existing run-budget | **Disproven as a spend source.** `run_budget.py` counts *priced planning-agent spend only*; coding-harness, crew and research spend is not counted (`BUDGET_SCOPE_NOTE`). A child run's spend is therefore not fully measurable through it. Spend caps need their own unit (Q2) | `src/sdlc/run_budget.py:14-16` |
| H4 | The 023a incident machine already has the states 023b needs | **Partly.** `IncidentState` has `APPROVED_NOT_EXECUTED`, `ESCALATED`, `RESOLVED_EXTERNALLY` and `DEFERRED`, but **no** `EXECUTING`, `VERIFYING`, `VERIFIED`, `REOPENED` or `CLOSED`. Those are new states (B-FR-008..010) | `src/sdlc/maintenance/models.py:43-60` |
| H5 | FR-016 ("the loop never writes to a repository") forbids 023b | **Forbids the loop, not the factory.** 023a's FR-016 is tagged "023a scope". 023b must restate it precisely: the loop itself makes no git mutation; repository writes happen inside child runs (the factory's sanctioned path) and inside the existing verification-branch activity. This is a settled-decision amendment and is listed as Q4 | `.specify/specs/023-daper-maintenance-loop/spec.md` FR-016; `src/sdlc/maintenance/AGENTS.md` (invariant 1) |
| H6 | The threshold comparison is settled as strict `>` | **Settled in code and verification. The conflicting wording is in `research.md` R8 line 111** (`effective >= threshold`). `data-model.md` §R9 states the range and default only (`ge=0.5, le=1.0`, default `0.8`), so the verification note's pointer to "data-model §R9 `>=`" is off. The riders are in Part D | `research.md:111`; `verification.md` "Threshold boundary (T025)" |
| H7 | FR-401 incidents and FR-403 non-blocking memory writes can be built from existing parts | **Partly.** `memory/` has `retain`, `scrub.py` and a fake client. No incident retention exists, and FR-403 non-blocking behaviour for incident writes must be verified, not assumed | `src/sdlc/memory/{protocol,activities,scrub}.py` |

### A.3 Round size and the split boundary

Sizing rule (`.workspace/orchestration-protocol.md:186-194`): one L per crew run, XL decomposes first.

**Recommendation: one L round, `023b`.** Its surface is bounded: one new execute path that reuses tidyup machinery, one verification path that reuses the existing activity, a small state extension, two caps, one retention path.

**If sizing fails at plan time, the cut is drawn where the verification evidence lives.** The split is:

- **023b-i (evidence):** Execute (B-FR-001..005), verification branch and `verified` (B-FR-006..007), bounded reopen and escalation (B-FR-009), caps (B-FR-010..011).
- **023b-ii (closure and memory):** closure as `closed` on a later default-branch Detect (B-FR-008), incident retention to memory (B-FR-012..013).

The cut is drawn there because `verified` is the first point at which a run produces its own evidence. Closure and retention depend on it but do not produce new evidence.

---

## Part B — Round 023b: acts and verifies

### User Scenarios & Testing

#### User Story 1 — An approved code fix runs as a child run, without blocking the loop (Priority: P1)

An operator, or a policy-cleared mechanical plan, approves a plan with a `code_fix` action. The loop starts a seeded brownfield child run for it and goes on with the cycle. The child run is not waited on, and it never patches the repository directly.

**Why this priority**: This is the first time the loop acts. Without it, 023a only plans.

**Independent Test**: On the fixture tier, approve a seeded mechanical plan and a seeded judgement plan. Confirm each starts exactly one child run with a deterministic id, and that the cycle completes while the child is parked at its merge gate.

**Acceptance Scenarios**:

1. **Given** an execution-enabled project and an incident in `approved` with a policy-cleared mechanical `code_fix`-only plan, **When** the cycle reaches Execute, **Then** exactly one child run starts with a deterministic id (loop run id, incident, attempt), the cycle does not await it, and the incident moves to `executing`.
2. **Given** a judgement-class plan approved with `decided_by == "human"`, **When** Execute runs, **Then** the child run starts with a judgement-repair seeded work item whose acceptance criterion names the signal, rule and signal version.
3. **Given** a judgement-class, mixed, or reopened plan whose decision is `decided_by == "policy"` (possible at a lowered threshold), **When** Execute runs, **Then** nothing starts and the incident returns to `awaiting_decision` (B-FR-002).
4. **Given** a child run parked at its merge gate, **When** the cycle runs, **Then** the cycle completes and does not wait on the child.

**Independent Test**: fixture-tier workflow test with a stubbed factory child.

#### User Story 2 — A fix is verified by re-detecting on a verification branch (Priority: P1)

When a child run parks at its merge gate (its integration branch built, its PR not yet opened), the loop builds a verification branch from the child's base commit plus the child's branch, runs Detect on both, and compares them. A clean, collected result marks the incident `verified`, and the child's merge gate is left for a human. A dirty result rejects the child's merge gate, so no PR opens for a repair the loop has proven wrong. The verified state does not close the incident.

**Why this priority**: "Verified" is what separates 023b from a fix-and-hope loop. This is the evidence boundary.

**Independent Test**: Seed a build break. Run a mechanical fix that repairs it, then one that does not. The first becomes `verified`. The second reopens.

**Acceptance Scenarios**:

1. **Given** a child branch that repairs the seeded finding, **When** the verification re-detect is collected and the identity is absent (`RESOLVED`), **Then** the incident moves to `verified`, and a new repair for that identity is suppressed.
2. **Given** a child branch whose verification re-detect is not collected, **When** Report runs, **Then** the incident stays `verifying` and is never `verified` (B-FR-007).
4. **Given** a finding already absent at the child's base commit (fixed upstream), **When** Report runs, **Then** the incident becomes `resolved_externally` and the child is not credited.
5. **Given** a dirty verdict, **When** Report runs, **Then** the child's merge gate is rejected with `decided_by="policy"` and the verdict as the note, and no PR opens (B-FR-006a).
3. **Given** a child branch that fails to merge into the verification branch, **When** Report runs, **Then** the incident is recorded as conflicted, not verified, and follows the reopen rule.

#### User Story 3 — A failed repair reopens, then escalates, within a bound (Priority: P1)

If the finding is still present after a repair attempt, the incident reopens and a new attempt is planned. Attempts are capped. When the cap is reached, the incident escalates and the operator is notified.

**Why this priority**: Without a bound, a loop that cannot fix something runs forever and spends without limit.

**Independent Test**: Seed a fix that never works. Confirm exactly the bounded number of reopens, then `escalated`.

**Acceptance Scenarios**:

1. **Given** a dirty verification result and reopen count below the bound, **When** Report runs, **Then** the incident reopens, the count increments, and a new plan is requested.
2. **Given** a dirty verification result and reopen count at the bound, **When** Report runs, **Then** the incident moves to `escalated`, the operator is notified, and no further repair starts for that identity.

#### User Story 4 — Closure needs a later default-branch Detect (Priority: P2)

A `verified` incident closes only after its fix has merged to the default branch and a later Detect on that branch, collected, no longer reports the identity.

**Why this priority**: `verified` is a claim about a branch. `closed` is a claim about the product.

**Independent Test**: Verify an incident, merge the fix in the test harness, run a default-branch Detect, and confirm the incident moves to `closed`.

**Acceptance Scenarios**:

1. **Given** a `verified` incident and a later collected default-branch Detect that omits the identity at a commit from which the child's head is reachable, **When** the cycle runs, **Then** the incident moves to `closed`.
4. **Given** a `verified` incident whose identity is gone but whose child commit is not reachable from the default branch (fixed another way), **When** the cycle runs, **Then** the incident moves to `resolved_externally`, not `closed`.
2. **Given** a `verified` incident and a later Detect that is not collected, **When** the cycle runs, **Then** the incident stays `verified`.
3. **Given** a `verified` incident whose identity is present on the default branch at a commit containing the child's head, **When** the cycle runs, **Then** the incident reopens under the bound (B-FR-009). If the child head is not on the default branch, it stays `verified`.

#### User Story 5 — Repair execution is bounded per cycle and per project (Priority: P2)

Repair execution has a per-cycle cap on child-run starts and a per-project cap on repair spend. A capped incident is deferred to a later cycle. It is never dropped and never auto-approved.

**Why this priority**: A repair loop without caps is an unbounded spend and a risk to the repository.

**Independent Test**: Seed three approved mechanical plans with a per-cycle cap of one. Confirm one child starts per cycle and the other two are deferred, then start in later cycles.

**Acceptance Scenarios**:

1. **Given** three approved plans and a per-cycle cap of one, **When** a cycle runs, **Then** exactly one child starts, two incidents move to `queued` keeping their approval, and no incident is lost or re-gated.
2. **Given** three starts already in the rolling 7-day window, **When** the next cycle runs, **Then** no child starts, approved incidents move to `queued`, and the operator is told the window is full.

#### User Story 6 — Terminal incidents are retained to memory without blocking (Priority: P3)

When an incident reaches a terminal state, its symptom, cause, fix and outcome are retained to memory, scrubbed, and labelled with the outcome. A memory outage never blocks or fails a cycle.

**Why this priority**: This is FR-401's incident clause, which has been open since 2026 because no loop produced incidents. It is valuable, but the loop works without it.

**Independent Test**: Close an incident with the fake memory client, then with a failing one. Confirm the record in the first case, and a completed cycle in the second.

**Acceptance Scenarios**:

1. **Given** an incident entering a terminal state, **When** retention runs, **Then** exactly one scrubbed record exists with the symptom, the cause, the fix and the outcome, citing the source run, under the lesson kind if `closed` and the experience kind otherwise. A `verified` incident triggers no retention.
2. **Given** the memory service is unavailable, **When** retention runs, **Then** the cycle completes, the retain is retried, and no secret or path content is written unscrubbed.

### Edge Cases

- **Child run fails, or never reaches its merge gate**: the attempt is recorded as `execution failed` and counts against the reopen bound. The incident is not `verified`, and the cycle does not crash.
- **Child fails for a non-retryable configuration reason** (the graph refuses to start, no `origin` remote, no `gh`): the incident escalates on that attempt and does not reopen. It burns one start, not three (skeptic L2). Enabling execution checks for these up front (B-FR-025).
- **Child stuck before its merge gate**: after the child execution timeout, the loop requests cancellation of the child and counts a failed attempt (advisor D6.5).
- **Child produces an empty diff**: treated as a failed attempt.
- **Default branch moves while an incident waits or a child runs**: the child resolves its own branch head at start, and that head is recorded as the child's base commit. Verification is built on the **child's base commit**, not the Detect-pinned commit. A finding already absent at the child's base was fixed upstream, so the incident becomes `resolved_externally` and the child gets no credit (skeptic L1 scenario 1; advisor D3).
- **Finding fixed on the default branch between approval and Execute**: Detect runs before Execute, and an approved incident whose identity resolved becomes `resolved_externally` with no child started (skeptic L6.2).
- **Worker restart, or history roll-over, with a child in flight**: the child id is deterministic and duplicate starts are rejected, so the restarted loop re-attaches. A child survives the roll-over because the parent abandons it rather than terminating it (B-FR-001).
- **Disable, then re-enable**: a fresh loop gets a fresh run id. Child ids include it, so a new incident numbered 1 cannot collide with an abandoned child from the old loop (advisor D1). The 7-day start window resets with the fresh loop. This is an operator action and is accepted as documented.
- **Build-broken paradox**: a repair child passes merge only if it restores the build itself. A second unrelated break blocks every repair for that signal. This is documented, not solved (023a preview, skeptic (e)4).
- **Two plans touch the same path**: the second waits in `queued` until the first has a verdict.
- **Mixed plan** (a `code_fix` and an ops action): the `code_fix` runs and the ops action is recorded as `not executed — ops proposal only` (GATE 1 Q6). A mixed plan always needs a human decision (B-FR-002; skeptic L4).
- **Several `code_fix` actions in one plan**: one child per (incident, attempt) carries all of them as one seeded work item (skeptic L6.3).
- **Gate rejected**: nothing starts, as in 023a.
- **Dirty verification while the child is parked at its merge gate**: the loop rejects the child's merge gate (B-FR-006a), so no PR opens for a repair the loop has proven does not work. Approving a child's merge gate stays human-only.
- **Disable mid-execution**: disable stops new starts and withdraws the loop's own open gates. Children already running are left to their own run, with their merge gate still human.
- **Judgement or structural repair**: execution always needs a human decision (B-FR-002).
- **A closed fix later regresses**: the identity reappears as a new incident with a fresh number. The old lesson is not deleted, because reflect does not yet prune invalidated lessons (ARCHITECTURE §6 "Target"). The new incident's record cites the earlier one. This is a recorded residual (skeptic L3).
- **Execution not enabled for the project**: the loop behaves exactly as 023a (B-FR-018).

### Requirements

Traces: FR-502 (code-fix half only, see Part C), FR-503 (execute half), FR-401 (incidents), FR-403 (non-blocking memory writes), E-14, ADR-7, ARCHITECTURE §7 (Execute, Report). Reuse targets are named per requirement; the plan confirms each. No PRD or ADR wording changes.

Requirement IDs use the prefix `B-FR-` to keep them apart from 023a's `FR-001..018`.

#### Functional Requirements

- **B-FR-001 (Execute: one non-blocking child per attempt)**: Execute MUST run `code_fix` actions only. Each approved (incident, attempt) starts **one** seeded brownfield factory child run carrying all of the plan's `code_fix` actions. The child MUST be started without awaiting its result, under these rules:
  - The child id is deterministic: loop run id (stable across roll-over, new on every enable) + incident number + attempt.
  - A duplicate start of the same id MUST be rejected and treated as already attached.
  - The parent-close policy MUST be abandon, so neither roll-over nor disable terminates the child.
  - The attempt and the child id MUST be recorded in the same workflow step as the start.
  - The loop MUST NOT patch the repository directly.
  `execute_pipeline_child` awaits the child's result (`workflows/pipeline_child.py:49`), so a non-blocking start variant is required. The abandon-on-roll-over behaviour MUST be proven by a test before the plan relies on it. *(FR-502 code-fix clause; ADR-7; advisor D1; skeptic L6.1, L6.3; precedent `workflows/deployment.py:9`)*

- **B-FR-002 (Execution authority)**: Execute MUST start a child only when the governing decision is valid for the plan.
  - **`decided_by == "policy"`** is accepted only when **all** of these hold:
    - the finding is `MECHANICAL`;
    - every action is `code_fix`;
    - the finding was reproduced on two consecutive collected detects (an uncollected cycle in between breaks the run);
    - the incident has never reopened (`reopens == 0`);
    - effective confidence is strictly greater than the threshold.
  - **Every other plan** requires `decided_by == "human"`. This includes judgement, structural, mixed, and reopened plans.
  - A refused start leaves the incident in `awaiting_decision` and is never silently dropped.
  This guard holds at Execute even though the gate already enforces most of it, because an operator may lower the threshold to 0.5 (`models.py:93`), and the floor table may change. *(FR-503; 023a FR-012; advisor D6.6; skeptic L4, L5)*

- **B-FR-003 (Judgement work builder)**: A deterministic code-fix → seeded-work builder MUST exist for judgement repairs and for multi-action plans. It lives beside `seeded_work_for` in `tidyup/backlog.py`. Its acceptance criterion names the signal, rule and signal version, and it does not carry the mechanical-only "change nothing else" sentence. *(023a preview; advisor D2)*

- **B-FR-004 (Child configuration)**: Child runs MUST reuse tidyup's fix configuration (`_fix_gates`, `_default_fix_cfg`), with the deploy gate off. The child's merge gate stays HARD/HOLD, so only a human can let a repair PR open. *(`workflows/tidyup.py:56-72`; `core/models.py:374`)*

- **B-FR-005 (Non-blocking, observable, bounded)**: The cycle MUST NOT wait on a child. Child progress MUST be read by an activity, using the child's existing run-state query through the client, as the dashboard fleet view does. "Branch ready" means the child is parked at its merge gate with its integration branch built. A child that has not reached its merge gate within the child execution timeout MUST be cancelled and counted as a failed attempt. *(advisor D1, D6.5; `workflows/graph.py:88`; `dashboard/fleet.py:101`)*

- **B-FR-006 (Verification before the PR)**: When a child is parked at its merge gate, Report MUST do the following, in order:
  1. Build a verification branch from the **child's recorded base commit** plus the child's branch, taken from the child's own result, not from a naming convention. This uses the existing verification activity with a per-attempt key. A non-conflict merge failure MUST be recorded as `conflicted`, not crash the cycle.
  2. Run Detect on the child's base commit and on the verification head, with gating off, using a re-detect triage child id distinct from the cycle's.
  3. Classify with `compute_delta`.
  4. Remove the verification worktree and ref afterwards.
  *(`vcs/integration.py:123`; `workflows/tidyup.py:307-345`; advisor D3; skeptic L1)*

- **B-FR-006a (Dirty verdict rejects the child's merge)**: On a dirty or conflicted verdict, the loop MUST reject the child's merge gate. It records `decided_by="policy"` with the verdict as the note, so no PR opens for a repair the loop has proven wrong. The loop MUST NEVER approve a child's merge gate. *(Trust layer: deterministic checks decide toward inaction; humans decide the risky direction; skeptic L1 scenario 2)*

- **B-FR-007 (Verified is evidence-gated)**: An incident MUST move to `verified` only when the base Detect reports the identity, the verification Detect is collected, and the delta is `RESOLVED`. If the identity is absent at the child's base, the incident becomes `resolved_externally` (fixed upstream). An uncollected or `UNVERIFIABLE` result leaves the incident in `verifying`. *(023a not-collected rule; skeptic L1 scenario 1)*

- **B-FR-008 (Closure is a state check)**: A `verified` incident MUST move to `closed` when a collected default-branch Detect does not report its identity, **and** the child's head commit is reachable from the detected commit. This is a read-only ancestry check. If the identity is gone but the child's commit is not reachable, the incident is `resolved_externally`. Closure MUST NOT depend on observing a prev→cur `RESOLVED` transition, and the 023a `RESOLVED` → `resolved_externally` rule MUST NOT pre-empt `closed` for a `verified` incident. *(advisor D6.1, D6.2)*

- **B-FR-009 (Reopen and escalation transitions)**: Only an attempt's **verdict** moves the reopen counter, never a per-cycle Detect. Dirty means any of: the child failed, the diff was empty, the merge conflicted, the delta was `PERSISTED`, or a `verified` identity is present on the default branch at a commit containing the child's head (the fix landed and did not hold). Present without the child head means the PR is unmerged; the incident stays `verified` (research R8).
  - On dirty with `reopens < 2`: set `reopens += 1`, clear the plan, go to `reopened`, then re-plan.
  - On dirty with `reopens == 2`: go to `escalated` and notify. This gives three attempts in total (GATE 1 Q3).
  - A non-retryable configuration failure escalates on that attempt.
  - An incident in `executing`, `verifying` or `reopened` MUST NOT be reopened again by a per-cycle `PERSISTED`.
  - The real reopen count MUST reach the confidence floor, replacing the hard-coded `reopens=0` at `workflows/maintenance.py:199,252`. A reopened mechanical plan then floors at 0.75, below 0.8, so every retry is human-gated. This is intended.
  *(ARCHITECTURE §7; advisor D4; skeptic L2)*

- **B-FR-010 (Per-cycle cap and the `queued` state)**: At most `max_starts_per_cycle` children (default 1) MAY start in one cycle. An approved incident beyond a cap MUST move to a new `queued` state. That state keeps its approval and is never re-planned or re-gated by Detect. The 023a `DEFERRED` state, which Detect flips back to `OPEN`, MUST NOT be used for this. *(advisor D6.3)*

- **B-FR-011 (Per-project start window)**: At most `max_starts_per_window` child starts (default 3) MAY happen per project in a rolling 7-day window. Every start counts, including starts that later fail for infrastructure reasons. The start timestamps MUST be durable loop state, stamped with workflow time and pruned past 7 days, so they survive roll-over. Reaching the window MUST queue incidents and notify the operator. Dollar accounting is out of this round, because `run_budget` does not count harness spend. *(GATE 1 Q2; advisor D5; skeptic L2; `run_budget.py:14-16`)*

- **B-FR-012 (Memory retention, FR-401)**: Retention MUST happen once per incident, when it enters a terminal state. `closed` is retained under a lesson kind. Every other terminal outcome (escalated, rejected, timed out, withdrawn, resolved externally) is retained under an experience kind. `verified` is not terminal and triggers no retention. Lessons and experiences MUST be distinct memory kinds, so recall can filter them on the already-filterable `kind` tag. *(GATE 1 Q5, refined: `verified` is reached before `closed`; skeptic L3; `memory/hindsight_client.py:79,99`)*

- **B-FR-013 (Non-blocking, scrubbed memory, FR-403)**: Incident retention MUST be fire-and-forget with retries, pass the existing scrub hook, and never block or fail a cycle. *(FR-403; `memory/scrub.py`)*

- **B-FR-014 (Durability and idempotence)**: A restart, a retry or a roll-over MUST NOT start a second child for one (incident, attempt), nor write a second incident, gate, verification or retention record. *(023a FR-014; ADR-1, ADR-23)*

- **B-FR-015 (Roll-over carries execution state)**: The idle-boundary roll-over MUST carry the execution records (child id, base commit, attempt), the reopen counts, the 7-day start window, and the verification results needed for closure. A child in flight MUST NOT defer the roll-over indefinitely. A pending loop gate still defers it, as in 023a. The 023a byte-equal guarantee for incidents and baseline still holds. *(023a FR-013, SC-005; skeptic L6.1)*

- **B-FR-016 (Repository writes, amended per GATE 1 Q4)**: The loop MUST make no git mutation itself. Repository writes happen only:
  - (a) inside child runs, under the factory, which open PRs only after a human approves their merge gate;
  - (b) inside the existing verification activity, which also cleans up after itself.
  Read-only git operations (ancestry checks) are allowed. *(023a FR-016, amended; `maintenance/AGENTS.md` invariant 1 is reworded in the same diff)*

- **B-FR-017 (Ops actions not executed)**: Ops actions (rollback, restart, scale) MUST NOT be executed in any path. They stay proposal-only, and the FR-502 ops clause stays open. *(GATE 2 ruling 2)*

- **B-FR-018 (Enablement)**: Execution MUST be enabled per project by an explicit setting, default off. It requires the 023a unattended-execution acknowledgement, because children run the repository's own build and tests. A project without the setting behaves byte-for-byte as 023a. Approval there still lands in the terminal `approved_not_executed` state. *(023a FR-017; NFR-9)*

- **B-FR-019 (Gate contract unchanged)**: The repair gate MUST stay built in code. Nothing may make it open by policy-off or timeout-approve. A timeout still records `timed out — no action`. *(023a FR-011, SC-003)*

- **B-FR-020 (Floor and threshold unchanged)**: The floor table and the 0.8 default threshold (strict `>` for policy approval) are unchanged. The threshold range 0.5–1.0 stands, and B-FR-002 keeps execution safe across that range. *(GATE 2 ruling 4)*

- **B-FR-021 (Replay and benchmark invariance)**: Existing replay fixtures and benchmark records MUST stay byte-identical. The new workflow paths get their own replay coverage. *(023a FR-017; `tests/replay/AGENTS.md`)*

- **B-FR-022 (Live proof stays the owner's)**: No paid live execution run is part of 023b's acceptance. It is a recorded residual, run only on the owner's word. *(GATE 1 Q8; GATE 2 ruling 5)*

- **B-FR-023 (Non-terminal approval under execution)**: With execution enabled, a gate approval MUST land in a new non-terminal `approved` state, which Detect still tracks. A finding that resolves on the default branch before Execute therefore ends `resolved_externally`, and a recovered signal cannot open a duplicate incident. The R7 duplicate-key rule and persisted 023a states MUST validate unchanged. *(skeptic L6.2; advisor D6.4; `maintenance/models.py:63,248-263`)*

- **B-FR-024 (Detect keeps the incident current)**: On `PERSISTED`, the incident's finding and commit MUST refresh to the latest collected Detect, so an approval and an Execute never act on a stale commit. *(skeptic L5; `maintenance/incidents.py:201-209`)*

- **B-FR-025 (Enable-time preconditions)**: Enabling execution MUST refuse, naming what is missing, when the repository has no `origin` remote or the PR tool is unavailable. This stops a whole start window burning on a known-dead path. *(skeptic L2; `stages/merge/activities.py:210-225`)*

#### Key Entities

- **Execution record**: incident, attempt number, deterministic child id, the child's recorded base commit, child branch (from the child's result), child outcome, start time.
- **Verification result**: verification ref, base commit, base and verification triage, delta verdict, collected flag.
- **Incident (extended)**: adds the non-terminal states `approved`, `queued`, `executing`, `verifying`, `verified` and `reopened`, and the terminal state `closed`, to the 023a set. `approved_not_executed` stays terminal and is used only when execution is off. `attempt` and `reopens` are attributes (distinct from `plan_attempts`), not states.
- **Caps**: `max_starts_per_cycle` (default 1); `max_starts_per_window` (default 3, rolling 7 days, with durable start timestamps); reopen bound 2; child execution timeout.
- **Retention record**: scrubbed symptom, cause, fix and outcome, under a lesson kind (`closed`) or an experience kind (other terminals), citing the source run.

### Success Criteria

- **SC-B01**: On the fixture tier, every seeded mechanical fault whose fix repairs it reaches `verified` within one cycle of the child's verdict. 100% of seeded non-repairing fixes reopen and then escalate at the bound.
- **SC-B02**: Zero repair children start for a judgement-class or structural plan without a recorded human decision, across the test matrix.
- **SC-B03**: Zero ops actions executed across the test matrix.
- **SC-B04**: Zero incidents reach `closed` without a collected default-branch Detect that omits the identity at a commit containing the child's head. Zero incidents are credited `verified` for a finding already absent at the child's base.
- **SC-B05**: Cycle completion does not depend on the state of any in-flight child. A test with a child parked indefinitely still completes its cycles.
- **SC-B06**: Zero cycles start more children than the per-cycle cap, and zero 7-day windows hold more starts than the window cap. Zero capped incidents are lost or re-gated; each is queued and later started or escalated.
- **SC-B10**: Zero PRs opened by a child whose verification verdict was dirty, and zero child merge gates approved by the loop.
- **SC-B11**: A child in flight survives a history roll-over and is re-attached. Proven by a test.
- **SC-B07**: A memory outage causes zero failed cycles. Every retained record is scrubbed before it is written.
- **SC-B08**: Zero duplicate children, incidents, gates or retention records across restart and retry tests.
- **SC-B09**: Existing replay fixtures and benchmark records are byte-identical. The fast tier holds at the recorded known-baseline failure set, with no new failures.

### Assumptions

- **Tidyup machinery is reused, not forked.** Child configuration, the child start helper, the verification activity and `compute_delta` are called from here. Triage types are imported, not triage calls made from maintenance (`src/sdlc/maintenance/AGENTS.md`).
- **Execution is opt-in per project**, default off (B-FR-018).
- **Repair children run the triaged repository's own build and test commands**, which NFR-9 already accepts for the build probe. Execution widens that exposure to child runs. This is stated, and is governed by the same explicit-enable acknowledgement (the 023a `--ack-unattended-build-probe` pattern).
- **Default reopen bound is 2**; default per-cycle start cap is 1. These are proposals, pending Q2 and Q3.
- **Mechanical-only auto-execution.** Under the 0.8 threshold, only mechanical findings reproduced on two consecutive cycles reach policy execution. Advisory and credential plans are always human-gated (GATE 2 ruling 4).
- **Settled 023a decisions are not reopened**: the code-computed floor, the gate built in code, the baseline and `compute_delta`, `finding_identity`, nudge coalescing, and `continue_as_new` at idle.

### Out of scope (023b)

- **Rollback execution** — deferred past P4 (GATE 2 ruling 2).
- **Deploy liveness** — deferred past P4 (GATE 2 ruling 2). Detect remains the triage signals; the 023a narrowing stays recorded.
- **Execution of any ops action** (restart, scale, rollback) — the FR-502 ops clause stays open.
- **Re-baselining** as a verb — 023a's disable-and-re-enable path stands.
- **B2 σ-bands, A4 signal → intent, D1 incident → eval** — remain blocked on the Execute/Report halves, which this round delivers. They are not built here.
- **E-25 org-bank incident writer** — promotion of incident lessons to the `org` bank is not built here. Project-bank retention only.
- **MCP and dashboard exposure of incidents** — CLI only, as in 023a.
- **CI, quarantined-task and error-budget signals** — Detect stays the triage signal set.
- **Stale-PR notification** and **a repair-PR review workflow** beyond what the factory child already does.
- **Two worker pools (R024)** and **fleet runs (R025)** — sequenced after this round.
- **Paid live cycle** — the owner's run (GATE 2 ruling 5).
- **Swarm mode and the platform shell** — off this program's board (`parked-swarm-mode-skeleton`).

---

## Part C — FR-502 status after this round

FR-502 is split by the GATE 2 ruling:

- **Code-fix clause** ("`code_fix` actions SHALL execute as brownfield factory runs (children), never as direct patches"): **delivered by 023b** (B-FR-001, B-FR-016).
- **Ops clause** ("ops actions SHALL be risk-classed"): **stays open**. 023b does not execute ops actions (B-FR-017). When P4 closes, FR-502 is recorded as an honest partial with this clause open.

PRD FR-502 wording is not changed. The roadmap row records the partial state.

---

## Part D — Riders for the executor close-out

These are plan-phase docs and small code items. They are listed here so they are not lost. None changes a 023b requirement.

1. **Threshold wording alignment**: `research.md` R8 line 111 says `effective >= threshold`. The code and `verification.md` say strict `>`. Align R8 to `>`, and cite that the at-threshold plan stays human-gated. (`data-model.md` §R9 states only the range and default; the verification note's pointer to `>=` in §R9 is corrected here.)
2. **verification.md residuals scoped to 023b**: SC-007 (live cycle) stays owner-deferred. Advisory-kind incidents are unit-tier only. The workflow tier runs `advisory_source=none`. 023b must add a workflow-tier advisory case, or record it as still unit-only.
3. **Roadmap rows**: `ROADMAP.md` FR-502 stays `[ ]` until P4 closes, with the honest-partial note. FR-501's "half built" banner gains an 023b line only when 023b lands.
4. **Stale pointer**: `src/sdlc/maintenance/AGENTS.md` cites `workflow-wire.md` under 023a's directory. Keep it, and add the 023b contract under this directory.

---

## Open questions for GATE 1 (owner)

Each has a recommended answer. The round can be planned on the recommendations if the owner accepts them.

- **Q1 — Round shape.** One L round (`023b`), or split now into `023b-i` (execute, verify, reopen, caps) and `023b-ii` (closure, memory)? **Recommend: one L round**, with the Part A.3 cut named in case sizing fails at plan time.

- **Q2 — Spend cap unit and default.** `run_budget` does not count harness spend, so dollars are not a reliable unit for child runs. **Recommend: count child-run starts per project per 7-day window** (default 3), plus the per-cycle start cap (default 1). Dollar accounting can be a later round, once harness spend is counted.

- **Q3 — Reopen bound.** **Recommend: 2 reopens** (3 attempts total), then `escalated`.

- **Q4 — FR-016 amendment.** The loop makes no git mutation itself. Children (the factory) and the existing verification-branch activity write the repository, and children open PRs. **Recommend: confirm.** This is the one settled 023a decision 023b changes, and it changes it only in the way the factory's own design (ARCHITECTURE §7) already describes.

- **Q5 — Memory retention scope.** **Recommend: retain every terminal incident, labelled by outcome. Only `verified` and `closed` are labelled as lessons** (ARCHITECTURE §6 "only verified lessons are retained"). Escalated, rejected and withdrawn incidents are retained as experiences.

- **Q6 — Mixed plans.** A plan with both a `code_fix` and an ops action. **Recommend: execute the `code_fix`, record the ops action as `not executed — ops proposal only`.** Refusing the whole plan would make a useful code fix wait on an ops proposal the loop will never execute.

- **Q7 — Round id.** **Recommend `023b-daper-acts-verifies`.** `024` is reserved for the two-pool round in the roadmap.

- **Q8 — Live evidence.** 023a's SC-007 is owner-deferred. Should 023b's acceptance require a live seeded execution run, or stay fixture-tier with the live run owner-deferred as 023a's was? **Recommend: fixture-tier acceptance; the live run is owner-deferred, and its absence is recorded as a residual, not a blocker.**

---

## GATE 1 record (owner, 2026-11-15)

All eight recommendations were accepted, as relayed by the orchestrator.

1. **Q1 — Round shape:** one L round, `023b`. The Part A.3 cut (023b-i evidence / 023b-ii closure and memory) is named and is the fallback if sizing fails at plan time.
2. **Q2 — Spend cap:** the unit is child-run starts per project per 7-day window (default 3), plus a per-cycle start cap (default 1). Dollar accounting is deferred to a later round. B-FR-011 is read this way.
3. **Q3 — Reopen bound:** two reopens, then `escalated` (three attempts in total).
4. **Q4 — FR-016 amendment, confirmed explicitly:** the loop writes nothing itself. Child runs write the repository, the existing verification-branch activity writes the verification branch, and children open PRs, as ARCHITECTURE §7 already describes. B-FR-016 stands as written.
5. **Q5 — Memory:** `verified` and `closed` incidents are retained as lessons. Other terminal outcomes (escalated, rejected, withdrawn, timed out, resolved externally) are retained as experiences. B-FR-012 is read this way.
6. **Q6 — Mixed plans:** a plan with a `code_fix` and an ops action executes the `code_fix`. The ops action is recorded as `not executed — ops proposal only`.
7. **Q7 — Round id:** `023b-daper-acts-verifies`. `.specify/feature.json` already points there.
8. **Q8 — Live evidence:** acceptance is fixture-tier. The live execution run is owner-deferred and recorded as a residual, not a blocker.

**Standing consequence:** the spec's open-question section is closed by this record. No `[NEEDS CLARIFICATION]` markers were used.

## Consult record

`consults/advisor.md` (D1–D6) and `consults/skeptic.md` (L1–L6), 2026-11-15. The spec lead verified the load-bearing claims against source: `pipeline_child.py:49` awaits the child; the floor table in `confidence.py`; `step()` flips `DEFERRED`; only `kind` is filterable in recall; the seeded graph parks at merge before it opens the PR.

**Folded:**
- Non-blocking child start with abandon, reject-duplicate and a run-id-scoped child id (B-FR-001).
- Tightened policy-execution guard (B-FR-002).
- Verification from the child's base commit, at the child's merge gate, before the PR opens (B-FR-006).
- A dirty verdict rejects the child's merge gate (B-FR-006a).
- Closure as a state check with an ancestry test (B-FR-008).
- Exact reopen transitions, and the real reopen count fed to the floor (B-FR-009).
- A `queued` state distinct from `DEFERRED` (B-FR-010).
- Durable start window (B-FR-011).
- Retention once, at terminal entry, under distinct kinds (B-FR-012).
- Non-terminal `approved` (B-FR-023).
- Incident refresh on `PERSISTED` (B-FR-024).
- Enable-time preconditions, with configuration failures escalating on the first attempt (B-FR-025).
- One child per attempt carrying all `code_fix` actions.

**Not adopted:**
- The skeptic's clamp `effective > max(threshold, 0.8)` for policy execution. It would override the operator's threshold range, which 023a settled. B-FR-002's mechanical/reproduced/never-reopened guard gives the same safety.
- The suggestion to change `TAG_PROMOTED_KEYS`. Distinct memory kinds use the already-filterable `kind` tag.

**Recorded residual:** reflect does not prune lessons later invalidated (ARCHITECTURE §6 is still Target). A closed fix that later regresses leaves its lesson in place, and the new incident cites it.

## Items the owner should see at GATE 2

1. **B-FR-006a — the loop rejects a child's merge gate on a dirty verdict.** This is a deterministic check deciding toward inaction, and approval stays human-only. It is new decision authority for the loop, so it is surfaced rather than buried.
2. **Q5 refined.** `verified` is not terminal, so lessons are retained at `closed`, and an incident that was verified but later escalates is retained as an experience. The ruling's intent ("only proven fixes are lessons") is kept.
3. **Residual:** no lesson invalidation (above). The live execution run stays owner-deferred (Q8).

---

## GATE 2 record (owner, 2026-11-15)

The rulings were relayed by the orchestrator after the reviewer approved plan.md (pass 1, six non-blocking gaps folded) and tasks.md (pass 1, three non-blocking gaps folded). The exec tab consumes plan.md and tasks.md **as approved**, with no edits from this record.

1. **The loop's power to reject a child's merge gate is granted** (B-FR-006a, research R5). It is reject-only, and only on a dirty or conflicted verification. Approving a child's merge gate stays human-only. The restriction is pinned by a test (T024, SC-B10).
2. **The Q5 refinement is accepted.** `closed` incidents are retained as lessons, and every other terminal outcome is retained as an experience. `verified` is not terminal and triggers no retention (B-FR-012, research R13).
3. **The four residuals are accepted as recorded, not fixed.** They go into `verification.md` (T053):
   - squash merges resolve as `resolved_externally` and are retained as experiences only;
   - a `verified` incident whose fix never reaches the default branch stays `verified` (no stale-PR handling);
   - lessons are not invalidated when a closed fix later regresses;
   - advisory-kind execution is tested at the unit tier only.
4. **The live execution run stays the owner's**, outside acceptance (B-FR-022, quickstart §5). No paid run happens without the owner's word.
