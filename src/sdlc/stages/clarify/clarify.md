# Clarify Stage

The clarify stage resolves ambiguities in an incoming feature idea before architecture
and planning. It consumes an `IdeaBrief`, relevant past memories, and an optional
`CodebaseMap` (for brownfield mode). It runs a clarification agent or fans out across
specialist dimension probes (E-85), presents open questions to the human if gates are
active (or uses suggested answers if unattended), judges quality, and outputs a
validated `ClarifiedRequirements` artifact.

The caller (`FeatureWorkflow._pipeline`) owns the orchestrator workflow lifecycle,
board publishing (`_board_publish`), memory retention (`_retain`), and budget checks
(`_check_budget`). The stage owns agent prompt assembly, probe fan-out and merge,
question resolution interaction, quality judging, and benchmark recording.

## Requirements

### CLARIFY-1.1
The clarify step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or accesses unexported orchestrator
state directly. [FR-101]

### CLARIFY-1.2
The clarify step emits a schema-validated `ClarifiedRequirements` artifact containing
functional requirements, non-functional requirements, out of scope boundaries, and open
questions. [FR-101]

### CLARIFY-1.3
When open questions exist and the clarify gate is not OFF, questions are surfaced to the
user via `ctx.ask_and_wait`. When the gate is OFF, suggested answers are adopted automatically
and reported. Narrowing accepted with the slice: a client signaling `answer_question` before
the unattended branch runs is no longer surfaced as `answered_by="human"` — the step cannot
read workflow question state by design (spec A §3.2). [FR-102]

### CLARIFY-1.4
When `clarify_probes_enabled` is set, the stage fans out specialist probes across live
dimensions, isolates probe failures so single probe errors degrade gracefully, and merges
questions within the configured `clarify_question_cap`. [E-85]

### CLARIFY-1.5
The memoization key incorporates `prompt_digest(cfg)` salt and extra probe/map terms when
probes are enabled, ensuring cache invalidation on prompt or map changes while maintaining
strict flag-off byte-identity. [E-85]

## Failure modes

- **Model failure or timeout in single mode**: Handled by bounded retry policy or surfaces as workflow failure.
- **Probe failure in fan-out mode**: Bounded retry; on exhaustion or timeout, the failing dimension is dropped from results without failing sibling probes or the overall stage.
- **Gate timeout**: When `ask_and_wait` reaches timeout, raises gate timeout error per workflow gate policy.
- **Unattended execution**: When gate policy is OFF, suggested answers are used to ensure the pipeline proceeds without blocking.
