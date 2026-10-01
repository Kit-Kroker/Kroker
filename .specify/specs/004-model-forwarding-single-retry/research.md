# Research: 004 Model Forwarding and a Single Retry Layer

All facts below were read from main `b87be66` and the installed packages (`P/` = `.venv/Lib/site-packages/pydantic_ai`, read-only). Nothing was executed. Items marked **to prove** are settled by a named test in Phase A/B, not by reading.

## R1. Forwarding mechanism

- **Decision**: `agent.run(model=<override>)` inside `RoleHost._run_role`, only when the role is overridden with a model that differs from the registry model.
- **Rationale**: `TemporalDurability` documents that model-name strings cross the activity boundary as written and are rebuilt on the worker by the agent's model-id resolution chain, then `infer_model` (`P/durable_exec/temporal/_durability.py:185-198`; worker side `P/durable_exec/_base.py:1796-1822`). The activity name is derived from the agent name, not the model. Not passing `model=` for no-override runs keeps their inputs untouched by construction.
- **Alternatives**: a per-agent resolver carrying the override (the resolver sees only agent and deps; adding deps to 15 agents changes every activity input); `agent.override(model=)` (context-variable, implicit, easy to lose across the clarify `gather`).

## R2. What crosses the wire for a no-override run (to prove)

- The advisor reads the source as: the registry string already crosses as the model id for no-override runs. The skeptic claims it is null and that the worker then uses the agent's construction-time default model (`_resolve_model_for_request` returns `_models_by_id['default']` when the id is None, `_base.py:1807-1808`). The skeptic's quoted history line could not be found; the branch it cites does exist.
- **Why it matters**: if the id is None on the worker, the default model instance was built at agent construction, outside the resolver chain, and would keep SDK retries on.
- **Decision**: do not assume. Phase A dumps the model id of every `model_request` in a no-override run as a fixture; Phase B's always-429 test on a registry-model agent is the behavioural proof. Plan stop-guard SG-1 covers the negative outcome.

## R3. Disabling SDK retries

- **Decision**: one shared `ResolveModelId` capability whose resolver calls `infer_model(id, provider_factory=f)`; `f` calls the framework's `infer_provider(name)` and sets `provider.client.max_retries = 0` when that attribute is an int.
- **Rationale**: `infer_model` accepts `provider_factory` (`P/models/__init__.py:1607`). The provider's own constructor keeps base URL, credentials, timeouts and the `httpx2` client exactly as today (FR-009); `ANTHROPIC_BASE_URL` continues to be read by the SDK. Both SDKs default to 2 retries (`anthropic/_constants.py:10`, `openai/_constants.py:8`) and read `max_retries` from the client at request time (advisor: `anthropic/_base_client.py:430, 832, 1143`; **to prove** by the 429 test).
- **HTTP client generation**: anthropic 1.9.0 and openai 3.22.0 require `httpx2` and reject `httpx` objects (`anthropic/_base_client.py:146`). This design builds no client, so the constraint is met without code. Tests must not mock at the `httpx` layer.
- **Google**: retry is opt-in in the provider (advisor: `P/providers/google.py:114,127`); the attribute guard skips it. Covered by the single-layer provider test.
- **Alternatives**: constructing `AsyncAnthropic(max_retries=0, http_client=...)` ourselves (puts base URL, credentials and timeouts at risk); building `Model` instances in the 14 `agent.py` assets (changes the loader contract 003 just froze, and does not cover override strings).

## R4. Attachment sites

`loader.build_agents` (`loader.py:528-554`, beside the durability capability; the eval path with `durability_factory=None` stays capability-free), the two inline clarify agents (`roles.py`), and the two plain agents constructed in `stages/research/stage.py` (planner `:104`, synthesis `:358`). Lines `:238/:245` are run sites of the registry `research_agent`, not constructions. `research_agent` (sub-question fan-out and architect tool), `t_discover` and `t_risk` are registry agents and are covered by `build_agents`. A coverage test iterates `ALL_TEMPORAL_AGENTS` plus the two plain constructions.

Sub-question forwarding (plan review finding 1, verified): production calls `_research_subquestion_impl(inp)` with no model, so `research_agent` answers with its registry model while `RoleUsage(model=inp.model)` labels the override. Decision D7a: pass `model=inp.model` when it differs from the registry model. This corrects spec V2(b).

## R5. Offline validation

