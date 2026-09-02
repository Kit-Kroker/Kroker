# The Framework Contract — Stack, Context, and Seam Architecture

This document defines the architectural contract for writing workflow and stage
code in this repository. It specifies the component stack, the `StageContext`
protocol, the rules Temporal enforces on workflow code, the activity
registration contract, and how types move across slice boundaries.

The implementation of `StageContext` and the vertical slice structure begins in
spec A; this document establishes the binding rules they must satisfy.

## The stack

The pipeline coordinates three distinct layers of technology:

1. **Deterministic Orchestration:** Temporal (`temporalio` 1.30.0) orchestrates
   the 15-stage Directed Acyclic Graph (DAG) deterministically. The workflow
   coordinates execution flow, tracks run state, sets timers, registers signal
   and query handlers, and retries activities without side effects during history replay.
2. **Reasoning Proposers:** Pydantic AI agents *think*. They emit
   schema-validated, typed artifacts (`Requirements`, `ArchitectureSpec`,
   `Plan`, `Review`, `QAReport`). Proposer agents never touch tools, file systems,
   or subprocesses directly; their output is pure data.
3. **Sandboxed Coding Harnesses:** Coding harnesses (`claude -p`, `opencode run`)
   *do the work*. They execute exclusively inside isolated, per-task git
   worktrees. Only the diff their run produces is admitted back into the pipeline
   as a verified artifact.

See [`ARCHITECTURE.md`](../ARCHITECTURE.md) §1–2 for component responsibilities
and system boundaries.

## The step contract

A stage is the unit of agent work. Each vertical slice under
`src/sdlc/stages/<stage>/` implements an asynchronous entry point:

```python
async def step(ctx: StageContext, ...) -> Artifact:
    ...
```

The orchestrator (`FeatureWorkflow` in `src/sdlc/workflows/feature.py`) is the
sole coordinator. It passes run state as explicit arguments and supplies a
`StageContext` instance providing access to workflow-level services.

### The eleven services

`StageContext` exposes exactly eleven capabilities in five groups:

| Group | Services | Anchors in `src/sdlc/workflows/` | Description |
|---|---|---|---|
| **Reporting** | `emit`, `stage` | `feature.py:1226`, `:1234` | Appends structured lifecycle events to audit trail; updates active stage status. |
| **Role execution and memoization** | `run_role`, `cached_stage`, `revisable_stage` | `feature.py:1283`, `:1145`, `:1773` | Dispatches role activities; wraps stages in content-addressed memoization or bounded revision loops. |
| **Benchmark and memory** | `record`, `judge`, `recall`, `retain` | `feature.py:1012`, `:1026`, `:1062`, `:1080` | Emits benchmark telemetry; grades artifacts against rubrics; queries and stores long-term memory banks. |
| **Human decisions** | `gate` | `gates.py:168` | Waits for human approval or deterministic gate evaluation via signal or timeout. |
| **Human questions** | `ask_and_wait` | `feature.py:2845-2887` | Poses open questions to the operator and blocks on workflow condition until answered. |

`gate` is not optional: `self._gate(...)` is called at ten sites across `feature.py` (`src/sdlc/workflows/gates.py:168` is the definition), including `:2026` and `:2287` in the `qa` pilot. Any context lacking `gate` forces a stage to reach back into the workflow class.
`ask_and_wait` encapsulates human interactive questioning (`self._status`, `self._pending`, and `workflow.wait_condition` on `self._question_answers`) so a stage never touches those internal workflow attributes directly.

### Two rules that protect the protocol

1. **Data travels in the signature; only capabilities go on the context.**
   Values that the workflow holds — such as the codebase map (`CodebaseMap`),
   integration head commit SHA, idea brief digest, and seeded tasks — are passed
   as explicit function parameters, never attached as properties of `StageContext`.
   The review question for any proposed addition to `StageContext` is:
   *"Is this a capability the orchestrator provides, or a value it holds?"*
2. **A step owns no run state across calls.**
   A step function is pure logic over its inputs: it accepts arguments, calls
   context services, and returns an artifact. It must never store state on the
   workflow instance or on module-level globals.

   *Worked example of the failure:* `_escalation_round` (`feature.py:865`,
   `:2025`) was attached as instance state on `FeatureWorkflow`. When wave mode
   executes tasks concurrently or when gate approvals interleave, concurrent
   steps mutate and overwrite the instance attribute, corrupting loop counters.
   `workflows/gates.py:84-88` documents the exact same hazard for gate confidence:
   concurrency and interleaving make instance state unpredictable. Loop
   counters belong in the step's local scope or return envelope.

## What Temporal actually constrains

Temporal workflows execute deterministically. Workflows run inside a sandbox that
records execution history and replays it upon workflow recovery. This environment
imposes four non-negotiable constraints:

### 1. Handlers live on the workflow class's MRO, never in a step module

Signal handlers (`@workflow.signal`) and query handlers (`@workflow.query`) must
be present on the Method Resolution Order (MRO) of the `@workflow.defn` class.

`GateHost` (`src/sdlc/workflows/gates.py:54`) demonstrates the correct pattern:
it is a mixin class defining `@workflow.signal submit_gate_decision` (`:98`) and
three `@workflow.query` handlers (`:108`, `:112`, `:116`). `FeatureWorkflow`
inherits from `GateHost`.
A handler defined inside an external step module is not on the workflow class's
MRO and will silently never be registered by the Temporal worker.

### 2. Mutable run state has exactly one owner: the workflow instance

