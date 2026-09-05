# Plan Stage

The plan stage (Stage 3 / spec A §3.3 / spec A §5) generates a schema-validated `ImplementationPlan` from architecture specifications and clarified requirements. It runs the planner proposer role with memoization caching, records benchmark telemetry and memory summaries, and handles human gate approval through the revisable stage review loop.

The orchestrator (`FeatureWorkflow`) delegates planning execution to `plan.step`.

## Requirements

### PLAN-1.1
The plan stage slice exports `step`, `prompt_digest`, and `ACTIVITIES = []`. The step function accepts `ctx: StageContext` as its first argument, receives configuration, architecture spec, requirements, idea brief, and planner agents as keyword arguments, and never receives the workflow instance directly. [FR-301, spec A §3.3]

### PLAN-1.2
The plan stage returns a tuple of `(ImplementationPlan, GateDecision)`. The orchestrator handles board publishing, task synchronization, task graph validation, and gate branching without exposing workflow handlers or state across the slice boundary. [FR-302, spec A §3.4]

### PLAN-1.3
The plan stage runs the planner agent with memoization and revisable review loops, records benchmark telemetry and memory summary, and retains the task plan summary in the project memory bank. [FR-303, E-84, E-85]

## Failure modes

- **Invalid task graph**: Cyclic or missing task dependencies detected during orchestrator validation; fails early before scheduling work.
- **Planner prompt failure**: Model fails schema validation or structured output; retried with exponential backoff.
- **Gate rejection**: Human reviewer rejects implementation plan; workflow aborts or branches cleanly per gate decision.
