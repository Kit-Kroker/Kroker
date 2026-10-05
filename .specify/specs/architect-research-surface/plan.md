# Implementation Plan: Architect Research Surface

**Branch**: `architect-research-surface` (cut from main at exec, in the worktree `kroker-dev` is bound to) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

**Status**: Consults folded (advisor, skeptic, orchestrator resolutions 1-9). Plan review 1 (`.workspace/tmp/reviewer-c12-plan-1.md`): fixes-needed, design approved as written; B-1, N-1, N-2, N-3 and three nits applied. Plan review 2 (`.workspace/tmp/reviewer-c12-plan-2.md`): approve; its two nits applied. Tasks review 1 (`.workspace/tmp/reviewer-c12-tasks-1.md`): approve; two one-liners applied to T005. Waiting for GATE 2.

**Input**: approved spec (GATE 1, 2026-10-05: Q1-Q6 all A; post-GATE amendments AM1-AM4). Design decisions R1-R9 and the consult disposition in [research.md](research.md).

## Summary

The architect's `research` tool runs the research agent inside its own activity and returns only the brief. Its token spend is dropped (6.2), its deps ignore the configured run ceiling (N2), and its inner run has no request limit of ours (N3). After this feature the tool returns the brief with a small usage report beside it, on a channel the model never sees; the single model-egress point harvests the reports, prices them once per answering model and accounts them under the research role and in the architect stage's cost; the architect step passes the configured ceiling and request limit on deps; and a request-limit stop degrades to a gap-only brief with a clean text of our own. One new pure module, five source files edited, one call edited under `agents/`, one new replay history captured once.

## Technical Context

**Language/Version**: Python 3.13 (dev container; the host venv is not a verification environment).

**Primary Dependencies**: none added or changed. Uses installed `pydantic-ai-slim` 2.51 (`ToolReturn`, `UsageLimits`, `RunUsage`, `UsageLimitExceeded`) and `temporalio`.

**Storage**: none changed. One new committed test fixture: `tests/replay/histories/architect_research_usage.json`.

**Testing**: pytest. Unit tests, wire layer 2 and the replay row run in the fast tier. Wire layer 1 and the capture test are `temporal`-marked. One pytest invocation per command; do not add `-q`. Ruff, mypy (`src/` only), `scripts/check_file_size.py`.

**Target Platform**: Linux container `kroker-dev`.

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: none. A run with reports adds one local pricing activity per distinct answering model.

