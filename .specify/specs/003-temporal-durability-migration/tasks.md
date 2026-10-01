# Tasks: Migrate Durable Agents to TemporalDurability

**Input**: `.specify/specs/003-temporal-durability-migration/` (spec.md, plan.md, research.md, data-model.md, contracts/loader-build-contract.md, quickstart.md)

**Numbering note**: T045 and T046 were added after the reviewer pass and sit in the phase where they execute; execute in the listed position, not by number. Plan phases A-E map to tasks phases: A=1, B=2+US2 (T015-T019), C=US2 (T020-T022)+migration of assets (T013), D=US1+US3, E=6.

**Tests**: requested by the spec (FR-005, FR-019, FR-020): proof tests are part of the feature. TDD order: a test task precedes the change it guards and must be seen failing first.

**Environment (every run)**: dev container `kroker-dev`, primary checkout bind-mounted, named-volume venv (see quickstart.md). Never the host Windows venv. One pytest per command. Read `.workspace/tasks/2026-09-09-temporal-tier-hangs-on-windows.md` before any tier run. No commits by the executor: the orchestrator commits at integration; **Phase 1 artifacts must be committed before Phase 2 lands** (T009).

**Rules carried in**: agent names, toolset ids, activity names and the two config values are frozen; never edit an existing history/golden (SG-2/SG-3); read `src/sdlc/workflows/AGENTS.md` and `src/sdlc/stages/research/AGENTS.md` before touching those subpackages; 1000 lines/file. Anything that would break replay stops and is escalated to the orchestrator (do not rule it).

Format: `- [ ] Tnnn [P?] [US?] description with path`. `[P]` = independent files.

---

## Phase 1: Setup - capture on UNMODIFIED main (pre-migration evidence)

**Purpose**: fixtures and histories recorded with the old wrapper. No production code changes in this phase.

- [X] T001 Read `src/sdlc/workflows/AGENTS.md`, `tests/replay/harness.py`, `tests/replay/scenarios.py`; confirm `git rev-parse HEAD` = 203e7dd; if main has moved, record the actual base and flag it to the orchestrator as a deviation from the spec pin and the working tree has no migration changes
- [X] T002 Baseline in the dev container: run `pytest -m temporal -q` (single command) and `pytest -q` fast tier; record pass/fail counts and any host-hazard notes in `.specify/specs/003-temporal-durability-migration/research.md` (section "Baseline")
- [X] T003 [P] Write a throwaway-free fixture dumper `tests/replay/dump_agent_fixture.py` that, from `sdlc.agents.roles`, dumps per agent: name, toolset ids, registered activity names (`ta.temporal_activities`), scheduled names and model-request command attributes (start-to-close, heartbeat, max attempts, non-retryable types, arg count) into `tests/replay/fixtures/agent_activities_pre_migration.json`; include the base commit sha field
- [X] T004 Run the dumper on main; write `tests/replay/fixtures/agent_activities_pre_migration.json` (16 agents); check it lists `event_stream_handler` in registered and heartbeat 0
- [X] T005 [P] Capture history `architect_research_tool` (model turn -> `research` tool call -> answer; this is the only history that exercises the research path, see plan.md "Proposed spec amendment") into `tests/replay/histories/architect_research_tool.json` using `tests/replay/harness.py` with fakes; add the scenario to `tests/replay/scenarios.py` without altering existing scenarios
- [X] T006 [P] Capture history `clarify_fanout` (route + probe agents) into `tests/replay/histories/clarify_fanout.json` and register the scenario
- [X] T007 [P] Capture history `assessment_discover_risk` (`AssessmentWorkflow`, `discover` + `risk`) into `tests/replay/histories/assessment_discover_risk.json`; if infeasible, record why and downgrade to name-level in research.md (residual risk)
- [X] T008 [P] Capture provider-level request messages for a multi-turn architect run on main by patching the concrete model `request` method and recording `(messages, settings, params)` into `tests/replay/fixtures/architect_provider_requests_pre_migration.json` (input for FR-020a)
- [X] T009 Stop point: report the new files to the orchestrator; wait for them to be committed on main before starting Phase 2

**Checkpoint**: fixtures + 3 histories + payload capture exist and are committed.

---

## Phase 2: Foundational - loader contract (blocks all stories)

