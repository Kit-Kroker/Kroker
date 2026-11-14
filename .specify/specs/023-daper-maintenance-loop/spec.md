# Feature Specification: "Finish all of needed" = finish the P4 row — scope, round sequencing, and round 023a (DAPER maintenance loop: plans, gated, never acts)

**Feature Branch**: none (spec-only phase; plan-side seats write under `.specify/specs/023-daper-maintenance-loop/` only)

**Created**: 2026-11-14 · **Revised**: 2026-11-14 (GATE 1 rulings; advisor/skeptic pass — round split 023a/023b)

**Status**: GATE 1 cleared; advisor/skeptic folded (2026-11-14) — in planning

**Input**: Owner, 2026-11-14, right after a P4 status check: *"lets start crew v3 for finish all of needed"*. GATE 1 rulings relayed by the orchestrator the same day.

---

## Part A — What "needed" covers

### A.0 GATE 1 decision (owner, 2026-11-14)

- **Q1 → Option B, outright: finish the P4 row.** "Needed" = the three P4 items still open (DAPER maintenance loop, fleet scale) and P4's exit criterion (SC-1..3 at target).
- **Owner override, recorded:** this **reverses** the 2026-11-11 intent's *"the maintenance loop as designed (P4)"* entry under "Out of scope for now" (`docs/intent/2026-11-11-swarm-mode-and-poc-finish.md:35-37`) and its swarm-first order (`ROADMAP.md:571`, `docs/roadmap/ordering.md:3-8`). It is the owner's call, made 2026-11-14, and it supersedes the earlier intent. The spec lead recommended Option A; the owner chose B. The 2026-11-11 intent document is not edited by this phase. Updating it, `ROADMAP.md` §8 and `ordering.md` to match is a plan-phase docs task.
- **Swarm build and the platform-shell rounds are off this program's board.** The drafted swarm skeleton spec is parked, not deleted: `.specify/specs/parked-swarm-mode-skeleton/spec.md`.
- **Q2 (standing ruling):** whenever the platform shell is built, it proceeds regardless of any chain-vs-swarm comparison result.
- **Q3 (standing ruling):** when deterministic checks cannot decide, a swarm agent raises a human gate through FR-301/302 and waits. Parked with the swarm spec (folded into its FR-009).

### A.1 Hypotheses from the brief, checked against the repo

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | P4 is one of three done: MCP landed; DAPER and fleet scale never started | **Confirmed** | `ROADMAP.md:263-264`; FR-501..503 all `[ ]` (`ROADMAP.md:339-341`); `ARCHITECTURE.md:537-560` — `MaintenanceWorkflow` is "designed, not built"; nothing in `src/` matches `MaintenanceWorkflow\|DetectionReport\|RepairPlan\|DAPER`. Fleet scale = NFR-2 / ADR-9 (one queue `"ai-sdlc"`, `ROADMAP.md:460,525`), tracked as AP-2.5 (`docs/roadmap/agent-architecture-plan.md:41`) |
| H2 | SC-1..3 unmeasurable: no fleet runs; aggregation landed | **Partly confirmed — SC-2 has no instrument** | `src/sdlc/benchmarks/sc_rollup.py:80` totals **SC-1, SC-3, SC-4, SC-6** only. **SC-2 (≤15 min operator time) has no aggregation and no per-run signal** (`ROADMAP.md:477` "not measurable", with no "aggregation landed" note, unlike its neighbours). So R025 needs an operator-time instrument before its runs can put SC-2 at target. Also: `ROADMAP.md:475` cites `benchmarks/sc_rollup.py`; the file lives at `src/sdlc/benchmarks/sc_rollup.py` (stale path, a rider) |
| H3 | 2026-11-11 intent deferred the maintenance loop | **Confirmed, now overridden by the owner** (A.0) | intent `:35-37` |
| H4 | AP-1.0 judge fix pending | **Disproven — landed 2026-11-11** | `ROADMAP.md:542`; `agents/{reviewer,qa,deep_review,merge_verdict}/agent.yaml` = `zai:glm-5.3-flash`, `agents/dev/agent.yaml` = `zai-coding-plan/glm-5.3`. Relevant here: repair child runs inherit an independent judge. (`agent-architecture-plan.md:26` still shows `[ ]`; stale, a rider) |
| H5 | DAPER is blocked on something | **Unblocked; three ideas wait on it** | E-14 is "blocked on MaintenanceWorkflow existing at all" (`docs/roadmap/filesystem-first.md:78`). External ideas A4 (signal → intent), B2 (σ-bands), D1 (eval per incident) are all "⛔ Blocked · FR-501" (`docs/reports/external-ideas-2026-09.md:45,52,86`), and remain out of R023 (see B.Out of scope) |
| H6 | FR-401 lacks incidents for want of a maintenance loop | **Confirmed** | `ROADMAP.md:333` "no 'incidents' — needs maintenance loop"; `org` bank is designed to hold "cross-project incident learnings" (`SDLC-spec` bank table, line 320) |

