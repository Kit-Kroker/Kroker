# Code Stage

The code stage (Stage 4 / spec A §3.3 / spec A §5) executes coding tasks inside an isolated git worktree, either using a coding harness (`run_coding_task`) or multi-agent crew (`CrewTaskWorkflow`). It evaluates tool escalations, runs clean-context QA and review, drives the bounded fix loop, and returns a schema-validated `TaskResult`.

The orchestrator (`TaskHost` / `FeatureWorkflow`) delegates per-task execution to `code.step`.

## Requirements

### CODE-1.1
The code stage slice exports `step`, `prompt_digest`, and `ACTIVITIES = [run_coding_task]`. The step function accepts `ctx: StageContext` as its first argument, receives configuration, task definition, frozen validation contract, worktree path, handoff notes, and agents as keyword arguments, and never receives the workflow instance directly. [FR-801, FR-803]

### CODE-1.2
The code stage step is pure over its inputs and contains no workflow lifecycle decorators (`@workflow.defn`, `@workflow.signal`, `@workflow.query`). All signals and queries remain on the workflow orchestrator. [ADR-6, Rule 1]

### CODE-1.3
The code stage executes the coding task inside an isolated worktree against the frozen contract, coordinates deterministic test suite and clean-context review, drives the bounded fix loop, and returns a schema-validated `TaskResult` indicating `done`, `failed`, or `quarantined`. [FR-802, FR-804]

### CODE-1.4
The code stage records benchmark records for each attempt of the task, emitting `stage="code"` with `judge="contract"` derived from deterministic test runner results, and emitting `stage="qa"` with quality score evaluated against the rubric. [Finding 4, E-36, E-37]

### CODE-1.5
When the bounded fix loop attempts are exhausted without passing both tests and review, the code stage escalates to the human gate `task:{task.id}`. If the operator grants revision, it resets session context and continues; otherwise it quarantines or completes according to operator decision. [FR-105]

## Failure modes

- **Tool escalation timeout / rejection**: A suspended tool call is rejected by policy or human gate; execution resumes with denied grant.
- **Fix loop exhaustion**: Repeated attempts fail contract verification; escalated to operator gate.
- **Quarantine on task rejection**: Operator rejects failing task at gate; task marked as quarantined.