**Purpose**: the `capabilities` seam. See contracts/loader-build-contract.md.

- [X] T010 [P] Write failing tests `tests/durability/test_loader_contract.py`: `build_agents(..., durability_factory=...)` passes a fresh `capabilities=[dur]` per role; `None` factory leaves agents capability-free; both `build` shapes (3-arg and research 5-arg) accept `capabilities`
- [X] T011 Add `tests/durability/__init__.py` and a tiny fixture registry under `tests/durability/` (temp agents dir) for the contract tests
- [X] T012 Implement in `src/sdlc/agents/loader.py`: `durability_factory` parameter on `build_agents`, keyword-only `capabilities` passed to `build` (both shapes); no module-level temporal import (lazy inside the function)
- [X] T013 Update the 14 `agents/<role>/agent.py` `build()` signatures to accept `capabilities` and forward `capabilities=[*capabilities, *own]` (durability first/outermost; research: before `CodeMode`/exa); do NOT touch `name=` values: `agents/{adversary,analyst,architect,clarify,deep_review,devops_planner,discover,handoff,merge_verdict,planner,qa,research,reviewer,risk}/agent.py`
- [X] T014 Run `pytest tests/durability/test_loader_contract.py tests/test_agents_registry.py tests/test_registry_resolution.py -q` in the dev container (one command); all green

**Checkpoint**: contract in place; agents still capability-free until roles.py supplies the factory.

---

## Phase 3: User Story 2 - Registry contract carries durability configuration (P1)

**Goal**: durable behaviour comes from the registry contract; misconfigured roles fail closed.

**Independent Test**: load the registry; every agent exposes `TemporalDurability` with the frozen config; each fail-closed case raises `RegistryError` naming the role.

- [ ] T015 [P] [US2] Write failing tests in `tests/durability/test_loader_failclosed.py`: old-shape build (TypeError), capability dropped (`from_agent` is None), two durability instances, weakened `start_to_close_timeout`/`maximum_attempts`, non-none `heartbeat_timeout`, name mismatch, existing collision guard
- [ ] T016 [US2] Implement the fail-closed checks in `src/sdlc/agents/loader.py` (`RegistryError` with role name; lazy `TemporalDurability` import; `UserError` -> `RegistryError`)
- [ ] T017 [US2] In `src/sdlc/agents/roles.py` define the shared factory `TemporalDurability(activity_config=AGENT_ACTIVITY_CONFIG, model_activity_config={"heartbeat_timeout": None})` and pass it to `build_agents`; keep `AGENT_ACTIVITY_CONFIG` and `CLARIFY_FANOUT_ACTIVITY_CONFIG` values and separate names unchanged
- [ ] T018 [US2] Build `clarify_route_agent` / `clarify_probe_agent` in `src/sdlc/agents/roles.py` with `capabilities=[TemporalDurability(activity_config=CLARIFY_FANOUT_ACTIVITY_CONFIG, model_activity_config={"heartbeat_timeout": None})]`
- [ ] T019 [US2] Replace the 16 `TemporalAgent(...)` wraps in `src/sdlc/agents/roles.py` with plain aliases (`t_x = x_agent`; optional ones `None`-able); keep `ALL_TEMPORAL_AGENTS` as a list of agents and the module-level names
- [ ] T020 [US2] Registration handle: update `src/sdlc/worker.py:131` to `TemporalDurability.from_agent(a).temporal_activities` per agent; add `tests/durability/test_worker_registration.py` asserting every activity name is registered exactly once and none missing (FR-007)
- [ ] T021 [P] [US2] Update `tests/fakes/fake_agents.py` to `Agent(TestModel(...), name=<prod name>, capabilities=[TemporalDurability(<same config incl. heartbeat none>)])` with activities via `from_agent`; keep names identical (FR-008)
- [ ] T022 [P] [US2] Update the other test helpers that call `TemporalAgent`/`.temporal_activities` (`tests/research/test_research_e2e.py`, `tests/research/test_research_spike.py`, `tests/research/test_research_budget_store.py`, `tests/test_assessment_workflow_e2e.py`, `tests/test_assessment_workflow_e2e_proposer_hang_chaos.py`, `tests/deploy/test_deployment_workflow.py`, `tests/test_factory_purity.py`, `tests/test_memory_wiring.py`, `tests/test_module_imports.py`, `tests/test_operator_layering.py`, `tests/test_promptfoo_provider.py`, `tests/test_spike_agent_stub.py`) to the capability path
- [ ] T045 [US2] FR-021 guard: add `tests/durability/test_sandbox_module_marking.py` asserting every module under `src/sdlc/agents/` that a workflow imports inside the sandbox is either already passthrough/marked or unchanged since main; if a new module (e.g. `src/sdlc/agents/durability.py`) is created, mark it for the workflow sandbox in the same change (added after review; run before T023)
- [ ] T023 [US2] Run `pytest tests/durability -q`, then `pytest -q` fast tier (separate commands) in the dev container; green

