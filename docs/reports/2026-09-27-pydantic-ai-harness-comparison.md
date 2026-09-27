# Pydantic AI Harness — how Kroker compares, and what it can take

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD or ROADMAP line. |
| Date | 2026-09-27 |
| Follow-up | `docs/reports/2026-09-27-pydantic-ai-capability-adoption-map.md` — the maximal-adoption map, written after this report and assuming new graph node types. Where its verdicts differ from §4 and §7 here, it is the later position. |
| Source | [Pydantic AI Harness docs](https://pydantic.dev/docs/ai/harness/) — the index plus 38 capability pages (Coder, FileSystem, Shell, Modal Sandbox, Code Mode, Subagents, Dynamic Workflow, Advisor, Trajectory Judge, Guardrails, Prompt Injection Defender, Spend Limits, Memory, Step Persistence, Compaction, Tool Output Limits, Skills, Repo Context, Ask User, System Reminders, Planning, Background Tools, and others) — and core's [Temporal durable-execution page](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), read in full. Current PyPI releases: `pydantic-ai-harness` 0.36.0, `pydantic-ai-slim` 2.51.0. |
| Method | Docs read. The 0.36.0 and 2.51.0 wheels were downloaded and inspected for the API questions in §2; the locked 2.20.0 sources in the venv were read for model resolution and provider-client construction (§3). The Harness source was otherwise not read and nothing was run against a model. Kroker anchors are checked against `main` @ `eb34fe1`; the uncommitted working-tree changes are not considered. |

## 1. Two systems at different altitudes

The Harness is a **capability library for one agent's loop**. Its own
definition of the word: a harness is "everything around the model that turns
it into an agent" — a workspace, a plan, memory, sub-agents, context
management, durable execution. Everything in it is one primitive, a
*capability* composed onto `Agent(capabilities=[...])`, and its two complete
agents (`Coder`, `Researcher`) are themselves combined capabilities. Its unit
of work is a single agent run and the children it delegates to. Durability is
delegated to core's durable-execution integrations (Temporal, DBOS, Prefect,
…), and each Harness capability declares how it behaves under them: a stable
`id`, journaled operations, or an explicit refusal.

Kroker is the **loop around many agent runs**. A deterministic `GraphWorkflow`
sequences 15 stages; proposers are single structured-output calls that hold
no tools (ADR-2, ADR-6, `ARCHITECTURE.md:475`, `:496`); the code is written by
third-party coding CLIs (`claude -p`, `opencode run`, cursor) inside per-task
worktrees, and only their diff is admitted (`ARCHITECTURE.md` §4). Kroker uses
the word "harness" for exactly the thing the Pydantic package ships — the
difference is that Kroker **buys** its harness as a CLI and wraps it in an
adapter, where the Pydantic package **builds** one in-process.

