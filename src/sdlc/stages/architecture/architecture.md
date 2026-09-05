# Architecture Stage

The architecture stage (Stage 2 / spec A §3.3 / spec A §5) generates a schema-validated `ArchitectureSpec` from clarified requirements and brownfield codebase grounding. It runs the architect proposer role with memoization caching, checks proposed filesystem deltas against the repository tree via `check_brownfield_delta`, and handles human gate approval through the revisable stage review loop.

The orchestrator (`FeatureWorkflow`) delegates architecture execution to `architecture.step`.

## Requirements

### ARCH-1.1
The architecture stage slice exports `step`, `prompt_digest`, and `ACTIVITIES = []`. The step function accepts `ctx: StageContext` as its first argument, receives configuration, clarified requirements, codebase map, memory watermark, idea brief, and agents as keyword arguments, and never receives the workflow instance directly. [FR-201, spec A §3.3]

### ARCH-1.2
The architecture stage returns a tuple of `(ArchitectureSpec, GateDecision)`. The orchestrator handles board publishing and gate branching without exposing workflow handlers or state across the slice boundary. [FR-202, spec A §3.4]

### ARCH-1.3
The architecture stage runs the architect agent with memoization and revisable review loops, checks brownfield filesystem deltas via `check_brownfield_delta`, records benchmark telemetry and memory summary, and provides grounded research tools via dedicated budget scopes. [FR-203, E-84, E-85]

## Failure modes

- **Delta grounding mismatch**: Proposed file changes do not match repository layout; retries with delta guidance or raises ApplicationError.
- **Budget exhaustion**: Search budget exhausted during research subqueries; degrades gracefully into brief gaps without raising unhandled exceptions.
- **Gate rejection**: Human reviewer rejects architecture spec; workflow aborts or branches cleanly per gate decision.
