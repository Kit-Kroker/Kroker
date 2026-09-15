# E-74 — `GraphWorkflow` replaces `_pipeline` (FR-1203) — design

| | |
|---|---|
| Epic | E-74 (pipeline-as-data, Phase 2) → FR-1203 |
| Date | 2026-09-15 |
| Status | reviewer-approved (2026-09-15, round 2); skeptic round dispositioned and advisor-checked (§13); user rulings U1–U10; pending user gate on E74-OQ-1…E74-OQ-5 |
| Normative text | `PRD.md` §6 FR-1203, §11 OQ-10 (grace-retention, user ruling) |
| Frozen contracts | E-72 spec `2026-09-13-graph-model-node-registry-design.md`; E-73 spec `2026-09-14-graph-router-and-validator-design.md` (+ §6.7 erratum) |
| Consultation log | All under `.workspace/tmp/` (uncommitted scratch). **Advisor:** `e74-consult-q1.md` → `advisor-e74-q1.md` (runtime core); `e74-consult-q2.md` → `advisor-e74-q2.md` (dispositions check, command-projection walk, wiring walk, gaps G1–G9). **Skeptic:** brief `e74-skeptic-brief.md`, critique `e74-skeptic-full.md` (F1–F12), dispositioned in §13. **Reviewer:** brief `e74-reviewer-brief.md`; round 1 `e74-reviewer-r1.md` (CHANGES REQUESTED: R1–R2 Important, R3–R7 Minor; all applied, R2 escalated → U10); round 2 `e74-reviewer-r2.md` (**APPROVED**, riding Minors R8–R9 applied in this copy). |

## 1. Purpose and deliverable

E-74 makes the pipeline graph the execution path. A thin Temporal
`GraphWorkflow` drives E-73's `GraphRouter` over a validated `PipelineGraph`
pinned as workflow input, dispatching each `Activation` to a node handler.
Every **new** run — `sdlc start`, dashboard/operator start, benchmark cells,
tidy-up fix runs — starts `GraphWorkflow`. `FeatureWorkflow` stays registered,
behaviourally unchanged and replay-proven, only to carry in-flight executions
to their terminal states; it and `_pipeline` are deleted by a gated follow-up
(§8.5).

It lands as **two fast-forward merges** from one plan (user ruling U3):

- **M1 — behaviour-neutral foundation.** (a) Record FeatureWorkflow histories
  and golden traces from unchanged `main`; verbatim extractions of what both
  workflows share, proven by a `Replayer` test. (b) Pure graph-layer additions:
  terminal ports and the `failed` outcome in the router, `Halt` event,
  `NodeFailure` payload, the post-plan catalog, errata to E-72/E-73.
- **M2 — interpreter and cutover in one change.** `GraphWorkflow`, handlers,
  shipped graphs, golden-trace assertions, all start sites, per-child patches,
  inbox/fleet queries.

## 2. Decisions

### 2.1 User rulings (this brainstorm)

| # | Ruling |
|---|---|
| U1 | **Coarse post-plan.** Pre-code half is real topology (gate nodes; `_revisable_stage` gone from the graph path). `code` is ONE node wrapping today's task scheduler and per-task fix loop. `max_fix_attempts → GraphEdge.max_traversals` is **carved out** to a named follow-up epic that needs dynamic fan-out and per-instance counters (E73-OQ-7, OQ-14). Brief constraint 4 is amended accordingly. |
| U2 | **"Unchanged" = behaviourally unchanged.** `feature.py` may shed code into shared modules it imports or inherits, and shared stage code may be refactored, provided FeatureWorkflow's command sequence is identical — proven by a Temporal `Replayer` test over histories recorded from pre-change code. |
| U3 | **Two merges:** M1 (capture + extraction + pure graph layer), then M2 (GraphWorkflow + cutover together, so brief constraint 1's "same change" holds — nothing ever sits registered-but-unstarted on `main`). |
| U4 | **Revise bound templated from cfg.** Start sites stamp `cfg.max_gate_rounds` onto the shipped graphs' pre-code revise edges and reject `max_gate_rounds < 1` (§7.1). |
| U5 | **Role precedence (E72-OQ-6): run-level override wins** over `node.role` (§5.2). |
| U6 | **Grace edits:** a command-changing edit to code FeatureWorkflow executes is wrapped in `workflow.patched` while grace lasts, enforced by the Replayer test; golden traces re-baseline from GraphWorkflow (with diff) only after deletion (§8.3). |
| U7 | **Deletion is a separate follow-up** even when both Running queries are empty at M2 landing; PRD OQ-10's "collapse" wording is amended at M2 (§8.5, §10.6). |
| U8 | **Rollback = roll forward.** No start-site switch back to FeatureWorkflow (§8.4). |
| U9 | **No retro on a FAILED execution**, as today (D8); retro-on-failure is a follow-up improvement. |
| U10 | **Handler signature (brief constraint 3 refined):** `(NodeContext, Activation, PipelineConfig) -> NodeResult` (D2). Constraint 3's substance holds: inputs arrive only through `Activation`, a handler emits exactly one port, exceptions become routable `fail` emissions. |

Standing (brief): big-bang, no dual-running gate (constraint 1); grace-retention
(constraint 2); determinism lint (6); `default.graph.yaml` asserted to reproduce
today's sequence (7).

### 2.2 Design decisions

| # | Decision |
|---|---|
| D1 | **Placement.** Temporal-aware code never enters `sdlc/graph/` (purity pins). `workflows/graph.py` = `GraphWorkflow` + dispatcher; `workflows/graph_nodes/` = handlers (one module per node group); `workflows/graph_catalog.py` = shipped graphs, `executable()`, handler table; `workflows/graphs/*.graph.yaml` = shipped graphs. All sandbox-executed modules import models under `workflow.unsafe.imports_passed_through()`. |
| D2 | **Handler signature** `async (nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult` (user ruling U10): run facts are neither config nor router output, so they ride a third parameter (the StageContext precedent). |
| D3 | **Payload store.** Handlers never mint refs. The dispatcher mints `f"{activation_id}.{port}"`, stores `StoredPayload{model: BaseModel \| None, producer: activation_id, author_model: str \| None, meta: dict[str,str]}` in workflow memory, and builds `Emitted`. Never exposed by a query. |
| D4 | **Carry** (answers E73-OQ-4 for E-74). `nc.carry(node_id) -> dict[str, Any]`: host-owned, keyed by node id, never reset by region invalidation (E-73 U5 philosophy), dies with the run. Used for cross-round spend/start time and first-activation stage events. |
| D5 | **Side-channel rule.** A handler may write host *observability* state (trace, usage, board version, session refs, pending registry). Anything that decides control flow travels through a port — except write-once run facts produced by the entry node (§5.3). |
| D6 | **Terminal ports** (router, M1). `NodePort.terminal: Literal["rejected","failed"] \| None`; router step 4 generalises "gate `reject` with no edges" to "terminal port with no edges"; `Outcome` gains `failed`. A terminal port *with* edges routes normally (error routing is topology). |
| D7 | **`Halt` event** (router, M1). `Halt{kind:"halt", outcome: "rejected"\|"failed", reason}` in the event union: terminates like step 2/4, retires every live activation. Used for budget rejection and any dispatcher-level stop, so router state stays the post-mortem truth. |
| D8 | **Failure semantics.** Only a non-cancellation instance of `FAILURE_TYPES = (FailureError, UserError, PydanticUserError, AgentRunError)` becomes a `fail` emission (payload `NodeFailure`). `FailureError` fails an execution unconditionally in temporalio (`workflow_is_failure_exception`, `_workflow_instance.py:1824-1839`); the other three are what `PydanticAIPlugin` registers as `workflow_failure_exception_types` (`pydantic_ai/durable_exec/temporal/__init__.py:147`). Cancellations propagate (with the §5.4 fan-out). `asyncio.TimeoutError` also fails an execution in temporalio; it is not converted — today's gate-wait timeouts are caught inside `gates.py:173-177`, so no dispatcher rule is needed, and an escaping one fails the execution exactly as under FeatureWorkflow. Every other exception propagates as a workflow-task failure (retry — today's hotfix-recovery path). An **unrouted** `fail` re-raises the stored original exception object after the router records `failed`, so close status, failure type and message, parents' `ChildWorkflowError` branches and retro-not-run match today exactly. |
| D9 | **Outcome string** is a wire contract, reproduced exactly (§5.6). |
| D10 | **Research stays composite.** The `research` handler keeps today's internal refine loop and `research` gate. `gate.research` stays in the catalog (E-76 fixtures use it) but is **not executable** in E-74 (§5.8). |
| D11 | **One default graph per research setting**, branching greenfield/brownfield at intake: `default.graph.yaml`, `default-research.graph.yaml`, plus `seeded.graph.yaml`. |
| D12 | **Budget boundaries are type data.** `NodeTypeSpec.budget_after: Literal["none","continuing","exiting"]`, judged from topology (never port names), checked by the dispatcher at quiescence (§5.5). |
| D13 | **Per-child patch ids** in `TidyUpWorkflow` / `BenchmarkWorkflow`: `workflow.patched(f"e74-graph-child:{child_id}")` (§8.2). |
| D14 | **Validation at both ends.** Start sites resolve roles, `from_graph` + `executable` (fail fast); `GraphWorkflow.run` re-runs both (pure) on its pinned input. `check_node_types()` + handler coverage run at **worker boot**, never in the sandbox. |

