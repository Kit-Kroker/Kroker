# Pydantic AI 2.20 → 2.51 and Harness 0.13 → 0.36 — what the upgrade gives Kroker

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD or ROADMAP line. |
| Date | 2026-09-27 |
| Versions | From `uv.lock`: `pydantic-ai-slim` **2.20.0**, `pydantic-ai-harness` **0.13.0**. To: **2.51.0** / **0.36.0** (0.36 requires core `>=2.44`). |
| Companions | `2026-09-27-pydantic-ai-harness-comparison.md` (defects §3, pinning §6.5), `2026-09-27-pydantic-ai-capability-adoption-map.md` (landing zones, waves), `2026-09-27-pydantic-evals-for-kroker.md`. |
| Method | Read every release note: Harness v0.14–v0.36 and core v2.21–v2.51. Every feature below was located in the 0.36 / 2.51 wheel code and compared with what is importable in the installed 0.13 / 2.20 venv (column **0.13?**). Kroker anchors were read on `main` plus the working tree. Tests: one fast unit-tier run on the target versions (§6); the `temporal` tier was not run. |

## 1. What the transition is

It is three things.

1. **A pin plus one fix, which is the transition proper.**
   - Only the uv-synced dev venv is on 2.20 / 0.13. CI and the Docker image install without the lock and already run the newest releases: the last CI run installed 2.49 / 0.34.
   - Finishing the move means:
     - one required code fix: a stale failure-type list, §4 row R1, which has kept CI red since 2026-09-17;
     - pinning to 2.51 / 0.36 and installing from the lock;
     - deciding four behaviour changes that arrive by themselves (§3).
2. **Features that arrive for free:**
   - four security fixes, two of them on the operator chat;
   - fail-fast on malformed model responses and oversized results;
   - complete telemetry redaction;
   - a cached agent graph.
3. **Features that become possible.** This is the bulk of the value, laid out in §2 by Kroker area:
   - proposers (§2.1);
   - cost (§2.2);
   - research (§2.3);
   - graph (§2.4);
   - operator chat (§2.5);
   - the doer, i.e. `Coder`'s parts, with `verify` and `smoke` (§2.6);
   - research integrations and external systems: `Researcher`, Exa, web search and fetch, GitHub, Linear, Slack, Logfire MCP (§2.7).

   Most rows need a module or parameter that is **absent** from the installed 0.13 / 2.20: `Coder`, `Researcher`, `PlaywrightBrowser`, every hosted MCP integration, `ToolGuardrail`, `Planning(store=…)`, `FileSystem` events and `read_only`, `Shell.max_file_bytes`, `@durable_operation`, `cost_limit`, `resolve_context_window`. That covers most of the adoption map's wave 1 and the pyai doer of comparison §6.10. So the upgrade is not an alternative to those reports; it is their step zero.

## 2. Feature map by Kroker area

Column guide:

- **Today** — the Kroker module and how it works now.
- **Module** — the Pydantic AI or Harness module that serves the area in the target versions.
- **What arrives** — the feature, with the version it shipped in.
- **0.13?** — is it importable at the locked versions? (checked)
- **Change** — the edit in Kroker.
- **Gain** — what gets better, tied to a known defect or report item where one exists.

### 2.1 Durable proposers: the 14 stage roles and the 2 clarify fan-out agents

