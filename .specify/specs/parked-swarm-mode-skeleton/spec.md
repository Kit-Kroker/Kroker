# PARKED — Swarm mode walking skeleton

**Status**: Parked 2026-11-14 — **not scheduled.** Available for a future owner go.
**Origin**: Drafted as round 023's spec in `.specify/specs/023-swarm-mode-skeleton/` (since renamed `023-daper-maintenance-loop/`). At GATE 1 on 2026-11-14 the owner chose Option B (finish the P4 row), so the swarm build and the platform-shell rounds came off this program's board. The body below is kept verbatim except where the owner's standing rulings settle a question.
**Traces to**: ADR-22 amendment (`docs/adr.md:312-328`); intent `docs/intent/2026-11-11-swarm-mode-and-poc-finish.md`; ROADMAP §8 item 5.

## Standing owner rulings that bind this spec when it is revived (GATE 1, 2026-11-14)

- **Q2 — the platform shell proceeds regardless of any chain-vs-swarm comparison result**, whenever the shell is built.
- **Q3 — when deterministic checks cannot decide, a swarm agent raises a human gate through FR-301/302 and waits.** Folded into FR-009 below.

## Still open when revived

- Coordination surface = the agent board (E-78)? Default assumed below; not pressure-tested.
- Risky-action set and enforcement on opencode (no hook layer). Default assumed below.
- Prerequisite checks: AP-1.0 landed 2026-11-11 (judges on `zai:glm-5.3-flash`, `dev` on `zai-coding-plan/glm-5.3`). Re-verify on revival.
- Follow-on rounds as drafted: make swarm benchmarkable (M–L) → chain-vs-swarm comparison on one commit, ~6–7 runs per arm, paid on the owner's word (M).

---

## Swarm mode walking skeleton (parked spec body)

### Scope in one paragraph

An operator can start a run in **swarm mode** for one goal on one repository. Instead of the chain's fixed stage order, a small set of goal-driven agents coordinate through the shared agent board: the goal is broken into board tasks, agents claim tasks, do them, and post typed evidence; the run ends when the goal's acceptance criteria are met or a bound is hit. The output goes through the **same** deterministic merge gate the chain uses, with the same absolute floor and the same human gates. The mode sits beside the chain (not a node type in the pipeline graph), is off by default, and changes nothing about chain runs, their replay, or their benchmark signal.

### User Scenarios & Testing

#### User Story 1 — Start a swarm run and get a gated result (Priority: P1)

The owner starts a run for a goal in swarm mode and receives either a merge-gate verdict on an integration branch or a terminal status that says why not.

**Why this priority**: It is the whole mode; nothing downstream (benchmark, comparison) exists without it.

**Independent Test**: Start a swarm run on a deterministic fixture case with fake models; observe board tasks created, claimed, completed, and a merge-gate verdict produced by the same gate chain runs use.

**Acceptance Scenarios**:

1. **Given** swarm mode is enabled and a goal is supplied, **When** the operator starts a run in swarm mode, **Then** the run records its mode as `swarm`, creates board tasks derived from the goal, and reaches the merge gate with the chain's nine required checks evaluated.
2. **Given** a swarm run whose change fails an absolute check, **When** the gate evaluates it, **Then** the run ends `rejected:merge:absolute-gate-failed` with no override path — identical to the chain.
3. **Given** swarm mode is not enabled, **When** the operator asks for a swarm run, **Then** the request is refused with a message naming how to enable it, and no run starts.

#### User Story 2 — The trust layer is the same layer (Priority: P1)

No swarm agent can decide its own verdict: deterministic checks decide; a human decides risky things; judges are independent of the roles they judge.

**Why this priority**: The intent and ADR-22's amendment make this the non-negotiable condition for admitting the mode.

**Independent Test**: Configure a swarm whose judge shares the doer's model id; boot refuses. Have an agent post a self-approval; the gate ignores it.

**Acceptance Scenarios**:

1. **Given** a swarm role registry where any judging role uses the same model id as a doing role, **When** the system boots, **Then** it refuses to start (the AP-1.0 rule extended to swarm roles).
2. **Given** an agent marks its own task done, **When** the board is read, **Then** the agent-writable status may say `done` but the authoritative status changes only on workflow-computed evidence (ADR-21 split).
3. **Given** an agent attempts an action classed as risky, **When** the action is requested, **Then** it is escalated into the existing gate machinery (FR-301/302) and does not proceed until a human decides.

#### User Story 3 — Swarm runs are bounded and observable (Priority: P2)

The owner can see what the swarm did and trust that it stops.

**Why this priority**: An unordered mode without bounds or a trace cannot be benchmarked in R024/R025.

**Independent Test**: Run a swarm on a fixture whose goal can never be met; observe it stop at its bound with a named status and a readable trace.

**Acceptance Scenarios**:

1. **Given** a swarm run, **When** the run's spend crosses the run budget, **Then** the existing budget gate fires (approve = one more increment, reject = `rejected:budget`).
2. **Given** a swarm run, **When** the task-claim count or wall-clock bound is reached without the goal met, **Then** the run ends with a distinct terminal status naming the bound.
3. **Given** a running or finished swarm run, **When** the operator lists runs or opens the board, **Then** the run appears with mode `swarm` and every task's claim, evidence, and status transitions are visible in the board's change log.

### Edge Cases

