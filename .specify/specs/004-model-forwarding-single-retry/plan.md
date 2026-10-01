# Implementation Plan: Model Forwarding and a Single Retry Layer

**Branch**: none (spec directory `004-model-forwarding-single-retry`) | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Status**: GATE 2 cleared 2026-10-01

**Input**: approved spec (GATE 1: Q1 scope as recommended, Q2 offline `provider:model` check, Q3 accept the bound, no budget/backoff retune). Design inputs: advisor answer `.workspace/tmp/004-advisor-design.md`, skeptic report `.workspace/tmp/004-skeptic-spec.md`; every adopted claim was re-read in code (see [research.md](research.md), "Consult disposition").

## Summary

Two defects, one seam. (6.1) `RoleHost._run_role` forwards the per-run override to the call as `agent.run(model=<override>)`, **only when the run overrides that role with a model different from the registry model**, and fails loudly if the caller's label disagrees with what is forwarded. Proposer overrides are validated offline (`provider:model`, known provider class) on three entry paths: CLI, benchmark arm expansion, graph-node roles. (6.4) One shared model-id resolver capability, attached to every proposer agent, builds the provider through the framework's normal constructor and sets the SDK client's retry count to 0, so the workflow engine's attempt budget is the only retry layer. No custom HTTP client is built. Override memo keys are re-keyed so results the registry model produced under an override key are never served. A benchmark-record inventory is produced as research output.

## Technical Context

**Language/Version**: Python 3.13 (dev container and image; the host venv is not a verification environment)

**Primary Dependencies** (uv.lock): `pydantic-ai-slim` 2.51.0 (`[anthropic,openai,google,temporal]`), `anthropic` 1.9.0, `openai` 3.22.0, `httpx2` 2.13.1, `temporalio`, `genai-prices` 0.1.9. No dependency change.

**Storage**: N/A. The memoization cache is a local directory; no migration, stale entries become unreachable.

**Testing**: pytest tiers per `pyproject.toml`: fast default, `-m temporal` opt-in. Ruff, mypy (scoped to `src/`), `scripts/check_file_size.py`. One pytest per command.

**Target Platform**: Linux container (worker image = dev container base).

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: no workflow task trips the 2 s deadlock detector (TMPRL1101) more often than today, including the first task of a run whose override names a non-anthropic provider.

**Constraints**:
- Runs with no override: scheduled activity names, order and inputs unchanged; all captured histories and goldens replay with no fixture edit (FR-010).
- No attempt budget or backoff value changes (Q3).
- 1000 lines per file. `src/sdlc/stages/code/step.py` is at 991: its edit must be net-zero or negative.
- `core/` must not import provider SDKs; envelope models keep their current `extra` policy.
- No cross-stage calls; stages may import from `sdlc.agents`.
- Read the nearest `AGENTS.md` before editing: `src/sdlc/workflows/`, `src/sdlc/stages/{code,research,architecture}/`.
- All runs in `kroker-dev`.

