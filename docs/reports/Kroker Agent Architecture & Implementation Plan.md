# Kroker: Agent Architecture & Implementation Plan

Oct 4, 2026 · @Maksim

## Summary

Recommendation: build Kroker as a **deterministic workflow of bounded ReAct agents**. Code owns the control flow and every final verdict; each role is a small tool-using agent that investigates and returns structured evidence.

This fixes the four problems the benchmark exposes (reviewer approves 21/21 while the oracle rejects 93%; 58/73 tasks exhaust the fix budget; 16/17 research runs fail grounding; one model family everywhere):

- **Blind roles** get read-only repo tools, so they can check instead of guess.
- **Rubber-stamp verdicts** are replaced by code computing `approve` / `tests_passed` from per-assertion evidence.
- **Bad plans** are caught by validators and a contract dry-run before code is written.
- **Correlated errors** are broken by putting judges on a different model family than dev, checked by `model_id`.

Not recommended: one autonomous agent running the whole pipeline. It would be harder to measure, and the existing Temporal-style steps, human gates and prompt-gate already give a good skeleton.

Basis: the two analyses in this project (`agent-quality-plan.md`, `agent-architecture.md`, 2026-09-23) and the benchmark of 21 runs. The repo was not re-read for this doc, so file paths should be confirmed in Phase 0.

## Design principles

1. **Workflow outside, agents inside.** The orchestrator decides order, retries, budgets and gates. Agents never decide what runs next.
2. **Model observes, code decides.** Models emit per-item observations with evidence; booleans like `approve`, `tests_passed`, `stack_mismatch`, `plan_valid` are pure functions in code.
3. **Evidence before verdict.** Every output schema lists `evidence` fields before `status`; judge roles run with thinking on.
4. **Validate inside the conversation.** Anything checkable (paths exist, quote is in the file, ids unique, every requirement covered) is an `output_validator` raising `ModelRetry`, not an outer re-run.
5. **Read access, not reasoning access.** Clean context means no view of the developer's session; read-only access to the worktree is allowed (ADR-12 holds).
6. **Decorrelate judges.** Reviewer, critics and adversary use a different weights family than dev, enforced by `model_id`, not provider prefix (ADR-6).
7. **Every change is measured.** No prompt or model change ships without a before/after on prompt-gate or the benchmark, one variable at a time.

## Agentic patterns used

Kroker uses 10 of the 12 patterns in Google's catalogue, with **Custom Logic** as the backbone: code owns order, branching and verdicts, and the flexible patterns run only inside one bounded role step. Coordinator and Swarm are excluded on purpose.

| Pattern | Used | Where in Kroker |
| --- | --- | --- |
| Custom logic | Yes, backbone | Temporal workflow: stages, brownfield/greenfield branches, triggered deep\_review, budgets, computed `approve` / `plan_valid` |
| Sequential | Yes | clarify → architect → plan → per-task loop → merge |
| Parallel | Yes | clarify probes C3–C6, contract compile per task, 4 reviewer lenses, research sub-questions |
| Loop | Yes, bounded | per-task fix loop (2 attempts), research refine rounds |
| Review and critique | Yes | architect → critic, planner → plan critic, dev → QA + reviewer lenses; critics on another model family |
| Iterative refinement | Yes | fix loop with the task ledger; `output_validator` + `ModelRetry`; one revision round after a critic |
| ReAct | Yes, inside roles | roles with repo tools; dev and test harnesses |
| Human-in-the-loop | Yes | gates after clarify, architecture, plan and at merge; finding waivers |
| Hierarchical task decomposition | Partly | planner splits feature into tasks, then one contract per task; depth fixed by code |
| Single-agent | As a building block | each role is one agent with tools; the system is not |
| Coordinator | No | no LLM picks the next agent; Harness Dynamic Workflow and Subagents not used |
| Swarm | No | agents never talk to each other, only through typed evidence, so judges stay independent |

The trade-off is predictability over flexibility: runs must be measurable and replayable (prompt-gate, benchmark, watermarked memory). Source: [Google Cloud: choose a design pattern for your agentic AI system](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system).

## Agent runtime: shared building blocks