**Checkpoint**: US2 done; agents are durable via the capability.

---

## Phase 4: User Story 1 - No change to running or replayed workflows (P1) MVP

**Goal**: replay compatibility proven, not asserted.

**Independent Test**: all 16 existing histories + 3 new histories replay; graph goldens match; fixture diff empty; D8 pins green; in-flight mixed-prefix run completes.

- [ ] T024 [US1] Write `tests/durability/test_activity_fixture.py`: compare migrated agents to `tests/replay/fixtures/agent_activities_pre_migration.json`: scheduled names **exactly equal**; command attributes **exactly equal** (heartbeat 0, s2c 600, attempts, non-retryable list, arg count); every name a history can schedule is registered exactly once; expected registered deltas (`-event_stream_handler`, `+model_compact_messages`, `+validate_args`) listed; the fixture's recorded base sha is asserted
- [ ] T025 [P] [US1] Extend `tests/replay/test_feature_replay.py` (parametrization only, no edit to existing cases) to replay `architect_research_tool`, `clarify_fanout` and, if captured, `assessment_discover_risk`
- [ ] T026 [US1] Run in the dev container, separate commands: `pytest tests/replay/test_feature_replay.py -q`; `pytest -m temporal tests/replay/test_graph_golden.py -q`; `pytest tests/graph_workflow/test_graph_dispatch_chaos.py -q` (D8 pin, no edit to expected set); `pytest tests/durability/test_activity_fixture.py -q`. Any replay failure: STOP and escalate to the orchestrator
- [ ] T027 [US1] Mixed-prefix in-flight test `tests/durability/test_inflight_resume.py`: replay the old-recorded `architect_research_tool` prefix and continue with new code through a live worker to completion (SC-006)
- [ ] T028 [US1] Confirm no existing history/golden file changed: `git diff --stat -- tests/replay/histories tests/replay/golden` shows only added files (FR-006)

**Checkpoint**: US1 MVP proven.

---

## Phase 5: User Story 3 - Prove the durable path for tool/nested agents and record FR-020 outcomes (P2)

**Goal**: FR-011/FR-013 hold; each FR-020 hypothesis has a recorded outcome.

**Independent Test**: temporal research tests + assessment e2e pass; outcomes a-e recorded.

- [ ] T029 [P] [US3] FR-020(a): write `tests/durability/test_provider_payload_parity.py` re-running the T008 scenario on migrated code and asserting identical recorded provider request messages; record outcome. If they differ: STOP and escalate
- [ ] T030 [P] [US3] FR-020(b)+(c): write `tests/durability/test_no_unreachable_activities.py` asserting no shipped agent/workflow path schedules `validate_args` or `model_cancel_suspended_response` (search + a run of the architect flow inspecting scheduled types); record outcomes (c) as residual risk if reachable-by-construction, else escalate
- [ ] T031 [P] [US3] FR-020(d): write `tests/durability/test_first_workflow_task_time.py` (temporal tier) measuring the first workflow task duration for old-shape vs new with the real registry and asserting it is below the 2 s deadlock threshold with margin; if the spike hazard reproduces, implement a mitigation (import/warm-up outside the sandbox or sandbox passthrough) in `src/sdlc/worker.py` or escalate; record outcome
- [ ] T032 [US3] FR-020(e): confirm strict tool-result decoding via T027/T025 architect replays; record outcome (verified-neutral by source, proven by replay)
- [ ] T033 [P] [US3] Nested research path: extend `tests/research/test_research_e2e.py` (or add `tests/research/test_research_durability_nested.py`) proving `t_research.run` inside the architect's tool activity completes as a plain run and the persisted budget still bounds spend (FR-011)
- [ ] T034 [P] [US3] Failure routing: extend `tests/graph_workflow/test_graph_dispatch_chaos.py` neighbours only (no edit to the D8 expected set) with a case that a malformed model response is non-retryable and reaches the `fail` port under the capability (FR-010)
- [ ] T035 [P] [US3] Bounded retries: `tests/durability/test_bounded_retries.py` asserting every agent's activity config keeps `maximum_attempts=3` and a finite timeout (FR-013), including the fan-out agents
- [ ] T036 [US3] Run in the dev container, separate commands: `pytest -m temporal tests/research -q`; `pytest -m temporal tests/test_assessment_workflow_e2e.py -q`; `pytest -m temporal tests/test_assessment_workflow_e2e_proposer_hang_chaos.py -q`
- [ ] T046 [US3] FR-014 priced-usage check: in a temporal-tier run of the graph golden scenario, assert the `price_usage` activity inputs (model, input/output/cache tokens) and resulting `RoleUsage` records are equal to those in the pre-migration captured histories/goldens; record the record name checked (added after review; run before T037)
- [ ] T037 [US3] Append the FR-020 outcomes (a-e: verified-neutral | mitigated | ruled | escalated, with test ids) to `research.md`; escalate to the orchestrator anything not neutral

