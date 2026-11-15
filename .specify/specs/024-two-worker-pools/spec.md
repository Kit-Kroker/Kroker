# Feature Specification: Round 024 — two worker pools (fleet scale)

**Feature Branch**: none (spec-only phase; this round writes under `.specify/specs/024-two-worker-pools/` only)

**Created**: 2026-11-15

**Status**: Draft — awaiting GATE 1

**Input**: Orchestrator TASK BRIEF, 2026-11-15: "round 024: fleet scale, the two-worker-pool change (roadmap §'two worker pools'; NFR-2; ADR-9; AP-2.5). Spec the round." The consumer is R025, the fleet runs for SC-1..3. Pools must make at least 5 concurrent benchmark runs practical on one host, and must not break single-pool deployments. Chain replay stays byte-identical. The change is config-gated. GraphWorkflow, the stage contracts and the trust layer stay untouched. One L round. Cross-stage call ban and the 1000-line ceiling apply.

---

## Part A — Scope and round boundary

### A.1 What 024 is

Today one Temporal task queue (`"ai-sdlc"`) is served by one worker process. That process hosts every workflow and every activity. A coding-harness turn that runs for 30 minutes and spawns a CLI subprocess shares a process, an activity-slot budget and a host with a proposer's 10-second model call and a board write. Nothing bounds how many harness CLIs run at once.

024 delivers **ADR-9 as originally stated: two pools split by capability.**

- **Core pool** (the existing `"ai-sdlc"` queue). It hosts every workflow and every activity that is *not* in the harness class: proposer and agent model calls, memory, board, notify, pricing, recording and reporting. It scales on LLM throughput.
- **Harness pool** (a new, second queue). It hosts the **harness class**: every activity that (a) spawns a coding-harness CLI, (b) executes the target repository's own code, or (c) creates, mutates or removes a run's worktree or branches. It scales on coding concurrency, and its activity concurrency is capped.

Routing is **off by default**. With routing off, the system behaves exactly as today: one queue, one worker, and the same workflow command sequence. With routing on, the run-start path resolves the harness queue name once. It travels in the run's input, and every harness-class activity is scheduled to that queue. Child workflows inherit it.

### A.2 Hypotheses from the brief, checked against the repo

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | One task queue `"ai-sdlc"` serves everything | **Confirmed.** One constant, one `Worker(...)`, ten workflows and every activity registered together. No `execute_activity` call passes a `task_queue`. The only `task_queue=` uses are child-workflow starts, and those all propagate `workflow.info().task_queue` | `src/sdlc/task_queue.py:10`; `src/sdlc/worker.py:292-307`; grep `task_queue=` in `src/sdlc/workflows/`, `stages/deploy/step.py:142` |
| H2 | "Dashboards" run on the worker | **Disproven.** The dashboard API and MCP bridge are clients. They import `task_queue.py` alone so they avoid the worker import (022 R5). They are not a pool concern | `src/sdlc/task_queue.py:1-8`; `src/sdlc/operator/runtime.py:27` |
| H3 | `benchmarks/drift.py` already names the split | **Partly.** `CODING_ACTIVITIES = {run_coding_task, run_crew_turn}` names the two *harness-turn* activities, which is the core of the harness class. It is not the whole class: worktree activities (`create_worktree`, `merge_into_integration`, `build_verification_branch`, `prepare_crew`, `checkpoint_round`, …) and repository-executing activities (`grade_oracle`, `triage_build_probe`, …) touch the same host resources. The plan enumerates the class against rule A.1(a–c) | `src/sdlc/benchmarks/drift.py:80` |
| H4 | ADR-9 defines "two pools" | **Confirmed, then amended.** ADR-9 says "Proposer vs. harness queues: independent scaling, credential isolation, cheap fleet economics". Its 2026-10-11 amendment (plan, not built) widens the target to **five pools routed per role from `RoleSpec`** (ARCHITECTURE §9 table). AP-2.5 is written against the amended form ("routed from `RoleSpec`"). **`RoleSpec` does not exist yet:** AP-2.1 is open. `RoleConfig.kind ∈ {proposer, harness, research}` is the existing capability seam | `docs/adr.md:91-95`; `ARCHITECTURE.md` §9; `docs/roadmap/agent-architecture-plan.md:41`; `src/sdlc/core/models.py:185-189` |
| H5 | Crew session resume is not worker-pinned | **Confirmed as a recorded boundary.** On one host, with harness processes sharing one session store, a retry on another process can still resume. Scaled harness *containers* that each have their own `HOME` cannot. Worker-specific queues are AP-2.6, a separate item (Q2) | `docs/roadmap/crew.md:69-71`; `docker-compose.yml:38-79` |
| H6 | Replay stays byte-identical | **Holds by construction with routing off. Expected to hold with routing on, with one item to verify.** The golden command projection records the activity *type* only, not the queue (`tests/replay/projection.py:29`). With routing off, no `task_queue` argument is added, so the commands are unchanged. Whether the SDK's replay determinism check ignores a changed activity queue is a **plan research item**. Recorded histories carry `taskQueue` fields | `tests/replay/projection.py:24-40`; `tests/replay/AGENTS.md` |
| H7 | 023a used FR-1500/E-90 as accepted proposals | **Disproven.** FR-1500 and E-90 belong to the *parked swarm-mode* skeleton. The numbering proposal is in Part C | `.specify/specs/parked-swarm-mode-skeleton/spec.md` |
| H8 | The "P5 dev-server contention" note bears on pools | **Disproven.** That note (ROADMAP P5, the `TidyUpWorkflow` e2e) is about a Windows host's Temporal *dev-server* under multi-workflow fan-out. It is test infrastructure, and worker pools do not change it | `ROADMAP.md:268` |

