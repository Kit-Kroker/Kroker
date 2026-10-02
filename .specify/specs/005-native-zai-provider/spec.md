# Feature Specification: Native zai Provider for the glm Proposer Roles

**Feature Branch**: `005-native-zai-provider` (spec directory only; no branch was created)

**Created**: 2026-10-02

**Status**: GATE 1 cleared 2026-10-02; rulings folded in (see "Resolved Decisions")

**Input**: Decision C3 from `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md` ("its own feature with its own re-baseline"), unblocked by 004's resolver seam. Orchestrator brief: `.workspace/tmp/planner-brief-005-native-zai-provider.md`. User intent: "Переходим на нативный zai-провайдер" — the glm proposer roles stop piggy-backing on the Anthropic-compatible endpoint (`anthropic:glm-5.2` via `ANTHROPIC_BASE_URL`) and route natively as `zai:glm-5.2`.

## Context and verified findings

Every brief claim was checked against main `0f4ac11`: code by reading, library facts by read-only probes in the `kroker-baseline` container (pydantic-ai-slim 2.51.0, genai-prices 0.1.9, same commit). No test suite was run and nothing was changed. Where the code differs from the brief, the spec follows the code.

| # | Brief claim | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | 11 proposer roles carry `anthropic:glm-5.2`; 3 harness roles carry `zai-coding-plan/glm-5.2` | **True.** analyst, architect, clarify, deep_review, devops_planner, handoff, merge_verdict, planner, qa, research, reviewer. Harness: dev, test, devops. | The flip surface is these 11 `agents/<role>/agent.yaml` files. FR-001. |
| V2 | (not in the brief) Every proposer is glm | **False.** Three proposer roles are real Anthropic models: `adversary` (`anthropic:claude-sonnet-4-6`), `discover` and `risk` (`anthropic:claude-sonnet-4-5`). | The `anthropic` provider family stays in the registry after the flip. `ANTHROPIC_API_KEY` cannot simply be retired. FR-004, Q3. |
| V3 | After cutover proposers need no `ANTHROPIC_*` | **False as stated.** Besides V2, `harness/base.py:98-104` (`provider_env`) forwards every `ANTHROPIC_*` variable to env-authenticated coding CLIs (`stages/code/activities.py:149`, `src/sdlc/crew/activities.py:308`). With `ANTHROPIC_BASE_URL` set to z.ai (the shipped `.env.example`), the three claude roles in V2 are today also sent to z.ai's endpoint. | The `ANTHROPIC_*` story is a ruling, not a deletion. Q3. |
| V4 | No dependency change is needed | **True.** Installed metadata: the `zai` extra requires only `openai>=3.19.0`; the `openai` extra already installed requires that plus `tiktoken`. | No `pyproject.toml` / `uv.lock` change. FR-010. |
| V5 | 004's seam handles zai with no code change in `model_ids.py` | **True for validation and construction.** `validate_proposer_model("architect", "zai:glm-5.2")` passes. `infer_provider("zai")` yields an OpenAI-style client with `max_retries == 2` (integer), which is exactly the knob `single_retry_layer()` sets to 0. Base URL `https://api.z.ai/api/paas/v4/`. | The single retry layer holds for the new route by construction; it still needs a test that pins it. FR-006. No retry-policy edit (004 Q3). **Amended at GATE 1:** the provider's default base URL is unusable for this account (V13), so "no code change" no longer holds — every site that constructs a model from a proposer string must build the zai provider with the ruled base URL. FR-016. |
| V6 | First zai resolution inside a workflow task may trip TMPRL1101 | **Measured, low risk.** Out-of-sandbox, fresh process: `infer_model("zai:glm-5.2")` costs 0.8–1.1 s when nothing is warm, **0.13 s** when today's warm set (`anthropic`, `openai`, `google.genai`) is already imported — the cost is the `openai` SDK, which `_warm_workflow_side_imports` already warms. The remaining ~0.13 s is the zai provider/profile modules, which are not warmed. Not measured inside the Temporal sandbox. | Well under the anthropic-SDK 1.9 s that caused the original defect. FR-007 requires the plan to confirm it in-sandbox; whether to add the zai modules to the warm set is a plan decision, not a gate question. |
| V7 | Pricing lookups key on provider:model; the flip changes them | **True.** `pricing.py` tries the hinted provider, then unhinted. `anthropic:glm-5.2` misses under `anthropic` and falls back to the `zhipuai` price row; `zai:glm-5.2` hits the `zai` row directly. Per 1M tokens: input 1.103 → 1.400 (+27%), output 3.862 → 4.400 (+14%); +17% at a 1:1 mix. The brief's "19–23%" is a token-mix-dependent point inside this range. `zai-coding-plan/glm-5.2` (harness) still falls back to the `zhipuai` row and is unchanged. | The same tokens cost more on paper after the flip. Budget gates and benchmark cost columns shift. FR-008, FR-009, Q4. The `pricing.py:27` and `eval/promptfoo/provider.py:46` comments describing the fallback become stale for proposers. |
| V8 | Doctor documents/checks the env story | **True, and it would go silent.** `doctor/checks.py:246` maps provider family → key for `anthropic`, `openai`, `google`, `gemini` only. A `zai` family is "unmapped": after the flip doctor would not check `ZAI_API_KEY` at all, while a missing key fails agent construction at import. | Doctor must learn the new family. FR-005. |
| V9 | Tests assert the literal widely | **True.** 66 occurrences in 30 files under `tests/`, including `tests/conftest.py` (`_PROPOSER_AGENT_YAML`, and the dummy-key setup, which sets `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `EXA_API_KEY` but no z.ai key), `tests/durability/fixture_agents/*/agent.yaml`, and `tests/durability/_http_stub.py`. Not every occurrence should change: some tests use the string as an arbitrary proposer id or to exercise the anthropic path on purpose. | The sweep is per-occurrence triage, not search-and-replace. FR-011. |
| V10 | `wire_no_override.json` pins the registry string | **True** (6 occurrences). | Deliberate, documented regeneration. FR-012. |
| V11 | (not in the brief) ADR-6 family checks | `check_adr6_families` compares `model_family(dev)` to `model_family(reviewer)` by string. Today `zai-coding-plan` ≠ `anthropic`; after the flip `zai-coding-plan` ≠ `zai` — still passes, by a string difference between two prefixes of the same vendor and the same model. The adversary and promptfoo-judge guards compare model ids, not families, and are unaffected. Comments in `loader.py:248`, `eval/promptfoo/assertion.py:73` and `benchmarks/cases/crew-probe/case.yaml:31` name the old route. | No invariant breaks, but the existing known weakness (spec OQ-A4) becomes more visible. After the flip the strings also differ by model id (`glm-5.2` harness vs `glm-5.3` proposer); what the harness CLI's own endpoint actually serves under `glm-5.2` was not probed. Out of scope to fix; recorded against OQ-A4 at close-out (Q5). |
| V12 | (not in the brief) The route change is a protocol change | The Anthropic-compatible endpoint speaks the Anthropic messages protocol; the native provider speaks OpenAI-style chat completions with tool-mode structured output and a separate reasoning field. Test doubles that stub HTTP for proposer calls stub the Anthropic shape. | Model behaviour (structured-output reliability, reasoning, cache accounting) may differ, not just the label. US1 requires one live confirmation; durability HTTP stubs need triage under FR-011. |
| V13 | (not in the brief) Same credential, same billing, same model | **Resolved by live probes** run by the orchestrator with user authorisation on 2026-10-02 (key from `.env`, minimal calls; not re-run by the spec lead): (1) the provider's default endpoint `https://api.z.ai/api/paas/v4` authenticates the key but answers 429 code 1113 "Insufficient balance or no resource package" — the coding subscription does not cover the general API; (2) the coding endpoint `https://api.z.ai/api/coding/paas/v4` (OpenAI-compatible) accepts the same key, is subscription-covered, and replies; (3) the coding endpoint serves **glm-5.3** when asked for `glm-5.2`, and reports `glm-5.3` when asked for it explicitly, whereas today's `/api/anthropic` route serves glm-5.2 as named; (4) genai-prices prices `zai:glm-5.3` identically to `zai:glm-5.2` (1.400 in / 4.400 out per 1M). | The flip is a route change **and** a served-model upgrade 5.2 → 5.3. Registry strings are `zai:glm-5.3` (Q2b). The zai family needs a base-URL policy. FR-001, FR-016. The price break is route-level, not version-level. |
| V14 | Memoization | The model string is part of the role memo key (004 V3). | Every memoized glm proposer result is invalidated once by the flip. Expected; recorded as E3. |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - glm proposer roles are served by z.ai's native route (Priority: P1)

An operator starts a pipeline run with the shipped registry. Each glm proposer role's requests go to z.ai through the native provider, authenticated by a z.ai-specific key, with no dependence on an Anthropic base-URL redirect. The run's usage record, price and cache key all name the native route.

**Why this priority**: This is the feature. Everything else exists to make this flip safe and honest.

**Independent Test**: With the flipped registry and a valid z.ai key, run one real proposer stage; confirm the request reached the native endpoint and produced a schema-valid artifact, and that the recorded model string is the native one.

**Acceptance Scenarios**:

1. **Given** the shipped registry, **When** it is loaded, **Then** all 11 glm proposer roles declare `zai:glm-5.3` and registry validation passes, including ADR-6.
2. **Given** a z.ai key is set, no z.ai base-URL override is set and no Anthropic base-URL redirect is set, **When** a glm proposer role runs, **Then** its request goes to z.ai's coding endpoint, is served by glm-5.3, and returns a schema-valid artifact.
5. **Given** the optional z.ai base-URL override is set, **When** a glm proposer role runs, **Then** its request goes to the overriding URL — on every path that constructs a proposer model, not only the durable-agent path.
3. **Given** a transient provider error on the native route, **When** a proposer request fails, **Then** the number of HTTP calls equals the role's existing engine attempt budget — the SDK adds no retries of its own (004 invariant, unchanged budgets).
4. **Given** a worker that has just booted, **When** the first glm proposer request of a run is resolved inside a workflow task, **Then** no workflow-deadlock warning is raised.

---

### User Story 2 - A missing or placeholder z.ai key is caught before a run (Priority: P2)

An operator who has not set the z.ai key (or left the `.env.example` placeholder) runs the environment check and is told exactly which key is missing and which roles need it, instead of discovering it as an import-time failure or mid-run.

**Why this priority**: The flip introduces a new required secret. Without this, every existing checkout breaks on upgrade with an opaque error.

**Independent Test**: Unset the z.ai key and run doctor; it fails naming the key. Set the placeholder; it fails naming the placeholder. Set a real-looking value; it passes.

**Acceptance Scenarios**:

1. **Given** the flipped registry and no z.ai key, **When** doctor runs, **Then** the provider-keys check fails and names the z.ai key.
2. **Given** a fresh checkout, **When** the operator copies `.env.example`, **Then** it lists the z.ai key with a placeholder and explains which roles each provider key serves.
3. **Given** no real credentials at all, **When** the default unit test tier runs, **Then** it passes (dummy keys cover the new provider at import).

---

### User Story 3 - Cost history stays comparable across the route change (Priority: P3)

Someone reading benchmark results can tell which records were priced on the old route and which on the new, and is not misled into reading the price-table difference as a model regression or a cost regression.

**Why this priority**: The same tokens are priced 14–27% higher under the native provider's price row (V7). Unmarked, this corrupts every before/after comparison.

**Independent Test**: Open `BENCHMARK.md`; find the dated marker, the old and new per-token rates, and the statement of which records fall on which side.

**Acceptance Scenarios**:

1. **Given** the flip has landed, **When** a reader opens the benchmark documentation, **Then** a dated break marker states the route change **and** the served-model change (glm-5.2 → glm-5.3), both rates, and that earlier records were priced on the old route and answered by the old model.
2. **Given** a run after the flip, **When** its cost is computed, **Then** it uses the native zai price row (Q4), and that choice is stated next to the marker.

---

### Edge Cases

- **E1 — Operator override back to the old route.** `--role-model architect=anthropic:glm-5.2` remains a valid proposer override (004 FR-004) and must keep working when the Anthropic variables are set; it is the documented rollback lever, and it rolls back both the route and the served model (glm-5.2).
- **E2 — Override to another zai model.** `--role-model <role>=zai:<other-model>` is built with the same base-URL policy as the registry string (FR-016); it fails with the provider's own clear error when the key is absent. Note `zai:glm-5.2` on the coding endpoint is answered by glm-5.3 (V13) — a label/model mismatch the documentation must warn about.
- **E7 — Base-URL override set to an endpoint the subscription does not cover.** The provider's balance/authentication error surfaces attributed to the role (as E5); the system does not fall back to another endpoint.
- **E3 — Memoized results.** All memoized glm proposer outputs miss once after the flip (V14). No migration; first runs after the flip pay full cost.
- **E4 — In-flight workflows across the upgrade.** A run started before the flip and resumed after resolves the model string recorded at its start. Activity names do not change. The plan must state whether any replay path re-reads the registry string and, if so, how open runs are handled.
- **E5 — Key present, endpoint rejects it** (V13). The failure must surface as a provider authentication error attributed to the role, not as retries exhausting silently.
- **E6 — Anthropic key absent after the flip.** The three claude-model proposer roles (V2) still need it; doctor continues to require it while any registry role is in the anthropic family.

## Requirements *(mandatory)*

### Functional Requirements

**Route**

- **FR-001**: All 11 glm proposer roles (V1) MUST declare `zai:glm-5.3` — the model the coding endpoint actually serves (Q1 = A, Q2b). No role changes its instructions or kind. The served-model change 5.2 → 5.3 rides the flip and is recorded, not hidden.
- **FR-016**: The zai provider MUST be constructed against z.ai's coding endpoint (`https://api.z.ai/api/coding/paas/v4`) by default, with an optional environment override `ZAI_BASE_URL`. This policy MUST apply at **every** site that constructs a model from a proposer model string — the single-retry provider factory and any other — so no path silently uses the provider's own default. The plan MUST enumerate those sites; a test MUST pin the policy per site. `ZAI_API_KEY` is the only new required variable.
- **FR-002**: The three harness roles (dev, test, devops) MUST keep their `zai-coding-plan/*` model strings unchanged (004 FR-005).
- **FR-003**: The three Anthropic-model proposer roles (adversary, discover, risk) MUST keep their model strings unchanged.

**Credentials and environment**

- **FR-004**: The environment contract MUST state, in `.env.example` and `README.md`, which key serves which roles after the flip (Q3 = A): `ZAI_API_KEY` is required for the 11 flipped roles; `ZAI_BASE_URL` is documented as optional with its default; both `ANTHROPIC_*` variables stay as they are and are documented as serving the three claude-model proposer roles and env-authenticated coding CLIs.
- **FR-005**: The environment check (doctor) MUST treat the z.ai provider family as known: it requires the z.ai key when any proposer role uses that family, and reports absent and placeholder values the same way it does for existing families.
- **FR-006**: The single-retry invariant from 004 MUST hold on the native route and be pinned by a test: under an always-failing provider, HTTP calls equal the engine attempt budget. Attempt budgets and backoff MUST NOT be edited.
- **FR-007**: First resolution of the native model id inside a workflow task MUST NOT trip the workflow deadlock detector. The plan MUST measure this in the sandboxed worker and add warm-up only if the measurement requires it.

**Cost**

- **FR-008**: Post-flip usage MUST be priced on the native zai price row (Q4 = A), pinned by a test for `zai:glm-5.3`, and the stale comments describing the fallback pricing path for proposers MUST be corrected.
- **FR-009**: `BENCHMARK.md` MUST carry a dated break marker naming both the route change and the served-model change (glm-5.2 → glm-5.3), with the old and new per-token rates and the scope of records on each side. No benchmark is re-run in this feature.

**Change surface**

- **FR-010**: The feature MUST NOT change project dependencies (V4). If the plan finds otherwise, it stops and reports.
- **FR-011**: Tests MUST be updated by triage, not blanket replacement: occurrences that assert the shipped registry's value follow the flip; occurrences that use the old id as an arbitrary valid proposer id or deliberately exercise the Anthropic path stay, and the plan lists which is which. The default unit tier MUST pass with no real credentials.
- **FR-012**: The frozen wire fixture `tests/durability/fixtures/wire_no_override.json` MUST be regenerated once, deliberately, with the regeneration recorded in the feature's verification record; the only differences MUST be the model id strings.
- **FR-013**: Code comments and case files that name the old route as current fact (V7, V11, `agents/planner/agent.py:25`) MUST be corrected or dated. Historical documents (`docs/superpowers/`, earlier `.specify/specs/`, `docs/reports/`) are not edited.
- **FR-014**: `src/sdlc/stages/code/step.py` MUST NOT grow (991/1000 ratchet).
- **FR-015**: One live proposer call on the flipped registry MUST be made and recorded before the flip is declared done (US1 scenario 2, SC-007). The orchestrator's GATE 1 probes (V13) are evidence for the endpoint choice, not a substitute for this.

### Out of Scope

- Harness roles and the harness model grammar (`zai-coding-plan/*`).
- Any retry-policy change: attempt budgets, backoff, judge retries (004 Q3 binding).
- Benchmark re-runs and re-baselining of historical records (Q4 = A).
- Changing which model any role uses, or moving the three claude roles.
- Fixing the ADR-6 dev/reviewer same-model weakness (OQ-A4).
- Tuning native-only capabilities (reasoning effort, thinking settings).
- `ARCHITECTURE.md` / `ROADMAP.md` edits before merge (docs-describe-main convention; done at close-out).

### Key Entities

- **Registry role**: a named role with a kind (proposer / harness / research) and a model id string; the model id's provider prefix selects route, credential, and price row.
- **Provider family**: the prefix of a model id; drives the doctor key mapping and the ADR-6 family comparison.
- **Wire fixture**: the frozen record of what crosses the workflow/activity boundary for a no-override run, including model id strings.
- **Benchmark break marker**: a dated note in the benchmark documentation separating records priced on different routes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 11 glm proposer roles are served by z.ai's native route (coding endpoint, glm-5.3) in a no-override run; 0 glm proposer requests depend on an Anthropic base-URL redirect.
- **SC-002**: An operator with a missing or placeholder z.ai key learns which key is wrong from one environment-check run, before starting any pipeline run.
- **SC-003**: Under a permanently failing provider, the number of requests per model call on the new route equals the pre-existing attempt budget for that role (no multiplication).
- **SC-004**: No workflow-deadlock warning appears on the first glm proposer request after worker start, across the temporal test tier.
- **SC-005**: The full default test tier and the temporal tier pass in the dev container with no real credentials, with the same pass counts as main apart from tests this feature adds.
- **SC-006**: A reader of the benchmark documentation can state, from that document alone, which records precede the route change and by how much the per-token price differs.
- **SC-007**: One real proposer stage completes on the native route and yields a schema-valid artifact.

## Assumptions

- ~~The model on the native endpoint is the same model the Anthropic-compatible endpoint serves.~~ **False (V13):** the coding endpoint serves glm-5.3. The model upgrade rides the flip; quality re-baselining is deferred, not assumed unnecessary.
- The installed generation (pydantic-ai-slim 2.51.x, genai-prices 0.1.9) is the target; no upgrade rides this feature.
- Operators accept a one-time memo-cache miss (E3).
- Base is main `0f4ac11`; all verification runs happen in the dev container.
- Consults with advisor and skeptic happen after GATE 1 clearance, per the seat brief; amendments they cause are listed under "Post-GATE-1 consult amendments".

## Resolved Decisions (GATE 1, 2026-10-02)

User rulings, relayed by the orchestrator.

- **Q1 = A.** Flip all 11 glm proposer roles in one change.
- **Q2 = resolved by live probes** (V13). The provider's default endpoint is not covered by the subscription; the coding endpoint is, with the same key.
- **Q2b.** Registry strings are `zai:glm-5.3` — the honest string for what the coding endpoint serves. Design consequence: the zai family gets a base-URL policy — default to the coding endpoint, optional `ZAI_BASE_URL` override, no new required variable besides `ZAI_API_KEY` — applied at every proposer-model construction site (FR-016).
- **Q3 = A.** Keep both `ANTHROPIC_*` variables as-is; document them as serving the three claude-model proposer roles and env-authenticated coding CLIs; add `ZAI_API_KEY` alongside and document `ZAI_BASE_URL` as optional.
- **Q4 = A.** The native zai price row is the truth post-flip; dated break marker in `BENCHMARK.md` naming route and model change; no benchmark re-runs.
- **Q5.** Change nothing in this feature; record the ADR-6 observation against OQ-A4 at close-out.

Options considered and not taken: add-only or staged cutover (Q1 B/C); dropping the Anthropic base-URL redirect or adding a doctor warning for it (Q3 B/C); a post-flip baseline re-run or pricing on the old row (Q4 B/C).

## Post-GATE-1 consult amendments (2026-10-02)

Advisor (`.workspace/tmp/advisor-005-1.md`) and skeptic (`.workspace/tmp/skeptic-005-1.md`) were consulted after GATE 1. Every adopted claim was re-checked in code or by a container probe; full disposition in [research.md](research.md).

- **A1 (FR-016 sharpened).** A construction site is any place that can be handed a `zai:` string and turn it into a model. Seven were found; three build with no resolver today (non-durable loader path and eval runner, benchmark judge, operator chat) and would hit the uncovered default endpoint. All are in scope for the base-URL policy. The retry count is **not** changed at sites that do not already zero it (no retry-policy edits).
- **A2 (FR-016 guard).** A regression test MUST fail when a new site constructs a model from a string outside the shared helper.
- **A3 (FR-016 evidence).** The per-site pin MUST include the request URL observed on the wire (stub server), on the durable path as well, not only a client attribute.
- **A4 (E4 answered).** A run open across the upgrade finishes its remaining stages on the new route and model: the registry string is read from the worker, not from history. Already-recorded stages replay from history. A run that explicitly overrode a role to `anthropic:glm-5.2` keeps that route. `ZAI_BASE_URL` is read from the worker environment, like an API key, and is not recorded in history. The plan MUST show the existing in-flight and replay tests pass on the flipped registry; operators are told to drain open runs or accept a mixed-route run.
- **A5 (FR-013 extended).** Stale-comment sweep also covers the warm-up docstring ("every registry proposer model is anthropic-prefixed"), the loader's capability-free note, and the 004 seam docstring's "base URL stays the SDK default".
- **A6 (FR-007).** The zai provider, model and profile modules are added to host warm-up; the in-sandbox measurement is still required.
- **A7 (FR-009 extended).** The break marker also notes that research-stage dollar budgets (per sub-question and per run) are reached sooner on the same tokens; no ceiling is retuned here.
- **A8 (FR-015 extended).** The live confirmation records the model name the endpoint reports, since the coding endpoint has been seen to serve a different model than requested (V13).
- **A9 (observation, out of scope).** With the shipped `ANTHROPIC_BASE_URL` pointing at z.ai, the three claude-model proposer roles are sent to z.ai's endpoint; whether that endpoint serves them was not probed. This predates the feature and Q3 = A leaves it unchanged. Reported to the orchestrator as a follow-up candidate.
- **Rejected.** "glm-5.3 loses reasoning-effort support" — false: the installed profile for `zai:glm-5.3` supports it (it does report thinking as always enabled, a behaviour difference covered by FR-015). "Replay fails with non-determinism" — not supported: the engine matches commands by type and id, not by input; covered by A4's test requirement rather than assumed.