## 3. Verified anchors and corrected hypotheses

- `_pipeline` = `workflows/feature.py:470` (brief anchor correct); file is 775 lines.
- **Hypothesis 8a partly disproven.** Handlers are module-level `step(ctx, *, cfg, …)` (B0 moved them) but are not near `(Activation, PipelineConfig) -> Emission`: parameters mix run context (idea, repo_path, integration worktree, base SHA, memory watermark, agent objects, resolved models) with artifacts; return shapes are `str|None` (intake), `CodebaseMap|str|None` (context), `ResearchOutcome` with an internal gate loop (research), `tuple[artifact, GateDecision]` with the gate inside via `ctx.revisable_stage` and judge/record/retain *after* the gate (architecture, plan), `str` with internal gates (merge, deploy). An adapter layer is required; stage bodies are reused.
- **Hypothesis 8b partly disproven.** Only `research_enabled` collapses into "is there a node" (`feature.py:535`, also read at `architecture/step.py:117`). `deep_review_enabled` / `adversarial_review_enabled` / the `t_handoff` guard are read inside the per-task loop (`code/step.py:367,826,844`; `review/step.py:191,270`) and stay run-scoped settings under U1.
- **Constraint 4 infeasible on E-73 as landed** (→ U1): `max_traversals` is one counter per edge for the whole run and fan-out is static (E-73 U1), so a topological fix loop would share one budget across all tasks.
- **FR-1203 "`_pipeline` SHALL be removed" and grace-retention's "FeatureWorkflow unchanged" cannot both hold on landing day.** `_pipeline` is removed with FeatureWorkflow in the follow-up (§8.5); on landing, no new run executes it.
- **Constraint 5 scoped.** `_revisable_stage` leaves the graph path in M2; its code is deleted with FeatureWorkflow.
- Research's loop differs from gate topology (`research/step.py:298-343`): refine accumulates findings, exhaustion proceeds, bound is `research.max_refine_rounds`.
- Budget checks today (`feature.py:550,574,588,605,716,746`): after research section (skipped when research rejects), clarify, architecture step *incl. gate* (before the reject return — budget wins), plan step *incl. gate* (same), each task wave (inside the scheduler), analyze. None after intake, context, merge, deploy, none pre-code on the seeded path.
- Intake runs **before** `setup_integration_branch` (`feature.py:490-510`); a rejected intake creates no branch.
- `FeatureWorkflow._run_handoff` (`feature.py:318`) has no caller (the code stage uses its own) — dead code, deleted with FeatureWorkflow, not extracted.
- Temporal 1.30.0: `workflow.patched` is memoised per id per execution (`worker/_workflow_instance.py:1362`); `exceptions.is_cancelled_exception` exists (`exceptions.py:459`); no `Replayer` usage exists in the repo today.
- Hard-coded type strings: `channels/inbox.py:91,110`, `dashboard/fleet.py:59,61`. Start sites: `cli.py:442`, `interfaces/dashboard/api/main.py:56` (dashboard POST `/runs` and operator `start_run` via the starter), `benchmarks/workflow.py:269` (child), `workflows/tidyup.py:228` (child, seeded). `cli.py:764,782` retype.

## 4. M1 — behaviour-neutral foundation

### 4.1 Capture from unchanged `main` (plan Task 1, before any refactor)

A capture harness (env-gated, `SDLC_CAPTURE_HISTORIES=1`) wraps the existing
time-skipping FeatureWorkflow tests and writes, per scenario:

- `tests/replay/histories/<scenario>.json` — `handle.fetch_history()` JSON;
- `tests/replay/golden/<scenario>.json` — the **golden trace**, four
  projections: (1) ordered `STAGE_STARTED` stage names from the run trace;
  (2) ordered gate decisions `(gate_key, outcome, decided_by)`; (3) the **ordered
  command projection** of the history — for each `ActivityTaskScheduled` its
  activity type, each `StartChildWorkflowExecutionInitiated` its workflow type,
  each `TimerStarted` the literal `timer` (ids, payloads and markers excluded);
  (4) the close: the return string, or `FAILED:<failure type>:<message>` for a
  failed execution. Projection (3) is what makes board publishes, benchmark
  records, memory recalls/retains, cache reads/writes and notifications part of
  the reproduction claim (skeptic F10), not just the stage names.

