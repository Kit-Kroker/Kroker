# Pydantic AI capabilities — adoption map for Kroker

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD or ROADMAP line. |
| Date | 2026-09-27 |
| Companion | `docs/reports/2026-09-27-pydantic-ai-harness-comparison.md` (what Kroker is today against the Harness, and four defects found on the Temporal page). This report asks the opposite question: **how much of Pydantic AI and the Harness can Kroker take**, and where each piece lands. Where the two disagree on a verdict, this one is the later position — it assumes the graph can gain node types. |
| Source | Pydantic AI Harness docs (index, 55 capability pages) and core capability pages (Web Search, Web Fetch, Thinking, MCP, Tool Search, Select Model, Resolve Model ID, Prepare Tools, Prefix Tools, Set Tool Metadata, Include Tool Return Schemas, Process History, Process Event Stream, Raise Content Filter Error, Thread Executor, Image Generation, X Search), `pydantic_evals.online_capability`, and the Temporal durable-execution page. |
| Method | Docs read; Kroker anchors checked against `main` @ `eb34fe1`. No capability was run. Every "verify" below marks a claim the docs did not settle. |

## 1. Ground rules for where a capability can live

Kroker runs agent code in three execution contexts, and each capability's
documented durability behaviour decides which ones it may enter.

**Durable proposers.** The stage agents built from `agents/<role>/agent.py`
run inside `GraphWorkflow` under `TemporalAgent` today and
`TemporalDurability` after the migration (companion report §6.7). A
capability here must be attached at construction, must carry a stable `id`
when it contributes a toolset, and must not do I/O in hooks that run in
workflow code. Several capabilities say so outright: `TrajectoryJudge`
raises `UserError` in a durable run; `Advisor` local mode and `AskUser` are
unsupported there. MCP-backed capabilities (GitHub, Linear, Slack, Logfire
MCP) connect "inside every activity that lists or calls its tools" and must
read per-run credentials from `deps`, not globals.

**In-activity agents.** An agent that runs whole inside one activity — the
architect's research sub-run today (`src/sdlc/stages/research/toolset.py`),
the proposed in-process coder, a proposed verifier — is a plain,
non-durable Pydantic AI run. Every capability works there, including the
ones durable runs reject. Its crash unit is the activity.

**Non-durable surfaces.** The operator chat agent (`src/sdlc/operator/agent.py`,
E-86) runs in the dashboard process and only signals workflows. Every
capability works there too.

One more constraint cuts across all three. Twelve of the fourteen proposer
roles run `anthropic:glm-5.2` through an Anthropic-compatible endpoint
(`agents/*/agent.yaml`). Provider-native tools — native web search, web
fetch, the native advisor tool, native MCP, native compaction — are
Anthropic API features and cannot be assumed on that endpoint. Every
provider-adaptive capability below is therefore configured with its **local**
side (`local=True` or an explicit callable), and "native" is a bonus for the
roles on real Anthropic models (adversary, discover, risk, operator chat).

## 2. The full catalog

Landing zones: **R** runtime (every agent), **P** a proposer role's
`agent.py`, **N** a new or upgraded graph node type, **D** the doer slot
(harness adapter), **O** operator surfaces, **B** benchmark and eval.
Wave refers to §7.

### 2.1 Runtime and model control

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `TemporalDurability` | core | R | replaces the 16 `TemporalAgent` wrappers (`roles.py:214`) | 1 |
| `ResolveModelId` | core | R | builds every model with `max_retries=0` and the right base URL on the worker, and is where GLM roles move to the native `zai` provider (§11); also the fix for per-run model overrides (companion §3.1, §3.4). Must be deterministic and free of I/O — it re-runs inside each activity | 1 |
| `SelectModel` | core | R | per-step model routing — a cheap model for the first pass, the registry model on retry; feeds SC-7 tiering. Must stay inside the memoization key | 3 |
| `Thinking` | core | P | `Thinking(effort=...)` per role in `agent.yaml`: high for architect, planner, deep_review, adversary; off for handoff and clarify probes. Core ships a native `zai` provider whose profile maps unified thinking to Z.AI's `thinking` field and `reasoning_effort` on GLM-5.2/5.3; routed as `anthropic:glm-5.2`, the mapping is Anthropic's guess instead (§11) | 1 |
| `Instrumentation` | core | R | `include_content=False` by default (companion §2.4); `LogfirePlugin` for Temporal spans | 1 |
| `RepairToolArguments` | harness | R | on every proposer — structured output travels as a tool call, and truncated arguments are the failure `agents/settings.py:23` works around. Verify it covers output tools | 1 |
| `IncludeToolReturnSchemas` | core | P | research, architect: the model sees `ResearchBrief`'s shape when it calls `research` | 2 |
| `SetToolMetadata` | core | R | per-tool Temporal activity config (timeouts per tool class) | 1 |
| `PrepareTools` / `PrepareOutputTools` | core | P | hide tools by stage state — e.g. architect's `research` tool disappears once the run's research budget is spent, instead of failing inside the call | 2 |
| `PrefixTools` | core | P | required once a role carries two MCP capabilities with clashing names | 2 |
| `ProcessHistory` | core | P, D | redact secrets from history before each request (with the Guardrails detectors) | 2 |
| `ProcessEventStream` | core | O | live proposer progress into the dashboard SSE via Workflow Streams (`event_stream_topic`) | 3 |
| `RaiseContentFilterError` | core | R | a filtered response becomes a typed error the stage can route to `fail`, not a half-output | 1 |
| `ReinjectSystemPrompt` | core | O | operator chat: the bundled UI can drop the system prompt from history | 2 |
| `ThreadExecutor` | core | R | worker process: sync tools on a bounded pool (the worker is long-lived) | 2 |
| `WarnOnCacheBusts` | harness | D | long doer sessions only; proposers are single-shot | 3 |
| `ManagedPrompt` | harness | — | only if the resolved prompt text is hashed into `PROMPT_SHAS` per run, which keeps ADR-5 intact; otherwise no | later |