**Checkpoint**: all three stories independently verified.

---

## Phase 6: Polish, docs, close

- [ ] T038 [P] Update wording (artifact boundary rule, FR-009): `ARCHITECTURE.md` (Â§4, Â§13, ADR-2, diagram label line 37, tech table 722, tree 787), `README.md`, and comments/docstrings in `src/sdlc/agents/roles.py`, `src/sdlc/agents/settings.py`, `src/sdlc/naming.py`, `src/sdlc/worker.py`, `src/sdlc/workflows/{feature,assessment}.py`, `src/sdlc/stages/research/{stage,toolset,budget_store,deps,verify}.py`, `agents/research/exa_wrapper.py`; no living doc may name the wrapper as current
- [ ] T039 Search proof: `grep -rn "TemporalAgent" src agents` returns no production reference (SC-004); tests keep it only inside explicitly labelled deprecated-comparison comments, if any
- [ ] T040 [P] `ruff check .`, `ruff format --check .`, `mypy` (src scope) in the dev container; fix findings without altering frozen values
- [ ] T041 [P] `python scripts/check_file_size.py` in the dev container (SC-007); touched files stay under 1000 lines
- [ ] T042 Final full runs (separate commands): `pytest -q`; `pytest -m temporal -q`; compare pass counts with T002 (SC-005, at least 160 passed, no new failures)
- [ ] T043 Confirm the follow-up note exists: `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md` (FR-018) and that no out-of-scope item (model forwarding, `max_retries`, zai, 6.2/6.3) was touched (FR-014)
- [ ] T044 Report to the orchestrator: counts, FR-020 outcomes, residual risks (cancel activity shape, heartbeat side effect), and the files changed; do not commit

---

## Dependencies and order

- Phase 1 -> (orchestrator commit) -> Phase 2 -> US2 (Phase 3) -> US1 (Phase 4) -> US3 (Phase 5) -> Phase 6.
- US1 depends on US2 (agents must be durable before replaying against them) and on Phase 1 artifacts. US3 tasks T029-T031, T033-T035 are independent of each other once US2 is done; T032/T037 need T025/T027.
- T011 (package + fixture registry) must land before the tests in T010 can run; do T011 first even though both are marked [P].
- Inside Phase 3: T015 before T016; T017-T019 sequential (same file); T021/T022 parallel; T020 after T019.

## Parallel examples

- Phase 1: T003, T005, T006, T007, T008 in parallel after T001-T002 (T004 needs T003).
- Phase 5: T029, T030, T031, T033, T034, T035 in parallel (different files); T036 after them.
- Phase 6: T038, T040, T041 in parallel.

## Implementation strategy

MVP = Phase 1 + Phase 2 + US2 + US1: the migration with replay proof. US3 adds the FR-020 evidence and the nested/failure/retry guards and must complete before the feature is declared done. Deliver in that order; stop and escalate at any replay or payload difference.

## Counts

46 tasks: Setup 9, Foundational 5, US2 10, US1 5, US3 10, Polish 7. Parallel opportunities: 19 tasks marked [P].