| # | Today | Module | What arrives | 0.13? | Change | Gain |
|---|---|---|---|---|---|---|
| 1 | Each agent is built by `agents/<role>/agent.py::build()`, then wrapped in the deprecated `TemporalAgent` (`src/sdlc/agents/roles.py:214–268`) | `pydantic_ai.durable_exec.temporal.TemporalDurability` | The durability *capability*, which carries the full kwarg set: `models`, `name`, `activity_config`, `model_activity_config`, `toolset_activity_config`, `event_stream_handler`, `event_stream_topic` (2.46), `run_context_type` | yes (without `event_stream_topic`) | Attach `TemporalDurability(activity_config=AGENT_ACTIVITY_CONFIG, models=…)` in `build()` through the loader contract. Names stay as they are ("NEVER rename"). | Removes the dependency on a class slated for deletion in v3. **It is also the switch every durability-aware feature below looks for**: `RunContext.in_durable_context` (2.50), `@durable_operation` dispatch, the replay-safe `SpendLimits` / `StepPersistence`, and CodeMode's eager/speculate guard. Under `TemporalAgent` all of them see "not durable". |
| 2 | Per-run model override (`--role-model`, benchmark arms) is resolved and priced but **never passed** to `agent.run` (`role_host.py:135`; comparison §3.1) | `pydantic_ai.capabilities.ResolveModelId` + `run(model=)` | `ResolveModelId(resolver)`: `resolver(ctx: ModelResolutionContext(agent, deps), model_id) -> Model \| None`, sync or async; `None` falls through to `infer_model` | yes | Pass `model=` from `_run_role`. Add one runtime `ResolveModelId` that turns registry ids into `Model` objects. | The model × role sweep becomes real for proposers. Cost, cache key and the ADR-6 verdict finally describe the model that answered. |
| 3 | SDK retries under Temporal retries: 2 × 3 = up to 9 HTTP calls per request (comparison §3.4) | the same `ResolveModelId` + `pydantic_ai.providers` on **anthropic 1.x / openai 3.x (httpx2)** | Providers built by Kroker with an explicit client: `max_retries=0`, the endpoint URL, timeout | yes (API) / **no** (SDK generation) | Build the providers inside the resolver against the 1.x/3.x SDKs. Any custom `http_client` must be `httpx2.AsyncClient` (2.33). | One retry layer (Temporal) with bounded attempts. `Retry-After` is honoured by one owner. |
| 4 | GLM roles routed as `anthropic:glm-5.2` through an Anthropic-compatible endpoint (`agents/*/agent.yaml`, 11 roles) | `pydantic_ai.providers.zai` / `profiles.zai` | A native Z.AI provider: `glm-5.3` (2.34), mapped `finish_reason` values (2.37), `reasoning_effort` for GLM-5.2/5.3 in the profile | partly | Return a Z.AI model for `glm-*` from the resolver (row 2). | Thinking and finish reasons mapped by a GLM profile instead of Anthropic's guess. **Cost note:** `genai-prices` 0.1.9 prices `zai:glm-5.2` 23% above `anthropic:glm-5.2` for the same tokens. Mark that as a pricing break in benchmark history. |
| 5 | Reasoning depth only through `MODEL_SETTINGS` (`src/sdlc/agents/settings.py`), the same for all roles | `pydantic_ai.capabilities.Thinking` | `Thinking(effort=False \| 'minimal' … 'xhigh')`, provider-mapped | yes | Add a per-role `thinking:` key in `agent.yaml`, passed by the loader: high for architect, planner, deep_review, adversary; off for handoff and probes. | Depth where it pays; cheaper single-shot roles. |
| 6 | Structured output breaks on long `DevTask[]` lists; the planner gets `retries={"output": 3}` (`agents/planner/agent.py:28`) | `pydantic_ai_harness.guardrails.OutputGuardrail` and the core `before_output_validate` hook | `OutputGuardrail(guard)`: the guard gets the **typed** output and returns allow / block / `replace` / `retry` (retry re-prompts with your message); chains 0.16 | base yes, chains **no** | 1) A planner guard: every `DevTask` names its test path in the description and in `contract.test_commands` (retro defect №20) → `retry`. 2) A small Kroker capability on `before_output_validate` running `json_repair` over truncated output JSON. | Deterministic contract checks before the plan reaches the gate. Fewer burned output retries. **Not** `RepairToolArguments`: it skips output tools (§5.2). |
| 7 | Secrets scrubbed by 4 regexes in `src/sdlc/memory/scrub.py` | `pydantic_ai_harness.guardrails.detectors` | `redact_secrets`, `secret_data`, `redact_personal_data`, `personal_data`, `DEFAULT_SECRET_PATTERNS` (vendor keys, private-key blocks, cards, IBAN) | **no** | `OutputGuardrail(redact_secrets)` in the runtime set of every proposer; `scrub.py` calls the same detectors. | One maintained pattern set for proposer outputs and memory. |
| 8 | A filtered or refused response surfaces as a half-output or a generic error | `pydantic_ai.capabilities.RaiseContentFilterError` | A typed error | yes | Add it to the runtime set. | Routes to the node's `fail` port as `AgentRunError` (it is in `FAILURE_TYPES`). |
| 9 | One `ActivityConfig` for all tools of an agent (`roles.py:37`) | `pydantic_ai.capabilities.SetToolMetadata` / per-tool `metadata={'temporal': …}` | Per-tool activity config on the capability path (the replacement for `tool_activity_config=`) | yes | Architect's `research` tool gets a long timeout; cheap tools keep short ones. | Timeouts per tool class instead of a worst-case single value. |