- Two agents claim the same task at the same moment — exactly one claim wins (board optimistic concurrency, FR-1303); the loser picks other work.
- An agent crashes mid-task — the claim is released after a bound and the task becomes claimable again; the attempt is recorded.
- The goal decomposes into zero tasks — the run fails closed with a named status, not a vacuous pass (mirrors the empty-task bypass fix behind SC-5).
- Deterministic checks cannot decide (e.g. a check reports not-collected) — the agent raises a human gate and waits (FR-009).
- An agent's work spans files another task owns — the merge gate's advisory `plan_drift` reports it; nothing is silently accepted.
- The worker restarts mid-run — the run resumes from durable state; no task is done twice in the authoritative record.

### Requirements

New PRD family required (no PRD line covers swarm mode today). Proposed **FR-1500 (new scope)**, epic **E-90**; numbers are proposals until the PRD amendment lands. Each requirement cites the existing id it reuses.

#### Functional Requirements

- **FR-001**: The system MUST offer swarm mode as a run mode selectable at start, beside the chain, off by default, and MUST NOT represent it as a node type in the pipeline graph. *(ADR-22 amendment; FR-1203 untouched)*
- **FR-002**: A swarm run MUST record its mode on every artifact that identifies a run (run summary, live state, benchmark record) so chain and swarm results are never mixed. *(FR-1206 precedent)*
- **FR-003**: A swarm run MUST derive board tasks from the goal and coordinate agents only through the shared agent board; agents exchange typed evidence, not free-form instructions to each other. *(E-78, FR-1300..1303, ADR-21; default for intent open question 3 — see Assumptions)*
- **FR-004**: Task status that decides anything MUST be the authoritative (workflow-written) status, moved only on evidence the workflow verified; agent-written status is advisory. *(ADR-21)*
- **FR-005**: A swarm run's output MUST pass through the same deterministic quality gate as the chain — same required checks, same diff-scoped absolute floor, same advisory/override path, same human merge gate. *(FR-106, SC-5)*
- **FR-006**: Boot MUST refuse a swarm registry in which any judging role shares a model id with any role whose output it judges. *(ADR-6, AP-1.0, `check_adr6_families`)*
- **FR-007**: Actions classed as risky MUST escalate into the existing gate machinery and wait for a human decision; on a harness with no hook layer, the action MUST be prevented by default rather than allowed. *(FR-301/302, E-17, ADR-17 fail-closed; intent open question 2)*
- **FR-008**: A swarm run MUST be bounded by the run budget gate and by explicit task-claim and wall-clock limits, each ending the run with a distinct, named terminal status. *(FR-701, E-33)*
- **FR-009**: When deterministic checks cannot decide, a swarm agent MUST raise a human gate through the existing gate machinery and wait for the decision. *(FR-301/302; intent open question 1 — resolved by owner standing ruling Q3, 2026-11-14)*
- **FR-010**: Every model and tool call in a swarm run MUST be a durable, retry-safe activity so a worker restart resumes without duplicating authoritative work. *(ADR-1, ADR-23)*
- **FR-011**: A swarm run MUST emit the same end-of-run artifacts as the chain (run summary, event export, report) on every terminal path. *(FR-704, E-32)*
- **FR-012**: Enabling swarm mode MUST change nothing about chain runs: chain replay fixtures, chain memo keys, and chain benchmark records stay byte-identical. *(ADR-22 trade-off clause)*
- **FR-013**: The swarm MUST be startable from the existing operator surfaces (CLI at minimum); dashboard and MCP exposure MAY follow in R024+. *(FR-603; FR-601/602 deferred)*

#### Key Entities

- **Swarm run**: one goal, one repository, one pinned commit, mode `swarm`; owns its bounds and terminal status.
- **Goal**: the operator's request plus acceptance criteria the run is judged against.
- **Board task (swarm)**: a unit of work derived from the goal; claimable; carries evidence; has advisory and authoritative status.
- **Swarm agent**: a goal-driven role that claims and performs board tasks; has a model id subject to the judge-independence rule.
- **Evidence**: typed output an agent posts for a task; the only thing the workflow reads to move authoritative status.

### Success Criteria

- **SC-001**: On the deterministic fixture tier, 100% of swarm runs reach either the merge gate or a named bounded terminal status — no run ends without a stated reason.
- **SC-002**: Zero swarm runs pass the merge gate with a failed absolute check (SC-5 held for the new mode).
- **SC-003**: Zero boots succeed with a judge sharing a doer's model id.
- **SC-004**: Chain replay fixtures and chain benchmark records are byte-identical before and after the round.
- **SC-005**: One live swarm run (owner's word, z.ai subscription only) on one existing benchmark case reaches the merge gate or a named bound, and its full trace is readable from the board and run artifacts.
- **SC-006**: The fast test tier holds at the recorded known-baseline failure set — no new failures.

### Assumptions

- **Coordination surface is the existing agent board (E-78).** Intent open question 3; chosen as default because the board already has claims, optimistic concurrency, an authoritative/advisory split and a change log. To be pressure-tested by `skeptic` after GATE 1.
- **Risky-action set for R023** = the set the `pre_tool` hook already denies or escalates (out-of-worktree writes, recursive deletes, agent-config rewrites, non-allowlisted hosts); on opencode (no hook layer) these are prevented by sandbox/fail-closed defaults. Widening the set is later work.
- **Agent roster for the skeleton** is small (planner-like decomposer, doer, independent judge); roster design is `/speckit-plan`'s job.
- One model provider (z.ai subscription), no Anthropic arm; paid runs only on the owner's word.
- No PRD/ROADMAP/ADR edits in this phase; the PRD FR-1500 amendment is a plan-phase task.
- `.specify/feature.json` and `CLAUDE.md` carry pre-existing uncommitted changes that are not this seat's; this phase does not repoint `feature.json` or run the agent-context hook (which rewrites `CLAUDE.md`). The orchestrator decides when to repoint.

