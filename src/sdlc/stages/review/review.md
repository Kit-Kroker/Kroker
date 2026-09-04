# Review Stage

The review stage provides clean-context code inspection and validation against frozen contracts.
It runs the primary reviewer proposer role, generating findings and pass/fail verdicts over the
materialized task diff without access to implementer conversational history or worker harness sessions.
It also provides two review lenses: the adversary lens (a decorrelated second opinion on the approving path)
and the deep review lens (an advisory transcript inspection checking for anti-cheat integrity flags and plan deviations).

The caller (`TaskHost._dev_task`) coordinates the fix loop, orchestrates QA and code attempt execution,
and records benchmark cause rows. The stage owns prompt assembly for clean-context review, execution of reviewer
and adversary roles, transcript verification of deep-review integrity flags, and fail-open execution for lenses.

## Requirements

### REVIEW-1.1
The review step receives a `StageContext` protocol and required collaborators as keyword arguments,
and never receives the workflow instance directly or calls a gate directly. [FR-804]

### REVIEW-1.2
Primary review executes clean-context validation of the task diff against frozen contract assertions
and deterministic test results without access to narrative history or harness sessions. [FR-204]

### REVIEW-1.3
The adversary lens provides a decorrelated second opinion on the approving path, operating fail-open
to ensure safety checks never fail task delivery. [Spec 3.2]

### REVIEW-1.4
The deep review lens inspects the scrubbed session transcript for integrity flags and plan deviations,
verifying accusations against transcript evidence and failing open on error. [E-39, E-43]

### REVIEW-1.5
The slice exports `step`, `run_adversary`, `run_deep_review`, and `ACTIVITIES = []`. [FR-106]

## Failure modes

- **Model call failure in primary review**: If review fails or is disabled via `PipelineConfig.review_enabled=False`, returns `None`, allowing task flow to proceed according to configuration.
- **Adversary failure**: The adversary lens fails open: any exception logs a warning and returns `None`, which the orchestrator treats as agreement.
- **Deep review failure**: The deep review lens is strictly advisory and fails open: any exception or transcript loading error logs a warning and returns `None`, never blocking delivery.
- **Unverified transcript accusation**: If deep review claims an integrity violation or plan deviation whose evidence quote is not found in the transcript bytes, the flag is dropped before reporting.
