# Feature Specification: Model Forwarding and a Single Retry Layer

**Feature Branch**: `004-model-forwarding-single-retry` (spec directory only; no branch was created)

**Created**: 2026-10-01

**Status**: GATE 1 and GATE 2 cleared 2026-10-01; rulings folded in

**Input**: Model forwarding (defect 6.1) and a single retry layer (defect 6.4), the follow-up split out of 003 by GATE 1 ruling B2. Sources: `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md`; `docs/reports/2026-09-27-pydantic-ai-harness-comparison.md` §3.1, §3.4, §6.1, §6.4.

## Context and verified findings

Every claim in the brief was checked by reading the code on main `b87be66`. Nothing was run (spec phase is read-only). Where the code differs from the brief, the spec follows the code.

| # | Brief claim | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | `RoleHost._run_role` prices and tracks the resolved model but never forwards it | **True.** `src/sdlc/workflows/role_host.py:120-160`: `model` goes to `price_usage` and `_track_usage`; the call is `agent.run(*args, **kwargs)` with no `model=`. No call site passes `model=` in kwargs, and nothing in `src/` uses `agent.override`. | Confirmed defect. FR-001. |
| V2 | "Find every call site that needs the seam" | `_run_role` is the egress for 11 stage call sites (via `ctx.run_role`, wired in `workflows/feature.py:166` and `workflows/graph.py:68`) plus one direct call (`feature.py:216`, handoff). **Three proposer paths bypass it**: (a) `AssessmentWorkflow` calls `t_discover.run` and `t_risk.run` directly (`assessment.py:453, 675`) and keys/prices them on `STAGE_MODELS`, never on a per-run override; (b) the research stage calls models inside activities: its planner and synthesis agents are built on `inp.model` (`stages/research/stage.py:104, 358`), so the override reaches them, but the sub-question fan-out runs the registry `research_agent` with no model (`stage.py:238-248`; the `model=` branch is a test seam) while labelling the usage with `inp.model` (`stage.py:233`), so there the override does **not** reach the model; (c) the architect's research tool calls `t_research.run` (`stages/research/toolset.py:48`) with the registry model. | The seam covers more than one function. Scope ruled at GATE 1 (Resolved Decisions, Q1). |
| V3 | The override is priced, keyed and ADR-6-validated | **True.** `resolve_role_model` (`agents/roles.py:219`) feeds the memoization key (`role_host.py:108`), `RoleUsage.model`, `price_usage`, and `validate_run_roles` (CLI: `cli_roles.py:43`; benchmark: `benchmarks/workflow.py:109`). | Four records describe a model that did not answer. FR-002. |
| V4 | Override strings are not validated as model ids | **True.** `parse_role_models` (`cli_roles.py:19`) checks only `role=model` shape, known role, non-empty model. The existing tests use `openai/gpt-5.2` for a proposer role (`tests/test_role_model_resolution.py:19`, `tests/test_cli_role_model.py:24`), which is not a resolvable proposer model id. Harness roles legitimately use a different grammar (`zai-coding-plan/glm-5.2`, passed to the CLI adapter verbatim). | Validation must be per role kind. Existing tests encode the defect and will change. FR-004, FR-005. |
| V5 | Tests pin the resolver, not the model that answers | **True.** No test in `tests/` asserts which model served a proposer request under an override. The 003 fakes pin one test model for every id (`tests/fakes/fake_agents.py:52, 92`), which would hide a wrong id. | FR-006. |
| V6 | No `max_retries` or explicit provider/client in `src/` | **True.** `grep` over `src/` finds neither. All 16 durable agents are built from model-id strings (`agents/roles.py`, `agents/loader.py`). | FR-007. |
| V7 | SDK default retries are 2, under 3 Temporal attempts | **True.** Installed `anthropic/_constants.py:10` and `openai/_constants.py:8`: `DEFAULT_MAX_RETRIES = 2`. `AGENT_ACTIVITY_MAX_ATTEMPTS = 3` and `CLARIFY_FANOUT_MAX_ATTEMPTS = 3` (`agents/roles.py:38, 56`). Worst case 3 x 3 = 9 HTTP calls per model request. | FR-007, FR-008. Two attempt budgets exist, not one. |
| V8 | Installed versions: anthropic 1.9.0 / openai 3.22.0 / httpx2 | **True** (`uv.lock`): anthropic 1.9.0, openai 3.22.0, httpx2 2.13.1, pydantic-ai-slim 2.51.0, genai-prices 0.1.9. `httpx` 0.28.1 is also locked, and the installed anthropic client rejects `httpx` objects (`anthropic/_base_client.py:146`). | Any custom HTTP client must be the generation the installed SDK accepts. FR-009. |
| V9 | 003 sends the model string across the wire | **True.** Installed `TemporalDurability` documents that model-name strings cross the activity boundary as written and are built on the worker by the agent's model-id resolution chain (`durable_exec/temporal/_durability.py:185-198`). `SdlcPydanticAIPlugin` (`agents/runner.py`) warms only the `anthropic` provider on the host. | The resolution seam exists. A non-anthropic override resolves a provider that is not warmed: edge case E4. |
| V11 | (post-GATE-1 consult) A call site labels a model without resolving it | **True.** `stages/code/step.py:770` passes `reviewer_model=STAGE_MODELS.get("review", "unknown")` into the review step, so in the code stage's review loop the reviewer label ignores a `reviewer` override (`stages/review/step.py:134` takes the passed value first). `stages/analyze/step.py` can fall back to a provider-less label. `code/step.py` is at 991 of 1000 lines. | Forwarding at the egress alone would leave label and model disagreeing here. FR-002 requires a guard; the fix in `code/step.py` must not grow the file. |
| V12 | (post-GATE-1 consult) Overrides enter only via CLI and benchmark arms | **False.** A graph definition can carry a role on a node; `workflows/graph_nodes/base.py:135-137` copies it into the run's role config when the run has no override for that role. `graph/validate.py` checks it for ADR-6 only. | Third entry path for FR-004. |
| V13 | (post-GATE-1 consult) Every budget is 3 | **False for research.** The research sub-question activity allows 6 attempts (`stages/research/step.py:63`); other research activities allow 1 to 3. Worst case there is 18 HTTP calls today. The benchmark judge also calls a model inside an activity with 5 attempts (`workflows/benchmark_host.py:35, 150`); it is not a proposer role. | FR-008 is stated per agent's own budget. The judge is out of scope and reported at GATE 2. |
| V10 | `benchmarks/experiments/` is empty on main | **True**: the directory exists and is empty. `records/` holds design exports only (not benchmark records). Raw benchmark records are written under `runs/benchmarks/<bench_run_id>/` (`benchmarks/recorder.py`), which is not present in this checkout; `runs/` holds only `bf-e2e-*` directories. Only one committed case declares arms (`benchmarks/cases/crew-probe/case.yaml`), and its arm overrides harness roles only. | The affected record set may be empty on this machine. The inventory (FR-012) must state where it looked. |

