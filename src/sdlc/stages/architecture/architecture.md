# Architecture Stage

The architecture stage (Stage 2 / spec A §3.3 / spec A §5) generates a schema-validated `ArchitectureSpec` from clarified requirements and brownfield codebase grounding. It runs the architect proposer role with memoization caching, checks proposed filesystem deltas against the repository tree via `check_brownfield_delta`, and handles human gate approval through the revisable stage review loop.

The orchestrator (`GraphWorkflow`, since 020 deleted the legacy workflow) composes the architecture stage across the `architect` and `gate.architecture` graph nodes; the slice itself exports `prepare`, `produce` and `finish`.

## Requirements

### ARCH-1.1
The architecture stage slice exports `prompt_digest` and `ACTIVITIES = []` (the legacy-era `step` composite was deleted in 020; `step` remains only as the submodule holding the slice functions). The slice functions (`prepare`, `produce`, `finish`) each accept `ctx: StageContext` as their first argument and receive configuration, clarified requirements, codebase map, memory watermark, idea brief, and agents as keyword arguments, never the workflow instance. [FR-201, spec A §3.3, 020 FR-006]

### ARCH-1.2
`produce` returns an `ArchitectureSpec`; the gate decision belongs to the graph's `gate.architecture` wiring, and the orchestrator handles board publishing and gate branching without exposing workflow handlers or state across the slice boundary. [FR-202, spec A §3.4, 020 FR-006]

### ARCH-1.3
The architecture stage runs the architect agent with memoization and revisable review loops (the revisable loop is the `gate.architecture` node's revise wiring), checks brownfield filesystem deltas via `check_brownfield_delta`, records benchmark telemetry and memory summary, and provides grounded research tools via dedicated budget scopes. [FR-203, E-84, E-85, 020 FR-006]

### ARCH-1.4
The stage is composed of `prepare` (the once-per-stage prefix: stage event, start time, role usage, memory recall, map grounding, prompt salt), `produce` (one architect round including delta retries, keyed by the unchanged memo input) and `finish` (judge, benchmark record, memory retain). The graph's `architect` node calls `prepare` once and `produce` per round; the `gate.architecture` node carries the revisable loop. [E-74 spec §4.3, §6.1, 020 FR-006]

## Failure modes

- **Delta grounding mismatch**: Proposed file changes do not match repository layout; retries with delta guidance or raises ApplicationError.
- **Budget exhaustion**: Search budget exhausted during research subqueries; degrades gracefully into brief gaps without raising unhandled exceptions.
- **Request limit**: a research subquery that reaches its request limit degrades the same way; its spend is still reported.
- **Gate rejection**: Human reviewer rejects architecture spec; workflow aborts or branches cleanly per gate decision.