### A.2 Options weighed (kept for the record)

| Option | "Needed" means | Outcome |
|---|---|---|
| A — Intent order | Swarm → same-commit benchmark → platform shell | Recommended by the spec lead; **not chosen** |
| **B — Finish the P4 row** | DAPER (E-14, FR-501..503), two worker pools (NFR-2/ADR-9/AP-2.5), fleet runs to put SC-1..3 at target | **Chosen by the owner, 2026-11-14** |
| C — Whole roadmap to P8 | Every open row | Not chosen |
| D — A then P4 | Both | Not chosen ("outright, not D") |

### A.3 Round sequencing under Option B (revised after the advisor/skeptic pass)

Sizing per `.workspace/orchestration-protocol.md:186-194`: at most one L/XL per crew run; XL decomposes first; S riders batch up to ~8. Both consults independently sized the full DAPER loop as **XL** (`consults/advisor.md` §5, `consults/skeptic.md` (g)). It contains several firsts for the repo: the first `continue_as_new`, the first signal-with-start singleton workflow, a generalisation of the Reflect-only schedules package, a new proposer role, a six-state incident machine, and an execute-and-verify path. It is therefore decomposed into two L rounds. This round directory (`023-daper-maintenance-loop/`) plans and builds **023a**. 023b gets its own spec-kit round once 023a is verified.

| Round | Slice | Size | Traces to | Gate to enter |
|---|---|---|---|---|
| **023a** | **DAPER, "plans, gated, never acts"** (Part B): per-project `MaintenanceWorkflow` on a schedule and on nudge; Detect = triage child + baseline + `compute_delta`; code-assigned incidents; one proposer call producing analysis and repair plan; a code-computed confidence floor; a repair-plan gate whose timeout means inaction and that no configuration can open. An approved plan ends `approved — not executed` (advisory mode) | L | FR-501, FR-503; E-14; FR-915; ARCHITECTURE §7 (Detect/Analyze/Plan/gate) | GATE 2 |
| 023b | **DAPER, "acts and verifies"**: code fixes as seeded brownfield child runs started asynchronously; re-detect on a verification branch → `verified`; closure on a later default-branch Detect; bounded reopen; per-cycle repair and spend caps; incident retention to memory; and the ops half (deploy liveness + human-only rollback) **only if** the owner keeps it in P4 (GATE 2 question 2) | L | FR-502, FR-503, FR-401 incidents, FR-403; ADR-7; ARCHITECTURE §7 (Execute/Report) | 023a verified |
| 024 | **Two worker pools**: proposer/support work and harness work on separate task queues and worker pools, routed per role; worktree affinity so a task's harness steps stay with its worktree | L | NFR-2, ADR-9 (and the two-pool core of its 2026-10-11 five-pool amendment), AP-2.5, AP-2.6 | 023b verified |
| 025 | **Fleet runs to put SC-1..3 at target**, in three parts. (a) An SC-2 operator-time instrument: per-run human-wait and decision time into `RunSummary` and `sc_rollup` (the missing piece per H2). (b) At least 5 runs, **paid, on the owner's word only**, aggregated by `sdlc benchmark score`. (c) A read of SC-1/2/3 against target | M + operational | SC-1, SC-2, SC-3; E-34; `src/sdlc/benchmarks/sc_rollup.py` | 024 verified + owner says go |
| 026+ | **Conditional:** remediation rounds, only if R025 reads any of SC-1..3 below target. Sized from that read; the owner decides | — | SC-1..3 | R025 read |

