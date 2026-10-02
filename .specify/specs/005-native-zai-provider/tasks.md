# Tasks: Native zai Provider for the glm Proposer Roles

**Input**: `.specify/specs/005-native-zai-provider/` (spec.md, plan.md, research.md, data-model.md, contracts/zai-route-contract.md, quickstart.md)

**Tests**: required (spec FR-006, FR-011, FR-016, A2, A3). Every behaviour task is preceded by its RED test.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (see quickstart.md). Never the host venv. One pytest per command; do not add `-q` (already in `addopts`).
- Read the nearest `AGENTS.md` before editing a subpackage: `src/sdlc/agents/`, `src/sdlc/eval/`, `src/sdlc/benchmarks/`, `src/sdlc/operator/`, `src/sdlc/doctor/`.
- Commit per task: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`.
- A doc clause or comment changes in the same commit as the behaviour it describes.
- Reviewer gate is per task: task N+1 is not committed until the reviewer has replied approve or fixes-needed on task N's diff.
- No attempt budget, backoff or timeout value is edited anywhere (004 Q3). Sites that did not zero SDK retries before must not start to.
- No edit to `pyproject.toml`, `uv.lock`, `src/sdlc/stages/code/step.py`, `src/sdlc/harness/base.py`, or any harness role's `agent.yaml`.
- No captured history, golden or eval fixture is edited. The one sanctioned regeneration is `tests/durability/fixtures/wire_no_override.json` in T021.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A dependency change appears necessary (FR-010).
- **SG-2** A replay, golden or in-flight test is red on the flipped registry (plan D6).
- **SG-3** The regenerated wire fixture differs in anything other than `model_id` values (FR-012).
- **SG-4** `test_first_workflow_task_time.py` shows a deadlock warning or a slower first task than the baseline by more than 0.5 s (FR-007).
- **SG-5** The `client.base_url` assignment does not reach the wire (T006 red after T008) — fall back per research.md R2 only with clearance.
- **SG-6** `ZAI_API_KEY` is absent for T030, or the live call fails for an account reason. Do not substitute a stub.

## Phase order

Story phases run in dependency order, not priority order: the route policy (Foundational) and the key check (US2) land **before** the registry flip (US1), so no commit exists in which the shipped registry points at an endpoint the code cannot reach or a key nothing checks. US3 (cost marker) follows the flip it describes.

| Tasks phase | Plan design | Story |
|---|---|---|
| 1 Setup + baseline | — | — |
| 2 Foundational: route policy at every site | D1, D2 | — |
| 3 Key check and environment contract | D3 | US2 |
| 4 Registry flip | D3, D4, D5, D6 | US1 |
| 5 Cost history | D7 | US3 |
| 6 Polish and verification | D7, D8 | — |

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [X] T001 Create the feature branch `005-native-zai-provider` from main `0f4ac11` in a worktree, confirm `kroker-dev` syncs (`uv sync --frozen --extra dev`), and record the base sha in `.specify/specs/005-native-zai-provider/baseline.md`
- [X] T002 Run `pytest` and, as a separate command, `pytest -m temporal` on the base sha; record both pass counts and any pre-existing failures in `.specify/specs/005-native-zai-provider/baseline.md`
- [X] T003 Record the first-workflow-task timing printed by `tests/durability/test_first_workflow_task_time.py` on the base sha in `.specify/specs/005-native-zai-provider/baseline.md`
- [X] T004 Grep `tests/` for assertions that loader-built or eval-built agents carry no capabilities (search `capabilities`, `has_resolve_model_id`, `_root_capability` in `tests/durability/test_loader_*.py`, `tests/test_eval_*.py`, `tests/test_agents_registry.py`); record each hit and whether T010/T011 would break it in `.specify/specs/005-native-zai-provider/baseline.md` (plan Risks, item 2)

**Checkpoint**: baseline.md holds base sha, two pass counts, the timing, and the capability-assertion inventory.

---

## Phase 2: Foundational — the route policy at every construction site (blocks every story)

**Goal**: any `zai:` string, at any of the seven sites, reaches the coding endpoint by default and `ZAI_BASE_URL` when set (FR-016, contract C1–C7). The registry is still unflipped; tests use `zai:glm-5.3` explicitly.

- [X] T005 Add `os.environ.setdefault("ZAI_API_KEY", "test-dummy")` beside the existing dummies in `tests/conftest.py` (module top and the placeholder-key fixture near line 128), so zai agents can be constructed without credentials
- [X] T006 [P] RED: write `tests/durability/test_zai_route.py` policy unit tests against `sdlc.agents.model_ids` — `zai_base_url()` default / override / blank-and-whitespace override; `resolve_model("zai:glm-5.3")` client base URL = coding endpoint, `max_retries` left at SDK default; `single_retry_layer()` resolution of `zai:glm-5.3` has coding base URL and `max_retries == 0`; a non-zai provider (`openai:gpt-5.2`) is untouched by the URL policy; env read at call time (set `ZAI_BASE_URL` after import, observe it). Confirm they fail for the right reason
- [X] T007 [P] RED: write `tests/test_model_construction_sites.py` — AST-scan `src/sdlc/**/*.py` and `agents/**/*.py` for calls named `Agent`, `infer_model`, `infer_provider`; fail on any call site outside an allow-list naming plan D2's seven sites, the 14 `agents/<role>/agent.py` build functions and `src/sdlc/agents/model_ids.py`; additionally assert that sites 5, 6, 7 (`src/sdlc/eval/runner.py`, `src/sdlc/benchmarks/judge.py`, `src/sdlc/operator/agent.py`) reference `resolve_model`. Confirm the second assertion is red
- [X] T008 Implement in `src/sdlc/agents/model_ids.py`: `ZAI_CODING_BASE_URL`, `zai_base_url()`, `_provider_for(name, *, single_retry)`, `resolve_model(model_id)`, `route_layer()`; make `single_retry_layer()` use `_provider_for(name, single_retry=True)`; keep all provider imports inside functions; update the module and `single_retry_layer` docstrings (base URL is no longer always the SDK default — spec A5). T006 goes green
- [X] T009 GREEN expected (a red here is SG-5, not a missing implementation): extend `tests/durability/test_zai_route.py` with stub-server tests using `tests/durability/_http_stub.py` and `ZAI_BASE_URL=<stub>` — for a `route_layer()` agent and a `resolve_model()` model, one request is observed on a path ending `/chat/completions` under the stub base; with `ZAI_BASE_URL` unset the model's client base URL is the coding endpoint (no network call made)
- [X] T010 Non-durable loader path in `src/sdlc/agents/loader.py` (near line 530): when `durability_factory is None`, pass `capabilities=[route_layer()]`; rewrite the "loader-only path keeps building capability-free" comment; adjust any test inventoried in T004 that pinned capability-free agents, stating why in the commit body. If a T004 test pins it for a reason that still holds, use the plan's fallback (`resolve_model` inside the branch) and record the choice
- [X] T011 [P] Eval runner in `src/sdlc/eval/runner.py` (line 39-40): a string model goes through `resolve_model` before `build(...)`; an injected test model passes through unchanged. Add a test in `tests/test_eval_runner.py` that a `zai:glm-5.3` fixture model builds against the coding endpoint
- [X] T012 [P] Benchmark judge in `src/sdlc/benchmarks/judge.py` (`_run_judge_agent`, line 140): string → `resolve_model`. Add a test in `tests/test_benchmark_judge.py` that a `zai:` judge model builds against the coding endpoint and that a google judge string is passed to the framework unchanged in behaviour
- [X] T013 [P] Operator chat in `src/sdlc/operator/agent.py` (`build_agent`, line 188): `cfg.model` → `resolve_model`. Add a test beside the existing operator agent tests that a `zai:` chat model builds against the coding endpoint
- [X] T014 `tests/test_model_construction_sites.py` (T007) goes green; run `pytest` and compare with the T002 count

**Checkpoint**: the policy is live at all seven sites with the registry untouched; default tier green.

---

## Phase 3: User Story 2 — a missing or placeholder z.ai key is caught before a run (P2)

**Goal**: doctor names `ZAI_API_KEY` when a zai-family role exists and the key is absent or a placeholder; the environment contract documents both variables.

**Independent test**: `pytest tests/doctor` — absent → fail naming the key; placeholder → fail; set → pass.

- [X] T015 [P] [US2] RED: add three cases to `tests/doctor/test_doctor_checks_runtime.py` mirroring the existing anthropic cases (lines 111-145) with a `zai:glm-5.3` proposer role: key absent, key equal to the `.env.example` placeholder, key set; plus one case with both a `zai:` and an `anthropic:claude-*` role asserting both keys are required (spec E6)
- [X] T016 [US2] Add `"zai": "ZAI_API_KEY"` to `_FAMILY_KEYS` in `src/sdlc/doctor/checks.py` (line 246). T015 goes green
- [X] T017 [US2] Rewrite the provider blocks of `.env.example`: new z.ai native block (`ZAI_API_KEY=your-zai-api-key`; commented `# ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4` with one line on when to set it; the E2 warning that `zai:glm-5.2` on this endpoint is answered by glm-5.3); Anthropic block re-described per Q3 (serves the adversary/discover/risk roles and env-authenticated coding CLIs; both variables kept as-is). In the same commit correct the `.env.example` line references in the `src/sdlc/doctor/env.py` module docstring (lines 11-13)
- [X] T018 [P] [US2] Update `README.md` Develop section (line 128): add `ZAI_API_KEY` to the keys needed at import and the dummy-key note; add the E2 warning beside the `--role-model` text (line 177); add the upgrade note: drain open runs before upgrading, or accept that their remaining stages run on the new route and model (plan D6)