**Additional finding (not in the brief).** The research stage's activity-side agents (V2 b) are plain agents inside Temporal activities with their own retry policies. They carry the same SDK-retry stacking as the durable agents but are outside the "16 durable agents" wording. Ruled in scope for the retry requirements (Q1).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An overridden proposer role is answered by the model it names (Priority: P1)

An operator starts a run with a per-role proposer override (`--role-model architect=<model>`), or a benchmark arm sets a proposer model. The role's requests are served by that model, and the run's cost, usage record, cache key and ADR-6 verdict all describe the model that actually answered.

**Why this priority**: This is the defect. Today the label and the model disagree, which invalidates every proposer-arm comparison and lets ADR-6 approve a pairing that never ran.

**Independent Test**: Run one proposer role with an override against a recording fake that reports which model id it was asked to be; assert the recorded id equals the override, and equals the id in the usage record and the cache key.

**Acceptance Scenarios**:

1. **Given** a run with a proposer override for one role, **When** that role runs, **Then** the model that serves the request is the override, and the usage record, the priced model and the cache key name the same model.
2. **Given** a run with no overrides, **When** any proposer role runs, **Then** each role is served by its registry model exactly as today.
3. **Given** a benchmark arm with a `default` model, **When** the cell runs, **Then** every overridable proposer role in that cell is served by that model.
4. **Given** an override for one role, **When** a different role runs in the same run, **Then** the other role is still served by its registry model.