### 2.2 Cost, budget and payload size

| # | Today | Module | What arrives | 0.13? | Change | Gain |
|---|---|---|---|---|---|---|
| 10 | E-33: `price_usage` activity (`src/sdlc/pricing.py`) plus the workflow budget gate (`role_host.py:165`) | `pydantic_ai.usage` | `RunUsage.cost` (2.23), `UsageLimits(cost_limit=…)` (2.23) | **no** | Keep `price_usage` as the replay-safe record. Add `cost_limit` per proposer run as a **hard stop inside a single run**. | A runaway proposer (tool loop) stops mid-run, not after it returns. |
| 11 | Oversized prompt (full patch in `stages/review/step.py:68`, growing research history) hangs the workflow task (comparison §3.3) | `pydantic_ai.usage.UsageLimits` | `per_request_input_tokens_limit` (2.21) | **no** | Set it on reviewer and research below the ~2 MB payload ceiling. | The inbound hang becomes a typed `UsageLimitExceeded`. The outbound half is fixed by the upgrade itself (§3 row F2). |
| 12 | Cross-run spend is unknown: CLI harness spend (~$41 of NEON's $46) is outside Pydantic AI | `pydantic_ai_harness.spend` | `SpendLimits(budgets, store, price, on_unpriced)`; `BatchSpendStore` (`get_many` / `add_many`), `Window`, `SpendLimitExceeded`; replay-safe 0.28.1; `SpendRecordedEvent` via `@on_event` (0.30) | **no** | A Kroker `BatchSpendStore` written by both `_run_role` and the code stage. `exhausted()` as an admission check when a run starts. | Day and week budgets across runs and harnesses. The stop decision stays with the workflow gate. |
| 13 | Research budget: a disk-persisted counter charged inside tool activities (`src/sdlc/stages/research/budget_store.py:92`) because a tool activity gets a copy of `RunContext` | `pydantic_ai.capabilities.durable_operation` | `@durable_operation(name=…)` on a capability method: dispatched as its own activity in a durable run, a plain await otherwise (2.36); dispatched correctly from per-request hooks (2.44) | **no** | A `ResearchBudget` capability with a stable `id`. `charge` is a durable operation over the same store, and it is called before the Exa tool. | The charge is journaled, so replay never double-charges. The private `ExaSearchToolset` subclass loses its reason to exist (`agents/research/exa_wrapper.py:18`). |

### 2.3 Research role and stage

| # | Today | Module | What arrives | 0.13? | Change | Gain |
|---|---|---|---|---|---|---|
| 14 | `CodeMode()` + a private `ExaSearch` subclass (`agents/research/agent.py:45`) | `pydantic_ai_harness.code_mode` | Monty **1.0** workers, with an anyio portal inside a Temporal workflow. Default limits: 30 s / 256 MiB / 1000 suspensions; `max_tool_calls=100`; `resource_limits`; `repr` for non-JSON results (0.35). Also `eager`, `speculate` (off under durability) and `monty_sandbox_url` for remote workers. | partly (no limits, 0.0.19 runtime) | Set `max_tool_calls` and `resource_limits` explicitly. Keep `eager`/`speculate` off until row 1. | A bounded sandbox. The run survives odd return values. |
| 15 | Pages returned whole; history grows with every `get_page` | `pydantic_ai_harness.tool_output_limits` | `ToolOutputLimits(bands=[…Spill/Truncate/Summarize], store=OverflowStore, serializer=json_lines)`, plus a `read_tool_result` tool for paging (0.24) | base yes, serializers **no** | Spill `get_page` / `deep_search` into an `OverflowStore` over the claim-check store (ADR-10), shared by workers. | A small history, which also works against the §2.2 row 11 ceiling. Pages stay reachable by id. |
| 16 | Web text reaches the model unchecked | `pydantic_ai_harness.prompt_injection_defender` | `PromptInjectionDefender` (0.22; extra `[prompt-injection-defender]`, Python ≥3.11) | **no** | Only on in-activity research runs (plan / sub-question activities, the architect's sub-run). **Not** on a durable agent: its hook runs in workflow code (§5.3). | NFR-9: hostile content is withheld before the model sees it. |
| 17 | Hand-registered research tools + Exa | see §2.7 (Researcher, WebSearch, WebFetch, Exa) | — | — | — | — |
| 18 | Architect → research runs inside the architect's tool activity; its tokens are **unpriced** (comparison §3.2) | `pydantic_ai_harness.subagents.SubAgents` | `usage_limits`, `contain_errors`, `forward_usage`, `include_self`, `DelegationStart/EndEvent` (0.31) | base yes, events **no** | Only with usage carried out explicitly. No release changes the "delegate usage stays in the activity" rule. | Bounded delegation. Pricing still needs Kroker's own hand-back. |

### 2.4 Graph and runtime

| # | Today | Module | What arrives | 0.13? | Change | Gain |
|---|---|---|---|---|---|---|
| 19 | `FAILURE_TYPES` mirrors the plugin's list (`src/sdlc/workflows/graph_dispatch.py:51`) | `pydantic_ai.durable_exec.temporal.PydanticAIPlugin` | Adds `pydantic_graph.exceptions.UnsupportedEventLoopError` | — | **Required:** add it. | CI green. The error routes to `fail` instead of failing the workflow. |
| 20 | Dashboard polls workflow state (E-10 poller) | `TemporalDurability(event_stream_topic=…)` — Workflow Streams | Offset-addressed event channel per workflow (2.46) | **no** | One poller subscription per run, fanned out as today. | Live proposer progress (tokens, tool calls) in the dashboard with no new infrastructure. |
| 21 | Custom run-level signals and hooks | `pydantic_ai.capabilities.on_event`, `@agent.on_event`, `CustomEvent` / `CapabilityEvent` (2.38, 2.40) | Typed events in the run stream | **no** | Budget and guardrail capabilities emit events rather than callbacks (0.30 deprecates `on_spend` / `on_fire`). | One observation channel for the board and the dashboard. |
| 22 | ADR-13 context ceiling for CLI harnesses by substring table (`src/sdlc/harness/base.py:41` `CONTEXT_WINDOWS`, 5 entries) | `pydantic_ai.models.Model.context_window`, `profile={'context_window':…}` (2.38); `pydantic_ai_harness.compaction.resolve_context_window` (0.36) | Window from the profile, then genai-prices | **no** | Replace the table lookup with `resolve_context_window(model_id)`. The table stays only as a fallback for ids it cannot resolve. | Correct windows for every model the registry names, not just five substrings. |

### 2.5 Operator chat (`src/sdlc/operator/agent.py`, non-durable)

| # | Today | Module | What arrives | 0.13? | Change | Gain |
|---|---|---|---|---|---|---|
| 23 | `create_web_app(agent, deps=)` mounted at `/chat`, bound to `127.0.0.1:8500` | `pydantic_ai.ui` | Host validation + `allowed_hosts` (GHSA-q2xc, 2.30); JSON-only chat endpoint (GHSA-h4xc, **high**, 2.28) | **no** | None at localhost. `allowed_hosts=[…]` only if served under a hostname. | Closes a cross-site path to running the chat agent's tools. |
| 24 | 12 function tools, all always loaded | `pydantic_ai.capabilities.ToolSearch`, `defer_loading` (2.26), hosted MCP in `pydantic_ai_harness.github` / `linear` / `slack` / `logfire_mcp` (0.35) | Tools revealed on demand; read-only integrations | **no** (MCP) | Add GitHub / Linear / Logfire MCP read-only behind `ToolSearch`. | "What is PR #2 waiting on", "why was stage X slow" answered in chat. |
| 25 | Chat forgets between sessions; long chats grow | `pydantic_ai_harness.memory.Memory`, `compaction.SummarizingCompaction` / `FallbackCompaction` (0.23, 0.32) | A notebook per namespace; threshold compaction | Memory yes, Fallback **no** | An operator-namespace memory; compaction on chat only. | Continuity for the operator. Proposers stay ADR-5 clean. |

### 2.6 Doer slot: `Coder` and its parts (comparison §6.10, adoption map §5, §4.1)

Where these run: the pyai doer lives inside **one** heartbeating harness activity on the harness queue, as a non-durable run (comparison §6.10). Every part below is therefore allowed there, including the ones durable runs reject.

**What `Coder` is in 0.36** (read from `coder/_capability.py`). It is a `CombinedCapability` of:

- `FileSystem(root_dir=workspace, max_read_chars=60000, tools=(read_file, write_file, edit_file, list_files, grep))`;
- `Shell(denied_commands=[], allow_interactive=True, denied_env_patterns=LLM_API_KEY_ENV_PATTERNS, tools=['shell'])`, a **persistent**, unrestricted shell;
- `RepoContext`;
- `SubAgents(include_self=True)`, i.e. delegation to the **same** agent and model;
- `ClearToolResults(max_fraction=0.7)`;
- `WarnNearLimits(max_context_fraction=0.9)`;
- `ToolOutputLimits` truncating at 64,000 characters;
- `RepairToolArguments`.

Its own docstring: "Commands are unrestricted and can outlive runs."

That is why both reports take the **parts** and not `Coder()` (comparison §7): the unrestricted shell, the denylist-only env and same-model delegation are each at odds with ADR-17 and ADR-6.

| # | Part | Module / params verified in 0.36 | 0.13? | Kroker today | Kroker change | Gain |
|---|---|---|---|---|---|---|
| 26 | `CodingHarness` `pyai` | composition below; `Coder` itself unused | Coder **no** | `claude_code` / `opencode` / `cursor` adapters (`src/sdlc/harness/`) | A new adapter returning `HarnessRunResult`, running `agent.run()` in the existing harness activity | A fourth harness-axis arm where the model is decoupled from the CLI; typed transcript (ADR-16); a critic or reviewer seat of any family |
| 26a | `FileSystem` | `root_dir`, `cwd`, `allowed/denied/protected_patterns`, **`read_only`**, **`max_read_chars`**, `max_list_results`, `content_hashes`, **`tools`** (tool subset); recoverable errors (0.24); no host-path leaks (0.24); `FileChangeRequestEvent` with `cancel(reason)` before each write, plus read/edit/search events (0.32) | base yes; `read_only`, `cwd`, `tools`, `max_read_chars`, **all events: no** | Worktree cwd + CLI-native deny (containment) | `root_dir=<worktree>`; `protected_patterns` for `<stage>.md` and agent config; listen to `FileChangeRequestEvent` and `cancel()` anything containment refuses | An in-process veto before a write (twin of the `pre_tool` hook). The file events are most of the canonical `HarnessSession` for free. |
| 26b | `Shell` | `env`, `denied_env_patterns`, `allowed_commands`, `denied_commands`, `denied_operators`, **`max_file_bytes`** (0.34, POSIX-only), **`tools`** (choose run-scoped tools vs the persistent `shell`), recoverable spawn failures (0.26) | base yes; `max_file_bytes`, `tools` **no** | Env allowlist `build_env` / `ENV_ALLOWLIST` (`harness/base.py:72,98`) | `Shell(env=build_env(...))`: the **allowlist**, not `LLM_API_KEY_ENV_PATTERNS`. Use run-scoped tools, not `tools=['shell']`, whose commands outlive the run on the worker. | Same env fence as the CLIs; bounded output files |
| 26c | `ToolGuardrail` | `guard`, `result_guard`, `tools`, `hidden`; `approve()` → `ApprovalRequired` → the run ends with `DeferredToolRequests` (0.15) | **no** | `pre_tool` hook + `policy/containment.yaml` compiled by `harness/containment.py` | A guard evaluating the compiled predicates; `approve` surfaces as a deferred call into the E-17 gate | A second enforcement layer the `ContainmentReport` can declare (`hook` beside `native`) |
| 26d | `RepoContext` | `nested_traversal`, `nested_inject` driven by FileSystem traversal events (0.30; `traversal_tool_names` deprecated) | base yes, event-driven **no** | CLIs load `AGENTS.md` natively | Enable nested traversal | The nearest `AGENTS.md` is loaded on first read into a directory, the rule `CLAUDE.md` says is *not* automatic today |
| 26e | `Skills` | `directories`, `include`, `exclude`; deferred behind `load_capability` | yes | `crew/skills/<role>/SKILL.md` (frontmatter already matches) | `Skills('crew/skills/<role>')` | Procedures on demand, not inlined |
| 26f | `Planning` | **`store`, `store_resolver`**, `enable_subtasks`, `inject`, `tools` (0.15, which folds in `pydantic-ai-todo`) | **no `store`**: at 0.13 `Planning` has only `guidance`, `cache_ttl` | Plan → board (ADR-21) | A `PlanStore` over the board's SQLite graph; the plan rides a cache-safe tail reminder | The approved plan reaches the doer without a prompt dump; `PlanStatusChangedEvent` moves the board's live view only |
| 26g | `SubAgents` | `include_self`, `max_depth` (0.36), `contain_errors`, `forward_usage`, `models`, `tool_retries`; `DelegationStart/EndEvent` (0.31) | base yes; `include_self`, `max_depth`, events **no** | — | A read-only explorer delegate, never `include_self` for anything that reviews | Cheap context gathering; ADR-6 stays with the crew critic |
| 26h | `StepPersistence` | `store`, `run_id`, `parent_run_id`, **`capture_frontier`**; replay-safe (0.28.1); conversation persistence with revision-checked saves (0.32) | base yes (not replay-safe) | CLI `--resume` + checkpoint commits | A file store under `runs/<run_id>/`; `annotate_tool_effect` on push and PR tools | Resume and fork = snapshot + checkpoint commit (StepPersistence has no workspace snapshot) |
| 26i | `WarnNearLimits` / `resolve_context_window` | **`max_context_fraction`, `context_window`, `fallback_context_window`** (window resolved from the model, 0.36) | base yes, fraction/window **no** | ADR-13 ceiling via `CONTEXT_WINDOWS` | The ADR-13 sensor: end the session and hand off at the fraction, never compact | The ceiling is correct for any registry model (row 22) |
| 26j | `BackgroundTools`, `SystemReminders`, `TrajectoryJudge`, `Advisor` (`output_type`), `AskUser` | 0.33 / 0.16 / 0.30 / 0.34 / 0.32 | **no** | Crew critic between rounds | Tests in the background (guards inside the tool: background results skip hooks); the frozen contract re-injected; a cross-family mid-run judge (steering, never review); AskUser only with an answerer that ends the session into a crew gate | Crew-critic parity inside one process |
| 27 | `verify` node (retro defect №21) | 26a with **deny** globs over the coder's tests + 26b | FS deny yes; the rest per 26a/26b | — | An in-activity agent of another family; output `VerificationReport` into merge | Tests the coder did not write; blindness enforced by the tool |
| 28 | `smoke.browser` node (retro lesson 6) | `pydantic_ai_harness.playwright.PlaywrightBrowser` (0.24; extra `[playwright]`) | **no** | — | An in-activity agent. It is rejected under durable execution; relax `block_private_addresses` for the local stack; check downloads over HTTP. Screenshots via `media` stores (MinIO). | DoD checked on the running stack; console and network logs catch the wiring class of NEON incident 16 |
| 29 | Hosted sandbox | `pydantic_ai_harness.modal_sandbox.ModalSandbox` (unchanged fields) | yes | FR-1002 open | P7 only: a Modal account, no worktree mount | — |
| 30 | Prompt gate on promptfoo / Node (E-82) | `pydantic_evals` = `pydantic-ai-slim[evals]` (2.51 pins `pydantic-evals==2.51.0`) | not installed | E-82 | See the Evals report §4.1 | Node leaves the build; the gate is repeatable |

### 2.7 Research integrations and external systems

**What `Researcher` is in 0.36** (read from `researcher/_capability.py`). It is:

- `WebSearch(local=True)` — the local search backend, DuckDuckGo;
- `WebFetch(local=True)`;
- `SubAgents` over a `researcher` delegate carrying the same three capabilities;
- `ToolOutputLimits()` with its default local store.

It has **no Exa and no typed output**. Its delegates are `SubAgents`, whose usage stays in the activity under Temporal (comparison §3.2).

| # | Integration | Module / params verified | 0.13? | Kroker today | Kroker change | Gain |
|---|---|---|---|---|---|---|
| 31 | `Researcher` | as above | **no** | `agents/research/agent.py`: `CodeMode` + `ExaSearch` + 4 own tools | **Take the parts, not `Researcher()`:** `ExaSearch` (kept), `WebFetch(local=True, allowed_domains=…)`, `ToolOutputLimits` with a **shared** store (row 15), `CodeMode`, typed `output_type=ResearchBrief`. The DDG `WebSearch(local=True)` only as an explicit fallback provider. | A research role composed from maintained parts, with Kroker's provider, budget and typing kept |
| 32 | `ExaSearch` / `ExaAgent` | `exa/` byte-identical 0.13 ↔ 0.36: `client: ExaClient` seam, `ExaSource` citations in `ToolReturn.metadata`, `ExaAgent(execution='external')` | yes | Private `_toolset` subclass for budget + page capture (`exa_wrapper.py`) | Budget → `@durable_operation` capability (row 13); page capture → an `ExaClient` wrapper; `verify.py` reads `ExaSource` metadata instead of mirroring page text | Retires the private import; grounding from structured citations |
| 33 | `WebSearch` (core) | `native`, `local`, `allowed_domains`, `blocked_domains`, `max_uses`; `openrouter:web_search` (2.30); `blocked_domains` forwarded to OpenAI (2.44) | yes (2.20) | Tavily / Exa behind `ResearchConfig.provider` | `WebSearch(local=<exa or tavily callable>)`; native only on real-Anthropic roles (adversary) | One tool name across providers. On a native-search model it collides with Exa's `web_search`, so pick one per agent. |
| 34 | `WebFetch` (core) | `local`, `allowed_domains`, `blocked_domains`, `max_content_tokens`; 50 MiB body cap (2.24); SSRF / IPv6-zone, superlinear parse and domain-spelling fixes (2.44); `ModelRetry` on an invalid URL (2.46) | yes, but **without** the 2.24 / 2.44 security fixes | None (Exa `get_page`) | Per-role `allowed_domains` = FR-703 egress allowlist | A tool-level egress fence. Adopt only on ≥2.44. |
| 35 | `GitHub` | `auth: str \| Callable[[RunContext], str]` (else env), **`read_only`**, `toolsets`, `client`, `url` (hosted MCP, 0.35; extra `[github]`) | **no** | PR creation = deterministic `gh pr create` activity (`stages/merge/activities.py:189`) | `read_only=True`: `intake.issue`, context reads of linked issues/PRs, merge reads CI/review state, operator chat. PR creation stays the activity. | Issues as intake; "what is PR #2 waiting on" in chat |
| 36 | `Linear` | same shape, extra `[linear]` | **no** | Board (ADR-21) | `intake.issue` from Linear; a `publish.tasks` node projecting `DevTask[]` (observational only) | Plans visible where teams track work; the workflow still owns status |
| 37 | `Slack` | same shape, extra `[slack]` | **no** | Webhook notifier (`notify/notifiers.py`) | Read-only thread context for clarify and research; operator chat. Alerts stay on the deterministic notifier. | The idea's origin thread as context |
| 38 | `LogfireMCP` | same shape, `url` US/EU, extra `[logfire-mcp]` | **no** | NEON retro assembled from traces by hand | `retro` node and operator chat query the run's own traces | Retro evidence (slow stages, retries) gathered by the node |
| 39 | Notion, Google Workspace | same shape (0.35) | **no** | — | `intake.document` → `IdeaBrief` | PRD-in-a-doc intake |
| 40 | Grain, Day AI, PostHog, Pylon | 0.36; docs 404, modules present | **no** | — | Later: PostHog for `outcome.watch` (FR-1100) | — |

**Shared constraint on rows 35–39.** `auth` is a callable over `RunContext`, i.e. over `deps`. Under Temporal, `deps` are serialized into workflow history, so the callable must dereference a secret *reference* on the worker. Put a real token in `deps` and it sits in history in clear text. The same `auth` callable makes the integrations usable on durable proposers at all.

## 3. What changes by itself on upgrade

| # | Change | Where Kroker feels it | Decision |
|---|---|---|---|
| F1 | `UnexpectedModelBehavior` and `FallbackExceptionGroup` become **non-retryable** on agent activities (2.22, 2.32.2) | A malformed model response used to get 3 activity attempts (`roles.py:37`). Now the node goes to `fail` at once. | Accept. Retries for a flaky endpoint belong to row 3's provider, not Temporal. |
| F2 | An oversized activity **result** is non-retryable (2.27, #7110) | Closes the outbound half of comparison §3.3 | — |
| F3 | `include_content=False` really redacts (GHSA-4x9p, 2.44) | `logfire_setup.py:26` | Set `include_content=False`. It is complete only from 2.44. |
| F4 | Sync tools and hooks run in a thread pool, with `timeout=` (2.32); the agent graph is cached (2.51) | Research tools; every proposer run | — |
| F5 | Operator chat security (row 23) | `/chat` | — |
| F6 | `genai-prices` 0.0.73 → 0.1.9 | Registry models price identically. `zai:` changes (row 4). | Note it in the benchmark baseline. |
| F7 | `exa` module unchanged (empty diff 0.13 ↔ 0.36) | `exa_wrapper.py` keeps working | — |

## 4. Required, and what can break

| # | Item | Why | Fix |
|---|---|---|---|
| R1 | `FAILURE_TYPES` is missing `UnsupportedEventLoopError` | The plugin's list grew. CI has failed on it since 2026-09-17 on every run, and in the target venv. | Add it (row 19). |
| R2 | CodeMode runs Monty 1.0 through a portal thread **inside workflow code** under `TemporalAgent` | The only new mechanism on a durable path. The unit tier does not reach it. | Run the `temporal` research tests before deploy (not run here). |
| R3 | Unpinned install | Every image rebuild jumps versions; the private `exa._toolset` import rides along. | Pin `>=2.51,<2.52` / `>=0.36,<0.37`; install from `uv.lock` (comparison §6.5). |

## 5. Corrections to the fresh reports

1. **The adoption map's wave 1 assumes 0.36 is installed.** `RepairToolArguments`, `PromptInjectionDefender`, `resolve_context_window`, the detectors, `ToolGuardrail`, `@durable_operation`, `cost_limit` and `per_request_input_tokens_limit` are all absent at 0.13 / 2.20. The upgrade is wave 1's step zero.
2. **`RepairToolArguments` does not repair structured output.**
   - It implements only `before_tool_validate`. Core skips that hook for `kind == 'output'` tools: `tool_manager.py`, "Output tools are internal — they don't fire user-facing tool hooks".
   - That answers the map's §9 question: no.
   - Use a `before_output_validate` capability instead (row 6).
3. **`PromptInjectionDefender` works in `after_tool_execute`, a capability hook.** On a durable agent that hook runs in workflow code. With `semantic_detection` the defender also offloads to a thread in `before_run`, and it has no durability check. Put it on in-activity agents only (row 16). `ToolGuardrail` result guards are the same kind of hook.
4. **Durability-aware harness features are blind under `TemporalAgent`.** They look for a durability capability, so row 1 comes before any of them.
5. **Comparison §3.3 is half closed** by F2. Row 11 closes the other half.
6. **GLM to native `zai` moves USD cost +19–23%** at the same tokens (row 4).
7. **The adoption map's "research becomes a `Researcher` composition" (§2.2, §3)** does not fit as written. `Researcher()` is DuckDuckGo `WebSearch(local=True)` + `WebFetch` + `SubAgents` + a local-store `ToolOutputLimits`. It has no Exa, no typed output, and its delegate usage leaks under Temporal. Take the parts (row 31).
8. **The adoption map's `PlanStore` over the board (§10) needs `Planning(store=…)`**, which the installed 0.13 does not have: its `Planning` has only `guidance` and `cache_ttl`.
9. **The adoption map's "FileSystem gives the doer a veto point" (`FileChangeRequestEvent.cancel`, §11) and `FileSystem(read_only=…)`** are 0.32+. Neither is in 0.13.
10. **`WebFetch` exists at 2.20 but without four security fixes** (body cap 2.24; SSRF / IPv6-zone, parse DoS and domain spelling 2.44). Adopt it for the FR-703 allowlist only after the upgrade (row 34).

## 6. Order and evidence

**Order**

1. R1.
2. Pin (R3).
3. F1 and F3 decisions.
4. The temporal tier for R2 and replay of captured histories. Deploy between runs (retro №22).
5. Rows 1–3, then the rest of §2.1–2.2 (the adoption map's wave 1 as corrected in §5).
6. §2.3–2.7 by wave: research parts (rows 13–16, 31–34) in wave 1–2; the pyai doer with `verify` and `smoke` (§2.6) in wave 2; the GitHub and Linear intake and publish in wave 2; Slack, Logfire MCP and documents in wave 3.

**Evidence**

- Versions:
  - `uv.lock` lines 1100–1101 and 1121–1122;
  - the PyPI JSON;
  - CI run 36005726615, which installed harness 0.34.0 / core 2.49.0: 1 failed, 5324 passed.
- Unit tier on 2.51 / 0.36:
  - throwaway venv, Python 3.12, `temporalio` held at 1.31.0;
  - 3 failures: R1; `test_env_allowlist`, which is order-dependent (passes alone, uncommitted working-tree edit); a poller timing test that fails on Python 3.12 whatever the anyio version and passes on the dev venv's 3.14 — `sdlc.dashboard.fleet` imports no pydantic-ai.
- **Not run:** the `temporal` tier (stopped at the user's request). R2, F1 and F2 are read from code, not observed.
