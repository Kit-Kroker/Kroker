# Research: Architect Research Surface

Baseline: anchors read on main `bcfbffc`; main is now `e5c8ef8` (one docs-only commit later). `R/` = `src/sdlc/stages/research/`.

Evidence tiers: **measured** (run in `kroker-dev`), **read** (seen in code, not run), **inferred**. Nothing in this file was run by the planner. The spike's measurements (`.workspace/tmp/c12-spike/FINDINGS.md`) are measured-by-the-spike and are re-run as the first task. Consults: advisor `.workspace/tmp/advisor-c12-1.md`, skeptic `.workspace/tmp/skeptic-c12-1.md`; orchestrator resolutions 1-9 of 2026-10-05.

## R1 — Where the report is built (FR-001, FR-002, FR-009)

- **Decision** (advisor OPEN-1, adopted verbatim): in `R/toolset.py`
  - `research_subquery_reported(deps, question) -> tuple[ResearchBrief, SubRunUsage | None]` holds all the logic;
  - `research_subquery(deps, question) -> ResearchBrief` keeps its exact contract as a thin wrapper; its docstring says only tests call it now;
  - `tool_return(brief, report) -> ResearchBrief | ToolReturn`, pure: the bare brief when `report is None`, else `ToolReturn(return_value=brief, metadata=metadata_for(report))`.
  - `agents/architect/agent.py`'s tool calls the reported function and returns `tool_return(...)`. Its annotation stays `-> ResearchBrief`.
- **Rationale** (read):
  - Three tests call `research_subquery` directly and use the result as a brief (`tests/architecture/test_architect_research_tool.py:90`, `tests/test_model_forwarding.py:343`, `tests/research/test_research_durability_nested.py:90`). The wrapper keeps their assertions (skeptic B1).
  - The annotation must not become `ToolReturn[ResearchBrief]`: a parameterized `ToolReturn[T]` generates a return schema and would change the tool definition the model receives (pydantic-ai `messages.py:1015-1019`, read by the advisor).
  - A bare brief when there is nothing to report makes the no-report path today's code path.