**Checkpoint**: US2 holds on the unflipped registry (doctor is registry-derived, so it starts requiring the key the moment T020 lands).

---

## Phase 4: User Story 1 — glm proposer roles are served by z.ai's native route (P1)

**Goal**: all 11 roles declare `zai:glm-5.3`, resolve to the coding endpoint, keep the single retry layer, and do not trip the deadlock detector.

**Independent test**: quickstart.md steps 1, 3, 4.

- [X] T019 [US1] RED: in `tests/test_agents_registry.py` replace the single reviewer assertion (line 117) with a shipped-registry test: the 11 roles in data-model.md are exactly `zai:glm-5.3`; dev/test/devops are exactly `zai-coding-plan/glm-5.2`; adversary is `anthropic:claude-sonnet-4-6`; discover and risk are `anthropic:claude-sonnet-4-5`; `validate_registry` passes (ADR-6). Confirm red
- [X] T020 [US1] Flip `model:` to `zai:glm-5.3` in the 11 files `agents/{analyst,architect,clarify,deep_review,devops_planner,handoff,merge_verdict,planner,qa,research,reviewer}/agent.yaml` (one commit; one `git add` path each). T019 goes green. The rest of the suite may be red until T021 (registry-derived assertions, the wire fixture); the reviewer gate for this task judges T019-green and the 11-file diff, not suite-green
- [X] T021 [US1] Run `pytest`; classify every red test as FLIP or EXTEND per research.md R7 and fix it; record actual-vs-predicted in `.specify/specs/005-native-zai-provider/verification.md`. Then regenerate `tests/durability/fixtures/wire_no_override.json` with the `wire_dump.REGEN_ENV` switch (`pytest -m temporal tests/durability/test_wire_neutrality.py`) and paste the fixture diff into verification.md — only `model_id` values may differ (SG-3)
- [X] T022 [P] [US1] Add the profile pin to `tests/durability/test_zai_route.py`: `zai:glm-5.3` resolves to structured-output mode `tool`, thinking supported, reasoning-effort supported, thinking field `reasoning_content` (research.md R11)
- [X] T023 [US1] RED then GREEN: add to `tests/durability/test_zai_route.py` (temporal tier, modelled on `tests/durability/test_single_retry_layer.py`) an always-429 stub run of one durable registry agent with `ZAI_BASE_URL=<stub>`: observed HTTP calls == that agent's engine attempt budget, and every observed path ends `/chat/completions` under the stub base — this is the durable-path wire evidence (spec A3) and the retry pin (FR-006). Add one always-400 case with the same stub: exactly one request, the provider error surfaces attributed to the agent, no second endpoint is tried (E5, E7)
- [X] T024 [US1] Add `pydantic_ai.providers.zai`, `pydantic_ai.models.zai`, `pydantic_ai.profiles.zai` to `_warm_workflow_side_imports` in `src/sdlc/agents/runner.py` (line 59) and correct its docstring (lines 46-57: registry proposers are no longer all anthropic-prefixed; `anthropic` stays for the claude roles and the rollback override)
- [X] T025 [US1] Run `pytest -m temporal`; record in verification.md: pass count vs T002, the first-workflow-task timing vs T003 (SG-4), and that `tests/durability/test_inflight_resume.py` and the replay tier are green on the flipped registry (SG-2)
- [X] T026 [P] [US1] EXTEND cases from research.md R7: add `zai:glm-5.3` to the accepted ids in `tests/test_proposer_model_validation.py`; add the new literal to the absence guard in `tests/test_memoization_wiring.py` (line 81)