Scenario matrix (each from an existing test's script of fakes and signals):
greenfield happy path; brownfield; intake reject; context reject; architecture
revise ×2 → final gate approve; architecture reject by timeout; plan revise
then approve; wave mode; seeded (tidy-up child input); budget crossing at
clarify; budget crossing with architecture reject; research on (greenfield);
brownfield delta-grounding `ApplicationError` (FAILED close); workflow
cancellation while a long activity runs (projection (3) also lists
`ActivityTaskCancelRequested`); `max_gate_rounds=1`. Plus one mid-flight partial
history (awaiting the architecture gate). Captures run with memoization off.

**Capture-twice rule.** The harness runs each scenario twice and refuses to
write a golden file unless both projections are equal. An unstable scenario is
fixed in its fixture (e.g. unset gate `remind_after_hours`), never by normalising
the projection.

Provenance is recorded (commit SHA in each file). Fixtures are data, never a
live call to FeatureWorkflow, so they survive its deletion.

### 4.2 Replayer test (fast tier)

`tests/replay/test_feature_replay.py` replays every history with
`Replayer(workflows=[FeatureWorkflow, DeploymentWorkflow, CrewTaskWorkflow], data_converter=pydantic_data_converter, plugins=[PydanticAIPlugin()])`
and **no runner override**: the default `workflow_runner` is
`SandboxedWorkflowRunner()` (`temporalio/worker/_replayer.py:46`). In production
the plugin reaches the `Worker` through `Client.connect(plugins=[PydanticAIPlugin()])`
(`worker.py:219-223`); the Replayer has no client, so the fixture passes it
explicitly. A test pins the **effect** (skeptic F1 residue): the Replayer's active
config has a `SandboxedWorkflowRunner` whose restrictions pass `pydantic_ai`
through, and `workflow_failure_exception_types ⊇ {UserError, PydanticUserError,
AgentRunError}` (injected by the plugin; without them a history that failed on
`UsageLimitExceeded` would falsely report nondeterminism). No server. It runs on
every plan task from Task 2 onward and is the proof of U2.

Queries never appear in history, so replay does not exercise `run_state` /
`run_summary` (skeptic F2). The existing query unit tests
(`tests/test_run_state_query.py` and peers) are parametrised over both workflow
classes from the extraction task on, and one golden GraphWorkflow run queries
`run_state()` and `pending_decisions()` live while it waits on the architecture
gate (`current_stage == "architecture"`), exercising the real MRO in the sandbox.

### 4.3 Verbatim extractions (only what GraphWorkflow calls)

| From | To | Note |
|---|---|---|
| `_on_gate_awaited` / `_on_gate_decided` / `_on_notified` bodies, `run_state` body, `run_summary`, `_retro` | `workflows/run_host.py` `RunHost` mixin | Query decorators stay on each concrete class as one-line delegates (`workflows/AGENTS.md` rule 4; dashboard queries by name). Ownership table rows move. |
| scheduler loop `feature.py:635-716` | `workflows/build.py` `async run_tasks(host, *, cfg, plan, repo_path) -> tuple[dict[str, TaskResult], str \| None]` | Returns `(done, None)` when every task finished and merged (`done` in completion order), or `(done_so_far, failure)` where `failure` is exactly today's early-return string: `failed:dependency-cycle`, `failed:integration-conflict:<task>`, `failed:quarantined-tasks`. `_BudgetRejected` from the per-wave check propagates unchanged. FeatureWorkflow returns `failure` when set, else continues to analyze; the `code` handler maps `None` → `results: BuildResult`, a string → `halt` with that `result` (reviewer R5). |
| `architecture.step` / `plan.step` | split into `prepare(…)` (the once-per-stage prefix: `ctx.stage`, `_started`, `RoleUsage`, `recall` snapshot, map block/key, `prompt_digest` salt), `produce(prep, guidance)` (one round; re-initialises `delta_retries = cfg.max_delta_retries` per call as today, `architecture/step.py:131`; same `cached_stage` key) and `finish(prep, artifact, decision)` (`_ended` taken first, then judge/record PASS\|REVISED/retain); `step()` keeps composing them around `ctx.revisable_stage` | Command sequence identical. Per-type `finish` text differs (architecture retains `architect: {overview}`, plan its own). |
| `_validate_task_graph` | `stages/plan/validation.py` (pure) | Imported back by feature.py. |

`feature.py` shrinks. Every extraction task ends with the Replayer test green.

### 4.4 Pure graph-layer additions (`sdlc/graph/`, fast tier)

- **Router** (D6, D7): `Topology.terminal_ports` (sorted, from `validate`);
  step 4 generalised; `Outcome = running|completed|rejected|escalated|failed`;
  `_TERMINAL` includes `failed`; `Halt` joins `Emitted` in a discriminated union.
  Gate-kind `reject` ports are declared `terminal="rejected"` and
  `check_node_types` asserts it (today's special case becomes data). E-73
  theorems carry over: step 4 fires only on an applied emission on an edgeless
  port (the precondition of today's gate-reject branch); `Halt` is `_terminate`
  with `emitter=None` and is legal only on a RUNNING state — `Halt` after a
  terminal outcome raises `RouterError` (an interpreter bug; §5.4 orders budget
  before advance so it cannot arise).
- **Registry fields:** `NodePort.terminal` (out-ports only), `NodeTypeSpec.budget_after`.
- **Payloads** (`PAYLOAD_TYPES`, each in a `models` module): `NodeFailure{activation_id, error_type, message}` in `sdlc/core/models.py` (an envelope no stage produces); in `sdlc/workflows/models.py` (orchestrator envelopes): `BuildResult{task_results: list[TaskResult]}` (completion order), `AnalyzeResult{report: AnalysisReport, untraced: list[str], integration_diff: dict[str, Any]}` (`get_task_diff` returns `files: list[str]` and `renames: list[list[str]]`, `vcs/git.py:115`), `PullRequest{url: str}`. Payload models are validated inside the workflow, where a `ValidationError` is a non-Failure that retries the workflow task forever, so **every payload model is constructed from real activity output in at least one golden scenario before landing**.
- **Catalog** — §6 table. Additive only: no E-72 port renamed or removed, so
  `pre_code.graph.yaml`'s golden sha and E-76 object fixtures stay valid; the
  served `catalog.json` fixture is regenerated.
- **`check_node_types` hardening** (inbox minor 2): `_resolve_payload` catches
  `Exception`, since boot now runs it.
- **Errata** appended to E-72 §5 (role precedence: a run-level `cfg.roles`
  override wins over `node.role`, E72-OQ-6 resolved by U5 — amends "a non-None
  `node.role` *replaces* the entry"; reviewer R7), E-72 §6 (new
  `NodePort`/`NodeTypeSpec` fields, research port change) and E-73
  §6.2/§6.6/§8 (terminal ports, `failed`, `Halt`).

## 5. GraphWorkflow runtime (M2)

### 5.1 Input and start

```python
class GraphRunInput(BaseModel):
    idea: IdeaBrief
    cfg: PipelineConfig
    graph: PipelineGraph
    roles: dict[str, RoleConfig]   # registry roles overlaid with cfg.roles, resolved at start
    seeded: SeededWork | None = None
```

`GraphWorkflow.run(inp)`: re-validate (`from_graph(graph, roles=inp.roles)` +
`executable(graph)`; failure → `ApplicationError(non_retryable)`), stash
`_idea/_cfg/_started_at/_run_id`, capture the memory watermark (preamble — no
branch side effect), `router.start()`, dispatch loop, retro, return.

### 5.2 `NodeContext` and cfg projection

`NodeContext` = the StageContext services + `facts: RunFacts` + `payload(ref) ->
StoredPayload` + `carry(node_id)` + `connected(port) -> bool` (from Topology) +
`node: GraphNode`.

Per-activation cfg projection `project(cfg, node, spec, graph)`:

- **roles** (user ruling U5 — run-level override wins): `cfg.roles[spec.role] :=
  node.role` only when `node.role` is set **and** `spec.role` is not already a
  key of `cfg.roles`. A key present in `cfg.roles` is a run-level override (CLI
  `--role-model`, benchmark arm); the `default_factory` keys `dev`/`test`/`devops`
  are always present, but no E-74 node type carries those roles, so the rule is
  unambiguous for E-74. `resolve_role_model` keys by role name, so type `plan`
  projects through role `planner`.
- **gates**: `cfg.gates[node.id] := node.gate` when set.
- **research**: `research_enabled := graph has a research-type node`.

**Pinned:** projecting each shipped graph onto a default cfg (and a
benchmark-cell cfg) returns an equal cfg, so memo keys and `prompt_digest` salts
are byte-identical to FeatureWorkflow runs.

### 5.3 Run facts

`RunFacts` (frozen): `idea`, `repo_path`, `run_id`, `seeded`, `memory_watermark`,
and — written once by the intake handler after it verifies — `integration`
(`IntegrationHandle`) and `base_sha`. A second write raises. `_integration_head`
is a code-node-internal cursor; `_codebase_map` is a `context.map` payload;
`_plan_version` is board observability (D5).

**Host mirrors.** The mixins read several of these as `self.` attributes, so the
code that writes a RunFacts field also sets the host attribute: the preamble sets
`_memory_watermark` (read by `RoleHost._cached_stage` via `getattr`,
`role_host.py:109`, and `MemoryHost._recall`) and `_budget_threshold`; the intake
handler sets `_integration_head`, `_integration_wt`, `_base_sha` (read and
advanced by `TaskHost._merge_task`, `task_host.py:208`); the plan gate's
`finalize` sets `_plan_version` (`board_host.py:95,116`). Captures run with
memoization off, so a missed `_memory_watermark` mirror would be invisible to
the golden trace (the memo key silently becomes `"none"`): a unit test pins
every mirror after the preamble/intake, and one memo-ON parity test asserts the
`content_key` inputs of the architect's first round equal FeatureWorkflow's.

### 5.4 Dispatch loop

Router state is owned by the `run` coroutine alone; handler tasks never touch
it (skeptic F3).

`FAILURE_TYPES = (FailureError, UserError, PydanticUserError, AgentRunError)` is
one constant = `{FailureError}` ∪ the plugin's registered
`workflow_failure_exception_types` (D8). These fail the **execution** when they
escape `run`, as does `asyncio.TimeoutError` (not converted, D8); every other
exception fails the workflow **task** (retry).

1. `step = router.start()`; `held = list(step.activations)`.
2. Start every held activation (sorted by node id) as an `asyncio` task. The
   task wrapper is `try: r = await handler(...) except BaseException as e: r = e`,
   then appends `(activation_id, r)` to a FIFO list. The wrapper catches, never
   decides.
3. `await workflow.wait_condition(lambda: bool(results))` — **no timeout** (a
   timeout would add a `TimerStarted` to the command projection) — and pop FIFO.
   A result whose activation is no longer live (cancelled by an invalidation) is
   discarded without advancing.
4. **Classify** (outside any `except` block):
   - `is_cancelled_exception(e)` → re-raise (step 8 handles it);
   - `_BudgetRejected` → `advance(Halt(rejected, "budget"))`, go to 7;
   - `FAILURE_TYPES` instance, not cancelled, and the node type declares `fail` →
     `NodeResult(port="fail", payload=NodeFailure(...))`; the **original
     exception object** is kept keyed by activation id only while that `fail`
     port is unrouted;
   - anything else → re-raise from `run` — never a silent park on `wait_condition`.
5. **Budget boundary** (§5.5), if the emission is one: wait (no timeout) until no
   *other* handler task is running — the whole result is held meanwhile — then
   `_check_budget`. On `_BudgetRejected`: `advance(Halt(rejected, "budget"))`,
   **skip `finalize`** (today the raise at `feature.py:588` precedes the board
   publish at `:589`), go to 7.
6. Run the result's `finalize` hook (§7.2); store the payload; `advance(Emitted(...))`;
   cancel the handler tasks named in `step.cancelled` (activity/child/gate
   cancellation; `gates.py:236` cleans pending); append `step.activations` to
   `held`; back to 2. `advance` is pure, so running it after the budget check and
   `finalize` issues no extra commands, and `Halt` only ever meets a RUNNING state.
7. Terminal outcome, or `completed` with no running task → §5.6. For `failed`
   through an **unrouted** `fail`, `run` re-raises the stored original exception
   object from plain code — not inside an `except`/`finally`, and with no `from`
   clause, because CPython would overwrite `__context__` and the failure
   converter would serialise a spurious `cause` for parents (advisor Q2 F5
   traps). Proto-backed failures (`ActivityError`, `ChildWorkflowError`)
   round-trip exactly; a protoless `ApplicationError` differs only in
   `stack_trace`, which the golden projection does not compare.
8. **Workflow cancellation fan-out.** Temporal cancels only the primary task
   (`_workflow_instance.py:598-606`). `run` wraps steps 1–7 in `try/except
   BaseException as e`; if `is_cancelled_exception(e)`, it calls `cancel()` on
   every running handler task (sorted by activation id), `await
   workflow.wait_condition(lambda: all(t.done() for t in tasks))` (no timeout),
   then re-raises `e`. Without this, handler activities never receive
   `RequestCancelActivityTask`: harness processes run to timeout (the C6
   orphan-subprocess shape) and children are terminated instead of cancelled.
   This cleanup never raises a stored failure object.

No per-router-step commands (markers, search attributes, timers): the command
stream is a function of the handlers alone.

### 5.5 Budget boundaries

`budget_after: Literal["none", "continuing", "exiting"]`, judged purely from
topology, never from port names (skeptic F8):

- `continuing` — check after an emission on a port that carries forward edges
  (not a terminal, not a back edge);
- `exiting` — check after any emission whose port carries **no back edge**
  (forward, sink or terminal); an emission onto a back edge is a loop round and
  is never a boundary;
- `none` — never.

| type | `budget_after` | reproduces |
|---|---|---|
| `research` | `continuing` | `feature.py:550`, skipped when research rejects (`:544`) |
| `clarify`, `analyze` | `continuing` | `:574`, `:746` |
| `gate.architecture`, `gate.plan` | `exiting` | `:588`, `:605` — budget beats a reject; no check between revise rounds |
| every other type | `none` | `code` keeps its per-wave check internally (`:716`) |

With research absent, `:550`'s check is a no-op (intake/context spend nothing),
so no graph node is needed for it. The check runs only at **quiescence** (§5.4
step 5: no other running handler task; the boundary result is held, so nothing
new starts) — today's "never inside a gather" rule (`role_host.py:166-169`). A
rejection → `Halt`. On the default graphs no `continuing` type has a sink-only
emission, so "forward edges only" loses no boundary.

### 5.6 Outcome → return string

| router end | return |
|---|---|
| `rejected` via terminal emission with `result` | that result (`rejected:intake (…)`, `rejected:context (…)`, `rejected:research`, `rejected:merge:…`) |
| `rejected` via gate `reject` without result | `rejected:<gate node id>` (`rejected:architecture`, `rejected:plan`) |
| `rejected` via `Halt(budget)` | `rejected:budget` (also when it follows a gate reject — today's precedence) |
| `failed` via `halt` port with `result` | that result (`failed:plan-validation:…`, `failed:dependency-cycle`, `failed:integration-conflict:<t>`, `failed:quarantined-tasks`) |
| `failed` via unrouted `fail` | no return: re-raise the original exception object (D8, §5.4 step 7); retro not run (today) |
| `completed` | `result` of the last result-bearing sink emission: `deploy.done` carries every `deploy/step.py:57-76` string — `deployed:…`, `merged-not-deployed:…` (incl. merge's `skipped:benchmark-run-has-no-remote` flowing in as `PullRequest.url`), `deploy-broken:…`, `deploy-rejected:…`, `rolled-back:…`; all are `completed` in router state, as they are normal completions today. None → `completed:<sorted sink node ids>` (user graphs only) |
| `escalated` | `escalated:<router reason>` (unreachable on shipped graphs: gates map REVISE on an unavailable port to `reject`, E-73 §6.5) |

`NodeResult.result` on a non-terminal, edged port is an interpreter bug: raise
(workflow-task retry). Retro runs for every string outcome, as today. A table
test pins every wire string to `(node type, port, router outcome)`.

### 5.7 Queries and signals

`GraphWorkflow` composes the same hosts as FeatureWorkflow plus `RunHost`:
`run_state`, `run_summary`, `status`, `pending_gate`, `pending_decisions`,
`submit_gate_decision`, `answer_question` — same names, same shapes. No
`graph_state` (E-75). `current_stage` keeps reading the last `STAGE_STARTED`, so
E-76's linear fleet strip (E76-OQ-3) renders graph runs as it renders today's.

### 5.8 `executable(graph) -> list[Problem]`

Workflow-layer, separate from `validate` (legality stays pure and canvas-shared):
a node type with no registered handler; a `gate.research` node (research refine
loop is handler-internal until the research-as-topology follow-up); a gate-kind
node whose id equals a handler-internal gate name used by an executable node in
the same graph (`research`). The tiering is deliberate (skeptic F12):
`validate` answers "is this graph legal" for the canvas and every consumer;
`executable` answers "can this worker run it today". The canvas shows legality
only; start sites and `GraphWorkflow.run` apply both. Worker boot asserts
`set(NODE_TYPES) == set(HANDLERS) | NOT_EXECUTABLE` and `check_node_types() == []`.

## 6. Catalog (registry after M1) and handlers (M2)

`fail: NodeFailure (terminal=failed)` is on every stage-kind type; `reject`/`halt`
are signal ports. Existing E-72 ports are unchanged except research (flagged).

| type | kind | new/changed ports | handler (M2) → existing code |
|---|---|---|---|
| `intake` | stage | + out `brownfield`, + `reject` (rejected); `ok` = greenfield path | `intake.step`; on pass → `setup_integration_branch` → RunFacts; emits `ok`/`brownfield` by `idea.mode`; mode port not `connected` → `reject` with `rejected:intake (graph has no <mode> path)` |
| `context` | stage | + `reject` (rejected) | `context.step(commit_sha=integration head)` |
| `research` | stage | `trigger` becomes **optional**; + in `codebase_map: CodebaseMap` (opt, ordering only); + `reject` (rejected) | `research.step` unchanged (internal loop, gate `research`); `brief` payload `meta.digest` |
| `clarify` | stage | — | `clarify.step` (+ `brief_digest` from research payload meta) → `_board_publish("requirements")` → retain |
| `architect` | stage | — | `architecture.produce(guidance from GateDecision)`; carry: spend, start, first-activation stage event |
| `plan` | stage | — | `plan.produce(…)`; carry as above |
| `gate.architecture`, `gate.plan` | gate | `reject` marked terminal | generic gate, §6.1 |
| `plan_check` (new) | stage | in `plan: ImplementationPlan`; out `ok: ImplementationPlan`, `halt` (failed) | `validate_task_graph` → `_board_sync_tasks` |
| `seed.spec`, `seed.plan` (new) | stage | in `trigger` (opt); out `spec: ArchitectureSpec` / `plan: ImplementationPlan` | read `RunFacts.seeded`; `seed.plan` emits today's `_stage("coding","code")` |
| `code` (new) | stage | in `plan`; out `results: BuildResult`, `halt` (failed) | `build.run_tasks` (scheduler + `_dev_task` fix loop + merges + per-wave budget) |
| `analyze` (new) | stage | in `results`, `plan`; out `analysis: AnalyzeResult` | `get_task_diff` → `analyze.step` → `untraced_criteria` |
| `merge` (new) | stage | in `results`, `plan`, `spec`, `analysis`; out `pr: PullRequest`, `reject` (rejected) | `merge.step` (gate `merge` internal; stays in `RESERVED_GATE_NAMES`) |
| `deploy` (new) | stage | in `pr`; out `done` (sink, carries result) | `deploy.step` (gates `deploy`, `deploy_failed` internal; reserved) |

### 6.1 Generic gate handler (reproduces `_revisable_stage`, `role_host.py:219-271`)

- **Artifact and author** from `nc.payload(act.inputs["artifact"])`;
  `confidence = getattr(model, "confidence", None)`.
- **In-loop round** (`revise` not in `act.unavailable_ports`): calibration read
  **only if** `confidence is not None and cfg.gates.get(node.id, GateConfig()).policy
  is GatePolicy.SOFT` — the predicate copied verbatim onto the projected cfg, not
  the resolved `gate_settings()` policy (`GateConfig().policy` defaults to HARD
  while `_gate` falls back to `default_gate_policy`, so a SOFT default with no
  explicit entry reads nothing today). Then `_gate(node.id, cfg.gate_settings(),
  auto_decision=auto, round=act.round, context=GateContext(spec_summary=…),
  confidence=confidence, author_model=author)`.
- **Final round** (`revise` unavailable — `exhausted` or `target_dead`): **no**
  calibration read, `confidence` not passed, no `auto_decision`; `context` and
  `author_model` as above (`role_host.py:263-270`).
- **Mapping:** APPROVE → `approve` (same artifact); REJECT → `reject`; REVISE →
  `revise` (payload: the decision) or, on a final round, `reject` (E-73 §6.5).
  Rounds equal `_revisable_stage`'s: `name#1..M` in loop, `name#(M+1)` final.
- **Post (approve/reject only):** locate the producer via
  `StoredPayload.producer` → node id → `carry(node)` (never assume the id is
  `architect`; user graphs rename it) and run the per-type `finish` from a table
  keyed by gate *type* (the dispatcher never branches on type names).
- **`finalize`:** `_board_publish(key, artifact, approved=…)`; the plan gate's
  also sets `_plan_version`.
- The architect/plan handlers set `NodeResult.author_model` to the resolved
  model and read `guidance = decision.guidance or decision.comments` from their
  `guidance` input.

Canonical stages (`benchmarks/heatmap.py:25` members): `plan_check` →
`planning`, `seed.spec` → `architecture`, `seed.plan` → `planning`, `code` →
`code`, `analyze` → `analyze`, `merge` → `quality_gate`, `deploy` → `deploy`. E72-OQ-4 closed by `fail`/`NodeFailure`;
E73-OQ-5 closed by `NodePort.terminal`.

## 7. Shipped graphs and the reproduction proof

### 7.1 Graphs (`workflows/graphs/`)

`default.graph.yaml` (ids → types): `intake`, `context`, `clarify`, `architect`,
`architecture`=gate.architecture, `planner`=plan, `plan`=gate.plan, `plan_check`,
`code`, `analyze`, `merge`, `deploy`. Edges: `intake.ok→clarify.trigger`;
`intake.brownfield→context.trigger`; `context.map→clarify.codebase_map`,
`→architect.codebase_map`; `clarify.requirements→architect.requirements`,
`→planner.requirements`; `architect.spec→architecture.artifact`;
`architecture.revise→architect.guidance` (`max_traversals: 2`);
`architecture.approve→planner.spec`, `→merge.spec`; `planner.plan→plan.artifact`;
`plan.revise→planner.guidance` (2); `plan.approve→plan_check.plan`;
`plan_check.ok→code.plan`, `→analyze.plan`, `→merge.plan`;
`code.results→analyze.results`, `→merge.results`; `analyze.analysis→merge.analysis`;
`merge.pr→deploy.pr`.

Readiness (E-73 §6.3) settles the mode branch: greenfield kills `context`
(required trigger dead) so `clarify.codebase_map` is DEAD and `trigger` FILLED;
brownfield kills `clarify.trigger` and `codebase_map` waits for `context`.

`default-research.graph.yaml`: as default plus `research`
(`intake.ok→research.trigger`, `context.map→research.codebase_map`,
`research.brief→clarify.research`, `clarify.trigger` unconnected).
`seeded.graph.yaml`: `intake.{ok,brownfield}→seed.spec.trigger, seed.plan.trigger`,
`seed.plan.plan→code.plan, analyze.plan, merge.plan`, `seed.spec.spec→merge.spec`,
then code→analyze→merge→deploy as default (no `plan_check`: today's seeded
path skips validation and board sync).

**Selection** `select_graph(cfg, seeded) -> PipelineGraph`, pure: seeded →
`seeded`; `cfg.research_enabled and "research" in REGISTRY` → `default-research`
(mirrors `feature.py:535`'s `t_research is not None` guard, so a tree without
`agents/research/` keeps today's silent skip instead of failing validation);
else `default`. Then **templating** (user ruling U4): the pre-code revise edges
(`architecture.revise`, `plan.revise`) get `max_traversals = cfg.max_gate_rounds`;
start sites reject `max_gate_rounds < 1` (`GraphEdge.max_traversals` is `ge=1`,
`graph/model.py:124`; today `0` means "final gate immediately" — a named,
user-approved change). Task and `deploy_failed` gates keep reading
`cfg.max_gate_rounds` inside their handlers. The templated graph is the pinned
input, so its `content_sha` reflects the bound.

Shipped graphs load at import of `workflows/graph_catalog.py` (passthrough
module; the `REGISTRY` precedent), and parents resolve `GraphRunInput.roles` from
the import-time `REGISTRY` constant — never `load_registry()`, which does file
I/O — so in-workflow child starts (TidyUp, Benchmark) do no I/O. `select_graph`
and role resolution sit inside the determinism lint's module set.

### 7.2 Handler ordering hooks

`NodeResult{port, payload, author_model: str | None, meta: dict[str, str], result: str | None, finalize: Callable[[], Awaitable[None]] | None}`
(frozen dataclass). The dispatcher copies `author_model` and `meta` into
`StoredPayload` (skeptic F4): `architect`/`plan` set their resolved model, which
the generic gate passes to `_calibration_verdict` and `_gate(author_model=…)`
exactly as `_revisable_stage` does. `finalize` runs after the budget boundary.
This reproduces "judge/record/retain → budget → board publish → reject return"
for the pre-code gates with no deviation.

**Once-per-stage work stays once** (skeptic F10, via the command projection):
the architect/plan `recall` snapshot and prompt salt happen on the first
activation and live in `carry`; `STAGE_STARTED` follows the legacy call sites
verbatim — `architecture.step`'s `ctx.stage("architecting", …)` on the first
architect activation only; **no** stage event from `code` on the default graphs
(today `_stage("coding", "code")` fires only on the seeded path, `feature.py:518`;
skeptic F6), so `seed.plan` emits it.

### 7.3 Golden-trace assertion (constraint 7)

`tests/replay/test_graph_golden.py` drives `GraphWorkflow` with each captured
scenario's fakes and signal script on the selected shipped graph and asserts
**exact equality** with `tests/replay/golden/<scenario>.json` on all four
projections, with no normalisation. The advisor walked the default path
(`advisor-e74-q2.md` Q2) and found equality achievable given the conditions this
spec states normatively: once-per-stage prefix (§4.3, §7.2); final-gate
byte-exactness and the verbatim calibration predicate (§6.1); budget → finalize
→ advance ordering (§5.4); host mirrors (§5.3); no dispatcher timers (§5.4).
This is the regression proof; it is not dual-running. The benchmark before/after
run is recommended free evidence, not a gate.

## 8. Cutover mechanics (M2)

### 8.1 Start sites

| site | change |
|---|---|
| `cli.py` `start` | build `GraphRunInput` (selected graph, resolved roles), validate + `executable` locally (print problems, exit 1), start `GraphWorkflow.run`, id `feature-<slug>` unchanged |
| `interfaces/dashboard/api/main.py` `_start` | same; `dashboard/api.py` maps validation failure to 422 |
| `benchmarks/workflow.py` child | per-child patch (§8.2); invalid graph → existing "cell rejected" path |
| `workflows/tidyup.py` child | per-child patch; `seeded.graph.yaml` |
| `cli.py:764,782` | retype to `GraphWorkflow` (signals/queries by name serve both types) |
| `channels/inbox.py` (open runs) | WorkflowType disjunction gains `GraphWorkflow`; `FeatureWorkflow` leaves it with the deletion follow-up |
| `dashboard/fleet.py` (`_CLOSED_QUERY*`, closed runs) | disjunction of both types **permanently** — pre-cutover runs stay visible after FeatureWorkflow is deleted (skeptic F9) |
| `worker.py` | registers `GraphWorkflow` beside `FeatureWorkflow`; boot runs `check_node_types()` and handler coverage |

A Running FeatureWorkflow holding `feature-<slug>` makes a new start fail with
WorkflowAlreadyStarted (correct). Same-id restart after close keeps today's
stale-branch defect exactly (§11) — not more reachable, because the branch is
still created only after intake passes.

### 8.2 Parent workflows

A parent that started a FeatureWorkflow child before cutover must replay it
(Temporal matches a child start's type). `if workflow.patched(f"e74-graph-child:{child_id}")`
→ `GraphWorkflow`, else `FeatureWorkflow`. The id is **per child**: a single id
is memoised per execution, so an in-flight benchmark matrix would keep starting
FeatureWorkflow children after cutover, contradicting "no new run ever executes
the old path". Pinned by a replay of a pre-change parent history with one child
started, asserting the next child is `GraphWorkflow`.

### 8.3 Editing shared code during grace (user ruling U6)

From M1 on, the Replayer test fails on any command-changing edit to code
FeatureWorkflow executes (stage steps, hosts, `build.run_tasks`), and such an
edit would also break in-flight FeatureWorkflow runs. **Rule while grace lasts:**
a command-changing edit to that code is wrapped in `workflow.patched("<epic>-<slug>")`,
and the Replayer test is the enforcement — its histories are never re-recorded
to make an edit pass. Recorded in `workflows/AGENTS.md` at M1 landing.
**After deletion:** an intentional change to the golden projections re-baselines
them from GraphWorkflow, with the projection diff attached to the review.

### 8.4 Deploy and rollback

No switch back to FeatureWorkflow: rollback is roll-forward (U8). A client on
new code may start GraphWorkflow before the worker has it; the task retries
until rollout (nothing lost). Rolling the *worker* back strands GraphWorkflow
runs in workflow-task retry until it rolls forward again. Deploy order: worker
first, then clients.

### 8.5 Deletion criteria (follow-up)

The follow-up deletes FeatureWorkflow (with `_pipeline`, dead `_run_handoff`,
`_revisable_stage`, `StageServices.revisable_stage`, the `step()` composites of
architecture/plan, the patched `else` branches, the FeatureWorkflow histories
and legacy-only tests, the WorkflowType disjunctions) when **both** return empty:

```
temporal workflow list --query "ExecutionStatus='Running' AND WorkflowType='FeatureWorkflow'"
temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='TidyUpWorkflow' OR WorkflowType='BenchmarkWorkflow') AND StartTime < '2026-09-DDTHH:MM:SSZ'"
```

The second query extends PRD OQ-10's (parents' replay needs the old branch).
Its timestamp is the M2 worker deploy instant in RFC 3339 UTC (skeptic F11),
recorded in the follow-up inbox task that M2's landing files, carrying both
queries verbatim. `dashboard/fleet.py`'s closed-run disjunction is **not**
removed by the follow-up (§8.1).

## 9. `PipelineConfig` split by scope

| setting | graph path | FeatureWorkflow |
|---|---|---|
| per-node role | `node.role` fills `cfg.roles[spec.role]` unless the run overrides that role (U5, §5.2) | unchanged |
| pre-code gate policy | `node.gate` overlays `cfg.gates[node.id]` | unchanged |
| pre-code revise bound | back-edge `max_traversals`, templated from `cfg.max_gate_rounds` at selection (U4) | `max_gate_rounds` |
| `research_enabled` | presence of a research node (field kept for graph selection) | unchanged |
| `max_fix_attempts`, task/`deploy_failed` `max_gate_rounds`, review lens flags, clarify flags, research/deploy/memory/budget config, handler-internal gates (`clarify`, `merge`, `deploy`, `budget`, `task:*`, `deploy_failed`) | run-scoped, unchanged (U1) | unchanged |

No `PipelineConfig` field is removed in E-74 (FeatureWorkflow still reads them).

## 10. Determinism, testing, boundaries

### 10.1 Determinism lint (constraint 6)

`tests/test_graph_workflow_determinism_lint.py`: AST walk of `workflows/graph.py`,
`workflows/graph_catalog.py`, `workflows/graph_nodes/**`, `workflows/build.py`,
`workflows/run_host.py`. Rejects: `for`/comprehension over a `set` literal,
`set(...)`, set comprehension, or `.keys()/.values()/.items()` not wrapped in
`sorted(...)`; `asyncio.wait`, `asyncio.as_completed`; `random`, `time.time`,
`datetime.now/utcnow`, `uuid.uuid4`, `os.environ` reads; `asyncio.gather` over
anything but a list/tuple literal or a comprehension over `sorted(...)`. Allowlist
by `# determinism: <reason>` comment on the line, counted and pinned. The
pre-existing `feature.py` is out of scope.

**Expected allowlist class (reviewer R4).** The M1-extracted scheduler in
`workflows/build.py` legitimately walks insertion-ordered dicts keyed by task id
(`remaining.values()`, `done.values()`; today `feature.py:683,706,713,754`) and
gathers over the wave batch (`asyncio.gather(*[run_one(t) for t in batch])`).
Insertion order is deterministic given the recorded history, so these lines
carry `# determinism: insertion-ordered task dict` / `# determinism: wave batch
order` and are counted in the pin. They are **never** "fixed" by sorting: that
would change FeatureWorkflow's command sequence and fail the Replayer test.

### 10.2 Testing (in addition to §4.2, §7.3, §8.2)

- **Router** (M1): table rows for a failed terminal, a terminal port with edges
  routing normally, `Halt` from running with live activations, post-terminal
  drop after `failed`; property suite re-run with terminal ports — its
  `_ends_run` helper (`tests/graph/test_graph_router_properties.py:168`) switches
  from the hard-coded gate-reject test to `Topology.terminal_ports` (skeptic F7).
- **Catalog** (M1): `check_node_types() == []`; gate `reject` terminal asserted;
  shipped graphs validate clean; `executable` rows.
- **Router** (M1): `Halt` after a terminal outcome raises `RouterError`.
- **Dispatcher** (M2, test registries): cancellation of a live handler on a back
  edge; `RuntimeError` in a handler fails the workflow task (does not hang);
  `FAILURE_TYPES` instance → routed `fail` vs unrouted re-raise; an unrouted
  protoless `ApplicationError` reaches the parent with `cause.cause is None`;
  cancellation not converted; workflow cancellation fans out
  `RequestCancelActivityTask` to every running handler; a boundary result is
  held until quiescence; `result` on an edged port raises; `FAILURE_TYPES` pin:
  the plugin's registered triple ⊆ `FAILURE_TYPES` and `FailureError ∈ FAILURE_TYPES`.
- **Selection** (M2): `select_graph` rows (seeded; research on with/without
  `research` in `REGISTRY`; templated bound; `max_gate_rounds=0` rejected).
- **Host mirrors and memo-ON parity** (§5.3).
- **Projection-equality** (§5.2); **wire-string table** (§5.6, every deploy string);
  **benchmark purity**: `test_factory_purity` extended to the graph modules
  (`_record`/`_judge` only through guarded helpers).
- **Cold import** of `sdlc.workflows.graph` in a subprocess (benchmarks↔stages
  cycle, inbox task `2026-09-12-b0-lazy-step-export-shadowing`): handler modules
  import in feature.py's order.
- Temporal-tier golden runs use narrow selections under an external watchdog
  on Windows (inbox `2026-09-09-temporal-tier-hangs-on-windows`).
- Gates: `ruff check`, `ruff format --check`, `mypy`, `scripts/check_file_size.py`.

### 10.3 FR-1203 traceability

| clause | discharged by |
|---|---|
| generic `GraphWorkflow` executes the graph | §5, §6 |
| `_pipeline` removed; big-bang | new starts never run it (M2, §8.1); code removed by §8.5 follow-up |
| `default.graph.yaml` reproduces today's stage sequence exactly | §7.1, §7.3 golden traces |
| graph is pinned workflow input; edits never mutate a running workflow | §5.1 `GraphRunInput.graph` |
| grace-retention; removed once none Running | §8.2, §8.5 |

### 10.4 Obligations discharged

E-72: (1) role projection §5.2; (2) boot self-check + dispatch coverage §5.8;
(3) post-plan catalog §6. E-73: (1) gate handler rules §6; (2) validate at run
start with resolved roles §5.1, §8.1; (3) `merge`/`deploy` stay reserved (not
nodes); (4) `Step.cancelled` §5.4; (5) provider keys stay a worker-boot check.

### 10.5 Out of scope

Per-task topology and `max_fix_attempts → max_traversals` (follow-up, U1);
research-as-topology (follow-up); E-75 graph queries; E-76 canvas changes beyond
the catalog fixture regen; E-77 store and `graph_sha` on runs; OQ-14 subflows;
FeatureWorkflow deletion (§8.5); the stale-branch defect fix.

**E76-OQ triage (reviewer R6).** E76-OQ-3 (fleet strip for graph runs before
E-75) becomes live at M2, since every new run is a graph run; E-74 keeps
`STAGE_STARTED` / `current_stage` identical (§5.7), so the linear strip renders
graph runs as it renders today's — exact `skipped` rendering stays E-75's.
E76-OQ-1 (gate rename), OQ-2 (drag refusal), OQ-4 (revise comment) and OQ-5
(comment loss) need nothing from E-74.

### 10.6 Docs on landing (docs describe main)

M1: E-72/E-73 errata; `workflows/AGENTS.md` ownership rows for `RunHost` and
the grace-edit rule (§8.3); stage `.md` clauses for the split architecture/plan
steps. M2: tick E-74 in `docs/roadmap/pipeline-as-data.md` and the ROADMAP
mirror, naming the two follow-ups (per-task topology, research-as-topology) and
the deletion follow-up; ARCHITECTURE §1–2 (GraphWorkflow as the pipeline,
roll-forward-only posture); AGENTS.md "FeatureWorkflow is the sole coordinator"
→ GraphWorkflow; PRD §11 OQ-10 one-line amendment (deletion is a separate
follow-up, U7; parent-workflow query added, §8.5).

## 11. Inbox tasks named by the brief

- **Restart under the same id keeps stale branches** — E-74 neither fixes nor
  widens it: branch creation stays after intake (§6 intake handler). Grace-
  retention leans on it by not restarting in-flight runs.
- **B0 lazy step export shadowing** — not fixed; mitigated by import order and a
  cold-import test (§10.2).
- **E-72 review minors** — #2 folded in (§4.4); #1/#3/#4 already closed by
  E-73/E-76.

## 12. Open questions

Settled this brainstorm and recorded as rulings U1–U10 (§2.1): code scope,
"unchanged", landing, revise-bound templating, role precedence (E72-OQ-6), grace
edits, deletion collapse, rollback, retro on failure, handler signature
(constraint 3). Remaining:

- **E74-OQ-1 (owner E-75) — `completed:<sorted sink ids>`** as the return string
  for user graphs without a result-bearing sink; E-75 renders run outcomes.
- **E74-OQ-2 (owner research-as-topology follow-up)** — refine accumulation
  across rounds, exhaustion proceeds (needs a gate-type `on_exhausted:
  approve|reject`), `research.max_refine_rounds` as the bound; `gate.research`
  becomes executable.
- **E74-OQ-3 (owner per-task-topology follow-up)** — dynamic fan-out,
  per-instance counters, `max_fix_attempts → max_traversals`, review lens flags
  and handoff as nodes (E73-OQ-7, OQ-14).
- **E74-OQ-4 (owner E-75/E-76) — surfacing `executable()`.** A legal but
  not-executable graph (e.g. with `gate.research`) is drawable and fails at start.
  Recommendation: E-75 exposes `executable` beside `validate` with a distinct
  severity; the canvas renders it without blocking save.
- **E74-OQ-5 (owner follow-up) — retro on FAILED executions** (U9 keeps today's
  behaviour).

## 13. Skeptic dispositions (`.workspace/tmp/e74-skeptic-full.md`)

| ID | Sev. | Finding | Disposition | Where |
|---|---|---|---|---|
| F1 | Critical | Replayer runs unsandboxed, so sandbox-hostile extractions pass replay and fail in production | **Rejected on evidence, residue accepted.** `Replayer.__init__` defaults `workflow_runner=SandboxedWorkflowRunner()` (`temporalio/worker/_replayer.py:41`); `unsandboxed_workflow_runner` serves only `sandboxed=False` workflows, and `PydanticAIPlugin` extends the sandboxed runner. Residue: pin that the Replayer fixture and `worker.py` build the same runner/plugin configuration. | §4.2 |
| F2 | Critical | Queries are not in history; a broken `run_state` extraction replays green | **Accepted.** Query unit tests parametrised over both classes. | §4.2 |
| F3 | Critical | Dispatch-loop exception handling contradictory (wrapper vs `run`, router ownership, silent task death) | **Accepted.** Wrapper catches and appends; `run` alone classifies and advances; ordered rules. | §5.4 |
| F4 | Critical | `NodeResult` lacks `author_model`, so SOFT gates never auto-approve | **Accepted.** `NodeResult.author_model`/`meta` → `StoredPayload`. | §7.2 |
| F5 | Critical | Re-raised failure changes `type` (claimed replay nondeterminism) | **Accepted, refined.** The nondeterminism claim does not apply (GraphWorkflow has no pre-change histories), but the observable failure type/message would change for parents and dashboards. Fix: re-raise the stored original exception object. | D8, §5.4, §5.6 |
| F6 | Important | `code` emits no `STAGE_STARTED` on normal paths today | **Accepted.** Stage events follow legacy call sites verbatim; `seed.plan` emits `coding`. | §7.2 |
| F7 | Important | Property test `_ends_run` hard-codes gate reject | **Accepted.** Switch to `Topology.terminal_ports`. | §10.2 |
| F8 | Important | `budget_after` enum cannot say "except revise" | **Accepted.** `none/continuing/exiting` defined from edge kinds, not port names. | D12, §5.5 |
| F9 | Important | Removing FeatureWorkflow from the closed-run query hides history | **Accepted.** Closed-run disjunction permanent; open-run disjunction leaves with the follow-up. | §8.1, §8.5 |
| F10 | Important | Golden trace blind to board/benchmark/memory side effects | **Accepted, strengthened.** Golden trace adds the ordered command projection from history (activity types, child types, timers), which also catches repeated once-per-stage work. | §4.1, §7.2 |
| F11 | Minor | Deletion query timestamp format | **Accepted.** RFC 3339 UTC, recorded in the follow-up task. | §8.5 |
| F12 | Minor | `validate` vs `executable` split-brain | **Accepted.** Tiering documented. | §5.8 |

### 13.1 Advisor check (`advisor-e74-q2.md`)

The advisor confirmed every §13 disposition (F1's rejection verified at
`_replayer.py:46`) and surfaced:

| ID | Sev. | Finding | Disposition | Where |
|---|---|---|---|---|
| G1 | Critical | Workflow cancellation reaches only the primary task; handler activities never get cancel requests (C6 orphan shape) | **Accepted.** Cancellation fan-out in `run`; golden cancel scenario. | §5.4 step 8, §4.1 |
| G2 | Important | advance → budget → finalize lets `Halt` meet a terminal state; publish would precede a budget rejection | **Accepted.** Order budget → finalize → advance; `Halt` after terminal is `RouterError`. | §5.4, §4.4 |
| G3 | Important | `AnalyzeResult.integration_diff: dict[str, str]` mistyped → infinite workflow-task retry | **Accepted.** `dict[str, Any]`; every payload built from real output in a golden scenario. | §4.4 |
| G4 | Important | `cfg.max_gate_rounds` silently ignored on the graph path | **Escalated → U4** (template from cfg). | §7.1 |
| G5 | Important | produce/finish split details (per-round delta retries, once-per-stage prefix, `_ended` placement, producer lookup, per-type finish) | **Accepted.** `prepare`/`produce`/`finish`. | §4.3, §6.1 |
| G6 | Important | Parents must resolve roles from `REGISTRY`, not `load_registry()` | **Accepted.** | §7.1 |
| G7 | Important | §5.2 (node wins) contradicted OQ-6 (run wins) | **Escalated → U5.** | §5.2, §9 |
| G8 | Important | Replay-compat policy for shared code during grace | **Escalated → U6.** | §8.3 |
| G9 | Minor | `NodeFailure` placement vs purity pins | **Accepted.** `sdlc/core/models.py`. | §4.4 |
| C2/C3 | — | Final gate must skip the calibration read and confidence; copy the SOFT predicate verbatim | **Accepted.** | §6.1 |
| C5, H1 | — | No dispatcher timers; host attribute mirrors | **Accepted.** | §5.4, §5.3 |
| — | — | Deploy strings `deploy-broken:`/`deploy-rejected:`/`rolled-back:` missing; research selection guard; plugin failure types; F5 `__context__` trap; live query in a golden run; capture-twice | **Accepted.** | §5.6, §7.1, D8, §5.4, §4.2, §4.1 |

### 13.2 Reviewer round 1 (`e74-reviewer-r1.md`, CHANGES REQUESTED)

| ID | Sev. | Finding | Disposition | Where |
|---|---|---|---|---|
| R1 | Important | `FAILURE_TYPES` provenance misstated (plugin registers 3 types; `FailureError` fails executions in temporalio itself); `asyncio.TimeoutError` misclassified | **Applied.** Provenance restated, subset pin, TimeoutError sentence. | D8, §5.4, §10.2 |
| R2 | Important | Constraint 3 refinement self-decided | **Escalated → U10** (user approved the recommended signature). | §2.1, D2 |
| R3 | Minor | Cancellation anchor wrong | **Applied.** `_workflow_instance.py:598-606`. | §5.4 step 8 |
| R4 | Minor | Determinism lint trips on replay-safe scheduler orderings | **Applied.** Named allowlist class; never sort. | §10.1 |
| R5 | Minor | `run_tasks` return contract unstated | **Applied.** Signature and `(done, failure)` contract. | §4.3 |
| R6 | Minor | E76-OQ triage implicit | **Applied.** | §10.5 |
| R7 | Minor | U5 amends E-72 §5 without an erratum line | **Applied.** | §4.4 |

### 13.3 Reviewer round 2 (`e74-reviewer-r2.md`, APPROVED)

| ID | Sev. | Finding | Disposition | Where |
|---|---|---|---|---|
| R8 | Minor | §12 recap said U1–U9 and omitted the handler-signature ruling | **Applied.** | §12 |
| R9 | Minor | `run_tasks` signature carried an unused `idea` | **Applied.** Dropped. | §4.3 |