**Facts found that bear on fleet runs:**

- **F1 — queue wait does not consume activity timeouts.** Harness turns set `start_to_close_timeout` and `heartbeat_timeout` only (`stages/code/step.py:93-104`; `workflows/crew.py:98-105`). An activity waiting for a harness slot therefore does not time out. **But** the crew child workflow's `execution_timeout = wall_clock_s + 600` (`stages/code/step.py:305`), and its round wall-clock (`crew/layouts/code.yaml: wall_clock_s: 5400`), **do** include queue wait (Q3).
- **F2 — benchmark run ids collide at one-second granularity.** `bench-{case_id}-{int(time.time())}` (`benchmarks/cli.py:338`). Two same-case starts in the same second get the same workflow id, so a fleet start of the same case fails.
- **F3 — the cells inside one benchmark run are serial** (`benchmarks/workflow.py:340`). "≥5 concurrent benchmark runs" therefore means 5 `BenchmarkWorkflow`s in flight at once, each with one live cell.

### A.3 Design boundary

**Inside 024:** two task queues, the harness-class rule and its enumeration, the run-level routing switch, worker pool selection at boot, a harness concurrency cap, fail-fast start when routing is on and no harness worker is polling, a doctor check, compose and operator documentation for a two-process single host, fleet-safe benchmark run ids (F2), and the fleet-practicality proof.

**Deliberately not 024:** five pools and per-role routing from `RoleSpec` (needs AP-2.1), worker-specific queues and worktree affinity (AP-2.6), shared artifact storage and payload offload (AP-2.7), multi-host deployment, credential isolation enforcement between pools (E-20/E-21), and the R025 fleet runs themselves.

### A.4 Round size and the split boundary

Sizing rule: one L per crew run, and an XL decomposes first.

**Recommendation: one L round, `024`.** The surface is a boot-mode switch in `worker.py`, one routing field threaded through run input to the harness-class call sites, a cap, a start-time poller check, a doctor check, compose wiring, the benchmark id fix, and one temporal-tier load test on fake harnesses.

**If sizing fails at plan time, the cut is drawn at routing.** The split is:

- **024-i (pools exist):** worker pool modes, the cap, compose and docs, the doctor check, and the F2 id fix. Routing stays hard-off, so the deliverable is "the harness worker can boot and the system is unchanged".
- **024-ii (routing on):** the run-level switch, the call-site routing, the fail-fast start, and the fleet proof.

The cut is drawn there because routing is the only half that changes what a workflow schedules.

---

## Part B — Round 024: two worker pools

### User Scenarios & Testing

#### User Story 1 — Single-pool deployments are unchanged (Priority: P1)

An operator who changes no configuration upgrades to 024. They start one worker as before, and every run, benchmark, maintenance cycle and replay behaves exactly as it did.