Because Temporal tracks workflow state through replay of the workflow method,
mutable state spanning multiple activities or steps must be owned exclusively
by the workflow instance itself. Modules must not maintain mutable global or
module-level state.

### 3. The passthrough principle for sandbox imports

Workflow code executes in Temporal's deterministic sandbox. Inside a step module,
calling `workflow.unsafe.imports_passed_through()` is required for anything that
carries **host-shared identity or import-time effects**. Sandboxed imports without
passthrough are reserved for pure, side-effect-free helper routines.

Four categories must be passed through:
1. **Third-party and I/O-adjacent libraries:** Packages that configure logging,
   read network sockets, or manage C-extensions.
2. **Model modules:** Pydantic models and enumeration types.

   *Why enum identity matters:* Untyped JSON payloads survive duplicate class
   definitions across the sandbox boundary without error. However, Python
   enumeration identity does not: `val is EnumCopy.MEMBER` across a host/sandbox
   pair evaluates silently to `False` because the two classes are distinct objects.
   `feature.py` contains at least nine such `is` comparisons (twelve across the
   file today), three of which are critical in the migration pilots:
   - Line 1891: `if role_cfg.harness is HarnessKind.CREW:` (inside `_dev_task`)
   - Line 1927: `if role_cfg.harness is HarnessKind.CREW:`
   - Line 2293: `if decision.outcome is GateOutcome.REVISE` (task gate outcome check)

   Without passthrough, duplicated enum classes cause these checks to fail.
3. **The agent registry:** Initialisation of agent definitions and prompts involves
   file reads and dynamic registration at import time.
4. **Child workflow classes used as handles:** (see Rule 3a below).

**Rule 3a — workflow-class references used as child-workflow handles are passed through.**
Called out specifically because it is the trap an implementer is most likely to hit:
`_dev_task` starts `CrewTaskWorkflow.run` (`:1938`) and the deploy stage starts
`DeploymentWorkflow.run` (`:3601`); the `qa` pilot needs the crew reference.
Importing a `@workflow.defn` module inside the sandbox re-executes it sandboxed and
yields a duplicate class identity.

> [!NOTE]
> This is a **stricter discipline than `feature.py` follows today**. The legacy
> passthrough block in `feature.py` spans lines 20–223 and indiscriminately passes
> through approximately thirty internal modules, including pure helper functions.

### 4. A step module's top-level scope contains constants only

A step module must never execute I/O, read environment variables, or invoke system
clocks at the module level. Top-level scope is restricted to constant definitions
and static configuration. Lines 225+ of `feature.py` illustrate this pattern:
only static constants, type annotations, and `ActivityConfig` definitions exist
outside functions.

### In-flight payload compatibility

The worker and client use `pydantic_data_converter`, whose
`PydanticPayloadConverter.to_payload` sets metadata to `{"encoding": "json/plain"}`
and reconstructs models based on the recipient's type hints
(`temporalio/contrib/pydantic.py:66-99`). Because no Python class path is encoded
in the payload, moving a Pydantic model between modules does not invalidate
in-flight workflow execution histories.

The residual requirement: **field schemas must not change incompatibly mid-flight.**
There is currently no `workflow.patch` or `workflow.deprecated` call in `src/`.

## Activity registration

In the legacy codebase, `src/sdlc/worker.py` (lines 29–131) contained a 103-line
import block that had to be extended manually whenever an activity was created.

Under the slice architecture:
- Each stage slice exports an explicit list of its activity callables:
  ```python
  ACTIVITIES: list[Callable] = [...]
  ```
- `src/sdlc/stages/__init__.py` maintains an explicit list of active stage modules:
  ```python
  STAGE_MODULES = ...
  ```
- The Temporal worker registers activities via straightforward composition:
  ```python
  activities = [act for mod in STAGE_MODULES for act in mod.ACTIVITIES]
  ```

Registration is explicit, greppable, and deterministic. It avoids auto-discovery
magic while consolidating registration edits to one place.

## Ownership of types

**The producer owns its artifacts.**

A stage's `models.py` holds the types that stage *produces*:
- `ClarifiedRequirements` lives in `src/sdlc/stages/clarify/models.py`.
- `QAReport` lives in `src/sdlc/stages/qa/models.py`.

Downstream stages import those types directly from the producer's package. An import
of a data model is a type reference, not a cross-stage function call.

`src/sdlc/core/` holds only the types that **no stage produces**:
cross-cutting envelopes and shared configuration used across the orchestrator
(`PipelineConfig`, `GateDecision`, `RoleConfig`, `IdeaBrief`, `RunSummary`).

*Why the alternative was rejected:*
A rule stating that "any type touched by two stages belongs in `core/`" would
collapse the architecture. In a sequential pipeline, nearly every artifact is
consumed by downstream stages (`ClarifiedRequirements` is referenced across six
different files in `src/`). Placing all shared models into `core/` would re-create
the monolithic, 73-class `src/sdlc/models.py` that the modular slice architecture
was designed to decompose.

## Moving a symbol

When relocating code or models to a vertical slice:
1. **Call sites re-point immediately.** Update every import in the codebase in the
   same commit.
2. **No re-export shims.** Do not leave backward-compatibility shims (`from .new import Symbol`)
   in legacy files.

Shims create two problems:
- They allow two legal import paths for a single symbol, causing agents and human
  contributors to guess inconsistently.
- They prevent legacy monoliths (`models.py`, `activities.py`) from shrinking,
  defeating the shrink-only `.file-size-baseline.json` ratchet.