Every role is assembled from the same seven parts, so a new role is configuration plus a prompt, not new plumbing.

| Block | What it is | Used by | Build vs. reuse |
| --- | --- | --- | --- |
| `RoleSpec` (in `agent.yaml`) | model id, family, `ModelSettings` (thinking budget, max tokens), tool budget (max steps / tool calls), retries | all roles | **Reuse:** Thinking capability, Spend Limits, per-tool `max_retries`. **Build:** the per-role config schema and step caps |
| `RepoReadTools(root, commit)` | `read_file`, `grep`, `list_dir`, `git_show`, `find_tests`; read-only, pinned to a commit, output truncated with paging | clarify probes, architect, planner, QA, reviewer, analyst, discover | **Reuse:** FileSystem with `read_only=True` and `tools` incl. `grep`, `list_files` on `LocalWorkspace(worktree, read_only=True)`; Tool Output Limits. **Build:** `git_show`, `find_tests`, commit pinning via a git worktree. Note: walkers skip dotfiles (`.github`), so CI configs are read by explicit path |
| `SandboxTools` | `run_command(cmd, timeout)` and `run_single_test(name)` in an isolated worktree, budgeted | planner dry-run, QA | **Reuse:** Shell (allowlist, timeouts) inside Bubblewrap, Modal or E2B Sandbox. **Build:** thin `run_single_test` wrapper |
| Validators library | reusable `output_validator`s: `paths_exist`, `quote_in_file`, `ids_unique`, `dag_acyclic`, `covers_all(requirements)`, `fragment_was_fetched` | all proposer roles | **Reuse:** core `output_validator` + `ModelRetry`. **Build:** the validators themselves |
| Evidence schemas | `AssertionEvidence`, `Finding{path, line, quote, severity, lens}`, `Coverage{requirement, ids}`, all with `Field(description=...)` | QA, reviewer, architect, planner, analyst | **Build** (Kroker domain logic) |
| Verdict functions | pure Python: `review_verdict(qa_evidence, findings)`, `plan_verdict(plan)`, `task_verdict(...)`; unit-tested | gates, fix loop | **Build** (Kroker domain logic) |
| `ModelRouter` + ADR-6 check | resolves role to model; fails start-up if a judge shares a `model_id` family with dev | all roles | **Reuse:** Select Model, Resolve Model ID. **Build:** the family check |
| Tracing | tool calls, retries, tokens, cost per role | all roles | **Reuse:** Instrumentation + Logfire |
| dev-harness | coding agent for test and dev tasks | test-harness, dev-harness | **Option:** Coder + Repo Context instead of opencode (any model). **Build:** wrapper that refuses hand-off unless commands exit 0 |