**Why this priority**: backward compatibility is the precondition for shipping the round at all. Every existing deployment, test and replay fixture is a single-pool deployment.

**Independent Test**: run the full replay corpus and the fast and temporal tiers on 024 with no new configuration, and compare against the recorded baseline.

**Acceptance Scenarios**:

1. **Given** no pool or routing configuration, **When** the worker starts, **Then** it polls only `"ai-sdlc"` and registers the same workflows and activities as before 024.
2. **Given** the replay corpus, **When** it replays on 024, **Then** every history replays without a determinism error, and every golden projection is byte-identical.
3. **Given** a run started with routing off, **When** its history is inspected, **Then** no scheduled activity names a queue other than the workflow's own.

---

#### User Story 2 — An operator runs a two-pool single host (Priority: P1)

An operator starts one core worker and one harness worker on the same host, with a harness cap of N, and turns routing on. Proposer, memory and board work runs on the core worker. Every harness turn, repository execution and worktree mutation runs on the harness worker. No more than N harness-class activities run at once.

**Why this priority**: this is the capability itself, and R025 consumes it.

**Independent Test**: a temporal-tier test with the fake harness. Start both pools, run one pipeline with routing on, and assert from history which worker identity ran each activity.

**Acceptance Scenarios**:

1. **Given** a core worker and a harness worker with routing on, **When** a run reaches the code stage, **Then** every harness-class activity is completed by the harness worker, and every other activity by the core worker.
2. **Given** a harness cap of 2 and 4 runs at the code stage, **When** their harness turns are scheduled, **Then** at most 2 run at any instant, the rest wait, and none fails for waiting.
3. **Given** a crew task with routing on, **When** the crew child workflow schedules turns, **Then** the turns go to the harness queue: the child inherits the run's routing.
4. **Given** routing on and **no** worker polling the harness queue, **When** an operator starts a run, benchmark or maintenance cycle, **Then** the start is refused before any workflow exists, naming the missing queue. The run does not hang.
5. **Given** a core-only worker, **When** it boots, **Then** it does not register harness-class activities. **Given** a harness-only worker, **When** it boots, **Then** it registers no workflows and only harness-class activities.

---

#### User Story 3 — Five concurrent benchmark runs are practical on one host (Priority: P1)

R025's operator starts at least 5 benchmark runs at once on one host, including several of the same case. All of them start and progress. Harness load stays bounded by the cap, and proposer work for runs not in a harness turn keeps flowing.

**Why this priority**: this is the evidence that R025 is unblocked. Without it, the round has delivered a mechanism and no proof of the outcome.

**Independent Test**: a temporal-tier load test on the token-free fake harness and model. Start 5 concurrent `BenchmarkWorkflow`s, 2 of them on the same case, under a two-pool setup with cap 2.

**Acceptance Scenarios**:

1. **Given** 5 benchmark starts issued within the same second, 2 of them on the same case, **When** they are started, **Then** all 5 get distinct workflow ids and start.
2. **Given** the 5 runs in flight with harness cap 2, **When** they run to completion on fakes, **Then** all 5 complete, peak concurrent harness-class activities never exceeds 2, and every benchmark record has the same shape as a solo run of that case.
3. **Given** the harness pool saturated, **When** a run in a proposer stage schedules a model call, **Then** it is picked up by the core worker without waiting on a harness slot. Its schedule-to-start latency stays within the bound in SC-004.

---

#### User Story 4 — Operators can see and check pool health (Priority: P2)

An operator runs the doctor and sees whether each pool the configuration expects is being polled. A run that is waiting for harness capacity is distinguishable from a run that is stuck.

**Why this priority**: diagnosability. Two pools add a new failure mode — a missing poller — and a new normal state: waiting for capacity.

**Independent Test**: run the doctor with routing on and the harness worker down, then up.

**Acceptance Scenarios**:

1. **Given** routing on and no harness poller, **When** the doctor runs, **Then** the pool check fails and names the queue. **Given** a poller, **Then** the check passes.
2. **Given** routing off, **When** the doctor runs, **Then** the pool check reports "single pool" and passes.
3. **Given** an activity waiting in the harness queue, **When** the operator inspects the run, **Then** the pending activity is visible as scheduled but not started. This needs no new surface: it is what Temporal already shows.

---

### Edge Cases