---

### User Story 2 - A bad override is refused before the run starts (Priority: P2)

An operator mistypes a proposer model, or passes a harness-style string for a proposer role. The run is refused at submission with a message naming the role, the offending string and the accepted form. No workflow starts and nothing is spent.

**Why this priority**: Once the override really reaches the model (US1), an invalid string turns from a silent no-op into a mid-run failure after earlier stages have spent money. Rejection must move to the front.

**Independent Test**: Submit overrides with malformed and unknown-provider strings through the CLI and through benchmark arm expansion; assert each is rejected before any workflow is started.

**Acceptance Scenarios**:

1. **Given** a proposer override that is not a valid proposer model id, **When** the run is submitted, **Then** it is rejected before start with a message naming the role and the string.
2. **Given** a harness-role override in the harness grammar, **When** the run is submitted, **Then** it is accepted as today.
3. **Given** a benchmark case whose arm resolves to an invalid proposer model, **When** the matrix is expanded, **Then** the case is rejected before any cell runs.

---

### User Story 3 - A failing provider is retried by one layer only (Priority: P2)

A provider returns rate-limit or server errors. Each model request is retried only by the workflow engine's attempt budget; the provider SDK adds no hidden retries beneath it. A request that cannot succeed fails after at most that budget of HTTP calls and the stage reaches its existing degrade or fail-closed path.

**Why this priority**: Stacked retries triple provider load during an outage, hide failures from the layer that owns retry policy, and stretch a doomed stage.

**Independent Test**: Point a proposer at a stub that always answers 429 and count HTTP requests for one proposer call; assert the count is at most the role's attempt budget (3).

**Acceptance Scenarios**:

1. **Given** a provider stub that always returns 429, **When** one proposer call runs to exhaustion, **Then** the stub has received at most 3 requests and the call fails into the stage's existing failure path.
2. **Given** a provider stub that fails once then succeeds, **When** a proposer call runs, **Then** it succeeds on the second attempt and the stub has received exactly 2 requests.
3. **Given** an overridden role (US1), **When** its provider fails, **Then** the same single-layer bound holds for the override's provider.

---

### User Story 4 - The team knows which benchmark records the defect touched (Priority: P3)

Before any re-run or re-label is decided, the team has a list of benchmark records made with a proposer override while the defect was live, with enough detail per record to rule on it individually.

**Why this priority**: Ruling A3 (locked): inventory first, per-record verdicts later. It does not block the fix.

**Independent Test**: The inventory exists as a research artifact, names every location searched, and lists each affected record or states the location was empty.

**Acceptance Scenarios**:

1. **Given** the locations named in FR-012, **When** the inventory is complete, **Then** each affected record lists its run id, case, arm, the labelled proposer model and the registry model that actually answered.
2. **Given** a location that is empty or unreachable, **When** the inventory is complete, **Then** it says so explicitly rather than omitting the location.

### Edge Cases

- **E1** An override equal to the role's registry model: behaviour and records are identical to no override.
- **E2** Agents that share a role's model without being registry roles (the two clarify fan-out agents reuse the `clarify` role): an override for `clarify` must reach them too, or the label and the model diverge again.
- **E3** A memoized result computed before the fix under an override key was produced by the registry model. It must not be served as the override's output after the fix (FR-003).
- **E4** An override naming a provider other than the one warmed at worker start: the override string is first resolved inside the workflow task, so a cold provider import happens there. It must not trip the workflow deadlock detector or fail for a missing credential mid-run without a clear message.
- **E5** A run in flight across the upgrade, and replay of captured histories: runs without overrides must replay unchanged (FR-010).
- **E6** A provider response carrying a retry-after hint: with SDK retries off, the hint is no longer honoured by the SDK. Accepted at GATE 1 (Q3).
- **E7** Non-retryable provider errors (bad request, auth): still fail on the first attempt as today.
- **E8** Tool-calling runs: one proposer call is several model requests; the bound in FR-008 is per model request, and the per-call total is requests x budget.