**Constraints**:
- A run that carries no report MUST schedule exactly today's commands. **No `workflow.patched` marker** (orchestrator ruling; argument in research R6).
- What the architect model receives MUST NOT change: the tool's name, parameters, docstring, `-> ResearchBrief` annotation, tool definition and returned content.
- No edit to: `src/sdlc/core/models.py` (user's uncommitted work), `R/stage.py`, `R/step.py`, `R/budget_store.py`, `R/models.py`, `src/sdlc/workflows/report_host.py`, `src/sdlc/pricing.py`, `tests/replay/scenarios.py`, `tests/replay/harness.py`, any existing file under `tests/replay/histories/`, `tests/replay/golden/`, `tests/replay/fixtures/` or `tests/durability/fixtures/`, `tests/replay/test_fixtures_present.py`, `tests/replay/test_notify_registration_chaos.py`, `tests/durability/test_provider_payload_parity.py`, `tests/durability/test_priced_usage_parity.py`, `tests/test_model_forwarding.py`, `tests/research/test_research_durability_nested.py`, `pyproject.toml`, `uv.lock`, the register file, earlier `.specify/specs/*`.
- `SDLC_CAPTURE_HISTORIES` is never set. The new history has its own switch, used once on the branch, after the harvest is green.
- `AGENTS.md` and stage-doc wording is fixed in D6; any deviation goes to the orchestrator **before** commit.
- The user's uncommitted files in the primary checkout are not touched: `agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, `docs/reports/2026-09-22-neon-welcome-session-retro.md`, `docs/reports/external-ideas-2026-09.md`, the two `Pipeline Canvas` HTML files, and anything else `git status` shows modified there. **Expected to change with the feature** (the spec-kit convention, as 009 did; not user work, and no implementation task edits them): `CLAUDE.md` (the plan pointer) and `.specify/feature.json` (the feature directory); they ride the feature branch with the spec set.
- File ceiling 1000 lines: `tests/replay/scenarios.py` 907 by `scripts/check_file_size.py`'s count (906 content lines; not edited), `workflows/role_host.py` 300, `tests/durability/_http_stub.py` 170, `R/toolset.py` 70, `R/deps.py` 116, `architecture/step.py` 306.
- Read the root `AGENTS.md`, `src/sdlc/stages/research/AGENTS.md`, `src/sdlc/stages/architecture/AGENTS.md` and `src/sdlc/workflows/AGENTS.md` before editing.
- All runs in `kroker-dev`; never the host venv; never alongside a live pipeline run. Commits: `git commit -F <msgfile>`, one path per `git add`, subject and body, **no attribution trailers of any kind**. **No heredocs in any command** (the host parser aborts on over-length commands); files are written with the file tool. RC capture `> log 2>&1; echo RC=$?`.
- TDD: RED tests are written by the qa seat and seen failing for the stated reason before the change they cover. They ride that change's commit; no commit on the branch is red.
- Read `.workspace/tasks/` for known host hazards before any tier run.
- Base: main at exec (`e5c8ef8` today; `src/` anchors were read on `bcfbffc`). Re-locate by symbol, not by line number.

**Scale/Scope**: 1 new source module; 5 source files edited (`R/toolset.py`, `R/deps.py`, `architecture/step.py`, `workflows/role_host.py`, `observability/usage.py`); 1 file under `agents/` (one tool body); 2 existing test files edited (one fake's signature; the HTTP stub gains body recording); 7 new test modules; 1 new history; 4 doc edits.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/architect-research-surface/
├── spec.md
├── plan.md          # this file
├── research.md      # R1-R9, consult disposition, residuals
├── quickstart.md    # dev-container validation runbook
├── checklists/
└── tasks.md         # /speckit-tasks
```

No `data-model.md` and no `contracts/`: the one new data shape (the report) and the changed in-process interfaces are specified in D1-D4.

### Source Code (repository root)

```text
src/sdlc/observability/sub_run_usage.py   # NEW: key, SubRunUsage, metadata_for, harvest_reports
src/sdlc/observability/usage.py           # + add_spend (no relabel, no call)
src/sdlc/stages/research/toolset.py       # reported function, wrapper, tool_return, limit, degrade
src/sdlc/stages/research/deps.py          # + DEFAULT_MAX_REQUESTS, max_requests (ge=1), omitted at default
src/sdlc/stages/architecture/step.py      # deps carry ceiling and clamped limit
src/sdlc/workflows/role_host.py           # _price helper; harvest in _run_role
agents/architect/agent.py                 # tool body: reported function + tool_return

tests/test_sub_run_usage.py                            # NEW
tests/test_role_usage.py                               # + add_spend cases
tests/architecture/test_architect_research_tool.py     # edited: one fake's run signature
tests/architecture/test_architect_research_report.py   # NEW: tool side, 6.2 + N3
tests/architecture/test_architect_research_deps.py     # NEW: N2 + limit on deps
tests/test_run_role_sub_run_harvest.py                 # NEW: harvest, 6.2
tests/durability/_http_stub.py                         # edited: also records raw bodies (additive)
tests/durability/test_sub_run_usage_wire.py            # NEW: SC-002, both layers
tests/replay/architect_research_usage.py               # NEW: scenario + fake (not a test module)
tests/replay/test_architect_research_usage_replay.py   # NEW: replay row, pin, capture
tests/replay/histories/architect_research_usage.json   # NEW fixture

src/sdlc/workflows/AGENTS.md              # D6: one sentence
src/sdlc/stages/research/AGENTS.md        # D6: two bullets
src/sdlc/stages/architecture/AGENTS.md    # D6: one bullet
src/sdlc/stages/architecture/architecture.md  # D6: one failure-mode line
```

**Structure Decision**: the scenario lives in its own module outside `tests/replay/scenarios.py` and outside `SCENARIOS` (FR-012; 009 precedent `tests/replay/research_retain.py`): list membership would force a golden file and edits to two pin tests, and `scenarios.py` is at 907 lines.

## Design

### D1 — The report and its reader (FR-002; Q1 = A; R2, R5)

New module `src/sdlc/observability/sub_run_usage.py`, pure (no `temporalio`, no `pydantic_ai`, no stage import):

- `SUB_RUN_USAGE_KEY = "sdlc_sub_run_usage"`: the only place the key is spelled in `src/`.
- `SubRunUsage`: frozen pydantic model, `model: str`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`: `int`, `ge=0`.
- `from_run_usage(run_usage, model) -> SubRunUsage | None`: `None` when input and output counts are both zero; counts coerced with `or 0`.
- `metadata_for(report) -> dict`: `{SUB_RUN_USAGE_KEY: report.model_dump(mode="json")}`, a plain dict.
- `harvest_reports(result) -> list[SubRunUsage]`: duck-typed and total, exactly as research R5: `new_messages` by `getattr`, parts by `getattr`, `part_kind == "tool-return"`, `metadata` a dict holding the key, `SubRunUsage.model_validate` per part with a failure skipping that part, zero-token reports dropped, any other exception returning `[]`. Message order, then part order.

In `observability/usage.py`: `add_spend(bag, *, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd)` adds the four counts and, when `cost_usd is not None`, the dollars. It never touches `bag.model` or `bag.calls`.

### D2 — The tool side (FR-001, FR-007, FR-008, FR-009; N3; R1, R3, R9)

In `R/deps.py`: `DEFAULT_MAX_REQUESTS = 40`; `max_requests: int = Field(default=DEFAULT_MAX_REQUESTS, ge=1)` with a docstring saying it bounds the architect tool's inner run only and that the stage path passes its own limit; the wrap serializer also drops `max_requests` while it equals the constant.

In `R/toolset.py`:

- `research_subquery_reported(deps, question) -> tuple[ResearchBrief, SubRunUsage | None]`:
  - `run_usage = RunUsage()`, `UsageLimits(request_limit=deps.max_requests)`, both passed to `t_research.run(question, deps=deps, usage_limits=..., usage=run_usage)`; `model=deps.research_model` added only when set, as today;
  - `except BudgetExceeded`: today's gap-only brief, text byte-identical;
  - `except UsageLimitExceeded`: the gap-only brief built from **one text of our own**, `reason = f"request limit exhausted ({deps.max_requests} requests)"`: the gap's `why_it_matters` is `reason`, the summary is `f"Research stopped before this sub-question could be answered: {reason}"`. `str(exc)` is not used (AM2);
  - both degrade bodies go through one private gap-brief builder (`sub_question_id="architect-midrun"`, `what_is_missing=question`);
  - the report on all three paths is `from_run_usage(run_usage, model)` with `model = deps.research_model or REGISTRY["research"].model or "unknown"` (registry read lazily);
  - any other exception propagates as today (residual R1). 008's `UnexpectedModelBehavior` degrade is not mirrored.
- `research_subquery(deps, question) -> ResearchBrief`: `brief, _ = await research_subquery_reported(...)`; returns `brief`. Signature and return unchanged; docstring says only tests call it now.
- `tool_return(brief, report) -> ResearchBrief | ToolReturn`: pure; the bare brief when `report is None`.
- Module and function docstrings corrected for the report, the limit and the two degrade paths (FR-011).

In `agents/architect/agent.py`: the tool body becomes `brief, report = await research_subquery_reported(ctx.deps, question)` then `return tool_return(brief, report)`. The annotation stays `-> ResearchBrief`; it is never `ToolReturn[...]`. Nothing else in the file changes.

### D3 — The architect step (FR-006, FR-007; N2, N3; R4)

`architecture/step.py`: `architect_deps` gains `max_run_cost_usd=cfg.research.max_run_cost_usd` and `max_requests=max(1, cfg.research.max_requests)`.

### D4 — Harvest, pricing and fold (FR-003, FR-004, FR-005; Q2 = A, Q3 = A; R5)

`workflows/role_host.py`:

- A private `_price(self, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens) -> float | None` holding today's `execute_activity(price_usage, ..., **PRICE_ACT)` inside `try/except Exception: return None`. The architect's own pricing calls it under the same `if u.input_tokens or u.output_tokens` guard, so its command is unchanged.
- In `_run_role`, after the architect's own `_track_usage` and before `return result`:
  1. `reports = harvest_reports(result)`; if empty, nothing more happens.
  2. Group by `model` in first-seen order; sum the four counts per model; `usd[model] = await self._price(model, <sums>)`: **one pricing activity per distinct model**.
  3. For each report in message order: `self._track_usage(role="research", model=report.model, <its counts>, cost_usd=<its share>, into=None)`. Its share is `usd[model]` for the first report of that model and `0.0` for later reports of the same model; `None` for every report of a model whose batch was unpriced.
  4. If `into is not None`: per distinct model, `add_spend(into, <sums>, cost_usd=usd[model])`.
- New imports join the existing passed-through block.

Rules:

- **No report, no command.** With no reports nothing is scheduled, tracked or emitted beyond today.
- **Never `merge_usage` into the caller's bag**, and never `_track_usage(..., into=into)` for a report.
- **The architect's own accounting first**, unchanged.
- **A memoized round adds nothing**: `_cached_stage` returns before the closure that calls `run_role`.
- **Per-event split is a convention.** Per-role, per-activation and per-bag totals are exact; which same-model event carries the batch dollars is not meaningful. For the orchestrator's attention at GATE 2.

### D5 — Replay and wire tests (FR-010, SC-002, SC-005; Q5 = A; R7, R8)

**`tests/replay/architect_research_usage.py`** (not a test module): `NAME = "architect_research_usage"`; a fixed `REPORT` (`SubRunUsage` with non-zero counts and a model id); an architect fake built like `scenarios._architect_research_activities` (same agent name, deps type, output type, tool name and signature) whose own `research` tool returns `ToolReturn(return_value=RESEARCH_BRIEF_FAKE, metadata=metadata_for(REPORT))`, built inline so the module depends on the pure `sub_run_usage` module only; `activities()` = the `architect_research_tool` scenario's registrations with the architect agent's registrations dropped by activity name and the new fake's added; `drive` answers clarify and waits for `awaiting:architecture`; `SCENARIO = Scenario(NAME, greenfield_idea, <the architect_research_tool config>, activities, drive, before=reset_deploy, mode="partial", golden=False)` (the same `before` as `architect_research_tool`, whose registration bundle with `DEPLOY_FAKES` it reuses, so the double capture is deterministic), **not** in `SCENARIOS`. Captured with `GRAPH_STARTER`.

**`tests/replay/test_architect_research_usage_replay.py`**:

1. `test_report_carrying_history_replays` (fast): loads the history, replays with `test_feature_replay.replayer(GraphWorkflow, DeploymentWorkflow)`, asserts no replay failure.
2. `test_fixture_holds_the_harvest` (fast, PIN). Identification rule (every fake shares one model label, so model id cannot pick the architect's): walking the scheduled activities in order, **the architect's own `price_usage` is the first `price_usage` scheduled after the architect agent's final `model_request` activity; the research one is the `price_usage` scheduled immediately after it.** Inputs are decoded with the data converter as `PriceUsageInput` (the pattern `test_research_retain_replay.py` uses for `RetainInput`). Assertions: the research input's model and four counts equal `REPORT`; the architect's own input does **not** equal `REPORT`; across the whole history exactly one `price_usage` input equals `REPORT`; `source_commit` is 40 characters; `workflow == "GraphWorkflow"`.
3. `test_capture_architect_research_usage_history` (`temporal`, skipped unless `SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE=1`): captures twice with `capture(SCENARIO, GRAPH_STARTER, ..., sandboxed=True)`, asserts equal command projections, writes the history file only (never `write_fixtures`).

4. `test_pin_rejects_an_unharvested_history` (fast, PIN): the shape check of test 2 applied to the committed, report-less `architect_research_tool.json` finds no research `price_usage`.

**Negative control (evidence, never committed)**: in a detached worktree of the base commit, with the two new replay modules and the pure module copied in, run the capture switch and then test 2 against that file. It must fail (no research `price_usage`). The output goes into `verification.md`; the worktree and its file are discarded. `kroker-dev` is bound to one worktree, so mounting the scratch worktree is the orchestrator's call at exec; if it cannot be mounted, test 4 stands as the control and `verification.md` says so.

**Fallback**: if the graph partial capture cannot be produced, stop (stop-guard 9); with orchestrator clearance the scenario is recorded from `FeatureWorkflow` in the `architect_research_tool` shape and `verification.md` names it grace-lifetime.

**`tests/durability/_http_stub.py`** (edited, additive): each handled POST also appends its raw body bytes to a new `bodies` list. Existing attributes and behaviour unchanged.

**`tests/durability/test_sub_run_usage_wire.py`**:

- Layer 1 (`temporal`): twin durable stand-ins in the parity-test shape, bare brief vs `tool_return(brief, REPORT)`. Recordings equal after removing exactly the tool-return `metadata` key; the set of differing JSON paths is exactly that key; tool definitions equal.
- Layer 2 (fast, PIN from the start: it needs no source change): for the openai-chat mapping and the anthropic mapping, one `[user prompt, tool call, tool return]` history built with metadata `None` and with `metadata_for(REPORT)`, sent through the concrete model's public `request()` to the stub in `always_ok` mode; the two recorded bodies are byte-equal.

### D6 — Living docs (FR-011): exact wording

Approved in principle by the orchestrator; shown here before it lands.

**`src/sdlc/workflows/AGENTS.md`**, appended to the "Single model egress" section:

> Since architect-research-surface, `_run_role` also harvests sub-run usage reports: a tool that ran a model inside its own activity hands the usage back as `ToolReturn` metadata under `sub_run_usage.SUB_RUN_USAGE_KEY`; after the role's own usage is tracked, `_run_role` prices the reports once per answering model and tracks them under role `research` (`into=None`), then adds the spend to the caller's bag with `add_spend`, never `merge_usage`. A run with no report schedules nothing extra, which is why this needs no `workflow.patched` marker.

**`src/sdlc/stages/research/AGENTS.md`**:

- "Model forwarding (004)" bullet, appended: "The tool also bounds its inner run with `ResearchDeps.max_requests` (the architecture slice passes `cfg.research.max_requests`; omitted from serialization at the default) and returns the inner run's usage beside the brief as `ToolReturn` metadata, which the model never sees."
- "Budget enforcement", third bullet: "Its callers catch `BudgetExceeded` only (`toolset.py`)" becomes "`toolset.py` catches `BudgetExceeded` and `UsageLimitExceeded` and degrades both to a gap-only brief, reporting the spend made so far".

**`src/sdlc/stages/architecture/AGENTS.md`**, after the `scope="architect"` bullet: "The architect's research deps carry the configured run ceiling and request limit (`cfg.research.max_run_cost_usd`, `cfg.research.max_requests`, floor 1)."

**`src/sdlc/stages/architecture/architecture.md`**, failure modes, after "Budget exhaustion": "**Request limit**: a research subquery that reaches its request limit degrades the same way; its spend is still reported."

Docs describe main: these land on the feature branch, last.

### D7 — Tests

**`tests/test_sub_run_usage.py`** (fast). `from_run_usage`: counts, `None` counts, zero usage gives `None`. `metadata_for`: plain dict under the key. `harvest_reports`: one report; several in order; a result with no `new_messages`; a `MagicMock` result; a part that is not a tool return; metadata not a dict; missing key; payload missing a field; a non-integer count; a negative count; an empty-token report: each of these yields nothing for that part and raises nothing. One end-to-end case: a real small `Agent` (`TestModel`) whose tool returns `tool_return(brief, report)`; `harvest_reports(result)` returns that report (pins `part_kind` and the key on both sides). RED before D1.

**`tests/test_role_usage.py`** (added cases): `add_spend` adds counts and dollars, leaves `model` and `calls`, and a `None` cost leaves the bag's cost untouched. RED before D1.

**`tests/architecture/test_architect_research_report.py`** (fast), `roles.t_research` patched:

1. RED (6.2): a fake run adds known counts to the passed `usage` and returns a brief: the reported function returns that brief and a report with those counts.
2. RED (N3): the fake records its kwargs: `usage_limits.request_limit == deps.max_requests`.
3. RED (N3, AM2): a fake that adds counts then raises `UsageLimitExceeded` with the library's real message: no exception; the gap's `why_it_matters` and the summary both contain `request limit exhausted (<n> requests)`; neither contains `http` or the library's advice text; the report holds the counts.
4. RED (EC3): the same for `BudgetExceeded`; the brief equals today's exactly; the report holds the counts.
5. RED (N3, real agent): a `FunctionModel` research agent that loops on a trivial tool, `max_requests=3`: stops, gap-only brief, no exception, a non-zero report.
6. RED (EC6): with `deps.research_model` set the report's model is that id; unset, the registry model; registry model `None`, `"unknown"`.
7. RED: zero usage gives `report is None`, and `tool_return(brief, None) is brief`; with a report it is a `ToolReturn` whose `return_value` is the brief and whose metadata is `metadata_for(report)`.
8. PIN: `research_subquery` returns a `ResearchBrief`.
8a. RED (N3, base API; the SC-001 evidence for N3): `research_subquery(deps, question)` with a patched `t_research` whose `run(self, question, deps, **kwargs)` raises `UsageLimitExceeded`: returns a gap-only brief and raises nothing. On base the exception escapes.
9. RED: the architect agent's `research` tool definition (name, description, parameters schema) equals the one built on the base commit (a literal captured in the test), and the tool's annotation is `ResearchBrief`.
10. RED (the limit field, lands with the toolset): `ResearchDeps` round-trips `max_requests` for 40 (omitted on dump, reads back 40) and 12 (present); the deps default equals `ResearchConfig().max_requests` (drift pin); `max_requests=0` is rejected by validation; a default deps dump has no `max_requests` key.

**`tests/architecture/test_architect_research_tool.py`** (edited): `_ExhaustedAgent.run` accepts `**kwargs`. Every assertion stays.

**`tests/architecture/test_architect_research_deps.py`** (fast):

1. RED (N2): `produce` driven with a stub context capturing `deps`, `max_run_cost_usd=1.5`: the deps carry `1.5`.
2. RED (N3): `max_requests=7`: the deps carry `7`; `max_requests=0`: the deps carry `1`.
3. PIN: default config: the serialized deps equal a literal of today's payload (no `max_requests` key, `max_run_cost_usd == 4.0`).

**`tests/test_run_role_sub_run_harvest.py`** (fast), in the style of `tests/test_run_role_guard.py` (a `RoleHost` subclass recording `_track_usage`; `workflow.execute_activity` patched to record and answer `price_usage`):

1. RED (6.2, base API; the SC-001 evidence for 6.2): one report, given as a literal metadata dict under the literal key and importing nothing new: the architect is tracked as today, then one call with `role="research"`, the report's model and counts, `into=None`; one `price_usage` was asked for the report's model. On base there is no research call.
2. RED (AM3, SC-003): three reports, two models: exactly two research `price_usage` calls, each with that model's summed counts, in first-seen order; three research track calls in message order; the first report of each model carries the batch dollars, the later same-model one `0.0`; the `into` bag's counts and dollars grew by the architect's usage plus the sums, its `model` is still the architect's and its `calls` grew by one.
3. PIN (FR-005): a result with no message accessor, and one with no report: tracked calls and scheduled activities equal today's.
4. RED (EC5): `price_usage` raising for a report's model: its reports are tracked with `cost_usd=None`, the bag's dollars are untouched, no exception.
5. PIN: the architect's own pricing failure still degrades to `None` (the shared `_price`).
6. PIN (EC1, SC-004): `_cached_stage` on a cache hit never calls the closure; nothing tracked, nothing priced.
7. RED (budget): after a harvest the host's `_role_usage` holds a research cost and `_check_budget` counts it (a `ReportHost`-backed host).
8. RED (rollup): for a run with a report, roles rebuilt from the emitted `MODEL_USAGE` events equal `_role_usage` (no double count from the fold).

**Unmodified suites that are the regression check**: `tests/replay/` (every existing history and golden), `tests/durability/` (in particular `test_provider_payload_parity.py`, `test_priced_usage_parity.py`, `test_wire_neutrality.py`, `test_single_retry_layer.py`, `test_zai_route.py` for the stub edit), `tests/research/`, `tests/architecture/`, `tests/graph_workflow/`, `tests/test_model_forwarding.py`, `tests/test_run_role_guard.py`.

## Requirement coverage

| Requirement | Where |
|---|---|
| FR-001 report without changing what the model receives | D2; report tests 7, 9; wire layers 1, 2 |
| FR-002 one key, five fields, small | D1; `test_sub_run_usage.py` |
| FR-003 (AM3) harvest at the egress, priced per answering model, role research | D4; harvest tests 1, 2, 4, 7, 8 |
| FR-004 architect bag includes the spend, keeps label and calls | D1 `add_spend`, D4; harvest test 2; `test_role_usage.py` |
| FR-005 no report: nothing added, scheduled or emitted | D4 rules; harvest tests 3, 6; report test 7; unmodified replay suite |
| FR-006 ceiling on deps; default payload unchanged | D3; deps tests 1, 3 |
| FR-007 (AM4) per-call limit on deps, floor 1; default payload unchanged | D2, D3; report tests 2, 10; deps tests 2, 3 |
| FR-008 (AM2) limit stop degrades with a clean text and reports; budget stop reports | D2; report tests 3, 4, 5 |
| FR-009 unchanged surface | Constraints; report tests 4, 8, 9; unmodified suites |
| FR-010 zero re-recorded files; one captured-once history; stand-ins unaffected | D5; replay tests 1, 2; unmodified replay and parity suites |
| FR-011 notes corrected | D2 docstrings; D6 |
| FR-012 ceilings; where the scenario lives | Structure Decision; `scripts/check_file_size.py` |
| SC-001 one failing test per defect, on behaviour | 6.2: harvest test 1; N2: deps test 1; N3: report test 8a (base API). Report tests 1, 3, 5 add the API-level proof at their step |
| SC-002 (AM1) | wire layers 1, 2 |
| SC-003 | harvest test 2 |
| SC-004 | harvest test 6 |
| SC-005 | unmodified `tests/replay/`; replay tests 1, 2; negative control |
| SC-006 | quickstart; edited existing tests: `test_architect_research_tool.py` (one fake signature), `_http_stub.py` (additive) |
| EC1 / EC2 | harvest test 6 / each round is one `_run_role` call and `new_messages()` (harvest tests) |
| EC3 / EC5 / EC6 | report tests 3, 4 / harvest test 4 / report test 6 |
| EC4 (R1) | no behaviour change, no test; named residual |
| EC7 | harvest test 3; unmodified replay suite; research R6 |

## Delivery order

1. Setup and baseline; re-run the two spike probes in `kroker-dev` (`.workspace/tmp/c12-spike/c12_e1_toolreturn_visibility.py`, `c12_e2_durable_roundtrip.py`); one extra probe that prints `str(exc)` of a real `UsageLimitExceeded`, the `part_kind` of a tool-return part and a `FunctionModel` run's usage. Commit: spec set + baseline.
2. The three defect REDs first, seen failing: report tests (6.2 tool side, N3), deps tests (N2), harvest tests (6.2). Plus the unit REDs for the pure module and `add_spend`, and wire layer 2. The per-defect REDs that carry the SC-001 "fails for the stated reason" evidence are written against the **base API**, so they fail on behaviour and not on an import error: harvest test 1 builds its report as a literal metadata dict under the literal key `"sdlc_sub_run_usage"` and imports nothing new (6.2: no research tracking on base); deps test 1 drives `produce` with base symbols only (N2: 4.0 on base); and a base-API N3 test calls the existing `research_subquery` with an inner run that raises `UsageLimitExceeded` (N3: on base the exception escapes). Tests that need a post-change symbol (`research_subquery_reported`, `tool_return`, `SubRunUsage`) are RED by import until their own step and are not counted as SC-001 evidence; in the new test modules such symbols are imported inside the test functions that use them, never at module top, so the modules collect on base and the base-API tests are seen failing on behaviour. Wire layer 2 needs no new symbol while its metadata is a literal; it is a regression PIN that rides step 3's commit, not a base-state claim about our code.
3. Pure modules (D1). Commit with their tests and wire layer 2.
4. Toolset and the deps field (D2), the architect tool body. Commit with the report tests, the fake edit and wire layer 1.
5. The architect step (D3). Commit with the deps tests.
6. The harvest (D4). Commit with the harvest tests.
7. Capture the history once, replay tests, negative control (D5). Commit.
8. Living docs (D6). Commit.
9. Verification. Commit.

## Handoff to the executor (binding, goes into the executor's brief)

- **Per-task review gate, blocking**: you may not commit task N+1 until the reviewer has replied approve or fixes-needed on task N's diff, and a fixes-needed is resolved first.
- No heredocs in any command; write files with the file tool. One path per `git add`. `git commit -F <msgfile>`. No attribution trailers of any kind.
- Verification runs in `kroker-dev` only.
- D6 wording is fixed; a deviation goes to the orchestrator before commit.
- Stop-guards are binding; clearance comes only from the orchestrator.

## Stop-guards (binding; clearance from the orchestrator only)

1. A spike probe, re-run on the branch base, does not show the metadata workflow-side or shows it in the model-boundary content: stop before any source edit.
2. A change seems to need an edit to a path the Constraints forbid, a new activity, or a patch marker: stop.
3. Any existing test fails after a change and the plan does not name it as an intended edit: stop. Never edit it to pass. Never re-record or edit an existing history, golden or wire fixture.
4. After the harvest lands, `architect_research_tool.json` or any other committed history fails to replay: stop (spec A1 was wrong).
5. Wire layer 1 finds a differing path other than the tool-return `metadata` key or a differing tool definition, or layer 2 finds any byte difference: stop.
6. The captured history does not hold exactly one research `price_usage` equal to `REPORT`, or its two captures disagree: stop. Fix the scenario, not the projection.
7. `SDLC_CAPTURE_HISTORIES` is about to be set, or the capture test is about to run a second time on the branch: stop.
8. A test this plan marks RED passes before its change, or a PIN test is red: stop.
9. The graph partial capture cannot be produced: stop; the `FeatureWorkflow` fallback needs clearance.
10. The negative control passes on the base commit (the shape pin has no teeth): stop.

## Residuals (accepted, reported at GATE 2)

From research "Residuals": spend of an attempt that raises stays lost (spec R1); the tool path does not mirror 008's degrade-once for `UnexpectedModelBehavior`; the stage path's deps carry an unused, never-serialized `max_requests`; under batch pricing the per-event dollar split between same-model reports is a convention and a tiered price could differ from per-sub-run pricing; an old worker during a rolling deploy ignores the new deps key; `research_subquery` is production-dead and kept for its tests.

## Complexity Tracking

Empty: no constitution violations.
