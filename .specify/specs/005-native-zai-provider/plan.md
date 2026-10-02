# Implementation Plan: Native zai Provider for the glm Proposer Roles

**Branch**: none (spec directory `005-native-zai-provider`) | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

**Status**: Reviewer-validated 2026-10-02 (`.workspace/tmp/005-reviewer-plan.md`: fixes-needed F1/F2 applied with F3–F6, F8; reviewer waived re-review). Awaiting GATE 2

**Input**: approved spec (GATE 1: Q1 flip all 11; Q2/Q2b coding endpoint, `zai:glm-5.3`, `ZAI_BASE_URL` optional; Q3 keep `ANTHROPIC_*`; Q4 native price row, break marker, no re-runs; Q5 no ADR-6 change). Design inputs: advisor `.workspace/tmp/advisor-005-1.md`, skeptic `.workspace/tmp/skeptic-005-1.md`; every adopted claim re-checked (see [research.md](research.md), "Consult disposition").

## Summary

Flip 11 registry roles from `anthropic:glm-5.2` (served over `ANTHROPIC_BASE_URL`) to `zai:glm-5.3`. Because the provider's built-in endpoint is not covered by the subscription, the 004 seam in `src/sdlc/agents/model_ids.py` grows one provider factory that applies a base-URL policy to the `zai` provider (coding endpoint by default, `ZAI_BASE_URL` override) and, where it already did, zeroes SDK retries. Every site that can turn a `zai:` string into a model goes through that factory: the four that already carry `single_retry_layer()` inherit it; the three bare sites (non-durable loader path + eval runner, benchmark judge, operator chat) are routed through a URL-only helper that leaves their retry behaviour alone. Doctor learns the `zai` family, host warm-up gains the zai modules, tests get a dummy key and a by-failure triage, the wire fixture is regenerated once, and `BENCHMARK.md` gets a dated break marker for route + model + price.

## Technical Context

**Language/Version**: Python 3.13 (dev container and image; the host venv is not a verification environment)

**Primary Dependencies** (uv.lock, unchanged): `pydantic-ai-slim` 2.51.0 (`[anthropic,openai,google,temporal]` — the `zai` extra adds nothing beyond `openai`), `openai` 3.22.0, `anthropic` 1.9.0, `httpx2`, `temporalio`, `genai-prices` 0.1.9.

**Storage**: N/A. The memoization cache misses once for the 11 roles; no migration.

**Testing**: pytest tiers per `pyproject.toml`: fast default, `-m temporal` opt-in. Ruff, mypy (scoped to `src/`), `scripts/check_file_size.py`. One pytest invocation per command; do not add `-q` (already in `addopts`).

**Target Platform**: Linux container (worker image = dev container base).

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: no workflow task trips the 2 s deadlock detector (TMPRL1101) on the flipped registry, including the first task after worker start (`tests/durability/test_first_workflow_task_time.py`).

**Constraints**:
- No retry-policy edits (004 Q3): no attempt budget or backoff value changes; sites that did not zero SDK retries before still do not.
- No dependency change (FR-010). If one appears necessary: stop and report.
- Harness roles and `zai-coding-plan/*` strings untouched; `harness/base.py:provider_env` not widened.
- `src/sdlc/stages/code/step.py` (991/1000) is not edited.
- `model_ids.py` keeps provider imports lazy (it is imported by workflow code and passed through the sandbox).
- `ZAI_BASE_URL` is read at call time inside the factory, never at import; empty/whitespace = unset.
- Read the nearest `AGENTS.md` before editing `src/sdlc/agents/`, `src/sdlc/eval/`, `src/sdlc/benchmarks/`, `src/sdlc/operator/`, `src/sdlc/doctor/`.
- All runs in `kroker-dev`. Commits: `git commit -F <msgfile>`, one path per `git add`, no attribution trailers.
- Base: main `0f4ac11`.