**P4 closes** when 023a, 023b and 024 are verified and R025 reads SC-1..3 at target (`ROADMAP.md:263`).

**Riders in 023a's crew run** (S tasks; plan-phase docs tasks, per the orchestrator's GO):
- Record the Option B override in `ROADMAP.md` §8, `docs/roadmap/ordering.md` and the 2026-11-11 intent doc. The intent doc gets a dated addendum; its body stays as it is.
- Fix the stale path `ROADMAP.md:475` → `src/sdlc/benchmarks/sc_rollup.py`.
- Fix the stale AP-1.0 checkbox at `docs/roadmap/agent-architecture-plan.md:26`.
- Mark ARCHITECTURE §7's Detect inputs as deliberately narrowed (CI, quarantined tasks and error budgets are not built).
- PRD FR-501..503 need **no wording change**. 023a meets FR-501 and the gate half of FR-503 as written. The roadmap rows record the partial state (FR-502 open until 023b).

Outside this program's riders: the FR-202 validation-retries knob (**landed on `main` 2026-11-14, merge `80692c1b`**; no longer a rider, and the maintainer role inherits the knob) and the FR-602 live-client smoke (operator).

**Off this program's board:** swarm mode (parked spec), platform shell (FR-1001/1002, per-role interfaces), Tier 2 depth E-50..E-56, outcome loop P8, service E-59..E-63, AP-2..AP-6 beyond AP-2.5/2.6, P3/P5/P6 closures.

---

## Part B — Round 023a: DAPER maintenance loop — plans, gated, never acts

### Scope in one paragraph

The operator **enables maintenance for a project** by naming its repository, default branch and detector settings. Enabling it is the project's registration, and the loop's own durable state is the record (no new store). On a schedule, and whenever the operator nudges it, the project's single long-lived maintenance loop runs one **cycle**:

- **Detect**: run the existing deterministic triage against a pinned commit of the default branch.
- **Baseline**: the first cycle only records what already exists. Later cycles diff against the baseline and the previous cycle.
- **Incidents**: each *new* finding becomes an incident with a code-assigned identity, and recurrences attach to the open incident.
- **Analyze + Plan**: one proposer call per incident, producing a repair plan with a self-rated confidence. Code caps that rating with a deterministic floor.
- **Repair-plan gate**: built in code, so no operator configuration can make it auto-open or make a timeout approve.

In 023a nothing executes. An approved plan is recorded as `approved — not executed`. The loop never patches code, never acts on a timeout, is off by default, and changes nothing about existing runs.

### User Scenarios & Testing

#### User Story 1 — A new problem becomes a gated repair plan (Priority: P1)

The owner enables maintenance for a project. The first cycle records the baseline and opens nothing. Later a regression lands on the default branch (e.g. the build breaks). The next cycle detects it as new, opens one incident, and produces a repair plan. The plan waits at a human gate or, above threshold, is recorded as approved. Either way nothing touches the repository.

**Why this priority**: It is FR-501 plus FR-503's gate, the half of G5 that can ship without touching a repository.

**Independent Test**: On the deterministic fixture tier, enable maintenance on a fixture repo. Run cycle 1 and assert zero incidents and a recorded baseline. Commit a build-breaking change and run cycle 2. Assert one incident with identity `build_probe:<rule>::`, one repair plan, and one pending repair-plan gate. Assert zero writes to the repository.

**Acceptance Scenarios**:

1. **Given** maintenance was just enabled on a repository with existing findings, **When** the first cycle runs, **Then** it records the set of finding identities as the baseline and opens **zero** incidents.
2. **Given** a baseline exists, **When** a cycle's Detect reports a finding whose identity is in neither the baseline nor an open incident, **Then** exactly one incident opens, carrying the finding, the pinned commit, and the cycle that detected it.
3. **Given** an open incident, **When** a later cycle detects the same identity, **Then** it attaches as a recurrence and opens no second incident or plan.
4. **Given** an incident, **When** Analyze+Plan runs, **Then** the incident carries a repair plan with ordered proposed actions, the proposer's self-rating, the code-computed floor, and the effective confidence (the lower of the two).
5. **Given** any cycle, **When** it completes, **Then** the repository's refs, worktrees and remote are unchanged by the loop (no branch, commit or PR).