- **Decision**: `parse_model_id` + `infer_provider_class` (public, no instantiation, no credentials, no network). Reject: no provider part, empty name, the literal `test`, unknown provider (`ValueError`), provider whose SDK extra is not installed (`ImportError`). Nothing narrower (Q2); single-layer behaviour of every accepted provider is asserted by a test with stop-guard SG-5.
- **Rationale**: provider constructors need API keys, so "constructible" cannot mean "construct it". The harness grammar (`zai-coding-plan/glm-5.2`) has no `:` and is rejected for proposer roles for free; harness roles (`HARNESS_ROLES = {dev, test, devops}`, `loader.py:47`) are never passed to the check.
- **Registry compatibility**: every proposer role in `agents/` uses `anthropic:<name>`; all pass.
- **Entry paths**: `cli_roles.build_role_overrides`; benchmark `matrix.py` at `arm.resolve()` (before any cell) plus `workflow._cell_config`; graph validation beside `_adr6_problems` (`graph/validate.py:316-358`), because `graph_nodes/base.py:135-137` copies a node's role into the run config.

## R6. Memo invalidation (FR-003)

- **Decision**: narrow salt in the model slot (`fwd1:<model>`) when the model differs from the registry model.
- **Rationale**: only entries written under an override key were produced by the wrong model. Registry-model entries stay valid; no-override `cache_get`/`cache_put` inputs stay identical. `content_key` keeps its five positional arguments (the graph golden test compares them across workflows, per the advisor; to confirm when the test is run).
- **Cost**: research-stage entries under an override, which were correct, are re-keyed once.
- **Alternative**: global version salt. Invalidates every valid entry and changes every memoized run's activity inputs.

## R7. Single decision point and the label guard

`forwarded_model(cfg, role)` in `agents/model_ids.py` is pure over config. `_run_role` trusts it for forwarding and checks the caller's label against it. Known disagreeing call sites: `stages/code/step.py:770` (hardcodes `STAGE_MODELS["review"]`, verified) and the provider-less fallback in `stages/analyze/step.py` (advisor, to confirm at implementation). Deleting the dozen call-site resolutions is a separate refactor.

## R8. Cold provider in a workflow task (E4)

The override string is resolved workflow-side by `Agent.run`. The plugin's sandbox passthrough already includes the provider SDKs (advisor: `P/durable_exec/temporal/__init__.py:116-173`), so the cost is first-import time. `runner.py` warms only `anthropic`. Decision: also warm the openai and google provider modules, failure swallowed as today; measure with the existing first-workflow-task timing test.

## R9. Benchmark record inventory (ruling A3)

Method (read-only; produces `inventory.md` in this directory during Phase A):

| Location | State at spec time |
|---|---|
| `benchmarks/experiments/` + its git history | empty on main; one commit introduced the directory |
| `runs/benchmarks/` in this checkout | absent |
| other machines, container volumes | none exist (operator confirmation, 2026-10-01) |
| benchmark scratch area (`D:\srv`) | holds `scratch-repos/` only at top level; not walked |
| case and arm configs in git history | one case with arms today (`crew-probe`), harness roles only; history not yet walked |
| external stores | none exist (operator confirmation, 2026-10-01) |

**Operator confirmation (2026-10-01, GATE 2, relayed by the orchestrator):** there are no other machines, container volumes or external stores holding benchmark records. This checkout's locations (the first, second, fourth and fifth rows above) are the complete set. The inventory therefore has no open locations to escalate; it still walks the scratch area and the case/arm git history before stating its result.

A record is affected when a proposer role had `--role-model`, an arm `role_models` entry, or an arm `default`. Per record: run id, case, arm, labelled model, registry model that answered. No re-run, no re-label.

Research-only note (ruling C3): `genai-prices` 0.1.9 prices `zai:glm-5.2` 19-23% above `anthropic:glm-5.2`.

## Consult disposition

**Advisor** (`.workspace/tmp/004-advisor-design.md`): D1-D6 adopted. Its spec corrections 1-5 and 8 are folded into the spec (V11-V13, FR-002, FR-004, E4) or this plan.

**Skeptic** (`.workspace/tmp/004-skeptic-spec.md`): the report quotes spec text and code that do not exist (for example a `src/sdlc/cache.py`, an `AssessmentInput` body, a retry policy with intervals). Each finding was re-checked:

| Finding | Check | Disposition |
|---|---|---|
| F-01 `code/step.py:770` hardcodes the reviewer label | true | adopted (V11, D2) |
| F-02 judge runs in an activity with 5 attempts | true | out of ruled scope; GATE 2 risk 2 |
| F-03 research budget of 6 | true (`research/step.py:63`) | adopted (V13) |
| F-04 forward only under an override | agrees with D1; its "null model id" evidence unverified | R2, SG-1 |
| F-05 assessment has no pipeline config | consistent with Q1 as ruled (no override surface) | D8; its proposed `AssessmentConfig.roles` rejected, contradicts Q1 |
| F-06 validate without constructing | true | R5 |
| F-07 harness grammar collision | already FR-005 | none |
| F-08 retune budget/backoff | contradicts ruling Q3 | not adopted; GATE 2 risk 1 |
| F-09 stale memo entries | already FR-003/E3; proposed global version salt | R6 chooses the narrow salt |
| F-10 `code/step.py` at 991 lines | true | constraint, SG-4 |
| F-11 warm other providers | true | D9 |
