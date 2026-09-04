# Analyze Stage

The analyze stage (Stage 9, FR-106) executes clean-context acceptance criterion to test
traceability verification on the integrated worktree before the merge gate.
A clean-context Analyst role inspects the full diff stat, patch, aggregate test outputs,
and authoritative criteria from the plan to propose an `AnalysisReport`.

The workflow enforces traceability mechanically: an acceptance criterion is traced iff
the report maps it to at least one test. Untraced criteria become advisory findings
at the merge gate and are recorded in episodic memory as GOTCHAs.

## Requirements

### ANALYZE-1.1
The analyze step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or imports role definitions directly. [FR-101]

### ANALYZE-1.2
The analyze step executes the clean-context Analyst role against the integrated changes
and returns an `AnalysisReport` artifact. [FR-106]

### ANALYZE-1.3
The analyze step records the stage benchmark outcome and retains a stage summary in episodic
memory. [FR-106, E-32]

### ANALYZE-1.4
When acceptance criteria are untraced, the analyze step retains a GOTCHA memory for the
untraced criteria in the project memory bank. [FR-106, E-13]

### ANALYZE-1.5
The slice exports `step` and `ACTIVITIES = []`. [FR-106]

## Failure modes

- **Analyst model unavailable / rate-limited**: Step raises, triggering standard retry policy or workflow failure.
- **Untraced criteria present**: Traced criteria check fails at merge gate, GOTCHA retained in memory.
- **Malformed diff / worktree access error**: Diff activity raises, caught by Temporal activity retry policy.
