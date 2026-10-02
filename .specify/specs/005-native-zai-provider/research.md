# Research: Native zai Provider (005)

Probes ran read-only in `kroker-baseline` (main `0f4ac11`, pydantic-ai-slim 2.51.0, openai 3.22.0, genai-prices 0.1.9) on 2026-10-02. Live endpoint probes were run by the orchestrator, not by the plan author (spec V13).

## R1. Where the base-URL policy lives

- **Decision**: one provider factory in `src/sdlc/agents/model_ids.py` with a `single_retry` flag; `single_retry_layer()` uses it with the flag on; `resolve_model()` / `route_layer()` use it with the flag off.
- **Rationale**: the policy and the retry knob are both "what we do to a provider after the framework builds it". One function means one place to pin. The flag keeps the URL fix from changing retry behaviour at sites that never zeroed retries (004 Q3; judge retries is a named 004 follow-up).
- **Alternatives**: attach a resolver everywhere and no helper (does not fit sites that build outside the loader); a process-global patch of provider inference (invisible, leaks into tests, cannot be pinned per site).

## R2. How the zai provider gets its base URL

- **Decision**: after `infer_provider("zai")`, assign `provider.client.base_url`.
- **Probe**: assignment yields `https://api.z.ai/api/coding/paas/v4/` (slash normalised); `infer_model("zai:glm-5.3", provider_factory=…)` returns a `ZaiModel` whose client **is** the provider's client and whose `base_url` reports the new value. `ZaiProvider.base_url` (a property) still reports the built-in default — nothing reads it after construction; pin tests read the client and the wire.
- **Rationale**: same move 004 makes for `max_retries`; keeps the provider's key lookup and its missing-key error; builds no HTTP client.
- **Fallbacks, in order**: subclass overriding the `base_url` property (depends on constructor ordering in 2.51.0); construct the OpenAI client ourselves and pass `openai_client=` (public, but re-implements key lookup and the error text).
- `ZaiProvider.__init__` has no base-URL parameter and reads no base-URL environment variable (source read).

## R3. Construction sites

`grep` for `Agent(`, `infer_model`, `infer_provider`, `single_retry_layer(` over `src/`, `agents/`, `scripts/`. Result is the table in plan.md D2. Notes:

- `Agent.__init__` infers the model eagerly from a string **unless** a model-id resolver capability is present. So sites 1, 3, 4 do not need the key at import; sites 2, 5, 6, 7 construct a provider when built. Probe: `Agent("zai:glm-5.3")` with no key raises the provider's `UserError` at construction.
- `build_agents` is called from `src/` only with a durability factory (`roles.py:100`); the non-durable branch is reached by tests and loader-only consumers. `eval/runner.py:40` calls the role's `build(model, instructions, MODEL_SETTINGS)` directly with `fixture.model` (a string) or an injected test model.
- The benchmark judge default is a google model; the operator chat reads its own `agent.yaml`. Both accept any string, so both are sites.
- The 14 `agents/<role>/agent.py` files call `Agent(model, …)` with what the loader/eval runner hands them; they are covered through their callers and allow-listed in the guard.

## R4. Warm-up

- **Probe** (fresh process, outside the sandbox): `infer_model("zai:glm-5.2")` 0.8–1.1 s with nothing warm; **0.13 s** with `anthropic`, `openai`, `google.genai` already imported. Modules loaded by zai resolution: `pydantic_ai.providers.zai`, `pydantic_ai.models.zai`, `pydantic_ai.profiles.zai`.
- **Decision**: add those three to `_warm_workflow_side_imports`. zai is now the common path for 11 roles; a host-side import is free; the in-sandbox cost is unmeasured.
- **Still required**: `tests/durability/test_first_workflow_task_time.py` on the flipped registry (FR-007).

## R5. Doctor