#### User Story 2 — Silence and configuration can never open the gate (Priority: P1)

**Why this priority**: The trust layer. An unattended loop that a timeout or a config flag could turn into "approved" defeats FR-503.

**Independent Test**: For each of `on_timeout=APPROVE`, `policy=OFF` and `policy=SOFT` with threshold 0, try to configure the repair gate that way. Assert enablement is refused, or the gate is built from code regardless. Let a below-threshold gate time out and assert the incident records `timed out — no action`.

**Acceptance Scenarios**:

1. **Given** a plan whose effective confidence is below the threshold, **When** the gate opens, **Then** the operator is notified through the existing routes and the item appears in the cross-run inbox with the plan rendered.
2. **Given** that gate times out, **When** the timeout fires, **Then** the incident records `timed out — no action`, and the plan is never marked approved.
3. **Given** a maintenance configuration that asks for a repair gate with timeout-approve, policy off, or an auto-approve threshold outside the allowed range, **When** the operator enables maintenance, **Then** enablement is refused with a message naming the offending field.
4. **Given** a plan at or above threshold, **When** the gate resolves, **Then** it is recorded as approved by policy (not by a human). The record distinguishes `policy`, `human` and `timeout` as deciders, so 023b can require `human` where a risk class demands it.
5. **Given** the operator rejects a plan, **When** the decision lands, **Then** the incident records the rejection, actor and reason, and the plan is never re-proposed for that incident unless the incident reopens.

#### User Story 3 — The loop runs on schedule and on demand, one cycle at a time, and stays bounded (Priority: P2)

**Why this priority**: FR-501 / E-14. Unattended operation must neither overlap nor grow without bound.

**Independent Test**: Apply a maintenance schedule asset (dry-run first) and observe cycles at cadence. Nudge while idle and observe an immediate cycle. Nudge three times during a cycle and observe exactly one follow-up. Force a history roll-over and observe open incidents and pending gates survive.

**Acceptance Scenarios**:

1. **Given** a maintenance schedule asset, **When** the operator runs the schedules apply dry-run, **Then** it reports the change without applying it. A real apply then makes cycles run at the declared cadence. The existing nightly-reflect asset keeps working unchanged.
2. **Given** an enabled project, **When** the operator nudges it from the CLI, **Then** a cycle starts promptly. Nudging a project that is not enabled is refused with a message.
3. **Given** a cycle is running, **When** any number of nudges or timer fires arrive, **Then** exactly one follow-up cycle runs afterwards, and no two cycles of one project ever overlap.
4. **Given** the loop's history has grown past its bound, **When** it is idle (no pending gate), **Then** it continues in a fresh history carrying the baseline, open incidents and counters. If a gate is pending, the roll-over waits for the idle boundary.
5. **Given** an enabled project, **When** the operator lists incidents from the CLI, **Then** each incident shows identity, state, recurrences, effective confidence, gate status, and the last cycle that saw it.

### Edge Cases

- **A detector does not collect** (probe timeout, `advisory_source` = none): the signal reports not-collected and is never read as healthy. It opens no repair incident. Two consecutive not-collected cycles for one signal record a `not_collected` escalation under the synthetic identity `<signal>:not_collected::` and notify the operator. A signal disabled by configuration reads as *not configured*, not as a fault, and never escalates.
- **Signal version changes between cycles**: `compute_delta` reports the finding `UNVERIFIABLE`. That neither opens nor resolves anything, and the next cycle re-baselines that signal.
- **A finding disappears from the default branch while its incident is open** (someone fixed it by hand): a later Detect that no longer reports the identity, with the signal collected, marks the incident `resolved externally`. Only a collected, clean Detect does this, never an absence caused by not-collected.
- **Build broken for two different reasons**: the build probe carries no path or key, so both causes are one incident (`build_probe:build_failed::`). Accepted and documented.
- **Leaked credential**: a matched provider credential is `JUDGEMENT` (rotation is a human act), so its floor caps confidence below any auto-approve threshold and it is always human-gated. A committed `.env` file is `MECHANICAL` (`triage/signals/secrets.py:5-8,35-36`).
- **Proposer fails or returns invalid output**: the incident records `no plan — analysis failed` and notifies. The cycle does not crash, and the next cycle retries the plan (bounded).
- **Plan with zero actions**: the incident records `no action proposed` and goes to the human gate. It never counts as resolved.
- **Default branch moves mid-cycle**: everything in the cycle refers to the commit pinned at Detect.
- **Worker restart mid-cycle**: the cycle resumes from durable state, with no duplicate incident and no duplicate gate.
- **Repository not reachable or not a git repository at enablement**: refused with a message naming what is missing.

