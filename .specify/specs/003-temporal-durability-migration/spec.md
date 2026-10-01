# Feature Specification: Migrate Durable Agents to the TemporalDurability Capability

**Feature Branch**: `003-temporal-durability-migration` (spec directory only; no branch was created)

**Created**: 2026-09-30

**Status**: Draft, GATE 1 rulings folded in; awaiting user approval

**Input**: Migrate every durable agent from the deprecated `TemporalAgent` wrapper to the `TemporalDurability` capability (pydantic-ai 2.51 / harness 0.36 already pinned on main 203e7dd), without changing any activity name and without breaking replay of pre-migration workflow histories. Migration only and behaviour-neutral (GATE 1 ruling B2).

## Context and verified findings

The task brief's claims were checked against the code on main 203e7dd. Where the code differs from the brief, the difference is stated here and the spec follows the code.

| # | Brief / report claim | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | 16 agents are wrapped in `TemporalAgent` at `roles.py:~214-268` | True: 10 unconditional (`clarify`, the 2 clarify fan-out agents, `architect`, `planner`, `qa`, `reviewer`, `analyst`, `merge_verdict`, `devops`) plus 6 optional (`research`, `deep_review`, `handoff`, `adversary`, `discover`, `risk`), collected in `ALL_TEMPORAL_AGENTS`. | Scope is 16 durable agents. |
| V2 | "About 14 `agents/<role>/agent.py` assets" | True: 14 `agent.py` files. `agents/dev/` and `agents/devops/` hold only `agent.yaml` (harness roles, never built). The two fan-out agents are built inline in `roles.py`, not in assets. | 14 assets + 2 inline agents. The loader contract `build(model, instructions, model_settings)` is shared by 13 assets; `research` has a wider 5-argument variant (`tool_paths`, `provider`). Both shapes are in scope. |
| V3 | Replay of old histories is proven by replay tests | Partly. `tests/replay/test_feature_replay.py` replays 16 captured `FeatureWorkflow` histories through `Replayer` with `PydanticAIPlugin`. Those histories contain real agent activity names, but only `agent__<name>__model_request` is ever *scheduled*; the `event_stream_handler`, `model_request_stream`, `model_cancel_suspended_response` and `toolset__*` names appear only inside a "not registered on this worker" error text. `tests/graph_workflow/test_graph_golden.py` covers `GraphWorkflow` against golden traces. No captured history exists for `AssessmentWorkflow` (the only caller of `t_discover` / `t_risk`). | Replay proof covers 6 durable roles on `FeatureWorkflow` and `GraphWorkflow` goldens. Assessment agents and the optional agents have no captured history; the spec requires either a new captured history or an explicit name-level assertion for them. |
| V4 | The D8 `FAILURE_TYPES` pin exists | True: `tests/graph_workflow/test_graph_dispatch_chaos.py:327` pins `FAILURE_TYPES` (including the `UnsupportedEventLoopError` extra) against the plugin's list. `test_feature_replay.py::test_replayer_matches_the_production_worker_effect` pins the plugin's failure types too. | Both pins are kept green as gates. |
| V5 | Defect 3.1 / 6.1: `_run_role` never forwards the model | True: `RoleHost._run_role` (`role_host.py:120-135`) prices and tracks `model` but calls `agent.run(*args, **kwargs)` with no `model=`. The memoization key already moves with the override. | Confirmed defect; deferred to a follow-up (Decision B2). |
| V6 | Defect 3.4 / 6.4: SDK retries stack under Temporal retries | Consistent with code: no `max_retries`, no explicit provider or client anywhere in `src/`; agents are built from model-id strings; Temporal caps each proposer activity at 3 attempts. Installed SDKs: anthropic 1.9.0, openai 3.22.0, httpx2 2.13.1. | Confirmed; deferred to a follow-up (Decision B2). |
| V7 | `TemporalDurability` must be attached at agent construction | Consistent with the installed `TemporalDurability` (constructor-time, `temporal_activities` property). It registers the `event_stream_handler` activity only when a handler is supplied, whereas today's registered set includes it for every agent. Kroker registers no event stream handler. It also registers a `compact_messages` activity that `TemporalAgent` does not list. | The set of *registered* activity names changes by design; the set of *scheduled* names must be exactly equal. This is a stated, tested distinction (FR-005). |
| V8 | Only the workflow side calls `t_*` | False for one agent: `stages/research/toolset.py:48` calls `t_research.run(...)` from inside the architect's `research` tool, i.e. from an activity, and `stages/research/stage.py:206` runs the plain agent inside an activity. A durable wrapper used from inside an activity is a distinct code path. | Explicit edge case and acceptance scenario; the research path is an R2-class risk in the upgrade matrix. |
| V10 | Migration is behaviour-neutral (skeptic 003-1) | Partly refuted: `TemporalDurability` defaults `heartbeat_timeout=30s` on model activities, `TemporalAgent` did not (verified). Further skeptic claims (message re-preparation, `validate_args`, cancel-activity arity, sandbox model resolution, strict tool-result decoding) are hypotheses read from source by an agent and are NOT yet confirmed. | FR-019, FR-020; neutrality is a claim to prove, not assume. |
| V9 | `benchmarks/experiments/` holds proposer-arm records | The directory is empty on main. Records with proposer overrides may live elsewhere or not exist. | Inventory is the first step of the follow-up (Decision A3). |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Migrate all durable agents with no change to running or replayed workflows (Priority: P1)