- **Forced test edit**: `_ExhaustedAgent.run(self, question, deps)` (`test_architect_research_tool.py:80`) must accept `**kwargs`; the inner run now receives `usage_limits=` and `usage=`. Its assertions stay. The other two direct callers use real agents and need no edit.
- **Alternatives considered**: `research_subquery` returning `ToolReturn` or a tuple (two more test modules edited, the slice's second entry point changes type).

## R2 — The shared home of the key and payload (FR-002)

- **Decision** (advisor OPEN-4): new pure module `src/sdlc/observability/sub_run_usage.py`: `SUB_RUN_USAGE_KEY = "sdlc_sub_run_usage"`; `SubRunUsage` (frozen pydantic model: `model: str`, four token counts `int`, `ge=0`); `from_run_usage(run_usage, model)`; `metadata_for(report)` returning `{KEY: report.model_dump(mode="json")}`; `harvest_reports(result)`. No `temporalio`, no `pydantic_ai`, no stage import.
- **Rationale** (read): the key is needed activity-side and workflow-side. `observability/usage.py` imports `temporalio.workflow` and benchmark models at module level (`:7-12`), heavier than the tool needs. A research-slice module would make the generic host depend on one stage. `core/models.py` carries the user's uncommitted work.
- **Sandbox**: the metadata is a plain dict built with `model_dump(mode="json")`; after the durable round trip the workflow validates a dict, so no class instance crosses the boundary and the sandbox pydantic-duplication trap does not apply. The module is imported inside `role_host.py`'s existing passed-through block.

## R3 — The answering model id (FR-002, EC6; advisor OPEN-2)

- **Decision**: `deps.research_model` when set; else `REGISTRY["research"].model`, read lazily as `R/stage.py:289-292` does; else the sentinel `"unknown"` (already used: `tests/replay/research_retain.py:76`), which prices to no dollars.
- **Rationale** (read): `forwarded_model()` returns an override only when it differs from the registry (`agents/model_ids.py:186-204`), so "unset" means the registry model answered. The label equals what the stage path uses (`resolve_role_model(cfg, "research")`), so research rows from both paths carry one label.
- **Report is `None`** when the caller-owned usage has zero input and zero output tokens (mirrors `R/stage.py:316`): a call refused before any request stays silent.

## R4 — Deps (FR-006, FR-007; N2, N3; advisor OPEN-3, skeptic m1, m2)

- **Decision**: in `R/deps.py`, `DEFAULT_MAX_REQUESTS = 40` and `max_requests: int = Field(default=DEFAULT_MAX_REQUESTS, ge=1)`; the existing wrap serializer (`:72-79`) also drops `max_requests` while it equals the constant. In `architecture/step.py`, `architect_deps` gains `max_run_cost_usd=cfg.research.max_run_cost_usd` and `max_requests=max(1, cfg.research.max_requests)`.
- **Rationale** (read):
  - Omitted on dump, defaulted on load: lossless. Default-config architect payloads stay byte-identical. `max_run_cost_usd` is always serialized and is `4.0` at both defaults (`R/deps.py:58`, `core/models.py:289`).
  - `ResearchConfig.max_requests` has no lower bound (`core/models.py:301`, not editable here); a 0 would build a limit that stops before the first request. The clamp carries it as 1.
  - The stage path ignores the field: it passes its own limit (`R/stage.py:273`) and builds deps without it (`R/step.py:241`), so its activity inputs do not change. The field's docstring says it is for the architect tool only.
- **Hazards, each pinned by a test**: default drift (deps default equals `ResearchConfig().max_requests`); round trip for 40 and for another value; byte identity of the default payload.
- **Rolling deploy** (inferred): an old worker ignores an unknown `max_requests` key and falls back to the library default until upgraded. Accepted.
- **Rejected**: `int | None = None` meaning the library default: that is 50, not the stage path's 40, and keeps an unbounded-by-us path.

## R5 — Harvest, pricing and fold (FR-003, FR-004, FR-005; Q2 = A, Q3 = A; skeptic B2, M2, M3)

- **Decision**, in `RoleHost._run_role`:
  1. The existing price-then-`try/except` block becomes a private `_price(model, counts) -> float | None` used by the architect's own pricing and by the harvest. The command it issues for the architect call is unchanged.
  2. After the architect's own `_track_usage`: `reports = harvest_reports(result)`.
  3. **Batch pricing** (skeptic M3): group reports by model in first-seen order, sum the four counts, and call `_price` **once per distinct model**.
  4. **Per-report accounting**: for each report in message order, `_track_usage(role="research", model=<its model>, <its counts>, cost_usd=<see below>, into=None)`.
  5. **Fold**: once per distinct model, if `into is not None`, `add_spend(into, <summed counts>, cost_usd=<batch dollars>)`. Never `merge_usage`, never `_track_usage(..., into=into)` (skeptic B2).
- **Per-report dollars under batching**: one activity returns one number for a model's batch, but each report is tracked on its own. The batch's dollars are carried by the **first** report of that model; later reports of the same model carry `0.0`. If the batch is unpriced, every report of that model carries `None`. Totals per role, per activation and per stage bag are exact; the `all_priced` flag is right; only the split between same-model events inside one run is a convention. Stated in the plan for the orchestrator.
- **Tier caveat** (inferred, not checked): `genai_prices` prices from the counts it is given. If a model's price has token-count tiers, a summed batch can cross a tier that no single sub-run crossed. The outer run already prices a whole run's summed tokens the same way, so this is the existing convention widened, not a new one. Named as a residual.
- **`harvest_reports`** (advisor OPEN-5): duck-typed and total. `new_messages` via `getattr` and called only if callable; parts read with `getattr(m, "parts", ())`; a part counts only if `part_kind == "tool-return"` and its `metadata` is a dict holding the key; the payload is validated by `SubRunUsage.model_validate`, a failure skips that part; zero-token reports are dropped; any other exception returns `[]`. No `isinstance` against pydantic-ai classes (skeptic surface 5).
- **Why `new_messages()`**: no role call passes `message_history` (no match in `src/sdlc`), so it equals `all_messages()` today and stays right if a caller ever continues a conversation.
- **`add_spend`** in `observability/usage.py`: adds the four counts and, when not `None`, the dollars. Touches neither `model` nor `calls`. It is the only writer of a `RoleUsage` outside `merge_usage`; no row of the `workflows/AGENTS.md` ownership table changes (the bag is caller-held, not an attribute).
- **Other consumers** (advisor OPEN-6, each read): `_check_budget` sums `_role_usage` and now sees research dollars (intended); `_activation_spend` attributes them to the architect's activation; the retro rollup rebuilds roles from `MODEL_USAGE` events and stays equal to `_role_usage` because the fold emits none; the benchmark cost bag gains tokens and dollars with label and calls unchanged; `test_priced_usage_parity.py` compares a frozen no-report history and is unaffected; a cache hit returns before the closure runs.

## R6 — No patch marker (orchestrator ruling 8a)

`workflows/AGENTS.md` "Grace edits" says an edit that changes the command sequence of code `FeatureWorkflow` executes must be wrapped in `workflow.patched`. The harvest adds `price_usage` commands only when the run's messages hold a report. Only activity code from this change can put a report there, so no history recorded before the change can reach the new branch: it replays with zero added commands. A marker taken unconditionally would add a marker command to every new history; taken only on the report branch it would guard a branch no old history can enter. **Ruling: no marker.** Enforcement: every committed history, unedited, still replays; the new captured-once history pins the with-report sequence.

## R7 — Replay coverage (FR-010; Q5 = A; advisor OPEN-7)

- **Decision**: standalone `tests/replay/architect_research_usage.py` and `tests/replay/test_architect_research_usage_replay.py`, one new history `tests/replay/histories/architect_research_usage.json`. Not in `SCENARIOS`, no golden. `tests/replay/scenarios.py` (907 lines by `check_file_size.py`) is not edited.
- **Workflow**: `GraphWorkflow`, `partial` mode, driven through clarify to `awaiting:architecture` (the architect round and its harvest have run by then). Read: `harness.capture` supports `GRAPH_STARTER` and `partial` (`tests/replay/harness.py:65-115,185`); `test_graph_golden.py:44-49` drives a graph run to `awaiting:architecture`; `test_feature_replay.replayer(*workflows)` accepts the graph workflow classes. Reason: `FeatureWorkflow` is grace-retained and a fixture bound to it dies with it; the harvest lives in the shared host and `GraphWorkflow` survives.
- **Fallback**: if graph partial capture cannot be made to work, a `FeatureWorkflow` scenario shaped like `architect_research_tool`, recorded as grace-lifetime in `verification.md`. Taking the fallback is a stop-guard report, not a silent choice.
- **Captured once, after the harvest is green**. A history recorded before would hold the report but not the pricing command.
- **Honest RED**: the replay row cannot be red first. The REDs are the live tests of R5 and the tool. The fixture-shape pin is given teeth by a **negative control**: run the capture switch in a detached worktree of the base commit with the test modules copied in, show the shape pin fails on that file, record the output in `verification.md`, discard the file. Never committed.
- **A1 confirmed** by both consults: `architect_research_tool.json`, the T29 parity fixture, the wire-neutrality fixture and the priced-usage parity run do not drift.

## R8 — Wire neutrality (FR-001, SC-002 as amended; advisor OPEN-8)

- **Layer 1** (`temporal`): twin durable architect stand-ins in the `test_provider_payload_parity.py` shape, one tool returning the bare brief and one returning `tool_return(brief, report)`. Assert: recordings equal after removing exactly the `metadata` key of tool-return parts; the set of differing JSON paths is exactly that key; the tool definitions (name, description, parameters schema, return schema if present) are equal.
- **Layer 2** (fast): `tests/durability/_http_stub.py` reads and discards request bodies today (`:109-111`); extend it additively to also keep the raw body bytes. For the openai-chat mapping (the route `zai:glm-5.3` uses) and the anthropic mapping: build one history `[user prompt, tool call, tool return]` twice, with metadata `None` and with a report, call the concrete model's public `request()` once each against the stub in `always_ok` mode, assert the two recorded bodies are byte-equal.
- **Payload guard** (skeptic surface 4, read): `payload_guard.py:86-90` measures the dumped messages, which include the metadata: about 100 bytes against 1 MiB. No effect.

## R9 — The limit degrade text (FR-008, AM2; skeptic M1)

- **Decision**: on `UsageLimitExceeded` the tool builds one text of its own, `f"request limit exhausted ({deps.max_requests} requests)"`, used for the gap's `why_it_matters` and inside the summary. `str(exc)` is not used.
- **Rationale**: the skeptic reports from a live probe that `str(UsageLimitExceeded)` carries the library's advice and documentation URL, which would enter the architect's context through the brief (008 A1 cut the same text on the stage path). The first task prints `str(exc)` of a real `UsageLimitExceeded` so the mitigation is evidence-backed.
- The `BudgetExceeded` degrade keeps today's text byte for byte through a shared private gap-brief builder.

## Consult disposition

| Point | Source | Disposition |
|---|---|---|
| OPEN-1 hybrid, wrapper kept, `tool_return()`, bare brief when no report | advisor | adopted verbatim (R1) |
| B1 contract break | skeptic | resolved by R1 |
| B2 never `merge_usage` into the caller's bag | skeptic | adopted (R5) |
| M1 limit text leaks library advice | skeptic | adopted (R9, spec AM2) |
| M2 pricing outside a `try` | skeptic | resolved by the shared `_price` (R5) |
| M3 one pricing activity per distinct model | skeptic | adopted (R5, spec AM3) |
| m1 zero limit | skeptic | adopted: `ge=1` and clamp (R4, spec AM4) |
| m2 default drift | skeptic, advisor | adopted: constant plus pin test (R4) |
| m3 architect row has no per-model breakdown | skeptic | accepted trade-off of Q3 = A |
| OPEN-2 `"unknown"` sentinel | advisor | adopted (R3) |
| OPEN-3 omit-when-default, not optional | advisor | adopted (R4) |
| OPEN-4 pure module in `observability/` | advisor | adopted (R2) |
| OPEN-5 `new_messages()`, duck-typed, total | advisor | adopted (R5) |
| OPEN-6 consumer table | advisor | adopted as tests (plan D7) |
| OPEN-7 capture after green, graph partial, negative control | advisor | adopted (R7) |
| OPEN-8 two layers, extend the stub | advisor | adopted (R8, spec AM1) |
| Grace-edit rule needs a ruling | advisor | ruled: no marker (R6) |
| One sentence in `workflows/AGENTS.md` | advisor | approved in principle; wording in plan D6 |
| Do not mirror 008 D4 on the tool path | advisor | adopted: out of scope |
| Advisor hypotheses (`part_kind` literal; `FunctionModel` usage non-zero) | advisor | confirmed in the first task, not assumed |

## Residuals

- **R1 (spec)**: spend made by an attempt that raises is lost, as today. The limit degrade makes it strictly rarer (skeptic surface 10).
- The tool path does not mirror 008's degrade-once for `UnexpectedModelBehavior`.
- The stage path's deps carry an unused, never-serialized `max_requests`.
- Batch pricing: the per-event dollar split between same-model reports is a convention; a tiered price could differ from per-sub-run pricing (R5).
- An old worker during a rolling deploy ignores the new deps key (R4).
- `research_subquery` is production-dead after this change; kept for its three tests.
