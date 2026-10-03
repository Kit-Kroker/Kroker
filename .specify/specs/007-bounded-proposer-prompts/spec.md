# Feature Specification: Bounded Proposer Prompts

**Feature Branch**: `007-bounded-proposer-prompts` (spec directory only; no branch was created)

**Created**: 2026-10-03

**Status**: GATE 1 cleared 2026-10-03; rulings folded in (see [GATE 1 rulings](#gate-1-rulings)); consult amendments A1-A8 added the same day; GATE 2 cleared 2026-10-03

**Input**: Defect 6.3, "an oversized prompt hangs the run instead of failing it". Brief: `.workspace/tmp/planner-brief-007-bounded-proposer-prompts.md`. Sources: `docs/reports/2026-09-27-pydantic-ai-harness-comparison.md` §3.3 and §6.3; `ARCHITECTURE.md` §11 (line 490) and ADR-10 (line 548).

**Base**: main `721a802`.

## Context and verified findings

Every claim in the brief was checked by reading the code on main `721a802` and the installed packages (`temporalio` 1.31.0, `pydantic-ai-slim` 2.51.0). Nothing was run: the spec phase is read-only. Where the code differs from the brief, the spec follows the code.

| # | Brief claim | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | The shared proposer attempt bound is 3 and does not cover this failure | **True as far as code shows.** `AGENT_ACTIVITY_MAX_ATTEMPTS = 3` (`src/sdlc/agents/roles.py:39`, policy at `:42`). The bound is an activity retry policy; a payload rejected while the workflow schedules the activity never becomes an activity attempt. | The defect class is real. FR-001. |
| V2 | `_run_role` is the single model-egress point and already shows the wanted failure shape | **True for the shape, not for "single".** `src/sdlc/workflows/role_host.py:128`; the 004 label guard raises `ApplicationError(..., non_retryable=True)` before the call (`:158-164`). See V5 for the paths that do not pass through it. | The failure shape is settled precedent. FR-003. |
| V3 | The message history travels into the model activity as activity input | **True, and it is the whole history on every request.** Installed `durable_exec/temporal/_model.py:212-219` and `:258-265` pass `messages=` (the full list) as the activity argument for each model request. | The payload grows *during* one proposer call: each tool return and each output-validation retry is appended, and the next request carries all of it. A check made once before the call sees only the first request. Q2. |
| V4 | `_get_patch` returns the patch untruncated (`stages/review/step.py:69`), embedded in three prompts | **The function is as described; the patch is not unbounded.** `_get_patch` adds no cut, but the patch is produced by `get_task_diff`, which already cuts it to `max_chars = 60_000` (`src/sdlc/vcs/git.py:93, :115`). All four callers use the default (`stages/code/step.py:745`, `stages/analyze/step.py:81`, `workflows/feature.py:494`, `workflows/graph_nodes/postplan.py:71`). The deep-review transcript is cut to 512 KiB at load (`src/sdlc/artifacts/read.py:21, :39-41`). | The reviewer and adversary prompts cannot approach 2 MB through the patch. The "bounded patch in the reviewer prompt" half of the report's remedy already exists. Q1. |
| V5 | H2: every proposer call goes through `_run_role` | **False.** The 11 stage call sites and the handoff call do (`ctx.run_role`, wired at `workflows/feature.py:166` and `workflows/graph.py:68`; direct call at `feature.py:216`). Three paths do not: (a) `AssessmentWorkflow` calls `t_discover.run` and `t_risk.run` directly (`workflows/assessment.py:453, :675`), both durable agents whose history crosses as activity input; (b) the research stage runs its agents inside activities (`stages/research/stage.py:115, :248, :392`), so their history never crosses an activity boundary, but the activity *inputs* built by the workflow do; (c) the architect's research tool runs inside the architect's tool activity (`stages/research/toolset.py:53`), so its inner history is in-process and its result returns as activity output. | A guard placed only in `_run_role` misses (a) entirely. Q2. |
| V6 | H4: the review slice is the only practically reachable overflow | **False.** Given V4, the review slice is the best-bounded caller, not the most exposed. Prompts that embed inputs with no cap found in this pass: the idea and clarified requirements (user-supplied), the codebase map and recall grounding, the QA raw output (`_get_qa_raw_json`, `review/step.py:75`), the assessment discover context (`assessment.py:453`), and the architect's accumulated tool returns (V3). None was measured. | The systemic guard is the fix. Which inputs can really reach the cap is a plan research item (FR-009), not an assumption. |
| V7 | H1: workflow-task failures retry indefinitely under our worker config | **Not verified, and cannot be by reading.** The worker sets no workflow-task failure policy (`src/sdlc/worker.py:256-277`); the only registered workflow-failure types are the plugin's four (`durable_exec/temporal/__init__.py:193-198`), none of which is a payload error. The installed SDK exposes only warning thresholds in Python (`temporalio/service.py:212-222`: 512 KiB payload warning); the rejection itself is decided by the server (`docker-compose.yml:3` pins `temporalio/temporal:latest`, dev-server mode). Three outcomes are possible: the workflow task fails and retries without end (the page's claim), the server ends the run outright, or the request exceeds the transport limit and never completes. | All three outcomes skip the stage's failure path, so the feature is justified either way. The exact outcome decides the wording of US1 and the margin, so the plan MUST start with a measured reproduction (FR-008). |
| V8 | H3: the guard can measure a deterministic size proxy in workflow code without breaking replay | **Plausible; one trap.** Measuring serialized bytes is a pure function of workflow state. The trap: a captured history that recorded a successful call above the new limit but below the server cap would take a different path on replay. `src/sdlc/workflows/AGENTS.md:63-72` requires `workflow.patched` for any command-sequence change while `FeatureWorkflow` is registered. | FR-006. The limit's value interacts with replay, not only with the server cap. |
| V9 | No `PayloadCodec` or `DataConverter` override in `src/` | **True for the codec.** The client passes the stock `pydantic_data_converter` (`worker.py:258`, `cli.py:411`, `benchmarks/cli.py:209`), which the plugin re-wraps while preserving any codec (`durable_exec/temporal/__init__.py:75-95`). No codec is set. | A codec backstop would be new infrastructure on three client construction sites. Q1. |

**Additional findings (not in the brief).**

- **N1 — the patch cut is silent.** `get_task_diff` slices at 60,000 characters with no marker (`vcs/git.py:115`), so a reviewer can approve a diff whose tail it never saw and nothing records that. The benchmark judge's equivalent adds a marker (`benchmarks/oracle.py:107`). This is a review-quality defect, not a hang. It is reported here and left out of scope unless GATE 1 pulls it in (Q1, option B).
- **N2 — fail-open lenses will absorb the new failure.** The adversary and deep-review lenses catch every exception and continue (`review/step.py:243-249, :361-367`). A guard failure there becomes "lens did not run", recorded by the existing lens tombstone. The primary reviewer has no such catch and fails its stage. Q3.
- **N3 — a prompt near the cap is already unusable.** 2 MB of text is several times any current model's context window, so a payload that large would be refused by the provider even if it were delivered. The gap this feature closes is the *way* such a call fails, not whether it could have succeeded.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An oversized proposer payload fails its stage instead of hanging the run (Priority: P1)

An operator starts a run whose input makes one proposer call's payload larger than the workflow engine accepts. The stage that made the call fails promptly with a message naming the role, the measured size and the limit. The run then follows that stage's normal failure path. It does not sit in a state that never resolves.

**Why this priority**: This is the defect. A hung run holds its worktree, shows no error, and is found only by someone noticing it is still open.

**Independent Test**: Drive one proposer role with a synthetic prompt above the limit, using a fake agent; assert the call fails non-retryably before any model request is made, and that the stage reaches its existing failure outcome.

**Acceptance Scenarios**:

1. **Given** a proposer call whose payload is above the limit, **When** the stage runs, **Then** the call fails without retrying, no model request is made, and the failure names the role, the measured size and the limit.
2. **Given** a proposer call whose payload is under the limit, **When** the stage runs, **Then** it behaves exactly as today.
3. **Given** an oversized call in a graph run, **When** the node fails, **Then** the failure routes through the node's fail port like any other proposer failure.
4. **Given** an oversized call at a call site that is fail-open today, **When** it fails, **Then** that site's existing fail-open path runs and the task continues, as for any other failure there (what each site records is in A2).

---

### User Story 2 - A payload that grows during a call is caught too (Priority: P2)

A proposer that uses tools, or whose output is rejected and retried, sends a longer history on each request. If that history crosses the limit on the third request, the call fails the same way as in US1, not on a path the first check never saw.

**Why this priority**: Without it the guard covers only the first request of a call and leaves the original hang reachable on the others (V3).

**Independent Test**: Run a fake tool-using proposer whose tool returns grow the history past the limit on a later request; assert the same non-retryable failure and that the over-limit request was never sent.

**Acceptance Scenarios**:

1. **Given** a proposer whose history exceeds the limit on a later request, **When** that request is about to be made, **Then** the call fails as in US1 and the request is not sent.
2. **Given** the assessment workflow's two proposers, **When** either is given an oversized prompt, **Then** it fails the same way and the phase reaches its existing fail-closed result.

---

### User Story 3 - The team knows which inputs can actually reach the limit (Priority: P3)

Before deciding whether any prompt input needs its own cap, the team has a list of every unbounded input that feeds a proposer payload, with its realistic maximum size.

**Why this priority**: The brief assumed the review patch was the reachable case; it is already capped (V4). The real exposure is unknown, and bounding inputs blindly is wasted work.

**Independent Test**: The inventory exists as a research artifact, names every proposer call site, and gives for each embedded input either its existing cap (with citation) or "uncapped" with an estimate.

**Acceptance Scenarios**:

1. **Given** the inventory, **When** read, **Then** every proposer call site is listed with each input it embeds and that input's cap or lack of one.
2. **Given** an input marked "uncapped", **When** read, **Then** it carries an estimate of whether it can realistically reach the limit and a recommendation (leave to the guard, or cap in a follow-up).

### Edge Cases

- **E1** A payload exactly at the limit is accepted; the limit is the largest accepted size.
- **E2** The measurement is of encoded bytes, not characters: a prompt of multi-byte text is larger than its character count.
- **E3** A memoized stage hit makes no proposer call and is never checked.
- **E4** A run in flight across the upgrade, and replay of captured histories: a history that recorded a successful call must replay unchanged (FR-006).
- **E5** Parallel proposer calls (clarify fan-out, wave-mode tasks): one oversized call fails alone; its siblings are unaffected. The combined size of siblings is not checked (A5).
- **E6** A proposer override (004 forwarding): the limit is the same for every model, because it is the workflow engine's limit, not the model's.
- **E7** The guard's own failure message must not embed the oversized payload.
- **E8** The measured size and the true encoded size differ slightly (envelope, settings, tool definitions): the margin under the engine's cap must absorb the difference.
- **E9** A durable agent run inside an activity (the architect's research tool) is not checked and behaves as today (A1).

## Requirements *(mandatory)*

### Functional Requirements

**The guard**

- **FR-001**: A proposer model request whose payload exceeds the limit MUST fail before it is scheduled, without retrying. It MUST NOT be left to the workflow engine to reject.
- **FR-002**: The check MUST cover every model request that a durable proposer agent schedules from workflow code (the guard is attached to all 16 in `ALL_TEMPORAL_AGENTS`, which includes the assessment `discover` and `risk` agents; see A1), including requests after the first in one call (Q2). It MUST be inert when the agent runs inside an activity (E9). If the plan finds a request path the check cannot reach, it MUST name the path and stop for a ruling rather than ship a partial guard described as complete.
- **FR-003**: The failure MUST use the existing non-retryable failure shape (V2) and MUST name the agent, the measured size and the limit, in that order at the start of the message and within 300 characters (A7). It MUST NOT contain the payload (E7).
- **FR-004**: Each call site MUST reach the failure outcome it reaches today for a non-retryable proposer failure: fail-closed stages fail, fail-open call sites take their existing fail-open path (A2), graph nodes route to their fail port (Q3). This feature MUST NOT add a new run-level outcome.
- **FR-005**: The limit MUST be one value for all roles and models, set far enough under the workflow engine's payload cap to absorb the difference between the measured and the encoded size (E8). The plan fixes the value from the FR-008 measurement.
- **FR-006**: Runs whose payloads are under the limit MUST remain replay-compatible with captured histories; the existing replay and golden suites MUST stay green and MUST NOT be re-recorded to pass. The measurement MUST be deterministic in workflow code. The plan MUST state how a captured history containing a successful call above the new limit is handled.
- **FR-007**: Calls under the limit MUST be unchanged in behaviour, cost, records and scheduled commands.

**Evidence**

- **FR-008**: The plan's research MUST begin with a measured reproduction, in the dev container against the project's own server image, of what happens today when a proposer payload exceeds the engine's cap: which of the three outcomes in V7 occurs, at what size, and what the operator sees. US1's wording and the limit's value follow from it.
- **FR-009**: The plan's research MUST include the input inventory of US3. It MUST NOT cap any input; per-input caps are a separate decision.
- **FR-010**: Tests MUST use synthetic oversized payloads and fake agents. No test in this feature makes a real model call, and the fast tier's runtime MUST NOT grow materially.

**Boundaries**

- **FR-011**: Defect 6.2 (architect research sub-runs unpriced) is out of scope.
- **FR-012**: This feature MUST NOT add a payload codec or external payload storage (Q1), change any attempt budget or timeout, or change any prompt's content.
- **FR-013**: Repository constraints apply: 1000-line ceiling per file, no cross-stage calls, the user's uncommitted files are not touched (`agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, the 2026-09-22 retro, the two canvas HTML files).

### Key Entities

- **Proposer payload**: what one model request carries across the workflow-to-activity boundary: the full message history plus request settings.
- **Payload limit**: the largest payload size the guard accepts; one value, below the workflow engine's cap by a stated margin.
- **Oversize failure**: the non-retryable failure raised in place of scheduling an over-limit request.
- **Input inventory**: the list of inputs embedded in proposer prompts with each one's cap or lack of one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of oversized proposer requests end in a stage failure within one workflow task; zero leave a run open with no error.
- **SC-002**: An operator can tell from the failure alone which role overflowed and by how much, without opening the workflow history.
- **SC-003**: Runs with no oversized payload show no change in outcomes, spend or replay results; all existing replay and golden suites pass unmodified.
- **SC-004**: The reproduction (FR-008) records today's behaviour once, with the size at which it occurs, before any fix is written.
- **SC-005**: The input inventory covers every proposer call site and marks every embedded input capped or uncapped.

## Assumptions

- "Proposer" means a non-harness role's model call, as in 004. Coding harness sessions are out of scope: they are already claim-checked artifacts (ADR-16).
- The limit is a code constant, not an operator setting or a per-run config field (confirmed at GATE 1). An operator has no useful reason to raise it (N3), and a config field would have to cross the workflow boundary and be versioned.
- Activity *outputs* and tool *returns* that are too large fail on the activity side and are already bounded by the activity retry policy; they are not this defect. The plan confirms this in the FR-008 reproduction rather than assuming it.
- Research-stage activity inputs (V5 b) are listed in the inventory. They are fixed here only if the inventory shows one is reachable; otherwise they become a follow-up.
- All verification runs happen in the dev container.

## GATE 1 rulings

User rulings relayed by the orchestrator, 2026-10-03. No open questions remain.

- **Q1 = A, guard only.** FR-012 stands: no codec, no prompt content changes. N1 (the silent patch cut) stays out of scope; the orchestrator files it to the inbox.
- **Q2 = A, every model request of every durable proposer agent.** FR-002 and US2 stand.
- **Q3 = A, the call site's existing non-retryable semantics.** FR-004 stands. The N2 consequence (an oversized adversary or deep-review prompt is absorbed as "lens did not run") is accepted knowingly.
- **The limit is a code constant**, not config. Its value is fixed in the plan from the FR-008 measurement.
- **H1 stays unverified** until the FR-008 reproduction (V7).

## GATE 2 rulings

User rulings relayed by the orchestrator, 2026-10-03. Plan approved.

- **The limit is 1 MiB (1,048,576 bytes), a code constant.** The A3 consequence (prompts between 1 and 2 MiB are refused even for a large-window override model) is accepted.
- **Aggregate overflow (A5) is filed to the inbox**, not fixed here: `.workspace/tasks/2026-10-03-aggregate-payload-overflow-terminates-run.md`.
- **Silent absorption in deep review and handoff (A2) is not accepted silently.** It is filed to the inbox as a follow-up candidate: `.workspace/tasks/2026-10-03-deep-review-handoff-failures-leave-no-record.md`. FR-004 is unchanged for this feature.

## Post-GATE-1 consult amendments

From the advisor (`.workspace/tmp/advisor-007-1.md`) and skeptic (`.workspace/tmp/skeptic-007-1.md`) consults, each re-checked in code by the spec lead. They correct facts and wording. No GATE 1 ruling changes; A2 and A3 change what two rulings were described as accepting and are carried to GATE 2.

- **A1 (FR-002, V5) — the guard acts only on requests scheduled from workflow code.** The guard is attached to all 16 durable agents, but two never issue a workflow-scheduled model request today: the `research` agent runs only inside activities (`stages/research/stage.py:216-230`, `stages/research/toolset.py:53`), and `devops_planner` has no call site in `src/`. Inside an activity the history never crosses the boundary, so the guard MUST be inert there; firing in an activity would change the architect's research tool. FR-002 is read as "every model request a durable proposer agent schedules from workflow code". New edge case **E9**: an agent run inside an activity is not checked and behaves as today.
- **A2 (N2, US1 scenario 4, Q3) — only the adversary lens records that it did not run.** The adversary gets a lens tombstone (`stages/code/step.py:854`). Deep review is not in `lens_outcomes` (`code/step.py:884-885, :955-956`), and the handoff extractor is a fourth fail-open site the spec missed (`code/step.py:464-470`, falls back to a mechanical handoff). For those two, an oversize failure leaves a WARNING in the worker log and nothing in the run's records. US1 scenario 4 is read as: "the call site's existing fail-open path runs; the adversary records a tombstone, deep review and handoff log a warning". Fixing the missing records is out of scope (FR-012, and `code/step.py` is at 991 of 1000 lines).
- **A3 (N3) — a 2 MB prompt is not beyond every model.** 2 MB of text is about 500,000 tokens. That exceeds a 200,000-token window but fits a 1,000,000-token one, and a 004 override can name such a model. N3 is read as: "beyond the registry's models today, not beyond every model an override can name". Consequence: the limit can refuse a prompt that a large-window model would have served.
- **A4 (V4, V6) — the diff has uncapped fields.** `get_task_diff` cuts only `patch`; `stat`, `files` and `renames` are returned whole (`vcs/git.py:102-115`). The QA and analyst prompts embed `stat` (`stages/qa/step.py:174`, `stages/analyze/step.py:133, :144`). It joins the inventory (FR-009) as uncapped.
- **A5 (V7, E5) — sibling requests share one workflow task.** Parallel proposer calls (clarify probes, wave-mode tasks) are scheduled in the same workflow task, and one task completion carries all their inputs. Several under-limit payloads can together exceed the transport's message limit. A per-request guard cannot see the sum. E5 holds per request only; the aggregate case is measured in the FR-008 reproduction and named as a residual, not fixed here.
- **A6 (V8, FR-006) — replay is protected by a marker on the failing branch only.** A marker recorded on every run would change every new run's command sequence and the golden projections (FR-007). A marker taken only when the guard is about to fail leaves under-limit runs unchanged and makes a captured over-limit success replay as recorded. The plan states the mechanism.
- **A7 (FR-003) — message shape.** The failure message leads with the agent name, the measured size and the limit, and stays under 300 characters, because the assessment risk path truncates it there (`workflows/assessment.py:680`).
- **A8 (V3) — the payload is more than the message list.** The activity input also carries the request parameters (tool and output schemas, and a second copy of the instructions) and the model settings. The measurement covers all three (plan D2).

## Open Questions — GATE 1 (as asked)

Kept for the record. Each was written into the spec at its recommended answer, and each was ruled at that answer.

- **Q1 — What ships in V1?** Recommended **A: guard only.** The report's second half (a bounded patch in the reviewer prompt) already exists (V4), and a payload codec needs storage that outlives every replayable history, for a case the guard already turns into a clean failure. *B: guard plus input fixes* adds a visible truncation marker to the patch cut (N1) and caps whatever the inventory finds; this flips FR-009 and FR-012's "no prompt content change". *C: guard plus codec* removes the limit instead of enforcing it; it flips FR-012 and makes this a medium-size feature touching three client construction sites.
- **Q2 — How much must the guard cover?** Recommended **A: every model request of every durable proposer agent** (FR-002, US2), because the history is re-sent and grows on each request (V3) and two proposers bypass `_run_role` (V5 a). *B: the first request only, at `_run_role`* is the report's literal remedy and the smallest change, but it leaves the hang reachable on later requests and in assessment; it drops US2 and narrows FR-002.
- **Q3 — What does an oversize failure do to the run?** Recommended **A: whatever that call site does today on a non-retryable proposer failure** (FR-004), the 004 FR-011 precedent. Consequence, to accept knowingly: an oversized adversary or deep-review prompt is absorbed as "lens did not run" (N2). *B: always fail the run*, on the reasoning that an oversized input is an operator-visible input problem and should never be absorbed; this adds a new run-level outcome and overrides the lenses' fail-open rule.

Not a question, but stated to the gate: **H1 is unverified (V7).** If the reproduction shows the server already ends the run rather than hanging it, the feature still delivers a named stage failure in place of a terminated run, but "hang" in US1 is reworded and the priority may be reconsidered.
