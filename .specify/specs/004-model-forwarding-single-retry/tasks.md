# Tasks: Model Forwarding and a Single Retry Layer

**Input**: `.specify/specs/004-model-forwarding-single-retry/` (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: required (spec FR-006, FR-008). Every behaviour task is preceded by its RED test.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (see quickstart.md). Never the host venv. One pytest per command.
- Read the nearest `AGENTS.md` before editing a subpackage: `src/sdlc/workflows/`, `src/sdlc/stages/{code,research,architecture,analyze}/`.
- Commit per task: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`.
- A doc clause changes in the same commit as the behaviour it describes.
- Reviewer gate is per task: task N+1 is not committed until the reviewer has replied approve or fixes-needed on task N's diff.
- No attempt budget, backoff or timeout value is edited anywhere (ruling Q3).
- No captured history or golden is edited. A replay or golden failure is stop-guard SG-2.
- Stop-guards SG-1..SG-5 (plan.md) are binding: stop, diagnose, report; clearance comes only from the orchestrator.

## Phase order

Story phases run in the plan's order, not priority order: US3 (retries) before US2 (validation) before US1 (forwarding). Reason (plan.md, "Phases and stop-guards"): an override must never reach a provider that still stacks retries, and an invalid string must never reach a real call. US4 (inventory) is read-only and runs in the baseline phase.

| Tasks phase | Plan phase | Story |
|---|---|---|
| 1 Setup + baseline | A | - |
| 2 Foundational | B (module skeleton), D (recording fake) | - |
| 3 Inventory | A | US4 |
| 4 Single retry layer | B | US3 |
| 5 Validation | C | US2 |
| 6 Forwarding | D | US1 |
| 7 Polish | E | - |

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [X] T001 Create the feature branch `004-model-forwarding-single-retry` from main and confirm `kroker-dev` syncs (`uv sync --frozen --extra dev --extra logfire`); record the base sha in `.specify/specs/004-model-forwarding-single-retry/baseline.md`
- [X] T002 Run `pytest -q` and, as a separate command, `pytest -m temporal -q` on the base sha; record both pass counts and any pre-existing failures in `.specify/specs/004-model-forwarding-single-retry/baseline.md`
- [X] T003 Write `tests/durability/test_wire_neutrality.py` plus a dump helper that records, for one no-override FeatureWorkflow run on the fakes, the ordered scheduled activity names and the model id carried by each `model_request` input; generate `tests/durability/fixtures/wire_no_override.json` on the base sha (the fixture is frozen: the test must load it, never regenerate it at test time) and record in `baseline.md` whether the model id is the registry string or null (research.md R2)
- [X] T004 Record the first-workflow-task timing from `tests/durability/test_first_workflow_task_time.py` on the base sha in `.specify/specs/004-model-forwarding-single-retry/baseline.md`

**Checkpoint**: baseline.md holds base sha, two pass counts, the wire fixture verdict (R2) and the timing. The stacked-retry count on main (plan Phase A) is recorded by T009, because it needs the stub from T008.

---

## Phase 2: Foundational (blocks every story)

- [X] T005 Create `src/sdlc/agents/model_ids.py` with module docstring and no provider imports at module level; add it to the sandbox-module pin in `tests/durability/test_sandbox_module_marking.py` (it lives under the `sdlc.agents` passthrough)
- [X] T006 Change `tests/fakes/fake_agents.py` so each resolver records `(agent name, model id)` in a module list and returns `TestModel(..., model_name=<model id>)`; add an autouse reset fixture in `tests/conftest.py`; keep `fake_agents.py` behaviour identical for existing tests (same outputs), then run `pytest -q` to confirm the count from T002

**Checkpoint**: fast tier count unchanged; the fake can tell which model id it was asked to be.

---

## Phase 3: User Story 4 - Benchmark record inventory (P3, read-only, research input)

**Goal**: a list of benchmark records made with a proposer override before this feature, with every searched location named.

**Independent test**: `inventory.md` exists, has one row per affected record or one "none found" row per location.

- [X] T007 [P] [US4] Write `.specify/specs/004-model-forwarding-single-retry/inventory.md` per research.md R9 and data-model.md "Benchmark inventory row": search `benchmarks/experiments/` and its git history, `runs/benchmarks/` and `SDLC_BENCHMARKS_ROOT` in this checkout, the benchmark scratch area, and `git log -p -- benchmarks/cases` for arms with a proposer `role_models` entry or a `default`. These are the complete set: the operator confirmed on 2026-10-01 that no other machine, container volume or external store holds benchmark records, and `inventory.md` must quote that confirmation with its date. No re-run, no re-label, no edit to any record.

**Checkpoint**: SC-005 met.

---

## Phase 4: User Story 3 - A failing provider is retried by one layer only (P2)

**Goal**: one model request makes at most its agent's attempt budget of HTTP requests.

**Independent test**: an always-429 local stub sees at most 3 requests for one proposer call.

### Tests first

- [X] T008 [US3] Write `tests/durability/_http_stub.py`: a local `127.0.0.1` HTTP server fixture that counts requests and can answer always-429 (anthropic and openai error bodies, no retry-after header), fail-once-then-valid, and always-400; no `httpx` or `respx` mocking (SDKs use httpx2)
- [X] T009 [US3] Write `tests/durability/test_single_retry_layer.py` (marker `temporal`): a registry-model durable agent under the real `AGENT_ACTIVITY_CONFIG` and a time-skipping environment, pointed at the stub via `ANTHROPIC_BASE_URL`; assert always-429 count <= `AGENT_ACTIVITY_MAX_ATTEMPTS`, fail-once count == 2, always-400 count == 1 (E7); the exhausted always-429 call raises the same activity failure the stage's existing degrade or fail-closed path handles today (FR-011). Run it on a clean worktree of the base sha and record the stacked count (expected 9) in `baseline.md`: the test must FAIL on main
- [X] T010 [P] [US3] Write `tests/durability/test_single_retry_coverage.py`: every agent in `ALL_TEMPORAL_AGENTS` and the planner and synthesis agents built in `src/sdlc/stages/research/stage.py` carry the single-retry capability; parametrized over every provider name the installed framework can construct, the built client has retry count 0 or opt-in retries (RED)

### Implementation

- [X] T011 [US3] Implement `single_retry_layer()` in `src/sdlc/agents/model_ids.py` per contracts/model-resolution-contract.md: a fresh model-id resolver capability that builds the model through `infer_model(id, provider_factory=...)` and sets the provider client's `max_retries` to 0 when present; builds no HTTP client; lazy imports
- [X] T012 [US3] Attach it in `build_agents` in `src/sdlc/agents/loader.py` beside the durability capability (only when a durability factory is supplied; eval path stays capability-free) and on `clarify_route_agent` and `clarify_probe_agent` in `src/sdlc/agents/roles.py`
- [X] T013 [US3] Attach it to the planner (`:104`) and synthesis (`:358`) agents in `src/sdlc/stages/research/stage.py`; update the single-retry clause in `src/sdlc/stages/research/AGENTS.md` in the same commit
- [X] T014 [US3] Run `tests/durability/test_single_retry_layer.py`, then `tests/durability/test_single_retry_coverage.py`, then `tests/durability/test_wire_neutrality.py`, then `pytest -m temporal tests/replay -q` (four separate commands). **SG-1**: always-429 count still above the budget for the registry-model agent: stop and escalate with the count. **SG-5**: a constructible provider not single-layer: stop and escalate. **SG-2**: wire fixture or replay changed: stop.
- [X] T015 [US3] Extend `tests/durability/test_single_retry_layer.py` with the research sub-question budget (6 attempts, `src/sdlc/stages/research/step.py:63`): always-429 count <= 6 for one sub-question call

**Checkpoint**: US3 acceptance scenarios 1 and 2 green; scenario 3 (override provider) is closed in Phase 6 (T029).

---

## Phase 5: User Story 2 - A bad override is refused before the run starts (P2)

**Goal**: an invalid proposer override is rejected at submission on all three entry paths.

**Independent test**: malformed and unknown-provider strings are rejected by the CLI, by matrix expansion and by graph validation before any workflow starts.

### Tests first

- [X] T016 [P] [US2] Write `tests/test_proposer_model_validation.py`: the accept/reject table in contracts/proposer-override-validation.md against `validate_proposer_model`; assert it needs no API key in the environment and makes no network call (RED)
- [X] T017 [P] [US2] Update `tests/test_cli_role_model.py`: a proposer override `architect=openai/gpt-5.2` is rejected with a message containing the role, the string and `provider:model`; a harness override `dev=zai-coding-plan/glm-5.2` is accepted as today; valid cases use `openai:gpt-5.2` (RED)
- [X] T018 [P] [US2] Update `tests/test_benchmark_arms.py`: an arm whose `default` or proposer `role_models` entry is invalid fails at matrix expansion before any cell; an arm `default` is validated for the proposer subset only; move existing proposer-role ids to the `provider:model` form (RED)
- [X] T019 [P] [US2] Add to the graph validation tests under `tests/graph/` a case where a node carries a proposer role with an invalid model and expect the new problem code (RED)

### Implementation

- [X] T020 [US2] Implement `validate_proposer_model(role, value)` in `src/sdlc/agents/model_ids.py` (raises `RegistryError`; `parse_model_id` + `infer_provider_class`, no instantiation; reject `test`)
- [X] T021 [US2] Call it in the proposer branch of `build_role_overrides` in `src/sdlc/cli_roles.py`; update the `--role-model` text in `README.md` in the same commit
- [X] T022 [US2] Call it at arm resolution in `src/sdlc/benchmarks/matrix.py` and in `_cell_config` in `src/sdlc/benchmarks/workflow.py` (proposer roles only)
- [X] T023 [US2] Add a proposer-model problem code and check beside the ADR-6 check in `src/sdlc/graph/validate.py`; if this flips any graph wire capability or problem-code fixture under `interfaces/`, regenerate it and gate with `scripts/check_ui.py` in the same commit
- [X] T024 [US2] Update `tests/test_role_model_resolution.py` to valid ids; run the four test files from T016-T019, then `pytest -q` (separate commands)

**Checkpoint**: US2 acceptance scenarios 1-3 green; SC-002.

---

## Phase 6: User Story 1 - An overridden proposer role is answered by the model it names (P1)

**Goal**: the override reaches the call; label, price, usage and cache key name the model that answered.

**Independent test**: the recording fake sees the override id for the overridden role and the registry id for every other role.

### Tests first

- [X] T025 [US1] Write `tests/test_model_forwarding.py` (marker `temporal`, uses T006's recording fake): (a) a serial role (architect) with an override is served by the override id, and its `RoleUsage.model`, `price_usage` input and memo key name the same id; (b) with a `clarify` override both `clarify_route_agent` and `clarify_probe_agent` see it (E2); (c) a role not overridden in the same run sees its registry id; (d) an override equal to the registry model behaves exactly as no override (E1); (e) a benchmark cell built from an arm `default` serves every overridable proposer role with it; (f) the research sub-question fan-out under a `research` override sees the override id and labels it; (g) the architect's research tool under a `research` override sees it (RED on all but c and d)
- [X] T026 [P] [US1] Write `tests/test_run_role_guard.py`: `_run_role` with an override and a disagreeing `model` label raises a non-retryable error naming role, label and override; a caller-supplied `model=` kwarg is rejected; no override calls `agent.run` without `model=` (RED)
- [X] T027 [P] [US1] Add to `tests/test_role_model_resolution.py`: the memo key under an override differs from the pre-fix override key (raw string in the model slot) and from the no-override key; the no-override key is byte-identical to today; `content_key` still takes five positional arguments (RED)

### Implementation

- [X] T028 [US1] Implement `forwarded_model(cfg, role)` in `src/sdlc/agents/model_ids.py` (pure; override iff set and different from the registry model, keyed by registry role name)
- [X] T029 [US1] In `src/sdlc/workflows/role_host.py`: `_run_role` forwards `model=` and guards per contracts/model-resolution-contract.md; `_cached_stage` uses `fwd1:<model>` in the model slot when the model differs from the registry model; update the single-egress clause in `src/sdlc/workflows/AGENTS.md` in the same commit. Then add US3 scenario 3 to `tests/durability/test_single_retry_layer.py`: an `openai:`-prefixed override against the openai stub (`OPENAI_BASE_URL`) sees at most 3 requests
- [X] T030 [US1] Fix the reviewer label at `src/sdlc/stages/code/step.py:770` so it is the run's resolved model, with a net line count of zero or less (file must stay <= 991 lines, **SG-4**); update `src/sdlc/stages/code/AGENTS.md` in the same commit
- [X] T031 [US1] In `src/sdlc/stages/analyze/step.py`, make the label fallback agree with the forwarded model under an override (no provider-less label when an override exists); no behaviour change without an override
- [X] T032 [US1] In `src/sdlc/stages/research/stage.py`, the production branch of `_research_subquestion_impl` passes `model=inp.model` when it differs from the registry `research` model, else calls exactly as today (plan D7a)
- [X] T033 [US1] Add `research_model` to `ResearchDeps` in `src/sdlc/stages/research/deps.py` (omitted from serialization when None), populate it in `src/sdlc/stages/architecture/step.py` only under a `research` override, and pass it as `model=` in `src/sdlc/stages/research/toolset.py`; update `src/sdlc/stages/research/AGENTS.md` in the same commit
- [X] T034 [US1] In `src/sdlc/agents/runner.py`, extend `_warm_workflow_side_imports` to the openai and google provider modules (failure swallowed as today); add a non-anthropic-override case to `tests/durability/test_first_workflow_task_time.py`, and a case in `tests/test_model_forwarding.py` where the override's provider has no credential in the environment: the call fails with an error naming the provider or its credential (E4)
- [X] T035 [US1] Run, as separate commands: `tests/test_model_forwarding.py`, `tests/test_run_role_guard.py`, `tests/test_role_model_resolution.py`, `tests/durability/test_wire_neutrality.py`, `pytest -m temporal tests/replay -q`, `tests/durability/test_first_workflow_task_time.py`. **SG-3**: the guard fires in any no-override test: stop and report the call site. **SG-2**: wire fixture or replay changed: stop.

**Checkpoint**: US1 acceptance scenarios 1-4 green; SC-001, SC-004.

---

## Phase 7: Polish and close-out

- [X] T036 [P] Update `ARCHITECTURE.md` (agents/durability section, role-model override text, retry description) and `BENCHMARK.md` ("Model x role" row and the `--role-model` paragraph: proposer arms are real from this feature; records before it are listed in inventory.md)
- [X] T037 [P] File inbox tasks in `.workspace/tasks/`: (1) tune the agent attempt budget and backoff from evidence (plan risk 1); (2) benchmark judge stacks SDK retries under 5 attempts (plan risk 2); (3) call-site model resolutions can be collapsed onto `forwarded_model` (research.md R7); mark `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md` done
- [X] T038 Full verification per quickstart.md, each as its own command: `pytest -q`; `pytest -m temporal -q`; `ruff check .`; `ruff format --check .`; `mypy`; `python scripts/check_file_size.py`. Record counts against `baseline.md`; counts must be >= baseline with no new failure

---

## Dependencies

- Phase 1 -> Phase 2 -> Phases 3-6 -> Phase 7.
- T007 (US4) depends on nothing after T001 and can run alongside any phase.
- Phase 4: T008 -> T009; T010 parallel with T009; T011 -> T012 -> T013 -> T014 -> T015.
- Phase 5: T016-T019 parallel; T020 -> T021, T022, T023 (different files, may run in parallel after T020) -> T024.
- Phase 6 needs Phase 4 (single layer in place) and Phase 5 (validation in place). T025 first; T026, T027 parallel; T028 -> T029 -> T030..T034 (T030, T031, T032, T034 touch different files and may run in parallel; T033 after T032, same package) -> T035.
- T036 and T037 parallel; T038 last.

## Parallel examples

- Phase 5 tests: T016, T017, T018, T019 together.
- Phase 6 after T029: T030, T031, T032, T034 together.

## Requirement coverage

| Requirement | Tasks |
|---|---|
| FR-001 | T025, T029, T032, T033 |
| FR-002 | T026, T028, T029, T030, T031 |
| FR-003, E3 | T027, T029 |
| FR-004, FR-005 | T016-T024 |
| FR-006 | T006, T025 |
| FR-007 | T010-T013 |
| FR-008 | T008, T009, T014, T015, T029 |
| FR-009 | T011 (no client built), T014 |
| FR-010, E5 | T003, T014, T035 |
| FR-011, E7 | T009, T038 |
| FR-012 | T007 |
| FR-013, FR-014 | no task: exclusions, checked at review |
| FR-015 | T030, T038 |
| E1, E2 | T025 |
| E4 | T034 |
| E6 | accepted risk (Q3); T037 |
| E8 | T009 (bound asserted per model request) |

## Implementation strategy

MVP is Phases 1, 2, 4, 5 and 6 together: US1 alone is not shippable, because forwarding without the single retry layer and validation would send overrides to providers that still stack retries and would turn typos into mid-run failures. US4 and Phase 7 complete the feature.
