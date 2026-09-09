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

### REVIEW-1.6
Every lens in `GATING_LENSES` (`src/sdlc/stages/review/lenses.py`) yields a typed `LensOutcome` recording what it did: `PRESENT` with the report's verdict, or one of three absent states — `DECLARED_ABSENT` (the operator disabled it), `NOT_REACHED` (enabled, but its run site was never reached on this task), `UNDECLARED_ABSENT` (enabled and reached, but no report came back). `LensOutcome`'s validator makes an absent-and-approved outcome unconstructible, and every absent state carries a reason. `classify_lens` is the single producer, pure and derived from the same facts the runner's own pre-check consults, so a tombstone cannot disagree with the predicate that gated the run. Fail-open at the task layer is preserved and now explicit: `primary_admits` and `backstop_admits` admit every absent state, so absence never blocks delivery — it is graded at the merge gate instead (MERGE-1.8). [C8]

## Failure modes

- **Primary review absent**: the primary returns `None` in exactly two cases — `PipelineConfig.review_enabled=False`, or no reviewer agent configured. An exception inside the primary is *not* caught and propagates. Either absence is recorded as a `LensOutcome` (REVIEW-1.6) rather than read as approval.
- **Adversary failure**: the adversary lens fails open: any exception logs a warning and returns `None`, which no longer reads as agreement — it is recorded as an `UNDECLARED_ABSENT` tombstone (REVIEW-1.6) that the merge gate grades.
- **Deep review failure**: The deep review lens is strictly advisory and fails open: any exception or transcript loading error logs a warning and returns `None`, never blocking delivery.
- **Unverified transcript accusation**: If deep review claims an integrity violation or plan deviation whose evidence quote is not found in the transcript bytes, the flag is dropped before reporting.