- **Routing on, harness worker dies mid-turn.** The turn's heartbeat times out and the existing retry policy reschedules it to the harness queue. A replacement harness worker on the same host picks it up. Crew session resume works only if the replacement can reach the same session store (Q2).
- **Routing flips between run start and completion.** It cannot change a running run. Routing is resolved once at start and carried in input. A changed environment affects only new runs.
- **A long-running workflow started before 024, then replayed or continued on 024.** It carries no routing field, so it routes as "off", which matches its history.
- **Cap lower than the number of concurrent crew children.** Crew children wait in the queue. Their wall-clock budget and `execution_timeout` keep running (F1). With 5 runs, cap 2 and a 5400 s crew wall-clock, the third crew child may exhaust its budget waiting (Q3).
- **Cap set to 0 or a negative number.** Boot is refused.
- **Harness worker started but core worker not running.** Nothing starts, because workflows live on core. The run-start check (US2-AS4) targets the harness queue only. A core outage presents as today's "no worker".
- **Two harness workers on one host.** Allowed. The cap is per process, so the effective host limit is the sum. Docs state this.
- **Containerised harness replicas with separate filesystems.** Worktrees live on a shared named volume (`worker-worktrees`), and compose must mount it on both pools. Session stores live in `HOME`, which is not shared (Q2).
- **Maintenance probe and deploy children.** `probe_repair_child` and deploy children inherit routing like any child. The plan classifies each activity against rule A.1.
- **`TemporalDurability` agent activities.** These are always core. A proposer role with read-only repository tools reads the tree on the shared host filesystem. This is a single-host assumption.

### Requirements

#### Functional Requirements