Harness is 0.x, so pin its version; FileSystem and Shell run under Temporal. Sources: [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/), [FileSystem](https://pydantic.dev/docs/ai/harness/filesystem/).

All agents are `pydantic-ai` `Agent`s built by one factory: `make_agent(role_spec, output_type, tools, validators)`. That factory is also where tracing (tool calls, retries, tokens per role) is attached, which the evaluation work in Phase 3 depends on.

## Pipeline and per-role design

Five stages, each ending in a code-computed check and, where it exists today, a human gate. The per-task loop is where most quality is won or lost.

&#91;embedded content: Kroker target pipeline · 5 stages, fix loop in the per-task stage\]

Every dashed box is code, so no stage can pass on a model's say-so alone; the only loop is the bounded per-task fix loop.

| Role | Pattern | Inputs | Output (model) | Decided by code |
| --- | --- | --- | --- | --- |
| clarify router + probes C3–C6 | fan-out; probes are ReAct with repo tools | request, code map, repo | questions with `evidence` path | dedup by embedding, rank by `materiality`, evidence paths exist |
| architect | ReAct (repo + research) + validator | requirements, code map, memory | `ArchitectureSpec` + `requirement_coverage` | delta valid vs git tree, every requirement covered, each decision has alternatives |
| architect critic | single call, other family | requirements + spec only | `list[ArchCritique]` | blocking critique → one revision round |
| planner: decompose | ReAct (repo) | **requirements** + architecture + repo | task skeletons with `covers`, `files_hint`, `depends_on` | DAG acyclic, ids unique, coverage, size thresholds |
| planner: compile contract | fan-out, one call per task | one task, stack, repo test conventions | `ValidationContract` | commands exist; dry-run on empty worktree (exit 127 / not found = error) |
| test-harness | ReAct coding agent | contract | tests (frozen by C2) | tests exist and fail before implementation |
| dev-harness | ReAct coding agent | task, `test_commands`, `lint_commands`, `files_hint`, repo AGENTS.md, relevant ADRs | patch | wrapper refuses hand-off unless commands exit 0 |
| QA | ReAct (repo + `run_single_test`) | assertions, diff, test output | `list[AssertionEvidence]` | `tests_passed`, `stack_mismatch`; test names and impl locations exist |
| reviewer lenses ×4 | parallel ReAct, other family | assertions, diff, QA evidence, repo | `Finding`s per lens (correctness, test integrity, integration, security) | quote in file; `approve` = no critical/high and no `unmet` |
| regression check | deterministic activity | key assertion + its test | — | reverting the impl makes the test fail |
| deep\_review | single call, triggered | session transcript | `integrity_flags` | runs only on test edits, many reverts, drift |
| analyst | aggregation + LLM for gaps | all QA evidence, integration branch | cross-task issues, verdicts for `unverifiable` | trace matrix built in code |
| research | plan → fetch → cite → synthesize | question | claims citing `fragment_id` | cited fragment was fetched |
| release summary (was merge\_verdict) | single call | gate results, waivers, unverifiable items | summary for the human | gate stays deterministic |

**Removed or merged:** devops\_planner folds into planner decompose (`role="devops"` tasks). adversary is replaced by self-consistency on the correctness lens (two samples; disagreement goes to a human). merge\_verdict stops voting and becomes the release summary. handoff, discover and risk keep their design; handoff moves to a cheap model and discover gets repo tools.

**Fix loop:** dev receives the full FAILURES section (6–8k characters instead of 1.5k), each unmet `AssertionEvidence`, and reviewer findings as `path:line` + quote. Budget stays at 2 attempts until Phase 4 shows the loop converges.

## Tools and hooks per agent

Each agent gets the smallest toolset that lets it check its own claims; hooks enforce budgets and boundaries in code, so prompts never carry rules the runtime can enforce. Names below are pydantic-ai / Harness APIs; anything else is Kroker code.

**Baseline for every agent** (attached by `make_agent`):

- Capabilities: Instrumentation, Thinking (effort from `RoleSpec`), Tool Output Limits, Spend Limits.
- `before_run`: assert the ADR-6 family rule for this role; tag the run with role, task id and model for tracing.
- `prepare_tools`: once the role's step budget is used, remove all function tools so the model must return its structured output instead of looping.
- `tool_execute_error`: turn missing-file or timeout errors into `ToolFailed` (model adapts) and transient errors into `ModelRetry`; anything else aborts.
- `after_run`: record tokens, tool calls, retries and outcome per role for the Phase 0 metrics.

| Agent | Tools / capabilities | Hooks and validators (beyond baseline) |
| --- | --- | --- |
| clarify probes C3–C6 | FileSystem `read_only=True` + `grep`, `list_files` | output validator: every `evidence` path exists |
| architect | FileSystem read-only, `git_show`, `research` tool | output validator: delta vs git tree, `requirement_coverage` complete, each decision has alternatives |
| architect / plan critic | none (thinking only) | `before_run` rejects same family as architect / planner |
| planner decompose | FileSystem read-only, `find_tests` | output validator: DAG acyclic, ids unique, every requirement in some `covers`, size thresholds |
| contract compile | FileSystem read-only with `allowed_patterns` on manifests (`package.json`, `pyproject.toml`, `Makefile`, CI files by explicit path) | output validator: each command references an existing script or matches `stack`; dry-run stays an orchestrator activity, not a tool |
| test-harness | Coder (FileSystem + Shell) in Bubblewrap or Modal; Repo Context | `on_event(FileChangeRequestEvent)`: cancel writes outside test paths; Shell denylist (network, `git push`); after run, orchestrator checks the new tests fail before implementation |
| dev-harness | Coder in sandbox; Repo Context; prompt carries `test_commands`, `lint_commands` | `read_only_patterns` include the frozen tests and CI config; `on_event(FileChangeRequestEvent)` cancels edits to them with a reason; Shell denylist; hand-off wrapper runs the commands and refuses on non-zero exit |
| QA | FileSystem read-only, `run_single_test` (Shell with an allowlist of the stack's test runner) | `before_tool_execute(tools=['run_single_test'])`: cap calls and reject names not in the test output or diff; output validator: test names and `impl_locations` exist |
| reviewer lenses ×4 | FileSystem read-only, `git_show`; no shell | output validator: each `Finding.quote` occurs at `path:line`, else retry; findings without evidence dropped |
| deep\_review | none; input is the transcript | triggered by orchestrator signals only |
| analyst | FileSystem read-only on the integration branch | output validator: every criterion is in the trace matrix or flagged `unverifiable` |
| research | Web Search + a fetch tool returning numbered fragments (wraps Web Fetch); Prompt Injection Defender | `after_tool_execute(tools=['fetch'])` records fetched fragment ids in deps; output validator: every cited `fragment_id` was fetched |
| handoff, release summary | none | none beyond baseline |

Read-only roles never get Shell. FileSystem `root_dir` limits only file tools, not Shell, so anything that runs commands sits in a sandbox workspace. Sources: [Hooks](https://pydantic.dev/docs/ai/core-concepts/hooks/), [FileSystem](https://pydantic.dev/docs/ai/harness/filesystem/).

## Memory

Kroker has one long-term memory (episodic, `src/sdlc/memory/`) and no real short-term memory: within a run, stages pass outputs through Temporal workflow state and each agent call starts fresh.

| Type | Today | Gap |
| --- | --- | --- |
| Long-term episodic | Hindsight (or in-process fake) via `recall` / `retain` / `reflect`; kinds `stage_summary`, `gotcha`, `gate_feedback`, `research_finding`, `run_summary`; watermark freezes each run's view; recall saved as a hashed `RecallSnapshot`; nightly `ReflectWorkflow` consolidates | off by default (`SDLC_MEMORY_ENABLED=false`); only clarify, architecture and plan recall; `org_bank` unused; lessons retained without checking they were right |
| Cross-run cache | content-addressed memoization of activity results, per checkout | none for quality; it is a cache, not memory |
| Within-run (short-term) | stage outputs in workflow state; fix loop gets 1.5k chars of test output; harness transcripts kept for observability only | inputs get lost between stages (planner never saw requirements); fix attempts don't know what was already tried |

### Improvements: short-term

1. **Typed run context.** One `RunContext` record (requirements, clarify answers, decisions, stack, repo conventions) that every stage receives; a stage's input contract is checked in code, so a missing field fails the run instead of silently dropping.
2. **Task ledger for the fix loop.** Per task, keep attempts, commands run, failing tests, unmet assertions and reviewer findings as structured data. Each fix attempt gets the ledger, so dev does not repeat a failed approach.
3. **Context hygiene inside long ReAct runs.** Harness Compaction (clear old tool results) and Tool Output Limits for dev, QA and reviewers; Planning capability for the dev harness on multi-step tasks.
4. **Keep judges' context clean.** Reviewer and critics get evidence and the ledger, never the developer's transcript (ADR-12 stays).

### Improvements: long-term

1. **Measure before relying on it.** Run the Phase 0 benchmark with memory off and on; the July–August numbers were likely produced without it. In benchmark runs, a `degraded` recall fails loudly.
2. **Recall where errors happen.** Give dev, QA and reviewer a small recall of `gotcha` and `gate_feedback` filtered by tags for the modules in `files_hint` and the stack. For ReAct roles expose it as a `recall` tool, still logged as a snapshot under the run's watermark so replays stay deterministic.
3. **Retain only verified lessons.** Tag each memory with its outcome (oracle pass, QA evidence met, human-approved) and a source run; recall prefers verified items, and `reflect` drops lessons from tasks that later failed. This stops wrong lessons reinforcing themselves.
4. **Use `org_bank` for stack knowledge.** During `reflect`, promote a gotcha to the org bank when it recurs in 2+ projects (for example how tests run in a `uv` project); project-specific facts stay in the project bank.
5. **Turn repeated feedback into checks.** Gate feedback that recurs becomes a prompt-gate veto or a validator, so the fix moves from prompt text into code.
6. **Prune by use.** Record which recalled items an agent cited in its evidence; items never cited after N recalls are expired at `reflect`.

**Where it lands in the plan:** enable and measure in Phase 0; typed run context in Phase 1; task ledger and recall for dev/QA/reviewer in Phase 3; verified-only retention, org bank and pruning in Phase 5.

## Scaling and runtime topology

Scale Kroker by routing each role's activities to its own Temporal task queue, not by starting a worker per agent per session. Today every workflow and activity runs on one `TASK_QUEUE` (`worker.py`), so one slow sandbox task competes with every LLM call.

| Worker pool (task queue) | Runs | Scales by |
| --- | --- | --- |
| `kroker-orchestrator` | workflows only (`FeatureWorkflow`, `GraphWorkflow`); no LLM, no I/O | small, 1–2 replicas |
| `kroker-llm` | tool-less role calls: critics, release summary, handoff | horizontally; bound by provider rate limits |
| `kroker-repo-read` | ReAct roles with read-only tools: architect, planner, QA, reviewer lenses, clarify probes | horizontally; needs a repo clone or the task sandbox |
| `kroker-sandbox` | dev-harness, test-harness, contract dry-run, `run_single_test` | heavy hosts or Modal/E2B; strict `max_concurrent_activities` |
| `kroker-memory` | recall, retain, reflect | small, next to Hindsight |

- **Routing is per role**, set in `RoleSpec` and passed as the `task_queue` of each role's activities (`TemporalAgent` activity config). Workflow code barely changes.
- **Task affinity for worktrees.** A task's git worktree lives on one host, so its dev, QA and reviewer activities must run there. Use Temporal's worker-specific task queue pattern: the first activity creates the worktree and returns its host queue (`kroker-sandbox@host-7`); later activities of that task go there; on worker loss the workflow times out and recreates the worktree elsewhere. With a remote sandbox (Modal, E2B) addressed by id, no affinity is needed.
- **Parallel DAG tasks.** Plan tasks with no dependency between them run as parallel child workflows; the pool sizes above become the real concurrency limits. This is the main scaling lever.
- **Shared storage is a prerequisite.** Once pools sit on different hosts, local disk no longer works. Add an `S3ArtifactStore` beside `LocalFileStore` in `artifacts/store.py` (the Protocol already allows it) for diffs, transcripts and test output, and register Temporal's `ExternalStorage` on the `DataConverter` of the client and every worker, same backend everywhere, so payloads over \~2 MB are offloaded as claim checks. Set a bucket TTL; offloaded objects are content-addressed and never deleted by the driver.

### What to take from Temporal Agent Harness

The [Temporal Agent Harness](https://github.com/temporal-community/temporal-agent-harness) (0.6, experimental) models each agent as a long-lived chat-session workflow. That fits interactive agents, not Kroker's batch pipeline, and Kroker already gets durability from `pydantic_ai.durable_exec.temporal`. Borrow designs, not the package:

| Harness piece | Decision for Kroker |
| --- | --- |
| `s3` extra (large-payload offload) | Take the idea via `temporalio` `ExternalStorage` directly (above) |
| Auto mode + `jev` extra | Copy the design for dev/test-harness tool gates: named criteria sets per tool (read-only, irreversible), a minimum confidence, any failure or doubt goes to a human. Evaluator is a different-family critic or plain code, not the external TypeSafe service |
| Standard lifecycle event stream | Extend Kroker's `RunEvent` trace with per-role `model_interaction`, `tool_start` / `tool_end`, approval and usage events in one schema; feeds Phase 0 tracing |
| Typed, self-describing agent operations | Publish an input schema per role; makes the typed run context enforceable at each boundary |
| `ui` extra (session UI, approval panels) | Later, optional: interactive gates (clarify Q&A, architecture review) beside the pipeline |
| `code-mode`, `pydantic-ai`, `genai`, `openai-agents` extras | Skip: research already uses Code Mode; Kroker already uses the upstream Pydantic AI Temporal plugin; Code Mode for other roles and the Agent DAG example are the Coordinator pattern Kroker avoids |

## SDK portability

Kroker owns each role's contract; an AI SDK is a swappable adapter behind a `RoleRunner` port. Today roles call `pydantic_ai.durable_exec.temporal` directly (16 agents built in `agents/roles.py`), while coding harnesses already follow this pattern (`CodingHarness` adapters for Claude Code, opencode and Cursor, normalized to `HarnessRunResult`). Extend the same pattern to roles.

| Kroker owns (SDK-neutral) | Each SDK adapter does |
| --- | --- |
| Role input and output schemas (pydantic) | Calls the model or agent in its SDK |
| Tool definitions: one typed signature and body | Translates tools into the SDK's format |
| Validators, verdict functions, retry loop | Returns raw output and events |
| Event schema (`RunEvent`: model, tool start/end, usage) | Maps SDK events onto that schema |
| Tool policy: allow-lists, approval, step budget | Enforces it through SDK hooks or a tool wrapper |
| `model_id` and family for ADR-6, cost accounting | Reports which model ran and its tokens |
| Durability: every model and tool call is a Temporal activity | Uses the SDK's Temporal plugin where one exists; otherwise Kroker wraps the call in an activity |

- **Quality logic leaves SDK hooks.** Validators and verdicts run in Kroker code after the SDK returns; a failed check resumes the same session with the error, Kroker's own equivalent of `ModelRetry`. Pydantic AI hooks stay an implementation detail of its adapter.
- **Tools are written once.** `read_file`, `grep`, `git_show`, `run_single_test` are Kroker functions; Harness FileSystem and Shell become the pydantic-ai adapter's implementation, not the contract.
- **Config.** `RoleSpec` gains `sdk: pydantic-ai | openai-agents | adk | …` beside the model.
- **Reference implementation.** Temporal Agent Harness's "Bring your own AI SDK" integrations (Gemini, OpenAI Agents, Pydantic AI; ADK, Strands, LangGraph planned) do exactly this translation of tools and events into one vocabulary. Use them as a reference now; reassess using that layer as Kroker's adapters after their 1.0.
- **Add an SDK only for a reason** (a model only reachable through it, a customer requirement). Each one adds maintenance, replay tests and its own durability bugs.

## Run UI

The dashboard's main screen should show evidence, not just progress: why each task was accepted or rejected. That is what tools like Orca or herdr cannot show, since they leave verification to a person reading the diff.

Today `dashboard/` shows the fleet, the run graph (`graph_view` query) and pending gates, refreshed by polling queries (`fleet.py`). Anything between two polls is lost, such as fix-loop attempts or tool calls inside a role.

**Evidence view (new, the main screen per task)**

- Contract assertions with status met / unmet / unverifiable, each linked to its test and implementation location.
- Reviewer findings by lens, with the `path:line` quote.
- The verdict and its reason, step by step through the verdict function (which rule failed).
- Gate decisions and waivers: who, when, why.
- Fix-loop history from the task ledger: what each attempt changed and what still failed.

**Borrowed from the Temporal Agent Harness UI** (its State Flow pane; observable state is on an exploration branch there, so copy the mechanism, not the code):

| Mechanism | For Kroker |
| --- | --- |
| Snapshot + JSON Patch on a workflow stream | Publish `RunState` as one snapshot, then RFC 6902 patches on each change (`temporalio.contrib.workflow_streams`). The dashboard sees every change in order; a late client replays the stream. Replaces polling |
| Replay scrubber over the event log | Scrub through a run's `RunEvent` log with markers for gates, validator retries and exhausted fix budgets. The main tool for "why did the reviewer approve this?" |
| Latency waterfall, usage by model | Time and cost per role and model per run; tracks the cost and latency risk |

Not borrowed: their agent/subagent graph (Kroker's graph is the stage and task DAG it already draws) and display hints (role schemas are fixed, so views are written explicitly).

## Model allocation

Spend the strong model where an error multiplies downstream, and keep judges off dev's weights family.

| Tier | Roles | Family rule | Thinking |
| --- | --- | --- | --- |
| Strong judge | reviewer lenses, architect critic, plan critic | must differ from dev (e.g. Claude or GPT if dev is glm-5.2) | on |
| Strong planner | architect, planner decompose | any; prefer strong | on |
| Worker | dev-harness, test-harness, QA, contract compile, clarify probes | any (glm-5.2 is fine) | off or low |
| Cheap | handoff, release summary, analyst gap-filling, research fetch/cite | any | off |

If budget allows only one upgrade, put the reviewer on a different strong family first, then the planner. Model swaps are measured separately from prompt changes.

## Implementation plan by phase

Six quality phases over roughly 7–9 weeks, plus an SDK phase when needed, for one or two engineers. Each phase ends with a gate: a benchmark or prompt-gate result that must hold before the next starts. Estimates are rough and assume the code matches the September analysis.

### Phase 0: Baseline and harness (2–3 days)

- [ ] Re-run the benchmark (todo-api-greenfield, cat-cafe, 2–3 deveval cases) on current `main`; record task pass, oracle pass, reviewer–oracle agreement, attempts per task
- [ ] Add per-role tracing in one place (tool calls, retries, tokens, latency)
- [ ] Confirm file paths cited in the analyses (`plan/step.py`, `code/step.py:514`, `review/prompts.py`, `_TEST_OUTPUT_MAX`)

**Gate:** baseline numbers stored and reproducible within noise across two runs.

### Phase 1: Quick wins on lost inputs (3–5 days)

- [ ] Pass `requirements` (incl. clarify answers) into the planner prompt
- [ ] Put `test_commands` / `lint_commands` into the dev prompt as the definition of done
- [ ] Raise `_TEST_OUTPUT_MAX` to 6–8k, send the full FAILURES section in the fix loop
- [ ] Add `Field(description=...)` to all output models; reorder fields evidence-first
- [ ] Turn on thinking for reviewer, architect, planner via `RoleSpec`

**Gate:** task pass rate up vs baseline; attempts-exhausted share down from 58/73.

### Phase 2: Runtime foundation and topology (about 1.5 weeks, reusing Harness)

- [ ] `make_agent` factory, `RoleSpec` in `agent.yaml`, `ModelRouter`
- [ ] ADR-6 check by `model_id` family; start-up fails on violation
- [ ] `RepoReadTools` with commit pinning, truncation and paging; unit tests
- [ ] Validators library and evidence schemas
- [ ] Dev-harness wrapper: refuse hand-off unless commands exit 0
- [ ] Per-role task queues and worker pools (orchestrator, llm, repo-read, sandbox, memory), routed from `RoleSpec`
- [ ] Worker-specific task queue for task worktree affinity, with recreate-on-loss
- [ ] `S3ArtifactStore` + Temporal `ExternalStorage` on all clients and workers
- [ ] Per-role lifecycle events added to `RunEvent` (model, tool start/end, approval, usage)
- [ ] `RoleRunner` port, SDK-neutral tool definitions and event schema; pydantic-ai as the only adapter, behaviour unchanged

**Gate:** no metric regression; all existing roles run through the factory.

### Phase 3: Evidence-based QA and reviewer (1.5–2 weeks)

- [ ] Reviewer eval set: (diff, oracle=fail, review=approve) pairs from history + seeded mutations (off-by-one, removed check, weakened test); wire into prompt-gate
- [ ] QA as evidence tracer: `AssertionEvidence`, repo tools, `run_single_test`; `tests_passed` computed
- [ ] Reviewer split into 4 lenses on another family, quote-in-file validator, `approve` computed
- [ ] Regression check activity for key assertions
- [ ] Replace adversary with self-consistency; trigger deep\_review on signals only

* [ ] Validators and verdict functions run as Kroker code after the SDK returns, with Kroker's own retry-with-error loop, not as pydantic-ai hooks

- [ ] Run UI: evidence view per task (assertions, findings, verdict reasons, gates, fix-loop history)
- [ ] Run UI: `RunState` snapshot + JSON Patch stream replacing dashboard polling; replay scrubber over `RunEvent`; latency and cost per role

**Gate:** reviewer recall on mutations ≥ agreed target with false-block rate below threshold; reviewer–oracle agreement clearly above today's.

### Phase 4: Planner and architect (1.5–2 weeks)

- [ ] Planner split: decompose (with repo tools) → compile contract per task
- [ ] Plan validators (DAG, coverage, size) and contract dry-run activity
- [ ] Fold devops\_planner into decompose
- [ ] Architect: repo tools, delta check moved into a validator, `requirement_coverage`
- [ ] Architect and plan critics on another family; one revision round
- [ ] Vetoes for planner and architect in prompt-gate

**Gate:** attempts-exhausted share and contract errors (exit 127, unverifiable assertions) down vs Phase 3.

### Phase 5: Test-first, research, cleanup (1–1.5 weeks)

- [ ] Test-harness writes tests from contract before dev; C2 freezes them
- [ ] Research: fragment-numbered fetch, citations by `fragment_id`, validator
- [ ] Analyst becomes aggregator; merge\_verdict becomes release summary
- [ ] Clarify probes get repo tools + dedup/rank; rewrite thin prompts (clarify, release summary)

**Gate:** research grounding rejections near zero; end-to-end pass above the 2/20 baseline by a margin agreed in Phase 0.

### Phase 6: Second SDK adapter (1–1.5 weeks, when a reason appears)

- [ ] Pick the SDK by need (OpenAI Agents SDK or Google ADK are the likeliest)
- [ ] Adapter: tool translation, event mapping, model and usage reporting, durability via its Temporal plugin or a Kroker activity wrapper
- [ ] Run one role on it first, e.g. one reviewer lens
- [ ] Replay tests for the new adapter

**Gate:** the same role on both SDKs gives comparable prompt-gate and benchmark results; no change to workflow code was needed.

## Measurement and rollout rules

The north-star metric is **reviewer–oracle agreement** alongside task pass rate: a pipeline that passes more tasks but still approves what the oracle rejects has not improved.

| Metric | Baseline (Jul–Aug) | Tracked from |
| --- | --- | --- |
| End-to-end pass | 2 / 20 runs | Phase 0 |
| Code tasks passed | 18 / 75 (24%) | Phase 0 |
| Tasks exhausting fix budget | 58 / 73 | Phase 1 |
| Reviewer approve rate vs oracle pass | 21/21 vs 4/60 | Phase 3 |
| Reviewer recall on seeded mutations | none yet | Phase 3 |
| Contract dry-run failures | not measured | Phase 4 |
| Research grounding rejections | 16 / 17 | Phase 5 |
| Tokens and wall-clock per task | not measured | Phase 0 |

Rules: one variable per PR (never a model swap with a prompt change); every role change runs prompt-gate if the role has an eval set, the benchmark otherwise; new behaviour ships behind a per-role flag in `agent.yaml` so a regression rolls back by config.

## Risks and open questions

- **Cost and latency rise** with tools, thinking and four lenses. Mitigation: tool-step budgets per role, cheap tier for extraction, lenses run in parallel, deep\_review only on signals.
- **Benchmark is small** (about 20 runs), so noise can hide or fake a gain. Run each comparison at least twice and add deveval cases in Phase 0.
- **Stricter reviewer may block too much**, stalling the fix loop. Track false-block rate on the mutation set and keep a human waiver path.
- **Tool output bloat** in agent context. `RepoReadTools` truncates and pages by default.
- **Test-first can freeze bad tests.** Contract dry-run and the test-integrity lens must land before Phase 5.
- **SDK lock-in.** Hooks, `output_validator` and Harness capabilities are pydantic-ai only. Keeping quality logic, tools and events in Kroker-owned code (Phases 2–3) keeps a second SDK a bounded adapter job.
- Open: which second model family is affordable for reviewer and critics?
- Open: what reviewer recall and false-block thresholds count as passing the Phase 3 gate?
- Open: worktrees on host-affine workers or in a remote sandbox (Modal/E2B)? The second removes affinity but adds cost and latency.
- Open: is an interactive gate UI worth building on the Temporal Agent Harness once the pipeline is stable?
- **Multi-host deploys break local storage.** Splitting pools across hosts needs S3-backed artifacts and payload offload first; otherwise activities on another host cannot read what a previous one wrote.