### Requirements

Traces to existing PRD lines: FR-501..503 (`PRD.md:284-290`), G5 (`PRD.md:78`), ADR-7 (`docs/adr.md:87-88`), E-14 (`docs/roadmap/filesystem-first.md:78`), and the design in `ARCHITECTURE.md:537-560`, deliberately narrowed (see riders). No new PRD family. Reuse targets are named per requirement; the plan confirms each.

#### Functional Requirements

- **FR-001**: The system MUST run one long-lived maintenance loop per enabled project. Enabling is the registration: repository path, default branch, cadence, detector settings, threshold. No separate project store. *(FR-501; ADR-8 Temporal as source of truth; advisor §1, skeptic (a)1)*
- **FR-002**: Enabling MUST require an explicit acknowledgement that the build probe executes the repository's own code unattended. The build probe MUST be individually disableable per project. *(NFR-9; `workflows/triage.py:7-9`; advisor §7.5)*
- **FR-003**: Cycles MUST start on a declared schedule asset applied through the schedules mechanism, with a dry-run. The schedules mechanism MUST be generalised beyond its single known workflow without changing the existing nightly-reflect asset's behaviour. *(E-14; `schedules/models.py:15-21`, `schedules/apply.py:48-73`; advisor §7.4)*
- **FR-004**: The operator MUST be able to nudge an enabled project from the CLI. The schedule and the nudge MUST reach the same single loop. *(FR-501 "on demand"; FR-603)*
- **FR-005**: At most one cycle per project MUST run at a time. Any number of nudges or timer fires during a cycle MUST coalesce into exactly one follow-up. *(FR-501)*
- **FR-006**: **Detect** MUST reuse the existing deterministic triage against a commit it pins, with the signal set build probe, dependency advisories and secrets, under the project's settings. A signal that is not collected MUST never read as healthy. *(FR-902, FR-915; `workflows/triage.py`; `fanout.run_or_degrade`)*
- **FR-007**: The first cycle MUST record a **baseline** of finding identities and open no incidents. Later cycles MUST classify findings with the existing before/after delta, never with a set difference. Only findings new relative to baseline and open incidents open an incident. `UNVERIFIABLE` results MUST neither open nor resolve. *(`triage/delta.py` `compute_delta`; advisor §4/§7.5, skeptic (a)4)*
- **FR-008**: Incident identity MUST be the existing finding identity (`signal:rule:path:key`). Not-collected escalations MUST use the synthetic identity `<signal>:not_collected::`, kept apart from finding incidents. No two open incidents MAY share an identity. *(`triage/models.py:194` `finding_identity`; advisor §3)*
- **FR-009**: **Analyze + Plan** MUST be one proposer call per incident needing a plan. It produces a repair plan (ordered proposed actions, each a code fix or an ops action, plus a self-rated confidence). A failed or invalid call MUST degrade to `no plan — analysis failed`, never crash the cycle. *(ARCHITECTURE §7 `RepairPlan{confidence, actions[]}`; `AssessmentWorkflow._judge` degrade shape; advisor §5)*
- **FR-010**: Effective confidence MUST be the lower of the proposer's self-rating and a **code-computed floor**. The floor is derived only from deterministic facts: fix class (mechanical high; judgement capped below the default threshold; structural zero), reproduction on a second detect, severity, reopen count, action count. *(ADR-24 direction; `triage/models.py` `FixClass`; advisor §2)*
- **FR-011**: The repair-plan gate MUST be constructed in code. Operator configuration MAY set only the threshold (within a bounded range) and the timeout duration. Enablement MUST refuse any setting that would make the gate open by policy-off or by timeout-approve. A timeout MUST record `timed out — no action`. *(FR-503; `gates.py:200-241`, `core/models.py:57-68`; advisor §7.3, skeptic (c))*
- **FR-012**: Every gate decision MUST record its decider (`human`, `policy`, `timeout`). In 023a an approved plan MUST be recorded as `approved — not executed`, and nothing executes. *(FR-302; `triage/admission.py` decider precedent)*
- **FR-013**: The loop MUST keep its durable history bounded by continuing in a fresh history only at an idle boundary (no pending gate), carrying the baseline, open incidents and counters. *(ARCHITECTURE §7 `continue_as_new`; ADR-1; first use in the repo; advisor §1)*
- **FR-014**: Every signal collection, model call and gate MUST be durable and retry-safe. A restart MUST NOT duplicate an incident or a gate. *(ADR-1, ADR-23)*
- **FR-015**: The operator MUST be able to list incidents and their state (`open`, `awaiting_decision`, `approved_not_executed`, `rejected`, `timed_out`, `resolved_externally`, `escalated`, `withdrawn`) from the CLI, and pending repair gates MUST appear in the existing cross-run inbox. *(FR-304 direction, FR-305, FR-604)*
- **FR-016**: The loop MUST NOT write to the repository: no branch, commit, worktree in the repo, or PR. *(ADR-7, NG5; 023a scope)*
- **FR-017**: Enabling the loop MUST change nothing about existing runs. Existing replay fixtures, memo keys and benchmark records stay byte-identical. The new workflow gets its own replay coverage. *(`tests/replay/AGENTS.md`)*