**Scale/Scope**: 11 registry yaml files; 1 seam module; 5 other source files with code edits; ~6 source/case files with comment-only edits; ~4 new test modules; an estimated 5–10 existing test files changed by triage; 1 fixture regen; 3 doc files.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/005-native-zai-provider/
├── spec.md
├── plan.md                 # this file
├── research.md             # R1-R12 decisions, probes, consult disposition, test-triage manifest
├── data-model.md
├── quickstart.md           # dev-container validation runbook
├── contracts/
│   └── zai-route-contract.md
├── checklists/
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
agents/<role>/agent.yaml            # 11 files: model -> zai:glm-5.3
agents/planner/agent.py             # comment only (FR-013)
src/sdlc/agents/model_ids.py        # provider factory + base-URL policy + URL-only helpers
src/sdlc/agents/loader.py           # non-durable path attaches the URL-only resolver; comments
src/sdlc/agents/runner.py           # warm-up list + docstring
src/sdlc/eval/runner.py             # string model -> shared helper
src/sdlc/benchmarks/judge.py        # string model -> shared helper
src/sdlc/operator/agent.py          # string model -> shared helper
src/sdlc/doctor/checks.py           # _FAMILY_KEYS: zai
src/sdlc/doctor/env.py              # docstring line references into .env.example
src/sdlc/pricing.py                 # comment only
src/sdlc/eval/promptfoo/{provider,assertion}.py   # comments only
benchmarks/cases/crew-probe/case.yaml             # comment only
.env.example  README.md  BENCHMARK.md
tests/conftest.py                   # dummy ZAI_API_KEY
tests/durability/test_zai_route.py              # new: policy + wire URL per site, retry pin
tests/test_model_construction_sites.py          # new: regression guard (A2)
tests/test_price_usage.py  tests/doctor/test_doctor_checks_runtime.py   # extended
tests/durability/fixtures/wire_no_override.json # regenerated once
```

**Structure Decision**: no new package. The policy lives beside the 004 seam because it is the same decision point ("how a proposer model string becomes a model"); splitting it would recreate the multi-site problem FR-016 exists to close.

## Design

Details and rejected alternatives are in [research.md](research.md); the behavioural contract is [contracts/zai-route-contract.md](contracts/zai-route-contract.md).

### D1. One provider factory (R1, R2)

`model_ids.py` gains:

- `ZAI_CODING_BASE_URL` constant and `zai_base_url()` — returns `ZAI_BASE_URL` if set and non-blank, else the constant. Reads the environment at call time.
- `_provider_for(name, *, single_retry)` — `infer_provider(name)`; if `name == "zai"`, set `provider.client.base_url = zai_base_url()` (the SDK client's own setter; probe-verified to normalise the trailing slash and to be the client the model uses); if `single_retry`, the existing `max_retries = 0` logic.
- `resolve_model(model_id)` — `infer_model(model_id, provider_factory=<_provider_for, single_retry=False>)`. For sites that hold a string and want a model.
- `route_layer()` — a `ResolveModelId` capability over `resolve_model`. For sites that pass a string to `Agent(...)` through a build function.
- `single_retry_layer()` — unchanged contract; its factory becomes `_provider_for(name, single_retry=True)`.

No HTTP client is built; key lookup and the missing-key error stay the provider's own.

### D2. Construction sites (R3) — the FR-016 enumeration

| # | Site | Today | Change |
|---|---|---|---|
| 1 | `agents/loader.py` durable path (14 registry agents) | `[dur, single_retry_layer()]` | none (inherits D1) |
| 2 | `agents/loader.py` non-durable path | no capability → eager default provider | attach `[route_layer()]` |
| 3 | `agents/roles.py` clarify route/probe agents | `single_retry_layer()` | none |
| 4 | `stages/research/stage.py` planner/synthesis agents | `single_retry_layer()` | none |
| 5 | `eval/runner.py` (`build(model, …)`, promptfoo/calibration path) | bare string | string → `resolve_model`; an injected test model passes through |
| 6 | `benchmarks/judge.py` `_run_judge_agent` | bare string | string → `resolve_model` |
| 7 | `operator/agent.py` `build_agent` | bare string | string → `resolve_model` |

Sites 5–7 keep SDK-default retries (no retry-policy edit). A guard test (`tests/test_model_construction_sites.py`) scans `src/sdlc` and `agents/` for `Agent(` / `infer_model(` / `infer_provider(` call sites and fails on any not in an allow-list that names these seven, the 14 `agents/<role>/agent.py` build functions (which only receive what sites 1, 2 and 5 hand them), and `model_ids.py` itself.

### D3. Registry flip and credentials (R5, R6)

11 yaml edits. `tests/conftest.py` sets a dummy `ZAI_API_KEY` beside the existing dummies. `doctor/checks.py` `_FAMILY_KEYS` gains `"zai": "ZAI_API_KEY"`. `.env.example` adds a z.ai-native block (`ZAI_API_KEY` placeholder, commented `ZAI_BASE_URL` with the default, and the E2 warning: on the coding endpoint a `zai:glm-5.2` request is answered by glm-5.3, so name the model you mean) and re-describes the Anthropic block per Q3; `doctor/env.py`'s docstring line references into `.env.example` are corrected to the new line numbers. `README.md` Develop section lists the key and repeats the E2 warning beside the `--role-model` text.

### D4. Warm-up (R4)

`_warm_workflow_side_imports` adds `pydantic_ai.providers.zai`, `pydantic_ai.models.zai`, `pydantic_ai.profiles.zai` (names probe-verified). Docstring corrected. `anthropic` stays (claude roles, rollback override). Evidence: `test_first_workflow_task_time.py` on the flipped registry.

### D5. Tests (R7, R8)

Triage by failure, not by grep: flip the registry, run the default tier, and every red test is classified FLIP (asserts the shipped registry value) or EXTEND (still valid, add a zai case); green tests stay. The pre-computed manifest in research.md predicts the result; divergence from it is recorded. Wire fixture: regenerate with the existing `wire_dump` regen switch and show the diff touches only `model_id` values.

New tests: policy unit tests (default, override, blank override, non-zai providers untouched, `max_retries` 0 only on the single-retry path); stub-server tests capturing the request path for each site category and under `ZAI_BASE_URL` pointed at the stub (the existing `_http_stub` already serves the OpenAI protocol shape); always-failing stub on a durable agent → calls == engine attempt budget (FR-006); profile pin for `zai:glm-5.3`; price pin (1.400 / 4.400 per 1M).

### D6. In-flight runs (R9)

No code. Evidence: `tests/durability/test_inflight_resume.py` and the replay tier pass on the flipped registry. Operator note in the verification record and README: drain open runs before upgrading, or accept that remaining stages run on the new route/model. A red in-flight or replay test on the flipped registry is stop-and-report, not a test adjustment: the remedy (pinning the registry snapshot into workflow state) is outside this feature.

### D7. Cost and docs (R10)

`pricing.py` logic unchanged (hinted hit on the `zai` row). `BENCHMARK.md`: dated break marker (route, served model 5.2 → 5.3, both rates, research-budget effect, no re-runs). Stale comments per FR-013/A5. `ARCHITECTURE.md`/`ROADMAP.md` at close-out only.

### D8. Live confirmation (R11)

One real proposer stage on the flipped registry in `kroker-dev` with the real key: schema-valid artifact, request seen on the coding endpoint, reported model name recorded. Needs `ZAI_API_KEY` in the container's `.env` — a prerequisite the orchestrator/user supplies; the task stops and reports if it is absent rather than substituting a stub.

## Requirement coverage

| Requirement | Design | Evidence |
|---|---|---|
| FR-001, FR-002, FR-003 | D3 | registry test asserts all 11 = `zai:glm-5.3`, 3 harness and 3 claude strings unchanged |
| FR-004 | D3 | `.env.example`, README diff |
| FR-005 | D3 | doctor tests: absent / placeholder / set |
| FR-006 | D1, D5 | always-failing stub: calls == budget |
| FR-007 | D4 | first-workflow-task-time test, temporal tier |
| FR-008 | D7, D5 | price pin test; comment diffs |
| FR-009 | D7 | `BENCHMARK.md` diff |
| FR-010 | — | `git diff` shows no `pyproject.toml`/`uv.lock` change |
| FR-011 | D5 | triage record vs manifest; default tier green with dummy keys |
| FR-012 | D5 | fixture diff limited to `model_id` |
| FR-013 | D7 | comment sweep list in research.md R10 |
| FR-014 | — | `code/step.py` absent from the diff |
| FR-015 | D8 | verification record |
| FR-016 | D1, D2 | per-site wire-URL tests + guard test |

## Risks

- **Served model drifts again** on the coding endpoint. Mitigation: D8 records the reported model; no runtime check added (would be a new feature).
- **Tests asserting capability-free loader agents** may exist; D2 site 2 reverses that. Task checks before editing; if a test pins it for a reason, the fallback is `resolve_model` inside the non-durable branch instead of a capability.
- **`client.base_url` setter** is SDK behaviour, verified on openai 3.22.0. A unit test pins it, so an SDK upgrade that removes it fails loudly. Fallback order in research.md R2.
- **Claude roles routed to z.ai** by the shipped `ANTHROPIC_BASE_URL` (spec A9): pre-existing, out of scope, reported.

## Complexity Tracking

None.