So the overlap is narrow and specific. It covers four seams: the proposer
runtime (Pydantic AI core's durability API), the one tool-using proposer
(research), the doer slot (`Coder` against the CLI adapters), and the
cross-cutting controls (secrets, injection, spend, telemetry). The pipeline,
the gates, the frozen Validation Contract, cross-family review, the board and
the benchmark have no counterpart in the Harness. It is a box of parts, not an
SDLC, and it does not try to be one.

## 2. Where Kroker stands with the Harness today

### 2.1 One consumer, bound to a private module

The Harness has exactly one consumer: the research role, which composes
`CodeMode` and an `ExaSearch` subclass (`agents/research/agent.py:6`, `:45`).
The subclass imports the private module `pydantic_ai_harness.exa._toolset`
(`agents/research/exa_wrapper.py:18`) and writes the private attribute
`toolset._id` (`:90`), because `ExaSearchToolset` passes no `id` to
`FunctionToolset` and the Temporal wrapper refuses an id-less leaf toolset.

Inspecting the 0.36.0 wheel: `ExaSearchToolset.__init__` still calls
`super().__init__()` with no `id`, and its constructor keywords and the
`web_search(query)`, `get_page(url)`, `deep_search(question)` signatures match
what the subclass overrides. The workaround therefore still fits the newest
release at the signature level (not exercised at runtime). It remains a
binding to a private module of a 0.x package whose version policy allows
breaking changes between minor releases.

The 2026-07-29 research design
(`docs/superpowers/specs/2026-07-29-research-agent-exa-harness-design.md:4`)
names `TodoCapability`, `ConsoleCapability` and `ContextManagerCapability`.
None of these exists in `pydantic-ai-harness` (no such module in the 0.36.0
wheel): they are the vstorm-co community packages `pydantic-ai-todo`,
`pydantic-ai-backend` and `summarization-pydantic-ai`, listed on Pydantic AI's
third-party page. The shipped agent carries only `CodeMode` and `ExaSearch`.

### 2.2 The lock is not what CI and the image install

`pyproject.toml:12` declares `pydantic-ai-slim[...]>=0.4` and `:18` declares
`pydantic-ai-harness[codemode,exa]>=0.7`. `uv.lock` pins 2.20.0 and 0.13.0.
CI (`.github/workflows/ci.yml:20`) and the image (`Dockerfile:82`) install
with `pip`, which does not read `uv.lock`, so both resolve the newest release
that satisfies the floors — 2.51.0 and 0.36.0 today. A uv-synced development
venv and CI therefore run code 31 minor versions (core) and 23 minor versions
(Harness) apart, and every image rebuild picks up whatever shipped that week.
For a 0.x dependency whose private module the research role imports, that is
a reproducibility gap rather than a style point. The floors are also
meaningless as floors: `>=0.4` admits versions that predate the Temporal
integration the worker registers (`src/sdlc/worker.py:26`).

### 2.3 `TemporalAgent` is deprecated

Already in the locked 2.20.0, and still in 2.51.0, `TemporalAgent` carries
`@deprecated` in favour of the `TemporalDurability` capability, beside
`# TODO(v3): remove`. Kroker wraps 16 agents in it
(`src/sdlc/agents/roles.py:214`–`:268`), and `ARCHITECTURE.md` §4, §13 and
ADR-2 name it as the mechanism.

The Temporal page states the replay condition: `TemporalDurability` "accepts
the activity names and payload shapes recorded by `TemporalAgent`" as long as
the agent `name`, toolset `id`s and `models=` registry keys stay the same and
any `event_stream_handler=` stays on the durability capability while old
workflows are in flight — "there's no need to drain or version your workflows
first". Kroker already pins every agent name ("NEVER rename") and registers no
event stream handler, and it uses no tool `args_validator`, whose activity
sequence the page says changes on upgrade. In-flight runs are not the
obstacle.

The real cost is structural. `TemporalDurability` must be attached when the
agent is **constructed** — passing capabilities to `run()` inside a workflow
raises `UserError` — and Kroker constructs agents in 14 asset files through
`build(model, instructions, model_settings)` (`src/sdlc/agents/loader.py`),
plus the two clarify fan-out agents in `roles.py`. The migration therefore
changes the registry's asset contract, not only `roles.py`.

The migration does not change the research budget problem recorded at
`src/sdlc/stages/research/toolset.py:21`: a tool activity still receives a
deserialized copy of `RunContext` — the page is explicit that "mutating them
inside an activity does not affect the run" — so the disk-persisted counter
(`src/sdlc/stages/research/budget_store.py`) stays necessary.

### 2.4 Telemetry records content

`src/sdlc/observability/logfire_setup.py:5` states the invariant: span
attributes are metadata only, "NEVER transcript payloads". Line 26 calls
`logfire.instrument_pydantic_ai()` with no arguments, and core's
`InstrumentationSettings` defaults `include_content=True`
(`pydantic_ai/models/instrumented.py:71` in 2.20.0) — prompts, completions,
tool arguments and tool results. When `LOGFIRE_TOKEN` is set, the invariant
does not hold. `logfire` is not installed in the development venv, so whether
its wrapper forwards `include_content=False` was not checked. The Temporal
page's `LogfirePlugin` instruments Temporal as well as Pydantic AI and keeps an
existing `logfire.configure()`; adopting it would need the same content
setting.

## 3. What the Temporal page adds

Read against the code, four statements on the Temporal page describe
defects in Kroker today. None is caused by the deprecation; all four exist
under `TemporalAgent` and would carry over unchanged into a migration.

### 3.1 Per-run proposer model overrides do not reach the model call

"Model Selection at Runtime" says a model is chosen per run by passing it to
`agent.run(model=...)`; a model-name string needs no registration. Kroker
resolves a per-run proposer model everywhere except the call.
`RoleHost._run_role` (`src/sdlc/workflows/role_host.py:120`) receives `model`
and uses it for pricing (`:143`) and usage tracking (`:153`), then runs
`agent.run(*args, **kwargs)` (`:135`) without it. No call site passes
`model=` either — the reviewer, for one, calls
`ctx.run_role(cfg, "reviewer", model, reviewer_agent, prompt)`
(`src/sdlc/stages/review/step.py:133`) — and nothing in `src/sdlc` uses
`agent.override(...)` or a `models=` registry. The agent runs on the model it
was built with from the registry at import.

The override is nevertheless accepted and recorded. `--role-model` builds
proposer entries (`src/sdlc/cli_roles.py`, `build_role_overrides`),
`Arm.resolve()` applies an arm's `default` to every proposer role
(`src/sdlc/benchmarks/models.py`), `validate_run_roles` checks ADR-6 over the
overridden map, and `resolve_role_model` moves the memoization key
(`role_host.py:108`). A benchmark arm or a CLI run that overrides a proposer
therefore runs the registry model while its cost, its `RoleUsage.model`, its
cache key and its ADR-6 verdict all describe the override. The model × role
sweep is only real for the harness roles, whose model reaches the CLI adapter.
`tests/test_role_model_resolution.py` pins the resolver and the key, not the
model that answers. The loader's own docstring names this failure class for
the harness roles: "Drift between them is what let ADR-6 validate a role that
never ran" (`src/sdlc/agents/loader.py:331`).

In the locked 2.20.0, `TemporalModel._resolve_model_id` resolves an
unregistered model-id string with `infer_model` inside the model activity
(`pydantic_ai/durable_exec/temporal/_model.py:399`), so forwarding the string
works under `TemporalAgent` as well. Override strings must then be real
Pydantic AI model ids (`provider:model`); the resolver tests use the
`openai/gpt-5.2` form, which is not one.

### 3.2 Research launched by the architect is unpriced

The page: "If a tool delegates to another agent with `usage=ctx.usage`, the
delegate's tokens and requests stay behind in the activity: they're missing
from the parent run's `result.usage` and are never charged against its usage
limits." The architect's `research` tool
(`agents/architect/agent.py`) calls `research_subquery`, which runs the
research agent inside the architect's tool-call activity and returns only the
`ResearchBrief` (`src/sdlc/stages/research/toolset.py`). `_run_role` prices
the architect's `result.usage` alone, so the research agent's model tokens on
this path reach neither the per-role cost (E-33) nor the run budget gate
(`role_host.py:165`, `_check_budget`). The persisted research budget does not
cover them: `Budget.cost_usd` counts per-search and per-fetch prices
(`src/sdlc/stages/research/deps.py:72`), not tokens. The research *stage*
already hands its usage back from its activities
(`src/sdlc/stages/research/models.py:80`); the architect path is the one that
does not.

### 3.3 An oversized prompt hangs the run instead of failing it

The page: values travelling *into* an activity — "the message history a
model request carries" — are encoded in workflow code, where an over-limit
payload fails the workflow *task*; "the retry policy doesn't bound it either:
the run retries indefinitely rather than raising." The per-payload cap is
2 MB by default. Kroker bounds every proposer activity at three attempts
(`roles.py:37`) precisely so that a stage fails instead of hanging
(the e2e-proposer-hang fix), but this failure never reaches the activity, so
that bound does not apply. The reviewer prompt embeds the full patch —
`_get_patch` returns `diff["patch"]` untruncated
(`src/sdlc/stages/review/step.py:68`) — and the research agent's history
grows with every page it reads. `ARCHITECTURE.md` §11 lists a "runtime guard"
for oversized payloads; no guard on proposer prompt size exists in `src/`.
The page offers two backstops: Temporal external storage on the
`DataConverter` (public preview), or a claim-check `PayloadCodec`, both of
which `PydanticAIPlugin` preserves. The second is ADR-10's own pattern, applied
at the codec instead of by convention.

### 3.4 Model requests retry inside retries

The page recommends turning off transport retries and "your provider API
client's own retry logic" under Temporal, because the layers multiply and
mishandle `Retry-After`. Kroker's proposers are built from model strings, so
Pydantic AI's `AnthropicProvider` constructs `AsyncAnthropic` without a
`max_retries` argument (`pydantic_ai/providers/anthropic.py:110`–`:115`), and
the SDK default is `DEFAULT_MAX_RETRIES = 2` (`anthropic/_constants.py:10`).
Under three Temporal attempts, one model request can reach nine HTTP calls.
The 2026-08-04 fan-out design already asked for this check ("9.2 No retries
beneath Temporal",
`docs/superpowers/specs/2026-08-04-research-fan-out-design.md:252`); it was
deferred to a manual check and is still open. Under `TemporalDurability` the
page's answer is a `ResolveModelId` capability that builds the provider with
`max_retries=0` on the worker.

### 3.5 Smaller points

- **Activity configuration.** `TemporalDurability` validates `ActivityConfig`
  keys at construction — a typo in the `TypedDict` otherwise fails inside the
  workflow and "is retried indefinitely" — and gives model-request activities
  a 30-second `heartbeat_timeout` by default. Kroker's bounded configs
  (`roles.py:37`, `:55`) carry over as `activity_config=`.
- **Persisted payload schemas.** Deps and workflow inputs are decoded by the
  currently deployed worker; "adding a required field … can cause payload
  decoding to fail before the workflow or activity body executes". New fields
  on `ResearchDeps` and on workflow inputs need defaults.
- **Workflow Streams.** `event_stream_topic` turns a workflow into an
  offset-addressed event channel a UI can subscribe to. The page's own caveat
  — one consumer per run, fanned out by the application — is the shape the
  dashboard's shared poller already has (E-10), so live proposer progress is
  reachable without new infrastructure if it is ever wanted.
- **Non-durable runs.** "A run is durable only inside a workflow." The
  architect's research sub-run is non-durable by that definition, as
  `toolset.py` already records; the operator chat agent is non-durable by
  design and only signals workflows, which is the pattern the page recommends.

## 4. Capability map

Verdicts: **Adopt** (take it roughly as shipped), **Adapt** (take the
mechanism, bend the defaults), **Experiment** (worth a measured trial),
**Watch** (relevant to an unbuilt phase), **Reject** (conflicts with an
invariant).

| Harness capability | Kroker today | Verdict |
|---|---|---|
| `TemporalDurability` (core) | `TemporalAgent` ×16, `roles.py:214` | **Adopt** — §2.3, §6.7 |
| `ResolveModelId` (core) | model strings, SDK-default client retries | **Adopt** with §6.7 — §3.4 |
| `Instrumentation` (core) | `logfire_setup.py:26`, content on | **Adapt** — content off, §2.4 |
| `CodeMode` | research role, in use | keep; upgrade with §6.5 |
| `Coder` = `FileSystem` + `Shell` + `RepoContext` + `SubAgents` + compaction + `ToolOutputLimits` + `RepairToolArguments` | `CodingHarness` adapters `claude_code` / `opencode` / `cursor` (`src/sdlc/harness/`) | **Experiment** — a fourth adapter built from the parts, not `Coder()` itself, §6.10 |
| `Shell` | CLI-native bash + env allowlist (`harness/base.py:72`, `:98`) | **Adapt** inside §6.10 — `Shell(env=...)` expresses the allowlist |
| `FileSystem` | worktree cwd + containment native deny | **Adapt** inside §6.10 — read-only globs express "never edit `<stage>.md`" |
| `Modal Sandbox` | E-21 / FR-1002 container tier, open (`ROADMAP.md:376`) | **Watch** — isolates tool calls of an in-process agent, not a CLI process |
| `SubAgents` | architect's `research` tool (`agents/architect/agent.py`), crew | no gain — delegate usage stays behind in the activity either way (§3.2) |
| `DynamicWorkflow` | `GraphWorkflow` (ADR-11); clarify fan-out (`stages/clarify/step.py:71`) | **Reject** between stages; **Experiment** as ADR-21's measured scheduler, §6.12 |
| `Planning` | planner → `ImplementationPlan` / `DevTask` + board | **Reject** for proposers |
| `Advisor` | crew critic (`crew/roles/critic.yaml`) | **Reject** under durability — native mode needs an Anthropic or OpenRouter pair; local mode is unsupported in durable runs |
| `Compaction` family | ADR-13 "compaction is failure"; ceiling via `CONTEXT_WINDOWS` (`harness/base.py:41`) | **Adapt** — `WarnNearLimits` / `ReportContextUsage` as the ceiling sensor; never summarise a doer session |
| `ToolOutputLimits` | `SUMMARY_MAX` (`harness/base.py:33`), claim-check | **Adapt** — spill mode for research `get_page`, which also bounds §3.3 |
| `Warn On Cache Busts` | — | low value — proposers are single-shot |
| `Memory` | Hindsight + `RecallSnapshot` (ADR-5) | **Reject** — agent-written memory mid-run breaks "memory is I/O" |
| `Conversation Search` | `HarnessSession` artifacts (ADR-16) | **Watch** — deep_review / retro |
| `Skills` | `crew/skills/<role>/SKILL.md` | **Adapt** inside §6.10 — the same files load on demand |
| `Repo Context` | CLIs load `AGENTS.md` / `CLAUDE.md` natively | **Adapt** inside §6.10 |
| `Guardrails` detectors | `src/sdlc/memory/scrub.py:10`, four regexes | **Adopt**, §6.9 |
| `ToolGuardrail` | `pre_tool` hook (`harness/hook.py`, `policy/containment.yaml`) | **Adapt** inside §6.10 — same policy, second enforcement point |
| `Prompt Injection Defender` | nothing screens web content | **Adopt** candidate for research, §6.8 |
| `Spend Limits` | `pricing.py` activity (E-33), run budget, `budget_store.py`, crew `cost_usd` cap | **Watch** — P7 per-tenant windows, §6.11 |
| `Ask User` | gates (ADR-4) + E-17 `defer` | **Reject** — holds the run open inside a tool call |
| `System Reminders` | — | low; possible inside §6.10 |
| `Trajectory Judge` | crew critic, between rounds | **Experiment** inside §6.10 only — the Harness itself rejects it in durable runs |
| `Repair Tool Arguments` | `max_tokens` workaround for truncated tool-call arguments (`agents/settings.py:23`) | **Experiment** — open question §8 |
| `Step Persistence` | Temporal history + checkpoint commits + CLI `--resume` | only inside §6.10, as the resume handle |
| `Managed Prompt` | prompts as git assets; `PROMPT_SHAS` (`roles.py:209`) in the memoization key | **Reject** |
| `Capability Creation` / `RuntimeAuthoring` | — | **Reject** |
| ACP, gh-aw | operator chat (E-86); MCP server FR-602 open (`ROADMAP.md:304`) | **Watch** |

## 5. Where each side is ahead

### 5.1 Kroker

**Governance between steps.** The Harness's human-in-the-loop primitives —
`AskUser`, `ToolGuardrail`'s `approve`, core's `HandleDeferredToolCalls` —
all resolve inside one run: `AskUser` "waits inside the tool call for the
answerer to return". Kroker's E-17 `defer` ends the run and parks the decision
in a workflow gate that can wait days, with a policy, a round identity and one
inbox across surfaces (ADR-4). For an unattended factory, the Kroker shape is
the durable one, and nothing in the Harness replaces it.

**Decorrelation by construction.** ADR-6 and ADR-12 make the judge a
clean-context proposer of a different model family. The Harness has no notion
of family independence. `Coder`'s `SubAgents(include_self=True)` delegates to
the same model by design — the opposite of what ADR-6 wants for anything that
reviews — and `Advisor` and `TrajectoryJudge` accept a different model without
enforcing one. (§3.1 qualifies this for per-run overrides: the check runs over
a map the proposers do not execute.)

**Containment as a declared, reported capability.** The Harness is explicit
that its controls are not a boundary: "Neither control is a security
boundary" (Shell env), "Path restrictions on file tools are not a shell
sandbox" (Coder), and `Coder`'s shell is unrestricted with only
`LLM_API_KEY_ENV_PATTERNS` stripped — "other host credentials and files remain
accessible". Kroker's env is an allowlist (`harness/base.py:72`), and ADR-17
records which layers each adapter enforces in a `ContainmentReport`, with
`strict` refusing partial coverage. Neither side is a sandbox; Kroker is the
one that says, per run, how much of a fence it had.

**Reproducibility.** The memoization key covers prompt hash, model and recall
snapshot (ADR-5), artifacts are claim-checked, sessions are artifacts
(ADR-16). Several Harness capabilities move the opposite way: `ManagedPrompt`
moves prompt identity out of git, `Memory` lets the model rewrite its own
inputs, `RuntimeAuthoring` lets it write new capabilities. Those are
conveniences for a product agent and controlled-variable violations for a
pipeline whose benchmark varies one axis at a time.

### 5.2 The Harness

**An in-process doer.** A Pydantic AI coding loop yields typed `ModelMessage`
history instead of CLI JSON to parse, runs any model Pydantic AI supports, and
has no CLI version skew. ADR-17's "adapter reality" paragraph
(`ARCHITECTURE.md:609`) is a list of exactly that skew: opencode 1.18.4 has no
config flag, cursor surfaces neither layer and fails closed. ADR-16's
canonical `HarnessSession` is close to free when the transcript is already
`ModelMessage`.

**Context engineering as components.** Kroker's ceiling depends on a
five-entry substring table (`harness/base.py:41`) where an unknown model
"falls back to the resume counter". The Harness resolves windows from model
profiles, reports usage live (`ReportContextUsage`), and spills oversized tool
output to a pageable store.

**Safety depth.** `detectors.secret_data()` and `personal_data()` cover vendor
key formats, private-key blocks, cards and IBANs; `scrub.py` has four regexes.
`PromptInjectionDefender` classifies untrusted tool results locally; Kroker
has no equivalent.

**Durability-aware design.** Each Harness capability states its replay
behaviour: a stable `id`, which operations are journaled, or an up-front
`UserError` (`TrajectoryJudge` in a durable run). That is a useful template
for Kroker's own activity-side components.

**Budgets across windows and tenants.** `SpendLimits` meters USD and tokens
per day, month or tenant, with an idempotency token per response so a
replayed accrual is not double-counted. Kroker meters per run, which is what
P1–P6 need; P7 needs per-tenant windows.

**Public benchmarking.** `Coder` ships a Terminal-Bench 2.1 playbook for
Harbor — the same harness the 2026-09-26 Harbor report
(`docs/reports/2026-09-26-harbor-framework-analysis.md` §3.2) considers as a
comparison point.

## 6. Candidates, ranked by value

The first four are defects from §3; they are ranked above everything that
only adds capability.

### 6.1 Forward the resolved proposer model to the call

- **Change:** `_run_role` passes its `model` to `agent.run(model=...)`, and
  the override parser rejects strings that are not Pydantic AI model ids.
  A test asserts the model that answers, not only the resolver.
- **Payoff:** proposer arms of the benchmark and `--role-model` runs measure
  the model they are labelled with; ADR-6 checks a map that runs.
- **Cost:** small in code. Every proposer-arm benchmark record made so far is
  suspect and needs re-running or re-labelling.
- **Status:** New. Defect.

### 6.2 Charge the architect's research sub-runs

- **Change:** `research_subquery` returns the delegate's usage with the brief
  (the page's advice: carry it yourself), and the architect stage adds it to
  the research role's `RoleUsage` before `_check_budget` runs.
- **Payoff:** E-33's per-role cost and the run budget gate see all model
  spend.
- **Cost:** small; the tool's return type changes.
- **Status:** New. Defect.

### 6.3 Bound proposer prompt size before the call

- **Change:** a size check in `_run_role` that fails the stage
  non-retryably above a margin under the payload cap, plus a bounded patch in
  the reviewer prompt; as a systemic backstop, a claim-check `PayloadCodec`
  on the client's `DataConverter`.
- **Payoff:** turns an unbounded workflow-task retry — a hang — into a stage
  failure, the same property the e2e-proposer-hang fix bought for activity
  failures.
- **Cost:** small for the guard; medium for the codec, whose stored payloads
  must outlive every replayable history.
- **Status:** New. Defect.

### 6.4 Turn off retries beneath Temporal

- **Change:** build proposer models with an explicit provider whose client
  has `max_retries=0` — under `TemporalAgent` by constructing the model in
  `build()`, under `TemporalDurability` through `ResolveModelId`.
- **Payoff:** one model request is at most three HTTP calls, not nine, and a
  429 storm fails where Temporal can see it (spec 2026-08-04 §9.2).
- **Cost:** small; touches the same `build()` contract as §6.7.
- **Status:** Open since 2026-08-04.

### 6.5 Pin the dependencies and install from the lock

- **Change:** either bound the ranges
  (`pydantic-ai-harness[codemode,exa]>=0.36,<0.37`, and a core floor at the
  first release with `TemporalDurability`), or switch CI and the image to
  `uv sync --frozen`.
- **Payoff:** CI, the image and development run the same code; a Harness
  minor that moves `exa._toolset` fails one upgrade PR instead of an image
  rebuild.
- **Cost:** small. The upgrade from 0.13.0 to 0.36.0 itself needs a pass over
  23 minors of release notes and the research tests.
- **Status:** New.

### 6.6 Drop content from telemetry

- **Change:** `logfire.instrument_pydantic_ai(include_content=False)` at
  `logfire_setup.py:26`, after confirming the parameter on the pinned
  `logfire`.
- **Payoff:** restores the module's own stated invariant (§2.4).
- **Cost:** one line.
- **Status:** New.

### 6.7 Migrate `TemporalAgent` to `TemporalDurability`

- **Change:** each `agents/<role>/agent.py` attaches
  `TemporalDurability(activity_config=...)` at construction — so `build()`
  gains a parameter supplied by the loader; `roles.py` keeps `t_*` as plain
  aliases of the agents; the worker registers them through
  `__pydantic_ai_agents__` or `AgentPlugin`; `ARCHITECTURE.md` §4, §13 and
  ADR-2 change wording in the same diff.
- **Payoff:** leaves a deprecated path before v3 removes it; config keys are
  validated at construction; and it is the precondition for every Harness
  capability with durable operations (`SpendLimits`, `ToolOutputLimits`
  summaries, compaction summaries) and for `ResolveModelId`.
- **Cost:** 14 asset files plus the two clarify fan-out agents built in
  `roles.py`, the loader, the worker, the `temporal` test tier. Replay of
  in-flight runs is covered by the page's condition, which Kroker already
  meets (§2.3). The research toolset still needs its stable id.
- **Status:** New. Deadline set by pydantic-ai v3.

### 6.8 Screen research tool results

Research is the pipeline's first outbound egress (`ROADMAP.md:313`, FR-703)
and repositories are hostile input (NFR-9). Page text flows through
`ResearchBrief` into the architect's context. `verify.py` checks that each
quote is a substring of a page fetched this run, but nothing checks the pages
for planted instructions.

- **Change:** `PromptInjectionDefender` (pattern detection; optional local ML
  classifier, no network call) on the research agent, with
  `block_high_risk=True` for `get_page` and `deep_search`, and
  `ToolGuardrail(result_guard=for_tool_result_text(redact_secrets))` beside it.
- **Payoff:** closes an injection channel that exists today and grows with
  the fan-out.
- **Cost:** one extra, two capabilities. It depends on §6.7 being settled,
  and on the open question in §8 about where result guards execute under
  durability.
- **Status:** New.

### 6.9 Replace the scrub regexes with the Harness detectors

- **Change:** `memory/scrub.py` delegates to `secret_data()` and
  `personal_data(only=[...])`; the same function serves ADR-16's fail-closed
  session scrub.
- **Payoff:** vendor key formats and private-key blocks, maintained upstream.
- **Cost:** small; the dependency is already present. The `email` detector
  rewrites `git@github.com` — the current regex has the same behaviour, so
  nothing regresses, but code-bearing text wants `only=` without `email`.
- **Status:** New.

### 6.10 A fourth `CodingHarness`: an in-process Pydantic AI coder

This is the largest item and the only one that changes what Kroker measures.

- **Shape:** a `CodingHarness` subclass that returns `HarnessRunResult` like
  the others and runs `agent.run()` in-process **inside the existing
  heartbeating harness activity**, on the `ai-sdlc-harness` queue. It does
  **not** use `TemporalDurability` per tool call: the worktree lives on one
  host's disk, and per-tool activities could be dispatched to another harness
  worker (ADR-9). One activity on one host is the property the CLI adapters
  already rely on. By the page's definition such a run is not durable — like
  a CLI session, a lost worker costs the session back to its last checkpoint
  commit.
- **Composition, not `Coder()`:** `FileSystem(root_dir=<worktree>)` with
  read-only patterns for `<stage>.md` contracts and agent config;
  `Shell(env=build_env(...))`, i.e. the allowlist rather than
  `LLM_API_KEY_ENV_PATTERNS`; a `ToolGuardrail` whose guard evaluates the
  predicates `harness/containment.py` already compiles from
  `policy/containment.yaml`, with `approve` surfacing as deferred tool
  requests into the E-17 gate; `RepoContext`; `Skills('crew/skills')`;
  `WarnNearLimits` as the ADR-13 ceiling sensor, ending the session for a
  fresh one with a structured handoff rather than compacting;
  `StepPersistence` with a file backend under `runs/<run_id>/` as the resume
  handle.
- **Payoff:** a fourth arm on the benchmark's harness axis
  (`BENCHMARK.md:195`) where the model is decoupled from the CLI; crew roles
  of any model family, which makes ADR-6 cheaper to satisfy; a transcript that
  is already typed; containment that can declare both a `native` layer
  (FileSystem root) and a `hook` layer (ToolGuardrail).
- **Limits:** it is still a fence, not a sandbox, exactly like the CLIs;
  FR-1002 is untouched. Whether it codes as well as claude-code or opencode is
  unknown, and that is what the benchmark has to answer before any registry
  default moves.
- **Status:** New. Large.

### 6.11 `SpendLimits` for the hosted phase

- **Change:** when P7 starts, per-tenant daily and monthly budgets through
  `SpendLimits` with a Postgres-backed store (the store protocol is two
  methods).
- **Payoff:** windows and tenants, which the per-run budget does not express;
  replay-safe accrual.
- **Cost:** requires §6.7; must coexist with E-33's pricing activity, which
  stays the source of per-role cost attribution.
- **Status:** Watch, gated on P7.

### 6.12 `DynamicWorkflow` as the measured scheduler

ADR-21 defers an LLM scheduler so that "it can be *measured* against the
workflow rather than adopted on faith" (`ARCHITECTURE.md:708`).
`DynamicWorkflow` is a ready-made version of that arm: the model writes one
sandboxed script over named sub-agents, bounded by `max_agent_calls`, and
under Temporal the script runs in workflow code and replays against recorded
activities.

- **Change:** a benchmark-only arm in which the stage proposers are
  `DynamicWorkflow` sub-agents and the orchestrator decides the sequence.
- **Payoff:** puts a number on ADR-11 instead of an argument.
- **Cost:** medium; benchmark-only, never on the production path. A script
  that computes for more than two seconds fails the workflow task, so
  sub-agent calls must be the only heavy work.
- **Status:** Experiment.

## 7. What not to take

- **`ManagedPrompt`** — moves prompt identity out of git and out of the
  memoization key (ADR-5, `ARCHITECTURE.md` §10 prompt lifecycle).
- **`Memory`** — the model writes its own future inputs mid-run; Kroker's
  memory is recalled by the orchestrator, snapshotted and hashed.
- **`AskUser`** — a gate that lives inside an activity cannot outlast a worker
  and cannot wait days.
- **Summarising compaction for doer sessions** — ADR-13 treats a compacted
  session as one that has lost its reasoning thread.
- **`TrajectoryJudge` and local `Advisor` in proposers** — the Harness itself
  refuses or does not support them in durable runs.
- **`DynamicWorkflow` between stages** — ADR-11.
- **`RuntimeAuthoring` / capability creation** — an agent that writes its own
  capabilities breaks the rule that a harness cannot rewrite what it is judged
  by (`AGENTS.md`, "Who may change what").
- **`Coder()` as shipped** — unrestricted shell, denylist env, same-model
  self-delegation; §6.10 takes its parts instead.

## 8. Open questions

- Under `TemporalDurability`, does a `ToolGuardrail` `result_guard` or
  `PromptInjectionDefender` run inside the tool activity or in workflow code?
  The answer decides whether the ML classifier's model load and inference are
  replay-safe (§6.8).
- Does `RepairToolArguments` repair output-tool calls — the structured output
  every proposer emits — or only function tools?
- Can per-tool activity configuration give host affinity on the harness
  queue? If it can, §6.10 could become durable per tool call instead of per
  session.
- `ExaSearchToolset` still sets no toolset `id` in 0.36.0. An upstream issue
  would retire the private workaround in §2.1.
- Which benchmark records so far carry a proposer override (§6.1)? The answer
  sizes the re-run.