- **P-FR-001 (Two queues)**: The system MUST define a second task queue for the harness pool beside `"ai-sdlc"`. Its name MUST come from configuration, with a documented default. *(NFR-2; ADR-9)*
- **P-FR-002 (Harness class rule)**: Every activity MUST be classified as core or harness by rule A.1(a–c). The classification MUST live in one place and be checked by a test that fails when a newly registered activity is unclassified. `benchmarks/drift.py`'s `CODING_ACTIVITIES` MUST be a subset of the harness class. *(ADR-9; AP-2.5)*
- **P-FR-003 (Worker pool mode)**: The worker MUST accept a pool mode: `all` (default — today's behaviour exactly), `core`, or `harness`. `core` registers all workflows and the core activities on `"ai-sdlc"`. `harness` registers no workflows and only the harness-class activities on the harness queue. Each mode runs the boot checks relevant to it, so a harness-mode worker still validates crew CLIs and harness versions. *(NFR-2)*
- **P-FR-004 (Harness concurrency cap)**: A harness-mode worker MUST bound concurrently executing activities to a configured cap. A cap below 1 MUST refuse boot. In `all` mode the cap MUST default to today's behaviour unless set. *(NFR-2; fleet economics)*
- **P-FR-005 (Run-level routing, off by default)**: Routing MUST be a run-level setting, resolved once at start and carried in workflow input. When it is absent or off, no harness-class activity call passes a queue, so the command sequence is identical to pre-024. When it is on, every harness-class activity is scheduled to the harness queue. *(Backward compatibility; replay invariance)*
- **P-FR-006 (Inheritance)**: Child workflows MUST inherit the parent's routing. This covers pipeline children of benchmark, tidy-up, maintenance and assessment runs, and crew and deploy children. Children stay on the parent's workflow queue, as today.
- **P-FR-007 (Fail-fast start)**: When routing is on, every start path MUST refuse to start the workflow, naming the queue, if no worker is polling the harness queue. The start paths are run, benchmark, maintenance, schedules and operator runtime. *(US2-AS4)*
- **P-FR-008 (Doctor check)**: The doctor MUST report the pool state: "single pool", or "routing on: harness queue polled" (pass), or "not polled" (fail).
- **P-FR-009 (Fleet-safe benchmark ids)**: Concurrent benchmark starts, including same-case starts in the same second, MUST receive distinct workflow ids. The id format MUST stay recognisable to existing record and report readers. *(F2; R025 enabler)*
- **P-FR-010 (Deployment wiring)**: The compose file MUST be able to run the two pools as two services on one host. Both MUST mount the shared worktree, repository and runs volumes. The single-service default MUST remain what `docker compose up` starts unless the operator opts in.
- **P-FR-011 (Replay invariance)**: Existing replay histories and golden projections MUST stay byte-identical, and no fixture may be re-recorded. Routing-on paths get their own replay coverage: one captured two-pool history whose command projection equals the single-pool projection of the same scenario. *(`tests/replay/AGENTS.md`; chain replay)*
- **P-FR-012 (Untouched surfaces)**: `GraphWorkflow`'s node and handler logic, every stage contract (`<stage>.md`), the trust layer (containment, the `pre_tool` hook, the env allowlist, gates) and the ADR-6 checks MUST NOT change behaviour. Routing is threaded through input and the activity-call options only. No stage calls another stage. *(Constraints)*
- **P-FR-013 (Docs)**: ARCHITECTURE §9's status note, ADR-9's status line, ROADMAP NFR-2 and AP-2.5, and the crew known-boundary MUST be updated in the landing diff to match what was built. That includes AP-2.5's per-role half being explicitly still open. *(Artifact boundary rule)*

#### Key Entities

- **Pool mode**: the worker's boot-time role: `all`, `core` or `harness`.
- **Harness class**: the set of activity names that rule A.1(a–c) selects. It has one authoritative definition.
- **Routing setting**: a run-scoped value, either off or the harness queue name. It is resolved at start, carried in input and inherited by children.
- **Harness cap**: the per-harness-worker limit on concurrent activities.

### Success Criteria

#### Measurable Outcomes

- **SC-001 (Single pool unchanged)**: With no new configuration, 100% of existing replay histories replay cleanly and 100% of golden projections are byte-identical. The fast tier holds at the recorded known-baseline failure set with no new failures. The temporal tier shows no new failures.
- **SC-002 (Placement)**: In the two-pool test, 100% of harness-class activities are completed by the harness worker, and 0 by the core worker. The reverse also holds for core activities.
- **SC-003 (Fleet practical)**: 5 concurrent benchmark runs, at least 2 of the same case and all started within one second, run on one host under two pools with harness cap 2 on fakes. All 5 start, all 5 complete, peak concurrent harness activities is at most 2, and every record matches its solo-run shape.
- **SC-004 (No starvation)**: During SC-003, with the harness pool saturated, the core pool's model-call activities show schedule-to-start latency under 5 seconds at p95. This is measured from history timestamps.
- **SC-005 (Fail closed, not hung)**: With routing on and no harness poller, 100% of start paths refuse within 10 seconds, naming the queue. No workflow is created.
- **SC-006 (Routing-on replay)**: The captured two-pool history replays cleanly, and its command projection equals the single-pool projection of the same scenario.
- **SC-007 (Ceiling)**: No file crosses 1000 lines, and baselined files do not grow.

### Assumptions

- **Single host, shared filesystem.** Both pools see the same worktree, repository, runs and session-store paths. Multi-host needs AP-2.6 and AP-2.7, and is out of scope.
- The token-free fake harness and model (`src/sdlc/demo/fakes.py`) are sufficient evidence for SC-003 and SC-004. Paid evidence is R025's.
- The pool mode, harness queue name, cap and routing switch are environment or CLI configuration, consistent with how `TEMPORAL_HOST` is read today. The plan picks the exact names.
- The SDK's replay determinism check ignores an activity's queue (H6). If plan research disproves this, routing-on needs a patch marker, and SC-006 is restated.
- Credential isolation between pools (ADR-9's second benefit) is a *deployment* property that 024 enables, by giving the pools separate processes and env files, but does not enforce. Enforcement is E-20/E-21.

### Out of scope (024)

- **R025's fleet runs themselves**, and any SC-1..3 measurement. That includes SC-2's operator-time instrument.
- Five pools and per-role routing from `RoleSpec` (AP-2.5's per-role half). This needs AP-2.1.
- Worker-specific task queues, worktree affinity and recreate-on-loss (AP-2.6), unless Q2 folds a minimal form in.
- S3 artifact storage and Temporal payload offload (AP-2.7, FR-702).
- Multi-host fleets, autoscaling and Kubernetes.
- Containment-tier changes, per-pool credential scoping (E-20/E-21) and any trust-layer change.
- Changing benchmark cells from serial to parallel inside one run (F3).
- Reviving the `_run_drift` harvester (`benchmarks/cli.py:348`).

---

## Part C — Numbering proposal

The PRD row already exists: **NFR-2** ("Scale / two pools", tracked as AP-2.5). No new FR series is needed. **Proposal:**

- Track the round as **E-91** ("two worker pools by capability"). E-90 is held by the parked swarm skeleton, and E-89 is the last landed epic.
- On landing, mark **NFR-2 delivered (two-pool form)**, and flip ADR-9's status line from "single queue" to "two queues built; five-pool amendment open".
- Split **AP-2.5** into **AP-2.5a**, two capability queues (this round, `[x]` on landing), and **AP-2.5b**, per-role routing from `RoleSpec` (open, depends on AP-2.1).
- Requirement ids stay round-local (`P-FR-*`, `SC-0nn`), as 023b's `B-FR-*` did.

---

## Open questions for GATE 1 (owner)

**Q1 — Is ADR-9's two-pool form the right deliverable, given the five-pool amendment?**
Recommendation: **yes (A).**
- **(A)** Two capability pools now. The per-role, five-pool form waits for `RoleSpec` (AP-2.1). AP-2.5 is split as in Part C. R025 needs harness isolation, not five pools.
- **(B)** Build the five-pool queue names now, routed by `RoleConfig.kind` as a stand-in for `RoleSpec`. This adds three queues no current deployment needs, and risks building on a seam AP-2.1 will replace.
- **(C)** Do AP-2.1 first. This delays R025 by at least one round.

**Q2 — Does crew session-resume pinning (AP-2.6's worker-specific queue) fold into 024?**
Recommendation: **(A).**
- **(A)** No. 024 states "one harness worker per session store". Compose mounts a shared session-store volume on every harness replica. The crew boundary note is updated to say exactly when resume is safe. Worker-specific queues stay AP-2.6.
- **(B)** Fold in a minimal worker-specific queue for crew turns only, without recreate-on-loss. Likely pushes 024 to XL, which means splitting.
- **(C)** No, and forbid more than one harness replica until AP-2.6.

**Q3 — Should queue wait for a harness slot count against a crew task's wall-clock budget?**
Today it does (F1). With 5 runs and cap 2, a waiting crew child can exhaust a 5400 s budget before its first turn.
Recommendation: **(A).**
- **(A)** Keep the current semantics, which change nothing in the crew contract. Document the sizing rule: cap ≥ concurrent crew runs, or a wall-clock with headroom. R025 sizes its fleet accordingly.
- **(B)** Start the crew wall-clock at the first turn's start. This changes `CrewTaskWorkflow` semantics and needs a patch marker and new replay coverage. That is a crew-contract change inside a scale round.
- **(C)** Cap concurrent *crew children* at the benchmark or fleet level instead. This is new fleet-scheduler logic and belongs to R025.

**Q4 — Numbering (Part C).** Accept E-91, NFR-2 as the PRD row, and the AP-2.5a/b split? *(Proposal, not decided.)*

## GATE 1 record (owner, 2026-11-15)

All four recommendations were accepted, as relayed by the orchestrator.

1. **Q1 — Deliverable:** two capability pools now (core / harness). The five-pool, per-role form waits for AP-2.1's `RoleSpec`. AP-2.5 splits into **AP-2.5a** (this round) and **AP-2.5b** (open, depends on AP-2.1).
2. **Q2 — Session-resume pinning:** not this round. Harness replicas mount a shared session-store volume (P-FR-010), and the crew known-boundary note is updated to say exactly when resume is safe (P-FR-013). Worker-specific task queues stay AP-2.6.
3. **Q3 — Crew wall-clock:** semantics unchanged. Queue wait keeps counting against the crew budget. The sizing rule (harness cap ≥ concurrent crew runs, or a wall-clock with headroom) is documented for operators and R025 (P-FR-013).
4. **Q4 — Numbering:** accepted. The round is **E-91**, **NFR-2** is the PRD row, and AP-2.5 splits a/b (Part C).

**Pre-authorized:** if plan-time sizing fails one L round, the spec lead splits 024-i / 024-ii per Part A.4 without another owner round-trip, and records the split decision in plan.md.

**Standing consequence:** the open-question section is closed by this record. No `[NEEDS CLARIFICATION]` markers were used.

## Consult record

`consults/advisor.md` (D1–D7) and `consults/skeptic.md` (L1–L6), 2026-11-15. Each finding is dispositioned in plan.md §Skeptic/advisor disposition. The spec lead verified the load-bearing claims:
- `Field(exclude_if=)` keeps routing-off payloads byte-identical through `pydantic_data_converter`;
- the SDK's `input.task_queue or info.task_queue` at `_workflow_instance.py:3311`;
- `check_test_drift` is unregistered;
- `paths_exist` reads the canonical `repo_path`.

**Folded:**
- the field-per-root-input routing with `exclude_if` (R1);
- amended rule A.1(c) and the 28-name class (R2);
- `on_harness` plus the AST and recorder proofs (R3, R4);
- the dual `Worker` in `all` mode, and `core` requiring a queue (R5);
- the activity-type poller check with freshness (R6);
- no `patched()` marker (R7);
- the janitor lock and placement, and the axis prune (R10);
- the barrier-fake load proof (R11);
- the R025 operating notes (R12);
- the pre-authorized split (plan §Split decision).

**Not adopted:**
- the memo/interceptor routing alternative (`continue_as_new` memo loss; not greppable), kept as the named fallback;
- the `MaintenanceKickWorkflow` pre-flight activity (queue-wait is the defined semantics), recorded as a residual;
- skeptic L2's "forbid replicas > 1". It was rebutted in part, and the Q2 ruling stands as written (R9).

## Items the owner should see at GATE 2

1. **The split was taken (pre-authorized).** 024-i is T001–T020: pools boot, routing hard-off, ops only. 024-ii is T021–T042: routing on and the fleet proof. **024-i alone does not unblock R025.**
2. **Latent defect found and fixed in 024-i (T005).** `check_test_drift` is called by the code stage on containment-on repair attempts (`stages/code/step.py:711`), but no worker registers it. Today such an attempt schedules an activity nothing serves.
3. **The Q2 ruling was kept despite the skeptic.** The skeptic said a shared session store across harness replicas "breaks". The plan rebuts this in part: concurrent CLIs on one store are today's status quo, and same-host containers share kernel locks. It adopts the mount-subpath care. Resume is documented as safe on **one host only**.
4. **Rollback asymmetry (reviewer plan-1 gap 1).** A pre-024 worker given a routing-on **maintenance** input refuses it loudly, because those models are `extra="forbid"`. The other seven input families silently route off. The remedy is documented (T019), and routing-off rollback is safe everywhere.
5. **Residuals, recorded and not fixed:**
   - a schedule-fired run with the harness worker down queues its harness work, with no pre-flight;
   - the R12 fleet-host limits (dev-server SQLite, Hindsight, provider RPM, fixed ports, board WAL) are R025's.

---

## GATE 2 record (owner, 2026-11-15)

Accepted under the owner's standing delegation, with the recommended answers taken independently. The rulings were relayed by the orchestrator after the reviewer approved plan.md (pass 2: one blocking gap fixed in pass 1, gap 7 folded) and tasks.md (pass 1: five non-blocking gaps folded). The exec tab consumes plan.md and tasks.md **as approved**, with no edits from this record.

1. **The pre-authorized split stands.** 024-i is T001–T020: pools boot, routing hard-off, ops only. 024-ii is T021–T042: routing on, fail-fast and the fleet proof. They are two crew rounds, run in order, and 024-ii needs 024-i merged. 024-i's close-out states that it does not unblock R025.
2. **The latent-defect fix is accepted** (T005, research R2). `check_test_drift` is registered on the worker, in the harness class, and the classification test pins it.
3. **The Q2 ruling stands, with the skeptic L2 rebuttal accepted** (research R9). Harness replicas share one session-store volume, mounted at the store subpaths so the `auth.json` bind is not shadowed. Resume is documented as safe on one host only. Worker-specific task queues stay AP-2.6.
4. **The rollback-asymmetry documentation is accepted** (research R1; T019, T042). The maintenance family refuses routing-on inputs on a pre-024 worker. The other seven families route off. The remedy is documented.
5. **The residuals are accepted as recorded, not fixed.** They go into `verification.md` (T042):
   - there is no schedule-fire pre-flight, so a schedule-fired run queues its harness work when the harness worker is down;
   - the R12 fleet-host limits are R025's;
   - a dead harness worker leaves activities queued (the F1 semantics).