## Requirements *(mandatory)*

### Functional Requirements

**Model forwarding (6.1)**

- **FR-001**: For every proposer call in scope (the `_run_role` call sites, the architect's research tool and the research stage's sub-question fan-out; Q1), the model that serves the request MUST be the model resolved for that role in that run (override if present, else registry model).
- **FR-002**: The model named in the usage record, the priced model, the memoization key and the ADR-6 validation input MUST be the same value that is forwarded to the call. There MUST be exactly one runtime point that decides which model is forwarded for a role in a run. A call site that supplies a different model label for that role under an override MUST fail the call loudly rather than record the wrong label (V11).
- **FR-003**: Memoized results written before this feature under a key that included a proposer override MUST NOT be served after it. The plan chooses the mechanism (key change or invalidation) and states it.
- **FR-004**: A proposer override that is not a valid proposer model id MUST be rejected at submission, before any workflow starts, on every entry path that accepts overrides (CLI `--role-model`, benchmark arm expansion, a role carried on a graph node (V12), and any other path that populates per-run role config). The message MUST name the role, the string, and the accepted form.
- **FR-005**: Validation MUST be per role kind: harness roles keep their existing grammar and behaviour unchanged. Validation MUST NOT require network access.
- **FR-006**: A test MUST assert which model answered a proposer request under an override, using a recording fake that distinguishes model ids, for at least: one serial stage role, the clarify fan-out agents (E2), and one benchmark-arm `default`. A test that inspects only the resolver's return value does not satisfy this.

**Single retry layer (6.4)**

- **FR-007**: Every proposer model request made under a workflow or activity retry policy (the 16 durable agents, including assessment `discover`/`risk`, the research stage's activity-side agents, and the architect's research tool; Q1) MUST be made with provider-SDK retries disabled, for registry models and for overrides alike, on every provider a role can resolve to.
- **FR-008**: One model request MUST produce at most that agent's configured attempt budget of HTTP requests (3 today for the shared and the clarify fan-out budgets; 1 to 6 for the research stage's activities, V13). A test with an always-429 stub MUST assert this bound per proposer call (former 003 SC-007), and a fail-once stub MUST show exactly 2 requests.
- **FR-009**: Any custom HTTP client introduced MUST be of the type the installed provider SDK accepts (V8). Building provider clients MUST NOT change request payloads, credentials source, base URL or timeouts relative to today, except the retry count.
- **FR-010**: Runs with no proposer override MUST remain replay-compatible with captured pre-feature histories, and the existing replay and golden suites MUST stay green. Any change to scheduled activity inputs for override runs MUST be stated in the plan.
- **FR-011**: Stage outcomes on exhausted retries MUST be unchanged: each stage reaches the same degrade or fail-closed path it reaches today, only sooner.

**Benchmark inventory (A3, research input only)**

- **FR-012**: The feature's research MUST include an inventory of benchmark records made with a proposer override (`--role-model` on a proposer role, an arm `role_models` entry for a proposer role, or an arm `default`) before this feature lands. It MUST cover: `benchmarks/experiments/` and its git history, `runs/benchmarks/` on every machine that ran benchmarks, any external record store, the benchmark scratch area, and prior case and arm configs in git history. It MUST record each location searched and its result. It MUST NOT re-run or re-label anything; per-record verdicts are a separate decision.

**Boundaries**

- **FR-013**: The resolution point from FR-002 is the seam a future native provider feature (ruling C3) will extend. This feature MUST NOT add a native zai provider, change any registry model string, or change pricing.
- **FR-014**: Defects 6.2 (architect research sub-runs unpriced) and 6.3 (oversized prompt hangs the run) are out of scope (ruling D1).
- **FR-015**: Repository constraints apply: 1000-line ceiling per file (shrink-only for grandfathered files), clean schemas, no cross-stage calls.