- **FR-018**: The operator MUST be able to disable a project's loop from the CLI. Disabling finishes any running cycle, withdraws open gates without synthesising any decision, and ends the loop. Re-enabling starts fresh with a new baseline. *(FR-603; 023a's only re-baseline path)*

#### Key Entities

- **Maintenance loop**: one per project; settings (repo, default branch, cadence, detectors, threshold, gate timeout); baseline; open incidents; counters.
- **Cycle**: pinned commit; triage result; delta; incidents opened or touched.
- **Baseline**: the finding-identity set recorded at enablement, with each signal's version.
- **Incident**: identity; finding; first-seen and last-seen cycle; recurrences; state; plan; gate decision with decider.
- **Repair plan**: ordered proposed actions; self-rating; floor; effective confidence.

### Success Criteria

- **SC-001**: On the fixture tier, the first cycle on a repo with pre-existing findings opens 0 incidents. For each R023a signal kind (build, advisory, secret), 100% of seeded new faults open exactly one incident, and 100% of recurrences attach without a second incident.
- **SC-002**: Zero repository writes by the loop across the whole test matrix.
- **SC-003**: Zero plans recorded as approved after a timeout, and zero enablements accepted with timeout-approve or policy-off on the repair gate.
- **SC-004**: Zero overlapping cycles and zero duplicate incidents or gates across concurrent-nudge and restart tests. Exactly one follow-up cycle per burst of nudges.
- **SC-005**: Open incidents and the baseline survive a history roll-over byte-equal.
- **SC-006**: Existing replay fixtures and benchmark records are byte-identical. The fast tier holds at the recorded known-baseline failure set, with no new failures.
- **SC-007**: One live cycle on the owner's word (z.ai subscription only) against a local scratch repository with a seeded build or advisory fault. It records the baseline, detects the fault, produces a plan, and gates it, with the incident readable from the CLI. No GitHub remote or deployed service is needed, because 023a opens no PR.

### Assumptions

- **Detect = the existing triage signals only** (build probe, dependency advisories, secrets). Deploy liveness and rollback are **out of 023a**: no per-project persisted deploy plan exists, the rollback target is never recorded, and both adapters ignore `to_version` (`deploy/adapters.py:86-90,116-117`; advisor §7.2, skeptic (a)2/(b)3). Whether they enter 023b is GATE 2 question 2.
- **Advisories need a declared source.** `advisory_source` defaults to `none`. Enablement may set the declared OSV source, which is the pipeline's existing second outbound egress (FR-703). With `none` the signal reads *not configured*.
- **One proposer role** (`maintainer`) is added to the runtime registry, a proposer, not a judge. Analyze and Plan are one call, since the signals are already deterministic findings with severities (advisor §5).
- **Default threshold 0.8**, so only mechanical findings reproduced on a second detect clear it. Advisory and secret plans are human-gated by construction. This is the conservative default; it is stated, not hidden.
- **Default cadence is daily.** The probe allows 40 minutes per cycle (`workflows/triage.py:70-72`), and sub-hourly cadences are refused.
- **Re-baselining** (accepting the current state as the new normal) is not in 023a. The operator disables and re-enables instead.
- **No PRD/ADR wording changes.** Roadmap, ordering and intent updates are rider tasks.
- **Pre-existing uncommitted files** that are not this round's stay untouched.