An operator deploys the new worker while runs started before the deploy are still in flight or are replayed from recorded history. Every one of the 16 agents runs through the new durability mechanism, and no existing workflow history fails to replay.

**Why this priority**: The deprecated wrapper is scheduled for removal in the next major version of the agent library. Without this migration the pipeline is stuck on the current major version, and later durability-aware capabilities cannot see the pipeline as durable. It is also the part with the hard safety constraint (replay determinism), so it must land first and alone be releasable.

**Independent Test**: Replay every captured history in `tests/replay/histories/` and every graph golden with the migrated code; all replay with no non-determinism error. Run the `temporal` tier in the dev container end to end; a full pipeline run with the fake agents produces the same stage/gate trace as before.

**Acceptance Scenarios**:

1. **Given** the captured `FeatureWorkflow` histories recorded by pre-migration code, **When** they are replayed on the migrated worker, **Then** every replay completes with no replay failure and no changed command sequence.
2. **Given** the migrated code, **When** the set of activity names each agent would schedule is compared against the names recorded in the captured histories, **Then** every recorded scheduled name still exists and no agent or toolset name has changed.
3. **Given** a workflow that was started on the old worker and is mid-run when the new worker starts, **When** the new worker picks up its next workflow task, **Then** the run continues to completion without draining, versioning or a restart.
4. **Given** the migrated worker, **When** it boots, **Then** every activity a workflow can schedule for any of the 16 agents is registered exactly once (no duplicate registration error, none missing).

---

### User Story 2 - Registry contract carries durability configuration for every agent (Priority: P1)

A maintainer adding or editing a role in `agents/<role>/` gets durable behaviour (activity timeout and bounded retries) from the shared registry contract rather than from a per-role wrapper line in `roles.py`.

**Why this priority**: Durability must be attached when an agent is constructed, so the contract between the loader and each `agent.py` must change. The two clarify fan-out agents, which are built inline, must follow the same rule. This is the structural core of the migration.

**Independent Test**: Load the registry and build all agents; each exposes the same durable activity configuration that its wrapper used to supply, heartbeat timeout included (FR-019) (10-minute start-to-close; 3 attempts; the fan-out agents use their own separately named config); a role whose `build` ignores the durability parameter is rejected at load time.

**Acceptance Scenarios**:

1. **Given** a registry with a role whose `agent.py` does not attach the durability configuration, **When** the registry is loaded, **Then** loading fails closed with an error naming the role.
2. **Given** the shared and the clarify-fan-out activity configurations, **When** the agents are built, **Then** the fan-out agents keep their own bounded configuration (their budget and the single-call budget stay independently adjustable).
3. **Given** two roles that build agents with the same name, **When** the registry loads, **Then** it is rejected (the existing collision guard is preserved).
4. **Given** the optional roles (`research`, `deep_review`, `handoff`, `adversary`, `discover`, `risk`), **When** their folder is absent, **Then** the pipeline still imports and runs without them, as today.

