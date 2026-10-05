# Tasks: Architect Research Surface

**Input**: `.specify/specs/architect-research-surface/` (spec.md, plan.md, research.md, quickstart.md)

**Tests**: required (spec SC-001 to SC-006; plan D5, D7). Every source change is preceded by its RED task. Inside a RED task, tests marked PIN pin behaviour that already exists and are expected to pass on first run; a red PIN test is a stop-guard, not a cue to edit source.

`R/` = `src/sdlc/stages/research/`. "Plan D7 report test 3" means test 3 of `test_architect_research_report.py` in plan D7; likewise "deps test", "harvest test".

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (see quickstart.md). Never the host venv. Never alongside a live pipeline run. One pytest per command; do not add `-q` (already in `addopts`). Capture with `> <log> 2>&1; echo RC=$?`.
- **No heredocs in any command** (the host parser aborts on over-length commands). Write every file with the file tool. Host shell may be PowerShell 5.1.
- Read `.workspace/tasks/` for known host hazards before any tier run. `-m temporal` runs in the container only.
- Read the root `AGENTS.md`, `src/sdlc/stages/research/AGENTS.md`, `src/sdlc/stages/architecture/AGENTS.md` and `src/sdlc/workflows/AGENTS.md` before T002.
- RED tasks are written by the qa seat and must be seen failing on the branch for the stated reason before the change that covers them starts. Their files are committed in that change's commit, so no commit on the branch is red.
- **Reviewer gate is per task and blocking: you may not commit task N+1 until the reviewer has replied approve or fixes-needed on task N's diff, and a fixes-needed is resolved first.** This applies to each RED diff on its own as well.
- Commit: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`.
- **`SDLC_CAPTURE_HISTORIES` is never set.** It re-records every existing replay fixture. The new history has its own switch, used once on the branch, in T011.
- **No `workflow.patched` marker** is added (orchestrator ruling; research R6).
- Forbidden paths: `src/sdlc/core/models.py`, `R/stage.py`, `R/step.py`, `R/budget_store.py`, `R/models.py`, `src/sdlc/workflows/report_host.py`, `src/sdlc/pricing.py`, `tests/replay/scenarios.py`, `tests/replay/harness.py`, every existing file under `tests/replay/histories/`, `tests/replay/golden/`, `tests/replay/fixtures/` and `tests/durability/fixtures/`, `tests/replay/test_fixtures_present.py`, `tests/replay/test_notify_registration_chaos.py`, `tests/durability/test_provider_payload_parity.py`, `tests/durability/test_priced_usage_parity.py`, `tests/test_model_forwarding.py`, `tests/research/test_research_durability_nested.py`, `pyproject.toml`, `uv.lock`, `docs/reports/external-ideas-2026-09.md`, earlier `.specify/specs/*`, and every `AGENTS.md` or stage doc line not named in T012. No activity is added. The user's uncommitted files in the primary checkout are not touched (the list is in plan.md Constraints; anything else `git status` shows modified there is also left alone). `CLAUDE.md` and `.specify/feature.json` are expected to differ: they are the spec-kit plan pointer and feature directory and ride the branch with the spec set in T001; no later task edits them.
- Tests use fakes, `TestModel`/`FunctionModel`, stub hosts and the local HTTP stub only. No real model call, no network beyond 127.0.0.1, no credentials.
- No file may exceed 1000 lines (`python scripts/check_file_size.py`).
- Line numbers in spec.md, plan.md and research.md are as of main `bcfbffc`; re-locate by symbol.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A spike probe on the branch base does not show the metadata workflow-side, or shows it in model-boundary content.
- **SG-2** An edit to a forbidden path, a new activity or a patch marker appears necessary.
- **SG-3** Any existing test fails after a change and this file does not name it as an intended edit. Do not edit it to pass. Never re-record or edit an existing history, golden or wire fixture.
- **SG-4** After T010 any committed history fails to replay (spec A1 was wrong).
- **SG-5** Wire layer 1 finds a differing path other than the tool-return `metadata` key or a differing tool definition; or layer 2 finds any byte difference.
- **SG-6** The captured history does not hold exactly one research `price_usage` equal to `REPORT`, or its two captures disagree. Fix the scenario, not the projection.
- **SG-7** `SDLC_CAPTURE_HISTORIES` is about to be set, or the capture test is about to run a second time on the branch.
- **SG-8** A test this file marks RED passes before its change, or a test marked PIN is red.
- **SG-9** The graph partial capture cannot be produced. The `FeatureWorkflow` fallback needs clearance.
- **SG-10** The negative control passes on the base commit.

## Phase order

| Phase | Purpose | Story | Plan | Commits |
|---|---|---|---|---|
| 1 Setup, baseline, probes | the channel still holds | — | Delivery 1 | 1 |
| 2 REDs | the three defects and the units, seen failing | US1, US2, US3 | D7, D5 | 0 (ride phases 3-5) |
| 3 Foundation: pure modules | report, reader, `add_spend` | — | D1 | 1 |
| 4 Tool side | the tool reports, is limited, degrades | US1, US3 | D2 | 1 |
| 5 Architect step | deps carry ceiling and limit | US2, US3 | D3 | 1 |
| 6 Harvest | the run accounts the spend | US1 | D4 | 1 |
| 7 Replay fixture | captured once, pinned | US1 | D5 | 1 |
| 8 Living docs and verification | — | — | D6 | 2 |

---

## Phase 1: Setup, baseline and probes on unmodified main (no source edits)

- [ ] T001 Create branch `architect-research-surface` from main in the worktree `kroker-dev` is bound to; confirm the container sees it at `/app` and syncs (`uv sync --frozen --extra dev --extra logfire`). Run `pytest` and `mypy` once each. Run the two spike probes as separate commands, each `MSYS_NO_PATHCONV=1 docker exec -i -w /app kroker-dev python - < .workspace/tmp/c12-spike/<script>` for `c12_e1_toolreturn_visibility.py` and `c12_e2_durable_roundtrip.py` (SG-1). Write, with the file tool, a third probe `.workspace/tmp/c12-spike/c12_e3_limit_and_parts.py` (not committed) and run it the same way: it prints `str(exc)` of a real `UsageLimitExceeded` raised by a `FunctionModel` agent that loops on a trivial tool under `UsageLimits(request_limit=2)` with a caller-owned `usage=RunUsage()`, the token counts left in that usage object, and the `part_kind` of the tool-return part of a `TestModel` run. Record in `.specify/specs/architect-research-surface/baseline.md`: the base sha, the fast-tier pass count, pre-existing failures, the mypy error count, the probe verdicts, the verbatim limit text (does it carry advice or a URL), the `part_kind` literal, whether the caller-owned usage is non-zero after the limit, and the line counts of `R/toolset.py`, `R/deps.py`, `src/sdlc/workflows/role_host.py`, `src/sdlc/stages/architecture/step.py`, `tests/durability/_http_stub.py` and `tests/replay/scenarios.py`. If `part_kind` is not `tool-return` or the usage is zero after the limit, stop (SG-1). Commit (spec set + baseline)

**Checkpoint**: baseline.md holds the base sha, counts and probe evidence; `git diff <base> --stat -- src` is empty.

---

## Phase 2: REDs (no source edits; nothing committed in this phase)

**Goal**: one failing test per defect (SC-001) and the unit REDs, each seen failing for the stated reason.

- [ ] T002 [US1] [US3] RED: create `tests/architecture/test_architect_research_report.py` with plan D7 report tests 1-10 and 8a, patching `sdlc.agents.roles.t_research`. Symbols that do not exist on the base commit (`research_subquery_reported`, `tool_return`, `SubRunUsage`, `metadata_for`) are imported **inside** the test functions that use them, never at module top, so the file collects on base and test 8a (base API: `research_subquery` with an inner `run(self, question, deps, **kwargs)` that raises `UsageLimitExceeded` must return a gap-only brief) fails there on behaviour, the exception escaping: that run is the SC-001 evidence for N3; and in `tests/architecture/test_architect_research_tool.py` widen `_ExhaustedAgent.run` to `run(self, question, deps, **kwargs)`, keeping every assertion. Test 3 raises `UsageLimitExceeded` with the verbatim message recorded in baseline.md and asserts the gap's `why_it_matters` and the summary both contain `request limit exhausted (<n> requests)` and contain neither `http` nor the library's advice text. Test 9 compares the architect `research` tool definition (name, description, parameters schema) with a literal taken from the base commit and asserts the annotation is `ResearchBrief`. Confirm on unmodified source: 8a fails on behaviour (`UsageLimitExceeded` escapes); 1-7 and 10 fail by import or attribute error (no `research_subquery_reported`, no `tool_return`, no `max_requests` field) and are not SC-001 evidence; 8 passes (PIN); 9 passes (PIN until T008, then must still pass); and `test_architect_research_tool.py` still passes. Save the run to `.workspace/tmp/c12-red-n3.txt`
- [ ] T003 [P] [US2] RED: create `tests/architecture/test_architect_research_deps.py` with plan D7 deps tests 1-3, driving `sdlc.stages.architecture.step.produce` with a stub context whose `run_role` captures the `deps` keyword and whose `cached_stage` calls the closure. The file imports base symbols only. Confirm on unmodified source: 1 fails on behaviour (deps carry 4.0, not 1.5; the SC-001 evidence for N2), 2 fails (no `max_requests` on deps), 3 passes (PIN: the serialized default payload equals a literal of today's). Save the run to `.workspace/tmp/c12-red-n2.txt`
- [ ] T004 [P] [US1] RED: create `tests/test_run_role_sub_run_harvest.py` with plan D7 harvest tests 1-8, in the style of `tests/test_run_role_guard.py`: a `RoleHost` subclass recording `_track_usage`, `temporalio.workflow.execute_activity` patched to record `price_usage` inputs and return a scripted price; results are small objects with `output`, `usage` and a `new_messages()` returning stub messages whose parts have `part_kind="tool-return"` and a `metadata` dict. Tests 7 and 8 use a host that also inherits `ReportHost`. Every report in this file is a **literal** metadata dict under the literal key `"sdlc_sub_run_usage"`; the file imports nothing that does not exist on the base commit, so it collects there. Confirm on unmodified source: 1, 2, 4, 7, 8 fail on behaviour (no research tracking, no research pricing; test 1 is the SC-001 evidence for 6.2), 3, 5, 6 pass (PIN). Save the run to `.workspace/tmp/c12-red-62.txt`
- [ ] T005 [P] [US1] RED: create `tests/test_sub_run_usage.py` per plan D7 and add the `add_spend` cases to `tests/test_role_usage.py`. The new `add_spend` cases import the function **inside** the test bodies, never at module top, so `tests/test_role_usage.py` still collects on unmodified source. Confirm on unmodified source: every new test fails (module and function absent); the existing tests in `tests/test_role_usage.py` pass
- [ ] T006 [P] [US1] PIN: in `tests/durability/_http_stub.py` add, additively, a `bodies` list that receives the raw body bytes of each handled POST (existing attributes and behaviour unchanged); create `tests/durability/test_sub_run_usage_wire.py` with layer 2 only (fast, no `temporal` mark): for the openai-chat mapping and the anthropic mapping build one `[user prompt, tool call, tool return]` history twice, the tool-return part's `metadata` being `None` and `{"sdlc_sub_run_usage": {...five fields...}}` (a literal here; T007 switches it to `metadata_for`), send each through the concrete model's public `request()` to the stub in `always_ok` mode, and assert the two recorded bodies are byte-equal and non-empty. Confirm it passes on unmodified source (SG-5 if not), and that `pytest -m temporal tests/durability/test_single_retry_layer.py` and `pytest -m temporal tests/durability/test_zai_route.py` still pass with the stub edit

**Checkpoint**: every RED is seen failing for its stated reason; every PIN is green; nothing under `src/` or `agents/` has changed.

---

## Phase 3: Foundation — the pure modules (blocks phases 4 and 6)

- [ ] T007 Implement plan D1. Create `src/sdlc/observability/sub_run_usage.py` (no `temporalio`, no `pydantic_ai`, no stage import): `SUB_RUN_USAGE_KEY = "sdlc_sub_run_usage"`; frozen pydantic model `SubRunUsage` (`model: str`; `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`: `int`, `ge=0`); `from_run_usage(run_usage, model) -> SubRunUsage | None` (`None` when input and output are both zero; counts coerced with `or 0`); `metadata_for(report) -> dict` returning `{SUB_RUN_USAGE_KEY: report.model_dump(mode="json")}`; `harvest_reports(result) -> list[SubRunUsage]`, duck-typed and total as in research R5 (`getattr` for `new_messages`, `parts`, `part_kind == "tool-return"`, `metadata` a dict holding the key, `model_validate` per part with a failure skipping the part, zero-token reports dropped, an outer `except Exception` returning `[]`). In `src/sdlc/observability/usage.py` add `add_spend(bag, *, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd)`: adds the four counts and, when `cost_usd is not None`, the dollars; never touches `bag.model` or `bag.calls`. Switch the literal in `tests/durability/test_sub_run_usage_wire.py` to `metadata_for(...)`. T005 goes green except its one end-to-end case, which needs `tool_return` and stays red until T008. Run, as separate commands: `pytest tests/test_sub_run_usage.py`; `pytest tests/test_role_usage.py`; `pytest tests/durability/test_sub_run_usage_wire.py`; `ruff check .`; `mypy`. Commit T005 (with the end-to-end case marked `xfail(strict=True, reason="needs tool_return, T008")`), T006 and T007 together

**Checkpoint**: the key, the payload and the reader exist and are tested; no behaviour has changed.

---

## Phase 4: User Stories 1 and 3 — the tool reports, is limited, and degrades (P1, P2)

**Goal**: the tool returns the brief with a report beside it, bounds its inner run, and degrades a limit stop with a clean text (FR-001, FR-007, FR-008, FR-009; plan D2).

**Independent test**: `pytest tests/architecture/test_architect_research_report.py`.

- [ ] T008 [US1] [US3] Implement plan D2. In `src/sdlc/stages/research/deps.py`: `DEFAULT_MAX_REQUESTS = 40`; `max_requests: int = Field(default=DEFAULT_MAX_REQUESTS, ge=1)` with a docstring (bounds the architect tool's inner run only; the stage path passes its own limit); extend the existing wrap serializer to also drop `max_requests` while it equals the constant. In `src/sdlc/stages/research/toolset.py`: add `research_subquery_reported(deps, question) -> tuple[ResearchBrief, SubRunUsage | None]` holding the logic (`RunUsage()` and `UsageLimits(request_limit=deps.max_requests)` passed as `usage=` and `usage_limits=`; `model=deps.research_model` only when set; `except BudgetExceeded` with today's text byte for byte; `except UsageLimitExceeded` with `reason = f"request limit exhausted ({deps.max_requests} requests)"` as the gap's `why_it_matters` and `f"Research stopped before this sub-question could be answered: {reason}"` as the summary, never `str(exc)`; one private gap-brief builder for both; the report on all three paths from `from_run_usage(run_usage, model)` with `model = deps.research_model or REGISTRY["research"].model or "unknown"`, the registry imported lazily); turn `research_subquery` into the wrapper returning the brief, signature unchanged, docstring saying only tests call it now; add pure `tool_return(brief, report)` returning the bare brief when `report is None`, else `ToolReturn(return_value=brief, metadata=metadata_for(report))`; correct the module docstring. In `agents/architect/agent.py`: the `research` tool body becomes the reported call followed by `return tool_return(brief, report)`; annotation stays `-> ResearchBrief`; nothing else changes. Remove the `xfail` from T005's end-to-end case. In `tests/durability/test_sub_run_usage_wire.py` add layer 1 (`temporal`-marked): twin durable stand-ins in the `tests/durability/test_provider_payload_parity.py` shape (module-level agents, `TemporalDurability` + `ResolveModelId`, a recording `TestModel`), one tool returning the bare brief and one `tool_return(brief, REPORT)`; assert the recordings are equal after removing exactly the tool-return `metadata` key, that the set of differing JSON paths is exactly that key, and that the two agents' tool definitions are equal (SG-5). T002 goes green. Run, as separate commands: `pytest tests/architecture`; `pytest tests/test_sub_run_usage.py`; `pytest tests/research`; `pytest tests/test_model_forwarding.py`; `pytest -m temporal tests/durability/test_sub_run_usage_wire.py`; `pytest -m temporal tests/research/test_research_durability_nested.py`; `pytest -m temporal tests/test_model_forwarding.py`; `pytest tests/replay`; `mypy`. Commit T002 and T008 together

**Checkpoint**: US3 holds; the tool reports; nothing harvests yet, so run accounting is unchanged and every history still replays.

---

## Phase 5: User Story 2 — the architect's research honours the configured bounds (P1)

**Goal**: FR-006, FR-007; plan D3.

**Independent test**: `pytest tests/architecture/test_architect_research_deps.py`.

- [ ] T009 [US2] [US3] Implement plan D3 in `src/sdlc/stages/architecture/step.py`: `architect_deps` gains `max_run_cost_usd=cfg.research.max_run_cost_usd` and `max_requests=max(1, cfg.research.max_requests)`. Nothing else in the file changes. T003 goes green. Run, as separate commands: `pytest tests/architecture`; `pytest tests/replay`; `pytest -m temporal tests/durability/test_wire_neutrality.py`; `pytest -m temporal tests/durability/test_provider_payload_parity.py`. Commit T003 and T009 together

**Checkpoint**: US2 holds; the default-config deps payload is unchanged.

---

## Phase 6: User Story 1 — the run accounts the spend (P1)

**Goal**: FR-003, FR-004, FR-005; plan D4.

**Independent test**: `pytest tests/test_run_role_sub_run_harvest.py`.

- [ ] T010 [US1] Implement plan D4 in `src/sdlc/workflows/role_host.py`. Extract today's price block into `async def _price(self, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens) -> float | None` (the same `workflow.execute_activity(price_usage, PriceUsageInput(...), **PRICE_ACT)` inside `try/except Exception: return None`); the architect's own pricing calls it under its existing `if u.input_tokens or u.output_tokens` guard, so its command is unchanged. After the architect's own `_track_usage` and before `return result`: `reports = harvest_reports(result)`; if empty do nothing; group by model in first-seen order and sum the four counts; `usd[model] = await self._price(model, <sums>)` once per distinct model; for each report in message order call `self._track_usage(role="research", model=report.model, <its counts>, cost_usd=<share>, into=None)` where the share is `usd[model]` for the first report of that model, `0.0` for later reports of the same model, and `None` for every report of a model whose batch is unpriced; then, if `into is not None`, per distinct model `add_spend(into, <sums>, cost_usd=usd[model])`. Never `merge_usage` into `into`; never `_track_usage(..., into=into)` for a report. Add the two imports to the existing `workflow.unsafe.imports_passed_through()` block. No patch marker. T004 goes green. Run, as separate commands: `pytest tests/test_run_role_sub_run_harvest.py`; `pytest tests/test_run_role_guard.py`; `pytest tests/replay` (SG-4); `pytest tests/graph_workflow`; `pytest tests/integration/test_feature_host_mixins.py`; `pytest -m temporal tests/replay`; `pytest -m temporal tests/durability/test_priced_usage_parity.py`; `pytest`; `mypy`. Commit T004 and T010 together

**Checkpoint**: US1 holds at the unit level; every committed history still replays with zero re-recorded files.

---

## Phase 7: User Story 1 — the replay fixture, captured once (P1)

**Goal**: FR-010, SC-005; plan D5.

**Independent test**: `pytest tests/replay/test_architect_research_usage_replay.py`.

- [ ] T011 [US1] Create `tests/replay/architect_research_usage.py` (not a test module) per plan D5, modelled on `tests/replay/research_retain.py` and on `_architect_research_activities` in `tests/replay/scenarios.py` (read, not edited): `NAME = "architect_research_usage"`; `REPORT = SubRunUsage(...)` with non-zero counts; a module-built architect fake with the same agent name `architect_agent`, deps type, output type, capabilities and tool name and signature, whose own `research` tool returns `ToolReturn(return_value=RESEARCH_BRIEF_FAKE, metadata=metadata_for(REPORT))` (built inline, so the module depends on the pure `sub_run_usage` module only and can be copied onto the base commit for the negative control); `activities()` = the `architect_research_tool` scenario's registrations with every registration belonging to `architect_agent` dropped by activity name, plus the new fake's `temporal_activities`; `drive` = `answer_clarify` then `wait_for(handle, "awaiting:architecture")`; `SCENARIO = Scenario(NAME, greenfield_idea, <the architect_research_tool scenario's cfg>, activities, drive, before=reset_deploy, mode="partial", golden=False)`, **not** added to `SCENARIOS`. Create `tests/replay/test_architect_research_usage_replay.py` with plan D5 tests 1-4: (1) replay with `tests.replay.test_feature_replay.replayer(GraphWorkflow, DeploymentWorkflow)`; (2) PIN, with the plan's identification rule: walking the scheduled activities in order, the architect's own `price_usage` is the first `price_usage` scheduled after the architect agent's final `model_request` activity, and the research one is the `price_usage` scheduled immediately after it; decode inputs as `PriceUsageInput` with `pydantic_data_converter.payload_converter.from_payloads` (the pattern in `tests/replay/test_research_retain_replay.py`); assert the research input's model and four counts equal `REPORT`, the architect's own input does not equal `REPORT`, and across the whole history exactly one `price_usage` input equals `REPORT`; `source_commit` has 40 characters; `workflow == "GraphWorkflow"`; (3) capture, `temporal`-marked, skipped unless `SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE == "1"`: captures `SCENARIO` twice with `capture(SCENARIO, GRAPH_STARTER, monkeypatch, <dir>, sandboxed=True)`, asserts equal `commands` projections (SG-6), writes **only** `tests/replay/histories/architect_research_usage.json` in the JSON shape `harness.write_fixtures` uses for a history (`workflow_id`, `workflow`, `source_commit`, `history`), never calling `write_fixtures`. Run the capture **once** (SG-7, SG-9): `SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE=1 pytest -m temporal tests/replay/test_architect_research_usage_replay.py::test_capture_architect_research_usage_history`. Then `pytest tests/replay/test_architect_research_usage_replay.py` (tests 1 and 2 green). Add test (4), fast, committed, PIN: the shape check of test 2, applied to the committed report-less history `architect_research_tool.json`, reports no research `price_usage` (the pin distinguishes a harvested history from an unharvested one). **Negative control** (SG-10, evidence only, never committed): `git worktree add --detach <scratch dir outside the repo> <base sha>`; copy into it the two new replay modules and `src/sdlc/observability/sub_run_usage.py`; run the capture switch there and then test 2 against the file it writes; confirm test 2 fails for lack of a research `price_usage`; save the output to `.workspace/tmp/c12-negative-control.txt`; `git worktree remove` the scratch directory. `kroker-dev` is bound to one worktree: how the scratch worktree is mounted is the orchestrator's call at exec, so ask before starting it. If it cannot be mounted, test (4) stands as the control and verification.md says so. Run `pytest tests/replay`, `git status --short tests/replay/histories tests/replay/golden tests/replay/fixtures tests/durability/fixtures` (only the one added file) and `python scripts/check_file_size.py`. Commit

**Checkpoint**: the with-report command sequence is pinned; zero existing fixtures changed.

---

## Phase 8: Living docs and verification

- [ ] T012 Apply the four doc edits with the exact wording of plan D6: one sentence appended to the "Single model egress" section of `src/sdlc/workflows/AGENTS.md`; the appended sentence in the "Model forwarding (004)" bullet and the reworded clause in the third "Budget enforcement" bullet of `src/sdlc/stages/research/AGENTS.md`; one bullet after the `scope="architect"` bullet in `src/sdlc/stages/architecture/AGENTS.md`; one failure-mode line after "Budget exhaustion" in `src/sdlc/stages/architecture/architecture.md`. Nothing else in those files. If any sentence is no longer true of what landed, stop and send the corrected wording to the orchestrator before committing. Commit
- [ ] T013 Run quickstart.md sections 1 to 7 as separate commands and record in `.specify/specs/architect-research-surface/verification.md`: each command's result; the three SC-001 tests red before (`.workspace/tmp/c12-red-62.txt`, `c12-red-n2.txt`, `c12-red-n3.txt`) and green after; both wire layers; the fixture's `source_commit` and its decoded research `price_usage` input; the negative-control output; `git status --short` of the four fixture directories showing only the one added file; the pass-count delta and mypy count against baseline.md; the empty forbidden-path diff (`git diff <base> --stat -- <each forbidden path>`); the line counts of every edited file; whether the graph capture or the fallback was used; and the per-task commit shas. Commit

---

## Dependencies

- T001 first; T013 last.
- T002, T003, T004, T005, T006 need only T001. T003, T004, T005 and T006 are `[P]`: different files, no shared state.
- T007 needs T005 and T006 seen (red and green respectively). It blocks T008 and T010.
- T008 needs T002 seen red and T007. T009 needs T003 seen red and T008 (the deps field). T010 needs T004 seen red and T007; it is ordered after T009 so each commit's regression runs see one change.
- T011 needs T010 green (the history must contain the harvest's command).
- T012 needs T011 (it describes what landed).

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001, SC-002 | T006 (layer 2), T008 (layer 1, report tests 7, 9) |
| FR-002 | T005, T007 |
| FR-003, SC-003 | T004 (1, 2, 4, 7, 8), T010 |
| FR-004 | T005 (`add_spend`), T004 (2), T007, T010 |
| FR-005, SC-004 | T004 (3, 6), T002 (7), T010 regression runs |
| FR-006 | T003 (1, 3), T009 |
| FR-007 | T002 (2, 10), T003 (2, 3), T008, T009 |
| FR-008 | T002 (3, 4, 5), T008; T001 (the leak, measured) |
| FR-009 | Standing rules; T002 (4, 8, 9); regression runs in T008 |
| FR-010, SC-005 | T010 (existing histories), T011 |
| FR-011 | T008 (docstrings), T012 |
| FR-012 | T011 and T013 (`check_file_size.py`) |
| SC-001 | on behaviour, base API: 6.2 T004 (1); N2 T003 (1); N3 T002 (8a). API-level: T002 (1, 3, 5) |
| SC-006 | T013; edited existing tests: `test_architect_research_tool.py` (T002), `_http_stub.py` (T006), `test_role_usage.py` (T005, additions only) |
| Edge cases | EC1 T004 (6); EC2 T004 (reader uses `new_messages`), T005; EC3 T002 (3, 4); EC4 none (residual R1); EC5 T004 (4); EC6 T002 (6); EC7 T004 (3), T010 replay runs |
| Amendments | AM1 T006, T008; AM2 T001, T002 (3), T008; AM3 T004 (2), T010; AM4 T002 (10), T003 (2), T008, T009 |
| Rulings | no patch marker: T010; `AGENTS.md` wording: T012; capture last: T011; negative control: T011, T013 |

## Implementation strategy

US3 and the tool half of US1 land first (T008) and are safe alone: an unharvested report is ignored. US2 (T009) is independent of the harvest. US1 completes at T010 and is pinned at T011. If T001's probes fail the feature stops with nothing under `src/` touched.

**Totals**: 13 tasks — setup 1, REDs 5, foundation 1, tool side 1, step 1, harvest 1, replay 1, docs and verification 2. Eight commits (baseline; pure modules; tool side; step; harvest; replay fixture; docs; verification).