### Key Entities

- **Role model resolution**: for a (run, role) pair, the single model value used to call, price, record, key and validate.
- **Proposer override**: a per-run role-to-model entry, from the CLI or a benchmark arm, for a non-harness role.
- **Attempt budget**: the workflow engine's maximum attempts for one model request of a given agent.
- **Affected benchmark record**: a record whose labelled proposer model differs from the registry model that answered.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of in-scope proposer calls under an override, the model that answers equals the model in the usage record, the priced model and the cache key.
- **SC-002**: 100% of invalid proposer overrides are rejected before a run starts, on every entry path; zero are accepted and fail mid-run.
- **SC-003**: A model request against an always-failing provider produces at most 3 HTTP requests (down from up to 9).
- **SC-004**: Runs without overrides show no change in which model answers, in spend figures, or in replay results; all existing replay and golden suites pass.
- **SC-005**: The benchmark inventory names every searched location and lists every affected record, or states that none exist, before any per-record decision is requested.

## Assumptions

- "Proposer call" means a model call made by a non-harness role. Harness roles already receive their model through the CLI adapter and are untouched.
- The default scope is the proposer calls that run under a workflow or activity retry policy. Offline paths (`eval` runner, benchmark judge when run outside a workflow, the operator agent) are out of scope (Q1).
- A "valid proposer model id" means a string of the `provider:model` form whose provider is one the installed framework can construct. Whether the model name itself exists at the provider is not checked (no network, FR-005).
- The existing tests that use `openai/gpt-5.2` for a proposer role are updated to a valid id; this is a deliberate consequence of FR-004, not a regression.
- All verification runs happen in the dev container; benchmark re-runs, if later ruled, follow the benchmark launch runbook.
- Research note only (ruling C3): `genai-prices` 0.1.9 prices `zai:glm-5.2` 19-23% above `anthropic:glm-5.2` for the same tokens. No requirement here depends on it.

## Resolved Decisions

- 2026-10-01 (GATE 2, user ruling relayed by the orchestrator): plan approved. Q3 stands with no attempt-budget or backoff change; the retune request is an inbox task. The benchmark judge's retry stacking (V13) stays out of scope, as an inbox task. For FR-012, the operator confirms no other machines, container volumes or external stores hold benchmark records: this checkout's locations are the complete set.
- 2026-10-01 (post-GATE-1 consults, spec lead): factual corrections V11-V13 added from the advisor and skeptic reports, each re-verified in code; FR-002, FR-004, FR-008 and E4 reworded to match. No ruling changed. The skeptic's request to retune the attempt budget and backoff conflicts with ruling Q3 and was not adopted; it is carried to GATE 2 as a stated risk.
- 2026-10-01 (GATE 1, user ruling relayed by the orchestrator): Q1, Q2 and Q3 ruled as recommended.
- **Q1 (scope of the bypass paths)**: The single-retry requirements (FR-007, FR-008) cover all three bypass paths in V2: (a) the assessment `discover`/`risk` agents, (b) the research stage's activity-side agents, (c) the architect's research tool. Model forwarding (FR-001) covers (c). Path (a) is routed through the single resolution point (FR-002) and MUST NOT gain a new per-run override surface: assessment keeps resolving to the registry model. Path (b) MUST take its model from the same resolution point. Correction after plan review (2026-10-01): only the planner and synthesis calls of path (b) receive the override today; the sub-question fan-out does not (V2 b) and is therefore covered by FR-001 as well.
- **Q2 (validation strictness)**: A valid proposer model id is a `provider:model` string whose provider is one the installed framework can construct. The model name is not checked against any list. Validation is offline. Validation is not narrowed beyond this: if a constructible provider turns out not to honour FR-007, that is a stop-and-escalate condition in the plan, not a silent rejection rule.
- **Q3 (resilience)**: The single-layer attempt bound is accepted as is. This feature MUST NOT change any attempt budget or backoff setting; tuning follows later from evidence. Consequence, accepted: a short rate-limit burst the SDK used to absorb can fail a stage (E6).