---

### User Story 3 - Prove the durable path against every kind of agent, including research (Priority: P2)

A reviewer can see evidence that agents which use tools, code-mode capabilities, or nested calls behave the same under the new mechanism as under the old one.

**Why this priority**: The unit tier does not reach the research path (upgrade matrix R2), and `t_research` is called from inside an activity, which the replay histories do not exercise.

**Independent Test**: The `temporal`-marked research tests and the assessment end-to-end test pass in the dev container; a research-enabled run through the migrated agents produces a brief and the per-run research budget still holds.

**Acceptance Scenarios**:

1. **Given** the architect calling its `research` tool, **When** the tool invokes the research agent from inside an activity, **Then** the call completes and the disk-persisted research budget still bounds total research spend.
2. **Given** an agent whose model returns a malformed response, **When** the activity fails, **Then** the failure is non-retryable and reaches the node's `fail` port (the `FAILURE_TYPES` routing is unchanged).
3. **Given** the assessment phase agents (`discover`, `risk`), **When** an assessment run executes under the migrated worker, **Then** it completes; its activity names are asserted against the pre-migration names.

---

### Edge Cases

- **In-flight run across the deploy**: a run whose next command depends on a not-yet-scheduled agent activity resumes on the new worker (US1 scenario 3).
- **Registered vs scheduled name set changes**: the migrated worker will not register an `event_stream_handler` activity (no handler is configured) and will register a `compact_messages` activity. A pre-migration history that contains only `model_request` schedules is unaffected; a history that scheduled an `event_stream_handler` activity would fail. FR-005 states how this is checked.
- **Two agents with one name**: still a load-time error.
- **Nested durable call**: `t_research` invoked from inside a tool activity (V8) must behave as a plain run, not attempt to schedule further workflow activities.
- **Optional roles absent**: the pipeline imports without them; none of the 6 optional agents may become mandatory.
- **Sandbox import cost and module duplication**: agent construction happens at import in the workflow sandbox path; an unmarked sandbox-executed module duplicating pydantic classes is a known trap (ValidationError with `input_type == class name`); the migration must not introduce new sandbox-executed modules without marking them.
- **File-size ratchet**: no touched file may exceed 1000 lines; `roles.py` (293) and `loader.py` (464) have headroom.
- **Heartbeat timeout default**: the capability adds a 30s heartbeat timeout to model activities that the old wrapper never had (FR-019); a worker whose event loop is blocked past it would see attempts time out where they did not before.
- **Suspended-response cancel activity**: never scheduled in any captured history, so its wire shape is unproven by replay (FR-020 c).
- **Test fakes**: `tests/fakes/fake_agents.py` builds fakes by wrapping in `TemporalAgent`; they must use the same mechanism as production or replay proof is meaningless.

## Requirements *(mandatory)*

### Functional Requirements

**Migration (US1, US2)**

