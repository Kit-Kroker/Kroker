# Feature Specification: Architect Research Surface

**Feature Branch**: `architect-research-surface` (spec directory only; the branch is cut at exec)

**Created**: 2026-10-05

**Status**: GATE 1 cleared 2026-10-05; all six questions ruled A (see [GATE 1 rulings](#gate-1-rulings))

**Input**: Register row C12 (`docs/reports/external-ideas-2026-09.md:80`): defects 6.2, N2 and N3 of assessment `research-budget-enforcement`, scheduled as one M follow-up. The 2026-10-05 user gate lifted D1 for 6.2 **only**; nothing else from the assessment's deferred table is in scope. Task brief: `.workspace/tmp/c12-spec-brief.md`. Prior art: the spike in `.workspace/tmp/c12-spike/FINDINGS.md`. Short-spec precedent: `.specify/specs/008-research-cap-handling/`.

**Base**: main `bcfbffc`.

## Context and verified findings

The architect can consult research mid-run through a `research` tool. The tool runs the research agent on one question, inside the tool's own activity. Three things are wrong with how that inner run is accounted and bounded.

Every anchor below was read on main `bcfbffc`. Nothing was run in this phase; the spike's measurements are cited, not repeated. `R/` = `src/sdlc/stages/research/`.

| # | Defect | Verified state | Consequence |
|---|---|---|---|
| 6.2 | The inner run's spend is lost | **True.** `R/toolset.py:56-59` returns `cast(ResearchBrief, result.output)` and drops `result.usage`. The architect's own run usage does not include the inner run (spike E2: outer 134/48 tokens with inner 424242/777 in flight). For contrast, the stage path hands usage back on its activity results (`R/models.py:80-95`, "an activity that calls a model must hand its usage back"). | US1. The run report, the run budget check and the architect stage's cost record all under-count. |
| N2 | The configured run ceiling is ignored | **True.** `src/sdlc/stages/architecture/step.py:149-161` builds `architect_deps` without `max_run_cost_usd`, so the `ResearchDeps` default `4.0` (`R/deps.py:58`) always applies. The stage path passes `cfg.research.max_run_cost_usd` (`R/step.py:202`). **Nothing else reads the default**: the only other `ResearchDeps(...)` construction in `src/` is the stage's (`R/step.py:241`), and its value is overridden per sub-question (`R/stage.py:262`). | US2. |
| N3 | The inner run has no request limit of its own | **True.** `R/toolset.py:56-58` calls `t_research.run(...)` with no `usage_limits`, so the library default (50 requests) applies. Only `BudgetExceeded` is caught (`:60`); `UsageLimitExceeded` escapes the tool. The stage path sets `UsageLimits(request_limit=cfg.research.max_requests)` (`R/stage.py:273`, default 40) and catches both (`:307`). | US3. |

**The channel (settled by the spike; prior art, not reopened).** The tool returns `ToolReturn(return_value=<ResearchBrief>, metadata={...})`. The metadata survives the durable `__call_tool` round-trip, is readable workflow-side in `result.all_messages()`, and never reaches the model: pydantic-ai 2.51's provider mappings serialize `content` only, and the spike's differential found the metadata field to be the sole difference in the message stream. The merge seam is `_run_role` (`src/sdlc/workflows/role_host.py:165-192`): `u = result.usage` → price → `_track_usage(..., into=...)`.

**Non-channels (ruled out by the spike).** Mutating `deps`; the disk budget store as a token sink; changing the tool's model-visible return value.

**Additional findings (not in the brief).**

- **A1 — the committed architect-research history does not drift.** The brief and the spike expect drift "where the architect research tool actually runs". The one committed history that exercises it, `tests/replay/histories/architect_research_tool.json`, is produced by `_architect_research_activities` (`tests/replay/scenarios.py:472-509`), whose fake architect **owns its own `research` tool** and returns a canned brief (`:501-505`); the production tool never runs. Its recorded tool result carries no report, so a harvest finds nothing and schedules nothing: the history replays unchanged. As read, the forced regeneration scope is **empty**, and no committed history covers a run that carries a report. See FR-010, Q5.
- **A2 — folding into the stage bag relabels it.** `merge_usage` sets `bag.model = model` and adds one call (`src/sdlc/observability/usage.py:25-27`). Folding research tokens into the architect stage's bag (`prep.spend`, labelled with the architect model, `architecture/step.py:95`) through the ordinary path would relabel the architect's cost record with the research model. See FR-004, Q3.
- **A3 — harvest adds workflow commands only when a report is present.** Pricing is an activity (`price_usage`). A run with no report must schedule no additional activity, or every existing history breaks. FR-005, FR-010.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The run reports what the architect's research spent (Priority: P1)

An operator reads a run's cost report, or a run budget threshold is evaluated, after an architect round that called the research tool. The tokens and dollars of the inner research runs appear under the research role and count toward the run budget and the architect stage's cost record. What the architect model receives is unchanged.

**Why this priority**: This is 6.2. Without it the other two fixes bound a spend nobody can see.

**Independent Test**: Run an architect round whose research tool performs a sub-run with known usage; assert the run's `research` usage grew by exactly that usage, priced at the model that answered. Fails on `bcfbffc`.

**Acceptance Scenarios**:

1. **Given** an architect run that calls the tool once and the inner run used X tokens, **When** it completes, **Then** research usage grew by exactly X and the run total includes its price.
2. **Given** an architect run that calls the tool N times, **When** it completes, **Then** research usage grew by the sum of the N inner runs.
3. **Given** an architect round served from the memoization cache, **When** it completes, **Then** zero research usage is added: the run was skipped, there is nothing to harvest.
4. **Given** the same architect run with and without the report, **When** provider-boundary request payloads are captured, **Then** they are byte-identical.
5. **Given** a tool return that carries no report (a test agent's own tool, an old-style bare brief), **When** the run completes, **Then** nothing is added, nothing is scheduled and nothing fails.

---

### User Story 2 - The architect's research honours the configured run ceiling (Priority: P1)

An operator sets `research.max_run_cost_usd`. The architect's research calls charge against that ceiling as the research stage's sub-questions do.

**Independent Test**: Build the architect's research deps from a config with a non-default ceiling; assert the deps carry it. Fails on `bcfbffc` (they carry 4.0).

**Acceptance Scenarios**:

1. **Given** `max_run_cost_usd = 1.5`, **When** the architect round builds its research deps, **Then** they carry `1.5`.
2. **Given** the default config, **When** the deps are built, **Then** the serialized deps payload is byte-identical to today's.

---

### User Story 3 - An architect research call cannot run away on requests (Priority: P2)

A research call from the architect that loops stops at the configured request limit and returns a brief recording the shortfall as a gap, as budget exhaustion does today. It does not escape the tool as an error that burns the activity's retry attempts.

**Independent Test**: Run the tool against a research agent that never finishes; assert it stops at the limit and returns a gap-only brief with no exception. Fails on `bcfbffc` (`UsageLimitExceeded` escapes, at 50).

**Acceptance Scenarios**:

1. **Given** a limit of L and a run that would need more, **When** the tool runs, **Then** it stops at L, returns a gap-only brief naming the limit, and raises nothing.
2. **Given** that stop, **When** usage is harvested, **Then** the spend of the requests completed before the stop is reported.
3. **Given** a run that finishes under the limit, **When** the tool returns, **Then** the brief is as today.

---

### Edge Cases

- **EC1 — memoization.** A cache hit skips the run and adds zero usage (US1.3). A cache miss harvests once; the cached artifact is the `ArchitectureSpec` only, so a later hit cannot replay the report.
- **EC2 — several architect rounds** (delta retries, revise loops). Each round is its own run and its own harvest; nothing is counted twice.
- **EC3 — degraded returns.** A budget-exhausted or limit-stopped call returns its gap-only brief **and** reports the spend made before the stop.
- **EC4 — spend lost to failed attempts. OUT OF SCOPE.** Harvest reads a returned run. Spend made by an architect run that raises, or by a tool attempt that fails and is retried, is not recovered. This is today's behaviour and is not changed; it is recorded as residual R1.
- **EC5 — unpriceable model.** Tokens are recorded without dollars, as the existing egress does; pricing never fails the stage.
- **EC6 — research model override.** The sub-run is priced and labelled at the model that actually answered.
- **EC7 — a run in flight across the deploy.** A history recorded before the change carries no report and replays as before (A3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (6.2): The architect's research tool MUST hand the inner run's usage back to the workflow without changing anything the architect model receives. Provider-boundary request payloads MUST be byte-identical with and without it.
- **FR-002**: The report MUST ride the settled channel under one reserved metadata key, named in exactly one place (Q1), and MUST carry what pricing needs: input, output, cache-read and cache-write token counts and the id of the model that answered. It stays small (order of 100 bytes; far below the 512 KiB payload warning).
- **FR-003**: The workflow MUST harvest every report in a run's messages at the single model-egress point (Q2), price each at its reported model through the existing pricing path with the existing never-fail rule, and account it under role `research` in the run-wide accumulator, where the research stage's own spend already lands.
- **FR-004**: The architect stage's cost record MUST include the research spend and MUST keep its own model label and call count (A2, Q3).
- **FR-005**: A run with no report (memoized, research off, a tool that returns a bare brief) MUST add zero usage, schedule no additional activity and emit nothing new. An absent report is not an error and records no gap (Q6).
- **FR-006** (N2): `architect_deps` MUST carry `cfg.research.max_run_cost_usd`. With the default config the serialized deps MUST be unchanged.
- **FR-007** (N3): Each call of the tool MUST bound its inner run with a request limit (Q4). The limit reaches the tool on deps, the only route it has to config, and MUST NOT change the serialized deps of a default-config run.
- **FR-008**: A request-limit stop MUST degrade exactly as budget exhaustion does: a gap-only brief naming the bound, a normal return, no exception. Both degrade paths MUST report the spend made before the stop.
- **FR-009**: Unchanged: the tool's name, signature, docstring-as-schema and model-visible return; the research stage path; the budget store and its charging; cap values and defaults.
- **FR-010** (replay): Every committed history MUST replay unchanged, with zero re-recorded files forced by this change (A1). A report-carrying run MUST be covered by a history captured **once**, as new content, under the 009 captured-once rule; where it lives and which scenario produces it is the plan's to name (Q5). The T29 parity stand-in (`tests/durability/test_provider_payload_parity.py`) and the replay fakes own their tools, keep returning bare briefs, and stay unaffected.
- **FR-011**: Notes this change makes false MUST be corrected in the same feature: the `R/toolset.py` docstring and any `R/AGENTS.md` line on the architect path's accounting or bounds. Edits to `AGENTS.md` need the orchestrator's approval.
- **FR-012**: No file may exceed 1000 lines (`tests/replay/scenarios.py` is near the ceiling; the plan says where new fixtures live).

### Key Entities

- **Sub-run usage report**: token counts and model id of one inner research run, carried beside the tool's return, never seen by the model.
- **Research role accumulator**: the run-wide per-role usage row the research stage already feeds.
- **Architect stage spend bag**: the architect stage's cost record for its benchmark row.
- **Architect research deps**: the budget and limit settings the architect round hands the tool.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Three tests, one per defect, each failing on `bcfbffc` and passing after: 6.2 (research usage grows by exactly the inner usage), N2 (deps carry a non-default ceiling), N3 (a never-finishing run stops at the limit with a gap-only brief).
- **SC-002**: Wire neutrality, shown in two layers (amended after GATE 1, see [Post-GATE-1 amendments](#post-gate-1-amendments)). Layer 1: durable-path recordings of an architect run with and without the report, in the `tests/replay/capture_provider_requests.py` shape, are equal after removing exactly the tool-return `metadata` key, the set of differing paths is exactly that key, and the tool definitions are identical. Layer 2: the raw request bodies sent for the openai-chat and anthropic mappings, recorded by the extended local HTTP stub, are byte-equal with and without the report.
- **SC-003**: With N inner runs of known usage, research usage equals their sum to the token; the architect stage's model label and call count are unchanged.
- **SC-004**: A memoized architect round adds exactly zero research tokens and schedules no pricing activity.
- **SC-005**: All committed replay histories replay with zero new failures and zero re-recorded files; the new captured-once history replays.
- **SC-006**: The research, architecture, replay and durability test directories pass in `kroker-dev`; no test is deleted or skipped; every edited existing test is listed in the plan with the assertion it keeps.

## Assumptions

- The spike's channel facts hold on the pinned pydantic-ai. The plan re-runs the two probes in `kroker-dev` as its first step rather than trusting the notes.
- The architect's `research` tool is reachable only when research is enabled, which is off by default.
- Tests run in `kroker-dev` only. The register file is updated by the orchestrator. Commits carry no attribution trailers.
- **Residual R1 (documented, no behaviour change):** spend lost to failed attempts (EC4) remains lost.
- Out of scope, binding: every other row of the assessment's deferred table (D1 stays in force for them); recovering R1; the stage path; cap values; the research agent, its tools and prompts; the salvage and keep-findings items.

## GATE 1 rulings

User rulings, relayed by the orchestrator on 2026-10-05: the spec is approved as written and **Q1-Q6 are all ruled A**. No open questions remain.

## Post-GATE-1 amendments

Orchestrator-approved on 2026-10-05 after the advisor and skeptic consults. GATE 1 intent is unchanged.

- **AM1 — SC-002 reworded.** The report sits on the tool-return part the model object receives, so two message recordings differ by that field by construction (advisor OPEN-8). SC-002 now names the two layers that make "byte-identical at the provider" true. FR-001 is unchanged.
- **AM2 — FR-008's limit text.** The request-limit degrade uses one clean text of our own for both the gap and the summary, naming the bound, with no library advice and no documentation URL (008 A1 pattern; skeptic M1).
- **AM3 — FR-003's pricing is batched.** Reports are priced once per distinct answering model, on summed counts; each report is still accounted on its own (skeptic M3). Totals are what FR-003 and SC-003 bind.
- **AM4 — FR-007's lower bound.** A configured request limit below 1 is carried as 1 (skeptic m1).

## Open Questions — GATE 1 (as asked)

Each has a recommendation; the spec is written to the recommendations, so no `[NEEDS CLARIFICATION]` marker remains.

1. **Q1 — Reserved key and payload shape.** (A, recommended) Key `sdlc_sub_run_usage` (the spike's), payload = the four token counts plus the answering model id, one report per tool return. (B) Tokens only, the workflow resolving the model itself: smaller, but the workflow cannot know which model answered under an override or a registry default without duplicating the tool's choice.
2. **Q2 — Harvest placement.** (A, recommended) A generic scan for the reserved key inside `_run_role`: E-33's single egress stays single and no future tool can forget it. (B) A stage-side helper the architect step calls after `run_role`: leaves `_run_role` untouched but creates a second accounting site.
3. **Q3 — Attribution and fold target.** (A, recommended) Role `research`, priced at the answering model, in the run-wide row; also added to the architect stage bag's tokens and dollars without touching its model label or call count. (B) Run-wide row only: simplest, but the architect stage's benchmark cost stays short. (C) Attribute to the architect: misprices the tokens and hides the research row.
4. **Q4 — Request-limit shape and source.** (A, recommended) Per call, `cfg.research.max_requests`, mirroring the stage path's per-sub-question limit. (B) One shared limit across all calls of an architect run: needs cross-activity state, which the spike ruled out. (C) A new architect-specific knob: new config surface with no evidence behind it.
5. **Q5 — Replay coverage, given A1.** (A, recommended) Leave `architect_research_tool.json` frozen and add one new captured-once history whose architect fake returns a report. (B) Teach the existing fake to return a report and re-record that history: one fewer fixture, but it rewrites a file pinned by three other tests. (C) No replay fixture, unit and durability tests only: leaves the harvest's command sequence unpinned.
6. **Q6 — Nothing harvested.** (A, recommended) Silent: no gap, no log. (B) Log or record a gap: noise on every stand-in tool and every research-off run.