**Scale/Scope**: 16 durable agents + 2 plain research-stage agents (planner, synthesis); 1 new module; 15 source files; ~8 test files; 3 entry paths.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/004-model-forwarding-single-retry/
├── spec.md
├── plan.md                 # this file
├── research.md             # R1-R9 decisions, consult disposition, benchmark inventory method
├── data-model.md
├── quickstart.md           # dev-container validation runbook
├── contracts/
│   ├── model-resolution-contract.md
│   └── proposer-override-validation.md
├── checklists/
└── tasks.md                # /speckit-tasks
```

### Source code touched

```text
src/sdlc/agents/model_ids.py        # NEW: validate_proposer_model, single_retry_layer(), forwarded_model
src/sdlc/agents/loader.py           # build_agents attaches the resolver capability beside durability
src/sdlc/agents/roles.py            # the two clarify fan-out agents get the capability
src/sdlc/agents/runner.py           # warm openai + google provider modules (E4)
src/sdlc/workflows/role_host.py     # _run_role forwards + guards; _cached_stage narrow salt
src/sdlc/stages/code/step.py        # line 770: resolve the reviewer label (net-zero lines)
src/sdlc/stages/analyze/step.py     # label fallback must not be provider-less under an override
src/sdlc/stages/research/stage.py   # planner + synthesis agents get the capability; sub-question run forwards inp.model
src/sdlc/stages/research/deps.py    # research_model (excluded when None)
src/sdlc/stages/research/toolset.py # nested t_research.run forwards deps.research_model
src/sdlc/stages/architecture/step.py# populate research_model only under an override
src/sdlc/cli_roles.py               # validate proposer overrides
src/sdlc/benchmarks/matrix.py       # validate at expansion (before any cell)
src/sdlc/benchmarks/workflow.py     # same check per cell (backstop)
src/sdlc/graph/validate.py          # new problem code for a bad proposer model on a node
interfaces/ (generated)             # only if the new problem code reaches the UI type fixtures: regenerate, gate with scripts/check_ui.py
tests/fakes/fake_agents.py          # recording resolver, TestModel(model_name=id)
tests/durability/                   # single-layer capability coverage, 429 stub tests, wire-neutrality
tests/test_role_model_resolution.py, tests/test_cli_role_model.py, tests/test_benchmark_arms.py  # valid ids
ARCHITECTURE.md                     # agents/durability section, role-model override (E-37) text, retry description
BENCHMARK.md                        # "Model x role" axis row and the --role-model paragraph: proposer arms now real; pre-004 records caveat
README.md                           # --role-model usage: accepted proposer form provider:model
src/sdlc/workflows/AGENTS.md        # _run_role forwards + guards (single egress clause)
src/sdlc/stages/research/AGENTS.md  # sub-question forwarding, research_model on deps, single retry layer
src/sdlc/stages/code/AGENTS.md      # reviewer label resolved per run
```

**Structure Decision**: one new module `src/sdlc/agents/model_ids.py`. `agents/` already owns `model_family`, ADR-6 checks and the registry, is importable from stages, CLI, benchmarks and graph validation, and is a sandbox passthrough (`runner.py`). Provider imports stay lazy inside functions so the eval path and CLI startup do not pay for them.

## Design decisions (detail and evidence in research.md)

| # | Decision | Requirement |
|---|---|---|
| D1 | Forward with `agent.run(model=override)` in `_run_role`, only when `forwarded_model(cfg, role)` is not None (override present and different from the registry model). No-override and override-equals-registry calls are made exactly as today. | FR-001, FR-010, E1 |
| D2 | `forwarded_model` is the one decision point. `_run_role` raises a non-retryable error if the caller's `model` label differs from it under an override, or if a caller passes its own `model=` kwarg. Call-site resolutions are not deleted in this feature. | FR-002, V11 |
| D3 | Retries off through one shared model-id resolver capability: `infer_model(id, provider_factory=...)` where the factory builds the provider normally and sets `client.max_retries = 0` when the client has that attribute. Attached in `build_agents` (the registry agents, which include `research_agent` used by the sub-question fan-out), on the 2 inline clarify agents, and on the 2 plain agents constructed in `stages/research/stage.py` (planner `:104`, synthesis `:358`). | FR-007, FR-009 |
| D4 | Validation accepts exactly what Q2 rules: any provider the installed framework can construct. A parametrized test enumerates every such provider and asserts its client runs single-layer (retry count 0, or retries opt-in). A provider that fails the assertion is stop-guard SG-5 (escalate), not a validation rule. | FR-004, FR-007, Q2 |
| D5 | Validation `validate_proposer_model(role, value)`: `provider:model` with non-empty parts, provider class resolvable without instantiation, `test` rejected. Proposer-kind roles only. Called from `cli_roles.build_role_overrides`, benchmark matrix expansion and `_cell_config`, and graph validation. | FR-004, FR-005 |
| D6 | Memo: in `_cached_stage`, the model slot of the key becomes `fwd1:<model>` when the run's model differs from the registry model. `content_key`'s signature is unchanged. | FR-003, E3 |
| D7a | Research sub-question fan-out (`stage.py:238-248`): the production branch passes `model=inp.model` when it differs from the registry `research` model, else calls as today. `inp.model` is already an activity input, so nothing changes on the wire; the usage label (`stage.py:233`) then matches the model that answered. | FR-001 (path b) |
| D7 | Architect research tool: `ResearchDeps.research_model`, serialized only when set, populated only under a `research` override; the tool passes it as `model=`. | FR-001 (path c) |
| D8 | Assessment `discover`/`risk`: no override input exists, so they keep the registry model and gain only D3 via `build_agents`. | Q1 (path a) |
| D9 | Worker warm-up imports the `openai` and `google` provider modules as well as `anthropic`. | E4 |
| D10 | No attempt budget, backoff or timeout value is edited. Non-retryable provider errors keep failing on the first attempt: D3 changes only the SDK retry count and the engine policy is untouched. Phase B adds one test with a 400-returning stub asserting exactly 1 request. | Q3, FR-011, E7 |

### Wire statement (FR-010)

- No override: nothing changes on the wire. `model=` is not passed; deps serialize identically (`research_model` omitted when None); memo keys identical.
- Override run: `model_request` activity input carries the override string as its model id; for the architect with a `research` override, deps gain `research_model`; memo `cache_get`/`cache_put` keys differ. Activity names and order do not change.
- Attaching the resolver capability must not change any scheduled activity name or input. This is a claim to prove (R2), not assume.

## Phases and stop-guards

**Phase A, baseline on unmodified main (no source edits).** Record: fast-tier and `-m temporal` pass counts; the 429 stub test written against main showing the stacked count (expected 9 for a 3-attempt agent); a wire fixture of scheduled activity names and `model_request` model ids for a no-override run; first-workflow-task timing. Produce the benchmark inventory (R9).

**Phase B, single retry layer (US3).** Module + capability, attach at all sites, coverage test over `ALL_TEMPORAL_AGENTS` and the two plain research-stage agents, 429, fail-once and 400 tests, single-layer provider test. **Stop-guard SG-1**: if the always-429 count for a registry-model agent stays above the budget after the capability is attached (i.e. the default model is not rebuilt through the resolver chain), stop and escalate with the measured count; do not improvise a second mechanism. **Stop-guard SG-5**: if the single-layer provider test finds a constructible provider that does not run single-layer, stop and escalate (Q2 does not allow narrowing validation). **Stop-guard SG-2**: any replay or golden failure, or a changed wire fixture for a no-override run, stops the run.

**Phase C, validation (US2).** `validate_proposer_model`, three entry paths, updated tests.

**Phase D, forwarding (US1).** Recording fake, `forwarded_model`, `_run_role` forward + guard, `code/step.py:770`, analyze fallback, research deps path, memo salt, warm-up. **Stop-guard SG-3**: if the guard fires in any existing no-override test, the role-name mapping assumption is wrong; stop and report the call site. **Stop-guard SG-4**: `scripts/check_file_size.py` failure on `code/step.py` is not solved by a waiver.

**Phase E, docs and close-out.** The six docs listed under "Source code touched", each in the same commit as the behaviour it describes; full verification per quickstart.

Order rationale: B before D so that when overrides start reaching new providers they already run single-layer; C before D so an invalid string can never reach a real call.

## Risks carried to GATE 2

GATE 2 rulings (2026-10-01, user, relayed by the orchestrator): risk 1 is accepted, Q3 stands with no attempt-budget or backoff change, and the retune request stays an inbox task (tasks T037). Risk 2 stays out of scope; the inbox task stands (T037). The benchmark inventory's location set is complete as this checkout (research.md R9). Risks 3 and 4 remain open and are covered by stop-guards SG-1 and SG-3.


1. **Resilience (accepted by Q3, restated with evidence).** After this feature a rate-limit burst longer than the engine's backoff span exhausts a 3-attempt call in seconds. Existing fail-open paths are reached sooner: the clarify fan-out degrades a dead probe to "asked nothing", and the adversary lens returns no verdict on any exception (`stages/review/step.py:243`). Behaviour is unchanged in kind (FR-011), more likely in frequency. The skeptic asked for a retune; Q3 forbids it here. Recommendation: file an inbox task to tune from evidence.
2. **Benchmark judge retries** (V13): 5 attempts x 3 SDK calls today, outside the ruled scope (not a proposer role). Recommendation: inbox task; the capability factory is reusable there.
3. **SG-1 unknown**: whether the registry-default model is resolved through the capability chain on the worker. Proven or refuted by the first Phase B test.
4. **Role-name mapping** between `_run_role`'s `role` argument and `cfg.roles` keys is verified for three call sites only; FR-006 tests and SG-3 cover the rest.

## Complexity Tracking

None.