**Checkpoint**: US1 holds offline; both tiers green.

---

## Phase 5: User Story 3 — cost history stays comparable (P3)

**Goal**: post-flip usage is priced on the native row, pinned; the benchmark documentation marks the break.

**Independent test**: `pytest tests/test_price_usage.py`; read `BENCHMARK.md`.

- [X] T027 [P] [US3] Add to `tests/test_price_usage.py`: `zai:glm-5.3` prices at 1.400 per 1M input and 4.400 per 1M output; `anthropic:glm-5.2` and `zai-coding-plan/glm-5.2` still price on the fallback row (1.103 / 3.862). Correct the comment in `src/sdlc/pricing.py` (lines 25-27) and in `src/sdlc/eval/promptfoo/provider.py` (lines 46-47): the fallback now serves harness strings and the rollback override, not the registry proposers
- [X] T028 [US3] Add a dated break marker to `BENCHMARK.md` (2026-10-02 or the landing date): route change `anthropic:glm-5.2` over the Anthropic-compatible endpoint → `zai:glm-5.3` on z.ai's coding endpoint; served model glm-5.2 → glm-5.3; old and new per-1M rates; records before the marker were priced on the old row and answered by the old model; research-stage dollar budgets are reached 14–27% sooner on the same tokens and were not retuned; no benchmark was re-run