- **FR-001**: Every one of the 16 durable agents MUST get its durable behaviour from the `TemporalDurability` capability attached at construction. After the change, no production code path constructs or imports `TemporalAgent`.
- **FR-002**: Every agent `name` and every toolset `id` MUST be byte-identical to today's. No `# NEVER rename` value may change.
- **FR-003**: The loader contract MUST supply each asset's `build` with what it needs to attach the durability configuration. A role that fails to attach it MUST fail registry load with an error naming the role. Both existing `build` shapes (three-argument; five-argument for `research`) MUST be supported.
- **FR-004**: The two clarify fan-out agents, built in `roles.py`, MUST attach the durability capability with their own bounded activity configuration. The shared configuration (10-minute start-to-close, 3 attempts) and the fan-out configuration (same values today, separately named) MUST keep their current effective values.
- **FR-005**: The migration MUST prove replay compatibility by test, not by assertion. Required proofs:
  1. every captured `FeatureWorkflow` history replays through `Replayer` (`tests/replay/`) with no failure;
  2. every `GraphWorkflow` golden trace still matches;
  3. a test derives, for every agent, the set of activity names the migrated agent *schedules from workflow code* and asserts it is **exactly equal** (no additions, no removals) to the scheduled names found in all captured histories and the frozen fixture, and asserts the *registered* set contains every name a history can schedule;
  4. the D8 pin (`test_graph_dispatch_chaos.py` `FAILURE_TYPES`) and the replayer/production-worker failure-type pin stay green with no edit to their expected sets;
  5. agents with no captured history split by whether they carry tools (advisor 003-1, verified against `agents/*/agent.py`):
     - **tool-bearing** (`architect` only: one `research` function tool with `ResearchDeps`): a history captured on pre-migration code (main 203e7dd; capture MUST happen before any migration change lands, while main still builds the old wrapper) MUST be added under `tests/replay/histories/` and replayed after migration. The architect history covers model turn -> `research` tool call -> answer (proves the tool-call payload and `ResearchDeps` round-trip); the research history uses local tools only (offline, deterministic) and either a CodeMode-wrapped call or an explicit "CodeMode name-checked only" note;
     - **`research`** (four plain tools, `CodeMode`, exa) is tool-bearing but no workflow ever schedules a `research`-agent activity (it runs in-process inside the architect's tool activity), so no captured workflow history can contain it: it is covered by the name-level fixture plus the nested-path test (FR-011) (amended 2026-09-30, see Change record);
     - **tool-free** (all others, including the two clarify fan-out agents once the plan confirms they are tool-free): a name-level assertion against a **literal fixture of pre-migration names** dumped on main 203e7dd (all 16 agents' activity names plus toolset ids) is sufficient; the fixture MUST NOT be generated at test time from the code under test;
     - a clarify fan-out history and an `AssessmentWorkflow` history (`discover`, `risk`) SHOULD be captured; if skipped, the plan records the residual risk.
  6. the captured `architect` history is the old-recorded prefix for the mixed-prefix in-flight test (SC-006).
- **FR-006**: No existing recorded history or golden file MAY be re-recorded or edited to make a test pass (existing stop-guards SG-2 / SG-3).
- **FR-007**: Worker registration MUST register every agent's durable activities exactly once, via the agents' own registration surface, without a hand-maintained list of names. `ALL_TEMPORAL_AGENTS` or its replacement MUST include the optional agents iff they are present.
- **FR-008**: Test fakes (`tests/fakes/fake_agents.py` and other `TemporalAgent`-wrapping test helpers) MUST use the same durability mechanism as production and keep the production agent names.
- **FR-009**: `ARCHITECTURE.md` §4, §13 and ADR-2, and any `AGENTS.md` / docs that name `TemporalAgent` as the mechanism, MUST be updated in the same change (artifact boundary rule).

**Behaviour preservation (US3)**

- **FR-010**: Failure routing MUST be unchanged: `FAILURE_TYPES` keeps its members (no removals), and an agent failure with a declared `fail` port still routes there.
- **FR-011**: The architect's `research` tool path (agent called from inside an activity) MUST keep working; the disk-persisted research budget MUST remain the enforcement mechanism (the migration does not remove the need for it).
- **FR-012**: The optional roles MUST remain optional; absence of an optional agent folder MUST NOT break import or worker boot.
- **FR-013**: Bounded retries MUST be preserved: no agent activity gets an unbounded retry policy (regression guard for bug e2e-proposer-hang).
- **FR-014**: The migration MUST be behaviour-neutral, defined here once: it MUST NOT change which model answers a request, the number of HTTP attempts per request, model pricing, or any per-run spend figure, except a difference explicitly ruled under FR-019/FR-020, which MUST state its effect on attempts and spend. Verification: attempt count and spend are asserted by the FR-019 command-attribute fixture and by an unchanged priced-usage record in the temporal-tier run (SC-006a). Model forwarding, SDK retry disabling, a native zai provider and defects 6.2/6.3 are out of scope (see Resolved Decisions).

**Wire-level neutrality (skeptic 003-1; each item verified or marked for the plan)**

- **FR-019**: The scheduled activity *command attributes* (start-to-close timeout, heartbeat timeout, retry policy, argument arity) for every agent MUST be equal to the pre-migration ones, or each difference MUST be an explicit, recorded ruling. Known difference, **verified in installed 2.51 source** (`_durability.py:83, 278`): `TemporalDurability` gives model-request activities a default 30-second `heartbeat_timeout` (with background heartbeating), whereas `TemporalAgent` sets none. Default: override it to none (strict neutrality). Accepting it as a ruled change requires recorded evidence that background heartbeating is reliable on this worker under load AND an explicit user ruling at the plan gate; it MUST NOT be left implicit. The expected attribute fixture (timeouts, heartbeat, retry policy, argument arity for every agent) MUST be dumped on main 203e7dd before the migration and MUST NOT be generated at test time from the code under test. Tests MUST assert the emitted command attributes, not only that replay completes (replay of completed histories does not exercise them).
- **FR-020**: The plan MUST resolve, by reading source and by test, the remaining skeptic hypotheses, each currently **unverified**: (a) whether the model-request path still re-prepares messages against the concrete model on the worker as `TemporalAgent` did (`_model.py:110, 477`), i.e. whether provider request payloads for multi-turn tool runs are unchanged; (b) whether any Kroker tool triggers the separate `validate_args` activity (Kroker registers no `args_validator` per the comparison report; re-verify by search); (c) whether `model_cancel_suspended_response` argument arity differs between the two mechanisms (only matters if a suspended response is ever cancelled across an upgrade); (d) whether model-id strings are resolved inside workflow (sandbox) code under the capability and whether all 16 roles' providers construct there without a sandbox restriction violation; (e) whether `tool_call_result_upgrade_lenient=False` rejects tool results recorded by `TemporalAgent`. Each outcome is recorded in the plan as verified-neutral, mitigated, or a ruled difference. If a hypothesis cannot be made neutral and would break a FR-005.1 replay or an in-flight run, the plan MUST stop and escalate to the user before proceeding; replay compatibility (FR-005.1/2) is not waivable by a ruling.

- **FR-021**: The migration MUST NOT introduce any new sandbox-executed module without marking it for the workflow sandbox (avoids the known pydantic class-duplication trap); a test or lint guards this.

**Process and constraints**

- **FR-015**: All verification MUST run in the dev container (`kroker-dev`, repo bind-mounted over `/app`, venv in a named volume), never the host Windows venv. Host hazards recorded in `.workspace/tasks/` (notably the Windows temporal-tier hang, 2026-09-09) MUST be read before any tier run.
- **FR-016**: No touched file may exceed 1000 lines (`scripts/check_file_size.py`).
- **FR-017**: The nearest `AGENTS.md` (`workflows/`, `stages/<stage>/`, etc.) MUST be read before editing a subpackage.
- **FR-018**: A follow-up inbox note recording the deferred work MUST exist in `.workspace/tasks/` (see Resolved Decisions).

### Key Entities

- **Durable agent**: a proposer agent whose model requests and tool calls run as Temporal activities. 16 of them; identified by a fixed name that doubles as its activity-name prefix.
- **Activity configuration**: timeout and bounded retry policy. Two named values today (shared; clarify fan-out).
- **Registry role**: an `agents/<role>/` folder (`agent.yaml`, `instructions.md`, `agent.py`) loaded and validated at import; the source of each role's model.
- **Captured history / golden trace**: recorded workflow histories used to prove replay determinism. Read-only evidence.
- **Scheduled vs registered activity names**: the names a workflow can schedule vs the names a worker serves; replay depends on the former, worker health on the latter.

## Resolved Decisions (GATE 1, final)

| # | Decision | Ruling | Effect on this spec |
|---|----------|--------|---------------------|
| A | Benchmark proposer-arm records made while the override was ignored | **A3**: inventory first, then decide per record; no blanket re-run or re-label | Owned by the follow-up note, not 003. 003 changes no model behaviour, so it creates no new suspect records. |
| B | Model forwarding (6.1) and `max_retries=0` (6.4) | **B2**: split out. 003 is migration-only and behaviour-neutral | Former (pre-GATE-1) user stories 4-5, former FR-014..017 and former SC-007 removed (the live FR-014..018 and SC-007 are different, process/neutrality items); recorded in the follow-up note. |
| C | Native zai provider for `glm-*` roles | **C3**: separate feature with its own re-baseline | Out of 003. The follow-up note records the `genai-prices` 0.1.9 +19-23% `zai:glm-5.2` pricing break. |
| D | Defects 6.2 (unpriced architect research sub-runs) and 6.3 (oversized prompt hangs) | **D1**: out of scope | 003 only has to not make them worse (FR-011, FR-014). |

The deferred work is filed as `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md`. Its first step is the record inventory from Decision A.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of captured `FeatureWorkflow` histories (16 today) replay with zero replay failures on the migrated code, with no history file modified.
- **SC-002**: 100% of `GraphWorkflow` golden traces still match with no golden file modified.
- **SC-003**: Zero activity-name or toolset-id changes: the per-agent set of scheduled names is exactly equal before and after (no additions, no removals), so the diff is empty in both directions.
- **SC-004**: Zero production references to the deprecated wrapper remain (verified by search); the deprecation warning count in the unit and `temporal` tiers is zero for it.
- **SC-005**: The `temporal` tier, run in the dev container, passes with at least the pre-migration count of passing tests (160) and no new failures; the continue-on-error CI step is not used to hide a failure.
- **SC-006**: An in-flight run started on the old worker completes on the new worker without draining or restart, demonstrated by a test that mixes an old-recorded prefix with new-code continuation.
- **SC-006a**: For every one of the 16 agents, the scheduled activity command attributes match the pre-migration frozen fixture, or each difference is listed in the plan as a ruled change (FR-019); each FR-020 hypothesis has a recorded outcome.
- **SC-007**: No touched file exceeds 1000 lines; the file-size check passes.
- **SC-008**: The architecture documents name the new mechanism and none still name the old one as current.

## Change record

- 2026-09-30 (GATE 2, orchestrator ruling): FR-005.5a amended. Captured histories are required for `architect` only; `research` is covered by the name-level fixture and the nested-path test (FR-011), because no workflow schedules a research-agent activity (verified, `research.md` R5). FR-005.6 and SC-006 use the single `architect` prefix. No other requirement changed.

## Assumptions

- The pins (pydantic-ai 2.51, harness 0.36, uv.lock) and the R1 `FAILURE_TYPES` fix are already on main; the `temporal` tier is green (160 passed) in the dev container. Not re-verified here beyond reading the code; the plan phase re-runs it as its baseline.
- The report's statement that `TemporalDurability` "accepts the activity names and payload shapes recorded by `TemporalAgent`" is a hypothesis. The installed 2.51 code was read (constructor, registration, `temporal_activities`) and is consistent with it, but the proof required by FR-005 is behavioural, not by reading.
- Kroker registers no event stream handler and uses no tool `args_validator`, per the comparison report; the plan phase re-verifies by search.
- `t_research` being called from inside an activity (V8) is legitimate today and stays; whether it should be replaced by the plain agent is a design question for the plan, not this spec.
- Scope challenge result: the hypothesised file list (roles, loader, worker, ~14 assets + 2 inline agents) is complete for the migration proper, plus tests/fakes and docs (FR-008, FR-009). `role_host.py` and the provider seam are NOT touched (Decision B2).
- Activity names, agent names, toolset ids and the two configuration values are frozen; anything that would change them is a defect in this feature, not a design choice.
- Rollout: workers are deployed between runs as one fleet (upgrade matrix §6 step 4, retro №22); mixed old/new workers on one task queue and production rollback tooling are out of scope. Rollback is redeploying the prior image, which is safe only because activity names and scheduled commands are unchanged.
- Verification environment is the dev container; the host Windows venv is not used and the host temporal-tier hang is a known hazard, not a test result.
