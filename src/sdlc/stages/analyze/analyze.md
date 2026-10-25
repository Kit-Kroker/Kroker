# Analyze Stage

The analyze stage (Stage 9, FR-106) executes clean-context acceptance criterion to test
traceability verification on the integrated worktree before the merge gate.
A clean-context Analyst role inspects the full diff stat, patch, aggregate test outputs,
changed file inventories, test tree listings, per-task changed files,
and authoritative criteria from the plan to propose an `AnalysisReport`.

The workflow enforces traceability mechanically via `enforce_traces` (or `untraced_criteria`
on unpatched pre-017 runs). Under `017-analyze-evidence`, a criterion is traced through one of
four evidence forms: test name, file present in tree, file absent with containment, or task
changed no files. Command evidence is recorded but never satisfies a criterion. Inexpressible
criteria stay untraced. Untraced criteria become advisory findings at the merge gate and are
recorded in episodic memory as GOTCHAs.

## Requirements

### ANALYZE-1.1
The analyze step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or imports role definitions directly. [FR-101]

### ANALYZE-1.2
The analyze step executes the clean-context Analyst role against the integrated changes
and returns an `AnalyzeOutcome` artifact carrying the report and enforced untraced criteria. [FR-106, FR-001]

### ANALYZE-1.3
The analyze step records the stage benchmark outcome and retains a stage summary in episodic
memory. [FR-106, E-32]
Under `017-analyze-evidence`, the benchmark record carries `trace` (`TraceBag`). Every rejection
is on the record with its cause (round 012 §6.1, C-2): a failing record's `error` carries the number
of untraced criteria and the first three `task_id: criterion` labels (marked '(command only)' if
in the command bucket); a passing record's `error` is None.

### ANALYZE-1.4
When acceptance criteria are untraced, the analyze step retains a GOTCHA memory for the
untraced criteria in the project memory bank. [FR-106, E-13]

### ANALYZE-1.5
The slice exports `step` and `ACTIVITIES = [build_trace_inventory]`. [FR-106, FR-004]

## Failure modes

- **Analyst model unavailable / rate-limited**: Step raises, triggering standard retry policy or workflow failure.
- **Untraced criteria present**: Traced criteria check fails at merge gate, GOTCHA retained in memory.
- **Malformed diff / worktree access error**: Diff activity raises, caught by Temporal activity retry policy.