### 2.2 Knowledge, search and the web

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `Researcher` | harness | P, N | the research role becomes a `Researcher` composition with a typed `output_type=ResearchBrief`, instead of hand-registered tools (`agents/research/agent.py`) | 2 |
| `WebSearch` | core | P | `WebSearch(local=<tavily or exa callable>)` beside Exa; native on the Anthropic-model roles | 2 |
| `WebFetch` | core | P | `WebFetch(local=True, allowed_domains=...)` — the domain filter is enforced locally, which gives FR-703 a per-role egress allowlist at tool level | 2 |
| `ExaSearch` / `ExaAgent` | harness | P | keep Exa; after the upgrade, `ExaAgent(execution='external')` returns long Exa runs as deferred calls the workflow can wait on durably | 2 |
| You.com search / research | harness | P | a second search provider behind the same `ResearchConfig.provider` switch; decorrelates the evidence base | 3 |
| `XSearch` | core | — | no SDLC use | — |
| `RepoContext` | harness | P, D | `context` stage (Cartographer) and the doer. Its opt-in nested-on-traversal mode surfaces a directory's `AGENTS.md` when the agent reads into it — the "read the nearest `AGENTS.md`" rule this repo's `CLAUDE.md` says is *not* loaded automatically (§10) | 2 |
| `Skills` | harness | P, D | `crew/skills/<role>/SKILL.md` and `agents/<role>/` procedures loaded on demand instead of inlined | 2 |
| `PyaiDocs` | harness | D | doer only, when the target repo depends on pydantic-ai | 3 |
| `Memory` | harness | O | operator chat notebook (per operator namespace). Not on proposers: recall stays orchestrator-driven and snapshotted (ADR-5). Under Temporal its injected snapshot is journaled, which would satisfy replay but not the memoization key (§10) | 3 |
| `ConversationSearch` | harness | P, O | deep_review, retro and operator chat: BM25 over sessions. `HistorySource` is substrate-neutral, so a source over the ADR-16 `HarnessSession` artifacts makes **CLI** sessions searchable too, not only pyai ones (§10) | 2 |
| `ToolSearch` | core | P, O | any agent with many MCP tools (operator chat with GitHub + Linear + Slack) pays tokens only for tools it uses | 2 |
| `MCP` | core | P, O | generic door for any MCP server a project declares (Sentry, a docs server, the project's own) | 2 |

### 2.3 External systems

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `GitHub` | harness | N, P, O | **intake** from an issue; **context** reads linked issues/PRs (read-only); **merge** reads CI and review state; **operator chat** answers "what is PR #2 waiting on". PR creation stays the deterministic `gh pr create` activity (`stages/merge/activities.py:189`) | 2 |
| `Linear` | harness | N, O | **intake** from a Linear issue; a new `publish.tasks` node projects the approved plan's `DevTask[]` to Linear issues (observational, like the board — ADR-21); status flows back only to the live view | 2 |
| `Slack` | harness | P, O | **clarify** and **research** read the thread an idea came from; **operator chat** reads/posts as the operator. Gate notifications stay on the deterministic webhook notifier (`notify/notifiers.py`) — an LLM does not sit on the alert path | 3 |
| `Notion`, `Google Workspace` | harness | N | intake sources: the PRD lives in a doc; `intake.document` turns it into an `IdeaBrief` | 3 |
| `Grain` | harness | P | clarify context from the meeting that produced the idea. Docs page 404 | later |
| `Pylon` | harness | N | P4 maintenance: customer-issue signals into DAPER detect. Docs page 404 | later |
| `PostHog` | harness | N | FR-1100 product-outcome source — the analytics adapter ADR-19 calls for, read by an `outcome.watch` node. Its docs page returns 404 (module present in the 0.36.0 wheel) | later |
| `Logfire MCP` | harness | N, O | **retro** queries the run's own traces; P4 **detect** reads production error rates; operator chat answers "why was stage X slow" | 3 |
| `LocalStack` | harness | D, N | devops tasks on AWS-shaped projects run against emulated AWS. `manage_container` needs Docker, which the worker sandbox lacks (NEON retro incident 2), and the image needs an auth token since 2026.03 — run it as a sidecar like the retro's Qdrant (§11) | 3 |
| `Macroscope` | harness | N | an external review lens — a `review.static` node on the integration branch, advisory into merge | 3 |
| `StackOne`, `Ordinal`, `Day AI` | harness | — | no SDLC use | — |
| `ImageGeneration` | core | — | only for frontend projects (mock-ups at architecture); low | later |

### 2.4 Doing: files, shell, browser, sandbox

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `Coder` (as parts) | harness | D | a fourth `CodingHarness`, `pyai`, built from the parts below (§5) | 2 |
| `FileSystem` | harness | D, N | worktree root, read-only globs for `<stage>.md` and agent config; deny globs give the verifier its blindness (§4.1) | 2 |
| `Shell` | harness | D | `Shell(env=build_env(...))` — the allowlist, not provider keys (retro incident 1 moved keys *into* the env; this undoes that for the pyai doer). Use the run-scoped tools, not the persistent `shell` tool `Coder` picks: persistent commands outlive the run on the worker. `max_file_bytes` is POSIX-only (§11) | 2 |
| `ModalSandbox` | harness | D | a hosted-tier option only: a Modal account, registry-tag images, no mounts, a cold start per run, the worktree cloned in rather than bind-mounted. Not the local FR-1002 answer (§11) | P7 |
| `PlaywrightBrowser` | harness | N | a `smoke.browser` node that walks the DoD against the running stack (§4.3). Rejected under durable execution, so the node runs an in-activity agent; `block_private_addresses` must be relaxed for a local stack; downloads are refused, so file deliverables are checked over HTTP (§11) | 2 |
| `BrowserUse` | harness | — | Playwright instead: typed, one action per call, reproducible | — |
| `CodeMode` | harness | P, D | keep on research; add to discover/risk (assessment scan over many signals) and the doer | 2 |
| `BackgroundTools` | harness | D | test suites and builds run in the background while the doer keeps working. A background result bypasses tool-result hooks, so `ToolGuardrail` and `PromptInjectionDefender` never see it — validate inside the tool (§10) | 3 |
| `StepPersistence` | harness | D | the pyai doer's resume handle (the equivalent of `claude --resume`) and fork for fix loops | 2 |
| `MediaStores` | harness | N | screenshots from `smoke.browser` into the claim-check store instead of history | 2 |

### 2.5 Delegation and planning

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `SubAgents` | harness | P, D | architect → research with per-delegate `usage_limits`, `timeout_seconds`, `max_calls`, `contain_errors`; a `models` menu with restricted keys can pin a reviewing delegate to another family (ADR-6). The delegate's usage must still be carried out of the activity (companion §3.2) (§10) | 2 |
| `DynamicWorkflow` | harness | N, B | inside the `research` node: typed sub-question fan-out replaces the hand-written fan-out; in the benchmark, the measured LLM-scheduler arm (ADR-21) | 2 / 3 |
| `Planning` | harness | D | a `PlanStore` over the board hands the approved plan to the doer as a cache-safe tail reminder, and plan events flow back as observational board updates (§10). The plan node still owns the task graph | 2 |
| `Advisor` | harness | D | in-session consult for the pyai doer (local mode is fine outside durability); family-different advisor model | 3 |
| `TrajectoryJudge` | harness | D | mid-session steering of the pyai doer by a different-family model — the in-session counterpart of the crew critic. Steering only; never counted as review (ADR-12) | 3 |
| `AskUser` | harness | D | only with an answerer that writes `question-v1` and ends the session, so the question becomes the existing crew gate and the answer resumes through `StepPersistence`. Verify the answerer can end a run cleanly | 3 |
| `HandleDeferredToolCalls` | core | O | operator chat resolves routine approvals by rule, leaving the operator the rest | 3 |

### 2.6 Context control

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `ToolOutputLimits` | harness | P, D | research `get_page` in spill mode; doer tool output bounded; also caps the payload growth behind companion §3.3. Under Temporal the spill store must be shared (an `OverflowStore` over the claim-check store), or `read_tool_result` on another worker finds nothing (§10) | 1 |
| `ClearToolResults`, `DeduplicateFileReads` | harness | D | cheap tiers in the doer — they drop stale tool output, not reasoning | 2 |
| `WarnNearLimits` / `ReportContextUsage` / `resolve_context_window` | harness | D, R | ADR-13's ceiling sensor in the doer; and `resolve_context_window` (profile, then `genai-prices`, which Kroker already depends on) replaces the five-entry `CONTEXT_WINDOWS` table for the **CLI** adapters too (§10) | 1 |
| `SummarizingCompaction`, `TieredCompaction`, `SlidingWindowCompaction` | harness | — | not in doer sessions (ADR-13); acceptable for operator chat's long conversations | 3 (O only) |
| Provider-native compaction | core | O | operator chat on a real Anthropic model | 3 |
| `SystemReminders` | harness | D | re-inject the frozen Validation Contract every N requests so a long doer session does not drift from it | 2 |
| `pin()` | harness | D | pin the task contract in history if compaction is ever enabled | — |

### 2.7 Safety, cost, evaluation

| Capability | Pkg | Zone | How it lands | Wave |
|---|---|---|---|---|
| `PromptInjectionDefender` | harness | P, D | research tool results (web), and the doer's reads of the target repo — NFR-9 treats that repo as hostile | 1 |
| `InputGuardrail` / `OutputGuardrail` + detectors | harness | R, P | `redact_secrets` on every proposer's output; the same detectors replace `memory/scrub.py`; and `OutputGuardrail.retry` as a deterministic contract check on the planner — every `DevTask` names its test path in both the description and `contract.test_commands` (retro defect №20) (§10) | 1 |
| `ToolGuardrail` | harness | D | the doer's second enforcement point, evaluating the predicates `harness/containment.py` compiles from `policy/containment.yaml`; `approve` → deferred call → E-17 gate | 2 |
| `SpendLimits` | harness | R | cross-run counters and an `exhausted()` admission check at run start. It prices only Pydantic AI responses, so the CLI harness spend (~$41 of NEON phase 1's $46) reaches it only through a Kroker `BatchSpendStore` the code stage also writes to; the stop decision stays the workflow's budget gate (§10) | 2 |
| `OnlineEvaluation` (pydantic_evals) | evals | B | score proposer outputs in production with the benchmark judge's evaluators, asynchronously — the production-proxy label source the calibration ledger (C7) already names. Verify it runs outside workflow code | 3 |
| `RuntimeAuthoring` / capability creation | harness | — | no: an agent that writes its own capabilities can rewrite what it is judged by (`AGENTS.md`, "Who may change what") | — |

## 3. Proposer roles, composed

Each row is what `agents/<role>/agent.py` builds after waves 1–2. Every role
also carries the runtime set: `TemporalDurability`, `ResolveModelId`,
`RepairToolArguments`, `RaiseContentFilterError`, output `redact_secrets`.

| Role | Adds | Keeps out |
|---|---|---|
| clarify (+ route, probe) | `Thinking(low)`; `Slack` / `GitHub` read-only for the originating thread or issue (wave 3) | web search — clarify asks the human, it does not guess |
| research | `Researcher` parts: `WebSearch(local=exa)`, `WebFetch(local, allowed_domains)`, `ExaSearch`, `DynamicWorkflow` fan-out, `ToolOutputLimits(spill)`, `PromptInjectionDefender`, `CodeMode` | `Memory` (recall stays a snapshot) |
| architect | `Thinking(high)`; research as `SubAgents` with usage carried out; `GitHub` read-only in brownfield; `PrepareTools` to drop research when the budget is spent | write tools of any kind |
| planner | `Thinking(high)`; `Skills` (planning procedures, including the test-path rule from retro defect №20) | tools |
| reviewer, qa | `Thinking(medium)` only | **tools, deliberately** — ADR-6/ADR-12: the judge holds no tools. Independent execution moves to the verifier node (§4.1) |
| deep_review | `Thinking(high)`; `ConversationSearch` over the scrubbed session (wave 3) | the raw session |
| adversary | `Thinking(high)`; native web search (it runs on a real Anthropic model) for known-vulnerability lookups | repo write |
| analyst, merge_verdict, handoff | `Thinking` as configured | — |
| devops_planner | `Thinking`; `LocalStack` knowledge via `Skills` | — |
| discover, risk (assessment) | `CodeMode` over the scan signals; `RepoContext`; `FileSystem` read-only on the scanned repo; `PromptInjectionDefender` (the scanned repo is untrusted) | — |

## 4. Graph improvements

The graph is data (`src/sdlc/workflows/graphs/*.graph.yaml`) over a typed
node catalog (`src/sdlc/graph/node_types.py`), so each item below is a
catalog entry with typed ports, a payload model in `graph/payloads.py`, a
handler, and — by the slice rule in `AGENTS.md` — a
`src/sdlc/stages/<stage>/` slice with its `<stage>.md` contract. None of them
changes an existing node's ports, so stored graphs keep their `content_sha`.

### 4.1 `verify` — independent verification (retro defect №21)

The retro's sharpest finding is that the coder writes both the code and the
tests that judge it. A `verify` node closes that with the Harness's parts:

- an in-activity Pydantic AI agent on a model family different from `dev`;
- input: the frozen contract's assertions and the integration branch's public
  surface — no diff, no coder narrative;
- `FileSystem` with **deny** globs over the coder's test files, so blindness
  is enforced by the tool, not requested by the prompt;
- `Shell(env=build_env(...))` to run its own tests, `ModalSandbox` when the
  container tier exists;
- output `VerificationReport`, a required input of the merge node.

Per-task placement (inside the code stage's task loop, beside review and QA)
and graph-level placement (one node after `code`, over the integration
branch) are both possible; the graph-level node is cheaper and can move
inward later.

### 4.2 `review.static` — Macroscope as an outside lens

An advisory node on the integration branch: `Macroscope` findings, validated
by a small agent that reads the cited code (the capability's own
instructions treat every finding as untrusted). Output joins `analyze` into
merge. A third-party reviewer is decorrelated from every model in the
registry by construction.

### 4.3 `stack.up` and `smoke.browser` — deployability before merge

Retro lesson 6: "the merge gate checks the correctness of the diff, not
deployability"; nine of ten day-2 defects were invisible to unit tests, and
lesson 11 adds the two-process wiring class. Two nodes before merge:

- `stack.up` brings the project's compose stack up in the sandbox (and
  `LocalStack` where the project is AWS-shaped), emitting a `StackReport`;
- `smoke.browser` runs `PlaywrightBrowser` against the stack, one check per
  DoD criterion from the spec, screenshots to the artifact store via
  `MediaStores`, emitting a `SmokeReport`.

Both feed the merge gate as evidence. This is the "stack-up is a separate
quality phase" the retro asks for, as graph nodes rather than operator work.

### 4.4 Issue-tracker edges: `intake.issue`, `publish.tasks`

- `intake.issue` (GitHub or Linear) and `intake.document` (Notion, Google
  Docs) produce the same `IdeaBrief` the current intake emits, so everything
  downstream is unchanged.
- `publish.tasks` projects the approved `ImplementationPlan` to Linear or
  GitHub issues. Like the board (ADR-21), it is a projection: the workflow
  alone owns `authoritative_status`.

### 4.5 `research` upgraded in place

Same ports; inside, `DynamicWorkflow` fans typed sub-question researchers out
and `ToolOutputLimits` spills pages. The `gate.research` node already exists
for runs that want a human on the brief.

### 4.6 `retro` and `outcome.watch`

- `retro` gains `Logfire MCP` (the run's own traces: slow stages, retries,
  timeouts — the evidence the NEON retro was assembled from by hand) and
  `ConversationSearch`.
- `outcome.watch` (FR-1100) reads `PostHog` after deploy against the frozen
  decision rule (ADR-20).

### 4.7 A default graph with the additions

```
intake(.issue) → context → research → clarify → architect ⇄ gate.architecture
  → plan ⇄ gate.plan → plan_check → publish.tasks
  → code → verify → review.static ┐
                  → stack.up → smoke.browser ┤→ analyze → merge → deploy → outcome.watch
                                                                         → retro
```

## 5. The doer slot: `pyai` harness

The fourth `CodingHarness` (companion §6.10), now with the full kit. It runs
in one heartbeating activity on the harness queue and returns
`HarnessRunResult` like the CLIs:

`RepoContext` · `Skills('crew/skills')` · `FileSystem(worktree, read-only
contracts)` · `Shell(env=allowlist)` · `ToolGuardrail(containment.yaml)` ·
`PromptInjectionDefender` · `Planning` · `SubAgents` (read-only explorer) ·
`BackgroundTools` (tests, builds) · `SystemReminders` (the frozen contract) ·
`ToolOutputLimits` · `ClearToolResults` · `DeduplicateFileReads` ·
`WarnNearLimits` (ADR-13 hand-off) · `StepPersistence` (resume, fork) ·
`RepairToolArguments` · `Thinking` · optional `Advisor` and
`TrajectoryJudge` on another family · `ModalSandbox` once FR-1002 lands.

It also gives the crew a cheaper shape: a critic or reviewer seat no longer
needs a third CLI vendor (`crew/layouts/code.yaml` leaves the reviewer slot
empty for exactly that reason).

## 6. Operator surfaces

The chat agent (E-86) is non-durable, so it can take everything: `GitHub`,
`Linear`, `Slack`, `Logfire MCP` read-only with `ToolSearch` so their tools
are loaded on demand; `Memory` for the operator's own notebook; compaction
for long conversations; `HandleDeferredToolCalls` for rule-based approvals;
`ReinjectSystemPrompt`. Beyond chat, `ACP` serves the same agent inside Zed,
and GitHub Agentic Workflows (gh-aw) can start a run from an issue label —
the trigger side of `intake.issue`.

## 7. Waves

**Wave 1 — runtime and safety, no new nodes.** The companion report's four
defects and hygiene items first (model forwarding, delegate usage, prompt
size, client retries, pinning, telemetry content). Then
`TemporalDurability`, `ResolveModelId`, `Thinking` per role,
`RepairToolArguments`, `RaiseContentFilterError`, `SetToolMetadata`, output
`redact_secrets`, `ToolOutputLimits` (with a shared spill store) and
`PromptInjectionDefender` on research, the planner's `OutputGuardrail`
test-path check, and `resolve_context_window` in place of the CLI adapters'
`CONTEXT_WINDOWS` table. Deploy between runs (retro defect №22).

**Wave 2 — new capability, measured.** The `pyai` harness and the `verify`
node (together: they share the composition); `smoke.browser` and
`stack.up`; research as `Researcher` + `DynamicWorkflow`; `intake.issue`
and `publish.tasks` with GitHub and Linear; `SubAgents` for architect →
research; `SpendLimits` across runs; operator chat integrations. Each new
node enters a benchmark arm before it enters `default.graph.yaml`.

**Wave 3 — depth.** `review.static`, `retro` with Logfire MCP,
`ConversationSearch`, `BackgroundTools`, `Advisor` and `TrajectoryJudge` in
the doer, `AskUser` via crew gates, `SelectModel`, `OnlineEvaluation`,
Workflow Streams, `ModalSandbox`, Slack and document intake.

**Later.** `outcome.watch` with PostHog (FR-1100), Pylon for DAPER (P4),
`ManagedPrompt` with per-run pinning, image generation for frontend
architecture.

## 8. Still out, and why

| Capability | Reason |
|---|---|
| `Memory` on proposers | the model would write its own future inputs; ADR-5 recall is orchestrator-driven and hashed |
| Summarising compaction in doer sessions | ADR-13: a compacted session has lost its thread; hand off instead |
| `TrajectoryJudge`, local `Advisor`, `AskUser` on proposers | the Harness rejects or does not support them under durability |
| `RuntimeAuthoring` / capability creation | self-extension can rewrite what the agent is judged by |
| `BrowserUse` | `PlaywrightBrowser` is deterministic per action; one browser capability per agent |
| `XSearch`, `StackOne`, `Ordinal`, `Day AI`, AWS Lambda durability | no SDLC use, or Temporal already covers it |

## 9. Open questions

- Does the GLM Anthropic-compatible endpoint honour `anthropic_thinking` and
  accept output-tool schemas unchanged when `Thinking` is on?
- Does `RepairToolArguments` cover output tools?
- Where do `ToolGuardrail` result guards and `PromptInjectionDefender` run
  under `TemporalDurability` — activity or workflow code?
- Can `AskUser`'s answerer end a session cleanly so the question becomes a
  crew gate?
- Does `OnlineEvaluation` dispatch from a context that is safe to use from
  code that also runs under a workflow?
- Which credentials does each MCP capability need on the worker, and how are
  they carried on `deps` without landing in Temporal history in clear text?

## 10. What a full read of the capability pages changed

The first version of this map was written from the Harness index, the
Coder and Temporal pages read in full, and the other capability pages read
in part. The 21 pages below were then read in full (prose, not the API
reference): Planning, Subagents, Dynamic Workflow, Advisor, Background
Tools, Tool Search, core and Harness Compaction, Tool Output Limits, Warn On
Cache Busts, Memory, Conversation Search, Skills, Repo Context, Pydantic AI
Docs, Guardrails, Prompt Injection Defender, Spend Limits, Trajectory Judge,
System Reminders, Ask User. The table rows above carry the corrections; the
reasons follow.

**Planning hands a plan between runs.** "A shared store is the whole handoff
mechanism between two runs. One agent writes the plan, a second one executes
it." The plan rides an ephemeral tail reminder behind a cache breakpoint and
never enters `message_history`; under durability the plan read is a
journaled operation (`id='planning'`). A `PlanStore` is a protocol, so one
over the board's SQLite graph lets the doer see the approved task list
without a prompt dump, and `PlanStatusChangedEvent` can move the board's
live view — never `authoritative_status` (ADR-21). "A store that raises
fails the run" is deliberate upstream and matches Kroker's fail-closed
preference. Stacking tail reminders (`Planning`, `SystemReminders`,
`Memory`) spends Anthropic's four cache breakpoints; core trims the oldest.

**Context windows can come from the model registry.** `max_fraction` resolves
per request against the model's profile, then `genai-prices`; the helper
`resolve_context_window` is exported. Kroker's CLI context ceiling rests on
a five-entry substring table (`src/sdlc/harness/base.py:41`) that falls back
to a resume count for unknown models, and `genai-prices` is already a Kroker
dependency. Two caveats from the page apply directly: registry entries can
be wrong (it names `anthropic:claude-sonnet-4-5` as recorded at 1M against a
real 200K — the model `agents/discover` and `agents/risk` run), and a
proxied endpoint reports a model id whose entry describes someone else's
deployment, which is the GLM-through-z.ai case. Both need an explicit
`context_window` override per registry role.

**Compaction has pieces ADR-13 can use without compacting.**
`ClampOversizedMessages` protects against one runaway generation;
`WarnNearLimits` watches iterations and total tokens as well as context;
compaction receipts plus a `StepPersistence` handle give a fresh session a
pointer to the persisted run it replaces; `bridge_prefix` marks a
cross-model handoff. None of these summarises the doer's reasoning.

**Spill stores are local by default.** `ToolOutputLimits`' `LocalFileStore`
keeps spills under a stable root on one host. A research agent's tool
activities can land on different workers, so the store has to be shared.

**Conversation search is not tied to Pydantic AI sessions.** `HistorySource`
is "substrate-neutral (enumerate runs, yield each run's durable message
record)". A source over ADR-16 `HarnessSession` artifacts puts every CLI
session behind BM25 for deep_review, retro and the operator — the retro's
manual incident archaeology is the use case.

**Repo Context implements this repository's own reading rule.** Its
nested-on-traversal mode surfaces a directory's `AGENTS.md` the first time
the agent reads into that directory, from `FileSystem` events rather than
argument sniffing. `CLAUDE.md` here states that the nearest-`AGENTS.md`
rules "are not loaded for you automatically"; for a pyai doer they would be.

**Skills are drop-in.** `crew/skills/<role>/SKILL.md` already carries the
`name` / `description` frontmatter the loader requires. Bundled
`references/` and `scripts/` are not loaded, every skill is deferred behind
`load_capability`, and selection is not an access boundary.

**Guardrails can enforce contracts, not only secrets.**
`OutputGuardrail.retry(instruction)` sends a failing structured output back
to the model under the output-retry budget. A tool guard never sees output
tools, so this is the hook for proposers. The planner check for retro defect
№20 is deterministic and costs no extra model call when it passes.
`ToolGuardrail.approve()` raises `ApprovalRequired`, the run ends with
`DeferredToolRequests`, and it resumes from history — the page lists this
shape for "durable execution, anything that cannot hold a process open",
which is E-17's shape.

**Background results skip the hooks.** "The later result message does not
pass through tool-result or tool-error hooks." Guards on a background tool
must live inside the tool.

**Sub-agents carry their own brakes.** Per-delegate `usage_limits`,
`timeout_seconds`, `max_calls` and `contain_errors` turn a delegate failure
into a steering message instead of a dead parent. A `models` menu with a
per-delegate restriction is a place to encode ADR-6 for delegates.
`DelegationEndEvent` carries the child's usage — but it is emitted from
inside the tool, and under Temporal a tool runs in an activity where
`ctx.emit()` is unsupported; whether the event survives there is open.

**Dynamic Workflow is bounded exactly.** `max_agent_calls` holds "exactly
even when the script fans out"; `forward_usage=True` is best-effort under
concurrent fan-out; scripts are type-checked against sub-agent signatures
before they run; `inherit_model=True` makes sub-agents follow a per-run
model override (companion §3.1); workflows do not nest, so research
sub-agents keep `CodeMode` but never `DynamicWorkflow`.

**Advisor's local mode leaks usage under Temporal.** "Temporal and Prefect
can checkpoint the returned advice, but changes to the activity-local
RunUsage do not merge back" — the same leak as companion §3.2. Native mode
needs `anthropic:`/`openrouter:` on both sides and would reach the GLM
endpoint, so the doer (non-durable) is the only safe home.

**Spend Limits meters Pydantic AI responses only.** It prices each
`ModelResponse`; a CLI harness's cost never passes through it. A store is
two methods (`get_many`, `add_many` with a replay token), so a Kroker store
over the board can also receive the harness `cost_usd` from the code stage.
A refusal is not a serializable pause ("Pydantic AI's deferral path is
tool-boundary only"), so the stop stays the workflow's budget gate;
`exhausted()` is the admission check at run start. Core's
`UsageLimits(cost_limit=...)` bounds a single run with no store.

**Memory is safe to replay, not to memoize.** Under Temporal the injected
snapshot is a journaled operation, so replay is deterministic, but a
proposer's output would then depend on notebook state the memoization key
(ADR-5) does not include, and the page itself calls memory "model-written,
untrusted content". The operator notebook stays the only fit.

**Trajectory Judge, System Reminders, Ask User** confirmed the map: the judge
is rejected in durable runs and threads its usage into the run; `GoalReanchor`
is a zero-cost reminder and `LLMReminder` is journaled under durability;
`AskUser` holds the tool call open until the answerer returns, and its
question schema (header, 2–6 options, custom answer) is a candidate shape for
Kroker's clarify question cards.

**Pydantic AI Docs** covers six topics (capabilities, hooks, tools,
tools-advanced, toolsets, agent). Kroker is itself a Pydantic AI project, so
it belongs in the pyai doer's kit when Kroker runs against Kroker.

## 11. Second full-read pass: the remaining pages

After §10, every remaining page was read in full (prose): Step Persistence,
Code Mode, Shell, FileSystem, Modal Sandbox, Exa Search, Researcher,
Playwright, Browser Use, You.com, GitHub, Linear, Slack, Notion, Google
Workspace, LocalStack, Macroscope, Logfire MCP, StackOne, Ordinal, Media,
Managed Prompt, Repair Tool Arguments, Capability Creation, ACP, GitHub
Agentic Workflows, AWS Lambda, and the core pages (Web Search, Web Fetch,
Thinking, MCP, Tool Search, Select Model, Resolve Model ID, Prepare Tools,
Prefix Tools, Set Tool Metadata, Include Tool Return Schemas, Process
History, Process Event Stream, Raise Content Filter Error, Reinject System
Prompt, Thread Executor, Handle Deferred Tool Calls, Instrumentation, Image
Generation, X Search, On-Demand Capabilities, Building Custom Capabilities,
Third-Party Capabilities, `pydantic_evals.online_capability`). The pages for
PostHog, Grain, Day AI and Pylon return 404; their modules are in the 0.36.0
wheel. What changed:

**Kroker can write its own durable capabilities.** `@durable_operation`
moves a capability's I/O into an activity under Temporal, keyed by the
capability `id` and a stable operation name; `ctx.in_durable_context` tells
a hook where it runs. That is the right home for two things Kroker built
around the boundary: the research budget, whose file lock
(`src/sdlc/stages/research/budget_store.py`) holds only on one host, and a
spend store that also receives CLI harness cost. A `DynamicCapability`
built from `RunContext` per run is supported under Temporal when its
factory is deterministic.

**GLM has a native provider.** `pydantic_ai/providers/zai.py` (present in
the locked 2.20.0) is an OpenAI-compatible provider with a GLM profile:
`reasoning_content` preserved across turns, the OpenAI JSON-schema
transformer, and the Thinking page's Z.AI row (`thinking={'type':
'enabled'}`, `reasoning_effort` on GLM-5.2/5.3; GLM-5.3 always reasons).
Routing proposers as `anthropic:glm-5.2` puts them on an Anthropic profile
guessed for a model Anthropic does not serve. `ResolveModelId` can build a
`ZaiProvider` with the coding-plan base URL. The ADR-6 family check reads
the prefix, so `zai` versus the dev role's `zai-coding-plan` would pass it —
the same-weights question (OQ-A4) does not go away.

**Step Persistence is messages, not workspace.** It records step events, a
tool-effect ledger (a `started` effect with no terminal record is
"unknown after crash") and continuable snapshots, and says outright that
workspace snapshots are out of scope. Kroker's checkpoint commit is exactly
the missing half, so a pyai doer's resume is snapshot plus commit. Tools
with external effects (a push, a PR) should call `annotate_tool_effect`.
`S3MediaStore` speaks to MinIO, which Kroker's compose already runs.

**FileSystem gives the doer a veto point and a transcript.**
`FileChangeRequestEvent` fires before a write with the diff and a
`cancel(reason)` — the in-process twin of the `pre_tool` hook — and the
read/write/edit/search events are most of ADR-16's canonical
`HarnessSession` for free. Walkers skip dot-directories unconditionally, so
the crew's `.workspace/orchestration/` round files are reachable only by
direct path.

**Code Mode details that bind.** Under Temporal `max_duration_secs` is off,
so a CPU loop in `run_code` is stopped only by the memory and suspension
caps and Temporal's two-second workflow-task deadline; `max_tool_calls`
(default 100 per `run_code`) is a second budget beside the research
counter; approval-gated tools called from `run_code` fail unless
`HandleDeferredToolCalls` resolves them inline; eager execution and
speculation are disabled under durability.

**Exa has a public client seam.** `ExaSearch(client=...)` takes any object
satisfying the `ExaClient` protocol. Budget charging and page capture can
move into a client wrapper, retiring the private `_toolset` import — but a
client sees no `RunContext`, so the run id and scope must reach it another
way (a per-run capability built from deps is the natural one). Every Exa
tool now returns structured `ExaSource` citations in `ToolReturn.metadata`,
which `verify.py` could read instead of mirroring page text. On a
native-search model, `WebSearch` and `ExaSearch` collide on the
`web_search` name.

**Playwright constrains `smoke.browser`.** It is rejected under durable
execution at construction; `block_private_addresses=True` by default
refuses `localhost` and RFC 1918 hosts, which is where a compose stack
under test lives; downloads are refused, so the NEON DoD's "download the
PPTX" check belongs to an HTTP probe; `console_messages` and
`network_requests` expose exactly the class of defect NEON incident 16 was
(an API process missing its wiring); `storage_state` carries a login.

**Integrations share one shape and one risk.** GitHub, Linear, Slack,
Notion, Google Workspace and Logfire MCP take a per-run token from a
function over `deps`, offer `read_only`, and are approval-wrapped with
`ApprovalRequiredToolset`. Under Temporal `deps` are serialized into
workflow history, so a token carried there is stored in clear text unless
the client's data converter encrypts payloads — carry a secret reference,
not the secret.

**Environment facts.** LocalStack needs Docker for `manage_container` and an
auth token since 2026.03; Modal needs an account and cannot mount the
worktree; gh-aw runs a Pydantic AI agent on Linux runners behind an egress
firewall, which is a ready container-plus-egress tier for a hosted phase and
a trigger for `intake.issue`; ACP is experimental and removable; Browser Use
falls back to a separately billed hosted model unless `llm=` is set.

**Prompt management stays in git.** `ManagedPrompt` resolves in `wrap_run`,
which runs in workflow code under Temporal, and its page states no
durability behaviour; it also bypasses the E-82 prompt gate. Not for
proposers.

**The 2026-07-29 names are third-party packages.** `TodoCapability`,
`ConsoleCapability` and `ContextManagerCapability` are vstorm-co packages
(`pydantic-ai-todo`, `pydantic-ai-backend`, `summarization-pydantic-ai`);
the Harness's `Planning` states that it supersedes `pydantic-ai-todo`.

**On-demand bundles fit toolchains.** A deferred capability gates
instructions, tools, model settings and hooks together behind
`load_capability`. In the pyai doer, each `ToolchainAdapter` language
(ADR-15) can be one such bundle, loaded when the worktree's marker file says
so; capability ids must stay stable because loaded state is replayed from
history.