---

## Phase 6: Polish and verification

- [X] T029 [P] Comment sweep (FR-013, spec A5; list in research.md R10): `src/sdlc/eval/promptfoo/assertion.py` (lines 72-76), `src/sdlc/agents/loader.py` (line 248 docstring — reword to the post-flip fact), `agents/planner/agent.py` (line 25 — date the observation to the old route), `benchmarks/cases/crew-probe/case.yaml` (lines 31-32), and the COMMENT rows of R7 (`tests/review/test_adversary_registry.py:5-6`, `tests/test_promptfoo_assertion.py:112`, `tests/test_promptfoo_provider.py:94`, `tests/plan/test_planner_agent_retries.py:2`). Comment-only diff
- [X] T030 Live confirmation (FR-015, SC-007; quickstart.md step 6): with the real `ZAI_API_KEY` in `kroker-dev`, no `ZAI_BASE_URL`, no override, run one clarify stage on the flipped registry; record in `.specify/specs/005-native-zai-provider/verification.md` the schema-valid artifact, the endpoint host and path, and the model name the endpoint reported. SG-6 if the key is absent
- [X] T031 Static gates, each as its own command: `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`; then `git diff --stat 0f4ac11 -- pyproject.toml uv.lock src/sdlc/stages/code/step.py src/sdlc/harness/base.py agents/dev agents/test agents/devops` must be empty. Record in verification.md
- [X] T032 Close-out in `.specify/specs/005-native-zai-provider/verification.md`: requirement-by-requirement evidence (plan "Requirement coverage" table), the triage record, the operator note (drain open runs or accept a mixed-route run; first post-flip runs re-pay full proposer cost because memo keys miss once; rollback via `--role-model <role>=anthropic:glm-5.2`), and the follow-ups to hand the orchestrator: ADR-6 observation against OQ-A4 (Q5), claude roles routed through the z.ai Anthropic endpoint (spec A9), registry-snapshot pinning for in-flight runs, research budget retune
- [X] T033 Living docs at close-out (docs-describe-main: after the feature is otherwise complete): update the provider/route statements in `ARCHITECTURE.md` and the C3 status in `ROADMAP.md`; mark tasks complete in this file

---

## Dependencies

- Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6.
- T005 before any test that constructs a zai agent. T008 before T009–T014. T010 depends on T004's inventory.
- T016/T017 (US2) before T020: the commit that flips the registry must already have the key check and the documented variable.
- T020 before T021, T023, T025. T024 before T025.
- T027/T028 after T020. T030 after T025. T033 last.

## Parallel opportunities

- T006 ∥ T007 (two new test files).
- T011 ∥ T012 ∥ T013 after T008 (three different source files, three different test files).
- T015 ∥ T018; T022 ∥ T026. T027 and T029 touch disjoint files and may be done in either order across the Phase 5/6 boundary.

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001, FR-002, FR-003 | T019, T020, T031 |
| FR-004 | T017, T018 |
| FR-005 | T015, T016 |
| FR-006 | T006, T023 |
| FR-007 | T003, T024, T025 |
| FR-008 | T027 |
| FR-009 | T028 |
| FR-010, FR-014 | T031 |
| FR-011 | T005, T021, T026 |
| FR-012 | T021 |
| FR-013 | T008, T010, T024, T027, T029 |
| FR-015 | T030 |
| FR-016 (A1, A2, A3) | T006–T014, T023 |
| E1, E4 (A4) | T025, T032 |
| E2 | T017, T018 |
| E3 | T032 (operator note) |
| E5, E7 | contract C5–C6; T023 shows provider errors propagate |
| E6 | T015 |

## Implementation strategy

MVP is Phases 1–4: the route policy, the key check and the flip. It is deliberately not "US1 alone": flipping without Phase 2 points eleven roles at an endpoint the account cannot use, and flipping without Phase 3 breaks every existing checkout with an opaque import error. Phases 5–6 make the change honest (cost marker, stale prose) and proven (live call).
