# Research Stage

The research stage (Stage 0, FR-107) executes an optional, fan-out web/corpus investigation
to inform requirements clarification and downstream pipeline stages.
The stage decomposes the idea into parallel sub-questions (`plan_research`), investigates each
independently (`research_subquestion`), synthesizes a `ResearchBrief` (`synthesize_brief`),
and verifies grounding of quotes against fetched pages (`verify_brief_activity`).

A human gate (`GateConfig`) permits approval, rejection, or refinement rounds.
Verified grounded findings are retained in episodic memory as leads for future runs.
Grounding failures degrade the research stage rather than aborting the pipeline.

## Requirements

### RESEARCH-1.1
The research step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance directly or imports role definitions directly. [FR-101]

### RESEARCH-1.2
The research step executes the fan-out research process (`plan_research`, parallel
`research_subquestion`, `synthesize_brief`) and produces a `ResearchBrief`. [FR-107]

### RESEARCH-1.3
The research step verifies grounding via `verify_brief_activity`, recording a benchmark
failure on ungrounded findings while degrading the stage rather than failing the workflow. [FR-107, E-32]

### RESEARCH-1.4
When the brief is grounded, the research step handles the human research gate and refine
rounds via `ctx.gate("research", ...)`, retains verified findings to memory, and records a benchmark pass. [FR-107, E-13]

### RESEARCH-1.5
The slice exports `step` and `ACTIVITIES = [plan_research, research_subquestion, synthesize_brief, verify_brief_activity]`. [FR-107]

## Failure modes

- **Model call failure / usage limit**: Degrades the stage to a degraded brief with recorded gap, proceeds to clarification.
- **Grounding violation**: Quote not found in fetched bytes; stage marked failed, brief digest cleared, pipeline continues ungrounded.
- **Human rejection at gate**: Step signals rejection (`"rejected:research"`), stopping the pipeline.