`doctor/checks.py:246` `_FAMILY_KEYS` has no `zai`; `check_provider_keys` would list it as unmapped and not check the key. Add the entry. `anthropic` stays required while adversary/discover/risk exist (spec E6). A doctor note for a known-wrong `ZAI_BASE_URL` was considered and dropped (Q3-C style warnings were declined at GATE 1).

`doctor/env.py:11-13` cites `.env.example` line numbers (`:8`, `:11`, `:25`); adding lines to `.env.example` shifts them — correct in the same change.

## R6. Environment and harness credential

`provider_env()` forwards only `ANTHROPIC_*`; opencode harness roles authenticate from the mounted `auth.json` (`docker-compose.yml:61-64`). No `ZAI_*` variable exists in the repo today, so `ZAI_API_KEY` is new and serves proposers only. `provider_env` is not widened.

## R7. Test triage manifest

66 occurrences of `anthropic:glm-5.2` in 30 files. Rule: after the registry flip, a test that goes red is FLIP or EXTEND; a green test stays. Predicted:

| Disposition | Files | Why |
|---|---|---|
| **FLIP** (asserts the shipped registry) | `tests/test_agents_registry.py:117`; `tests/durability/fixtures/wire_no_override.json` (regen, R8); possibly `tests/test_eval_fixture_build.py:47` and `tests/test_benchmark_arms.py` if they resolve from the real registry — confirm by running | value comes from `agents/` |
| **EXTEND** (valid as-is, add a zai case) | `tests/test_price_usage.py`, `tests/test_promptfoo_provider.py` (fallback pricing still serves harness strings), `tests/doctor/test_doctor_checks_runtime.py`, `tests/test_proposer_model_validation.py`, `tests/test_memoization_wiring.py:81` (literal-absence guard: add the new literal) | old path still real; new path unpinned |
| **STAY** (arbitrary valid id in a synthetic registry, or deliberately the Anthropic path) | `tests/conftest.py` yaml literals, `tests/graph/fixtures/registries.py`, `tests/durability/test_loader_*.py`, `tests/durability/fixture_agents/*`, `tests/durability/test_single_retry_coverage.py`, `tests/research/*`, `tests/review/test_review_models.py`, `tests/review/test_adversary_registry.py` (cases), `tests/clarify/test_clarify_memo_key.py`, `tests/docs_site/test_agent_registry.py`, `tests/test_benchmark_judge.py`, `tests/test_staged_judge.py`, `tests/test_eval_*.py`, `tests/test_promptfoo_assertion.py` (cases) | the string is a placeholder or the subject |
| **COMMENT** (prose names the old route as current) | `tests/review/test_adversary_registry.py:5-6`, `tests/test_promptfoo_assertion.py:112`, `tests/test_promptfoo_provider.py:94`, `tests/plan/test_planner_agent_retries.py:2` | date or correct the sentence |

Captured eval fixtures stay as recorded: a fixture is a recording of what a model said, and that model was glm-5.2 on the Anthropic route. New captures are `zai:glm-5.3`.

`tests/conftest.py` adds a dummy `ZAI_API_KEY`. The skeptic's "run with `ANTHROPIC_API_KEY` unset" check is not adopted: three registry roles still need it.

## R8. Wire fixture

`tests/durability/test_wire_neutrality.py` loads the frozen fixture and regenerates only under `wire_dump.REGEN_ENV=1`. Six `model_id` values change. Regenerate once, commit with the diff shown in the verification record; any non-`model_id` difference is a stop-and-report.

## R9. In-flight runs

`resolve_role_model` reads the worker's registry at execution time; the model string is not pinned into workflow state. So after an upgrade, an open run's remaining stages use `zai:glm-5.3`; completed stages replay from history. A run that explicitly set a role to `anthropic:glm-5.2` (previously equal to the registry, so not forwarded) is now a real forwarded override and keeps the old route — correct behaviour. The engine matches replayed commands by type and id, not input, so a changed cache-key argument is not expected to raise non-determinism; this is confirmed by running the in-flight and replay tests rather than assumed. Pinning the registry snapshot into workflow state is a separate feature.

