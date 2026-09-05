# Merge Stage

The merge stage evaluates quality and safety gates (Stage 10 / SC-5) before integrating changes into the codebase or opening pull requests. It runs integration checks against the merged integration worktree (ADR-14), evaluates the deterministic quality gate, escalates advisory checks or soft-policy verdicts to human review, records benchmark records and gate feedback memory, and opens a pull request.

The orchestrator (`FeatureWorkflow._build_and_merge`) delegates to `merge.step`.

## Requirements

### MERGE-1.1
The merge stage slice exports `step`, `prompt_digest`, `merge_verdict_prompt`, and `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`. The step takes `ctx: StageContext` as first argument, takes required collaborators as keyword arguments, and never receives the workflow instance directly. [SC-5, E-30, FR-106, FR-108]

### MERGE-1.2
On any absolute gate failure (`build_integration_green`, `lint_clean`, `security_scan_collected`, `security_no_critical`), the merge stage fails closed immediately with `rejected:merge:absolute-gate-failed:...`, retains gate feedback memory, records a failing benchmark record, and terminates without offering human override or consulting MergeVerdict. [SC-5, FR-915]

### MERGE-1.3
On advisory gate failures (`review_severity`, `traceability`, `coverage`), the merge stage presents the blocking advisory checks to the human merge gate. If rejected, it terminates with `rejected:merge:advisory`. If approved, audited `GateOverride`s are recorded, the gate is re-evaluated, and a revised benchmark record is recorded. [SC-5, FR-204, FR-106]

### MERGE-1.4
Under `GatePolicy.SOFT`, after the DeterministicQualityGate passes clean, the advisory `MergeVerdict` proposer role is consulted via `ctx.run_role`. If the verdict rejects or confidence is below threshold, it escalates to the human gate; rejection terminates with `rejected:merge:soft-verdict`. [Finding #5, FR-301]

### MERGE-1.5
On passing the quality gate and human/soft-policy checks, the merge stage records benchmark records and memory, opens a pull request on the repository (or returns `skipped:benchmark-run-has-no-remote` for benchmark repos), and returns the PR URL. [SC-5, ADR-14]

## Failure modes

- **Absolute gate failure**: Failing integration tests, lint failure, uncollected security scan, or critical security vulnerabilities terminate execution immediately without override.
- **Advisory gate rejection**: Failing review approval, untraced criteria, or below-threshold diff coverage rejected by the human reviewer.
- **Soft verdict rejection**: LLM merge verdict rejection or sub-threshold confidence rejected upon escalation to the human reviewer.