### Out of scope (023a)

Executing anything; seeded repair child runs; verification-branch re-detect; closure as `verified`/`closed`; reopen bound; repair/spend caps; memory retention of incidents (all 023b). Also out: deploy liveness and rollback (023b or later, GATE 2 question 2); B2 σ-bands; A4 signal → intent; D1 incident → eval; the E-25 org-bank writer; MCP and dashboard exposure; re-baseline verb; stale-PR notification.

### 023b preview (its own round; recorded so nothing is lost)

- **Execute**: code fixes start as seeded brownfield child runs, asynchronously, with deterministic ids. The loop never blocks a cycle on a child parked at its merge gate (merge is HARD/HOLD, `core/models.py:374`). Child config reuses TidyUp's `_fix_gates`/`_default_fix_cfg` (deploy gate off). A deterministic code-fix → `SeededWork` builder is needed; `seeded_work_for`'s "mechanical, change nothing else" wording does not fit judgement repairs (skeptic (e), advisor §6).
- **Human-required check**: execution requires `decided_by == "human"` for any human-required risk class, and accepts `policy` only for confidence-cleared code fixes.
- **Report**: build the verification branch on the pinned commit (`tidyup.py:330-345`), re-triage, then `compute_delta`. `RESOLVED` means `verified` (PR awaiting merge), and new repair runs are suppressed for that identity. `closed` only when a later default-branch Detect no longer reports it. A dirty result reopens, bounded, then escalates.
- **Correction carried from the first draft**: the repair child resolves the branch head at start, and only the verification branch is on the pinned commit. The claim "repair against the detected commit" is weakened accordingly (advisor §7.1).
- **Build-broken paradox**: a repair child passes merge only if it restores the build itself. A second unrelated break blocks every repair. Documented, not solved (skeptic (e)4).
- **Ops half, only if kept**: rollback requires an operator-supplied deploy config and a recorded last-healthy version, and is refused as unexecutable otherwise. It is always human-required. The risk classification is honestly a one-tier stub until restart/scale adapters exist (skeptic (b)).
- **Live check**: needs a scratch GitHub repo with `gh` and a token for the PR step (skeptic (f)).

### Consult record

`consults/advisor.md` and `consults/skeptic.md` (2026-11-14). Folded: split 023a/023b; long-lived loop with a schedule kicker; code floor on confidence; `finding_identity` reuse; baseline + `compute_delta`; gate built in code with decider recording; schedules generalisation scoped honestly; deploy/rollback out of 023a; NFR-9 opt-in; the async-child and `verified`-state designs carried to 023b. Not adopted: the skeptic's suggestion to retain escalation memories in 023a (memory moves as one piece in 023b).

---

## GATE 2 record (owner, 2026-11-14)

The rulings were relayed by the orchestrator after the reviewer approved plan.md (pass 1) and tasks.md (pass 2). plan.md and tasks.md are consumed **as approved**, with no edits from this record.

1. **The 023a/023b split is confirmed.** 023a (this round) plans, gates and never acts. 023b (execute and verify) gets its own spec-kit round after 023a is verified.
2. **Rollback execution and deploy liveness are deferred past P4.** They are not part of 023b. When P4 closes, FR-502 is recorded as an **honest partial**: its code-fix half is delivered by 023b, and its clause "ops actions SHALL be risk-classed" stays open. This supersedes the "only if the owner keeps it in P4" wording in A.3 and §023b preview.
3. **The NFR-9 build-probe risk is accepted** under the explicit-enable flag (`--ack-unattended-build-probe`), with `--no-build-probe` as the escape (FR-002, research R14), as planned.
4. **The confidence threshold stays 0.8.** Only mechanical findings reproduced on two consecutive cycles clear policy, and advisory and credential plans are always human-gated (research R8).
5. **The paid live cycle (SC-007) stays the owner's run.** The orchestrator asks at exec time; no paid run happens without that word.