## R10. Cost, markers, stale prose

- genai-prices 0.1.9 (probe): `anthropic:glm-5.2` → misses under `anthropic`, falls back to `zhipuai` row: 1.103 in / 3.862 out per 1M. `zai:glm-5.2` → `zai` row: 1.400 / 4.400. `zai:glm-5.3` same as `zai:glm-5.2` (orchestrator probe; re-pinned by a test here). `zai-coding-plan/glm-5.2` still falls back to `zhipuai`.
- Budgets: `run_budget_usd` defaults to 0 (off). Research budgets (`max_cost_usd` 1.0 per sub-question, `max_run_cost_usd` 4.0) are reached 14–27% sooner on the same tokens. Not retuned; stated in the break marker.
- Comment sweep (FR-013/A5): `pricing.py:25-27`; `eval/promptfoo/provider.py:46-47`; `eval/promptfoo/assertion.py:72-76`; `agents/loader.py:89-96` (examples — fine as examples, leave), `:248` (dev/reviewer "same glm-5.2 behind different providers" — false after the flip: reviewer is `zai:glm-5.3`; reword to the post-flip fact, same vendor behind two prefixes, model ids now differ by string), `:537-539`; `agents/runner.py:50-52`; `agents/model_ids.py` module and `single_retry_layer` docstrings; `agents/planner/agent.py:25` (date it: the observation was made on the old route); `benchmarks/cases/crew-probe/case.yaml:31-32`; `.env.example:5-6`.

## R11. Live confirmation

Profile probe: `zai:glm-5.3` → structured output mode `tool`, thinking supported and **always enabled**, reasoning-effort supported, thinking field `reasoning_content`, context window 1,000,000. Repo sets only `max_tokens` (64000) in shared settings — no thinking/effort settings to carry over. "Always enabled" thinking plus the protocol change is why one live schema-valid stage is required (FR-015), with the endpoint-reported model name recorded.

## R12. No dependency change

`pydantic-ai-slim` metadata: `zai` extra = `openai>=3.19.0`; installed `openai` extra = that plus `tiktoken`. Nothing to add.

## Consult disposition

| Source | Claim | Disposition |
|---|---|---|
| Advisor D1 | one factory, `single_retry` flag | Adopted (R1) |
| Advisor D2 | set `client.base_url` after construction | Adopted; probe-verified (R2) |
| Advisor D3 | all sites honour URL policy; guard test | Adopted (plan D2) |
| Advisor D4 | warm zai modules | Adopted; module names verified (R4) |
| Advisor D5 | fixtures are history | Adopted (R7) |
| Advisor M1/M2 | wire-level URL test, incl. durable path | Adopted (spec A3) |
| Advisor M3 | `ZAI_BASE_URL` not in history | Adopted as documented behaviour (spec A4) |
| Advisor M4 | key-name collision with harness | Checked: none (R6) |
| Advisor M5 | eager construction needs key | Verified (R3) |
| Advisor M6 | doctor note for wrong override | Not adopted (R5) |
| Advisor M9 | extra stale comments | Adopted (R10) |
| Skeptic 1 | glm-5.3 loses reasoning effort | **Rejected — false** (R11 probe). Profile pin test adopted. Endpoint drift → record served model |
| Skeptic 2 | bare sites hit the default endpoint | Adopted (same as Advisor D3) |
| Skeptic 3 | `ANTHROPIC_*` cannot serve both claude roles and CLIs | Pre-existing; Q3 ruled; reported as spec A9. No doctor conflict check (declined class of warning) |
| Skeptic 4 | budget ceilings +20%, eval cost audit | Not adopted as retune; effect documented (R10). No promptfoo cost threshold found in `eval/promptfoo/` |
| Skeptic 5 | dummy key, manifest | Adopted. "Unset Anthropic key" run rejected (R7) |
| Skeptic 6 | replay non-determinism; pin registry in state | NDE claim not supported; tested instead of assumed (R9). Snapshot pinning out of scope |
