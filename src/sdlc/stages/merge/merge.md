# Merge Stage

The merge stage evaluates quality and safety gates (Stage 10 / SC-5) before integrating changes into the codebase or opening pull requests. It runs integration checks against the merged integration worktree (ADR-14), evaluates the deterministic quality gate, escalates advisory checks or soft-policy verdicts to human review, records benchmark records and gate feedback memory, and opens a pull request.

The orchestrator (`FeatureWorkflow._build_and_merge`) delegates to `merge.step`.

## Requirements

### MERGE-1.1
The merge stage slice exports `step`, `prompt_digest`, `merge_verdict_prompt`, and `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`. The step takes `ctx: StageContext` as first argument, takes required collaborators as keyword arguments, and never receives the workflow instance directly. [SC-5, E-30, FR-106, FR-108]

### MERGE-1.2
On any absolute gate failure (`build_integration_green`, `lint_clean`, `security_scan_collected`, `security_no_critical`), the merge stage fails closed immediately with `rejected:merge:absolute-gate-failed:...`, retains gate feedback memory, records a failing benchmark record, and terminates without offering human override or consulting MergeVerdict. [SC-5, FR-915]
An absolute check that is *absent* from the gate input is an absolute failure by this same route — see MERGE-1.6.

### MERGE-1.3
On advisory gate failures (`review_severity`, `review_lenses_present`, `traceability`, `coverage`, `plan_drift`), the merge stage presents the blocking advisory checks to the human merge gate. If rejected, it terminates with `rejected:merge:advisory`. If approved, audited `GateOverride`s are recorded, the gate is re-evaluated, and a revised benchmark record is recorded. [SC-5, FR-204, FR-106]
An advisory check that is *absent* from the gate input is an advisory failure by this same route, and reaches the human gate carrying its `MISCONFIGURED` detail — see MERGE-1.6.

### MERGE-1.4
Under `GatePolicy.SOFT`, after the DeterministicQualityGate passes clean, the advisory `MergeVerdict` proposer role is consulted via `ctx.run_role`. If the verdict rejects or confidence is below threshold, it escalates to the human gate; rejection terminates with `rejected:merge:soft-verdict`. [Finding #5, FR-301]

### MERGE-1.5
On passing the quality gate and human/soft-policy checks, the merge stage records benchmark records and memory, opens a pull request on the repository (or returns `skipped:benchmark-run-has-no-remote` for benchmark repos), and returns the PR URL. [SC-5, ADR-14]

### MERGE-1.6
The deterministic gate fails closed on a required check it never received. `MERGE_REQUIRED_CHECKS` (`src/sdlc/gate.py`) is the authoritative list of the checks the merge gate must see. Every manifest name absent from the evaluated input is synthesized as a **failing** `CheckResult` at its manifest classification, carrying `MISCONFIGURED: required check '<name>' absent from gate input` as its detail, and is echoed in `GateReport.checks`. An absent absolute check is an absolute failure, handled per MERGE-1.2; an absent advisory check is an advisory failure, handled — including its audited override path — per MERGE-1.3. Separately, a check whose name is in `ABSOLUTE_FLOOR` is re-asserted as ABSOLUTE on input, so a directly-constructed `CheckResult` cannot be demoted to advisory and waived by one override. [SC-5, FR-915]

### MERGE-1.7
`plan_drift` (E4) is a required advisory check, evaluated across every task in `task_results` unconditionally — a quarantined task's drift counts the same as a done task's, matching MERGE-1.3's existing treatment of `review_severity`. A task's `PlanDrift` is read from `TaskResult.plan_drift`, computed once in the code stage from `compute_plan_drift` (`src/sdlc/stages/plan/models.py`) and carried through unchanged. Per task, drift trips the check only when `touched_unhinted` (files touched but not hinted in the plan) has at least 2 entries, or is at least half of `files_touched`; `hinted_untouched` (over-hinting) never trips it, and a task with one or zero files touched is exempt. `plan_drift is None` (an empty `files_hint` or an empty diff — "not measured") never trips the check. The check fails if **any** task in the run trips it — the aggregation is not an average, so many tasks each drifting a little cannot outweigh one task drifting past the threshold on its own. Like every other advisory check, a `plan_drift` failure is waivable only through the audited `GateOverride` path (MERGE-1.3); the override's `reason` is the record of why the drift was acceptable — there is no separate plan-amendment artifact, and `DevTask.files_hint` is never mutated by this check. [E4]

### MERGE-1.8
`review_lenses_present` (C8) is a required advisory check over `GATING_LENSES` (`src/sdlc/stages/review/lenses.py`), evaluated across every task in `task_results` unconditionally — a quarantined task's lens coverage counts the same as a done task's, matching MERGE-1.3's existing treatment of `review_severity`. Each task's `LensOutcome` list is read from `TaskResult.lens_outcomes`, classified once in the code stage and carried through unchanged. "Required" here means *the check must be produced*, not *every lens must have run*: the check **fails** when a lens in the manifest has no outcome recorded at all, or an outcome whose presence is `UNDECLARED_ABSENT` (the lens was enabled, its run site was reached, and no report came back). `DECLARED_ABSENT` (operator disabled it) and `NOT_REACHED` (the run site was never reached on this task) **pass**, and every presence state is named in the check detail regardless — absence is honoured, never silent. The check fails if **any** task in the run trips it. Like every other advisory check, a failure is waivable only through the audited `GateOverride` path (MERGE-1.3). Separately, `review_severity` grades only `PRESENT` reviewer lenses, through the same `primary_admits` predicate the task success condition uses, so the two layers cannot diverge on what "approved" means. [C8]

## Failure modes

- **Absolute gate failure**: Failing integration tests, lint failure, uncollected security scan, or critical security vulnerabilities terminate execution immediately without override.
- **Advisory gate rejection**: Failing review approval, untraced criteria, below-threshold diff coverage, or unacknowledged plan drift rejected by the human reviewer.
- **Soft verdict rejection**: LLM merge verdict rejection or sub-threshold confidence rejected upon escalation to the human reviewer.
- **Missing required check**: a name in `MERGE_REQUIRED_CHECKS` that never reached the gate is synthesized as a failing `MISCONFIGURED` check at its manifest classification — terminal if absolute, human-waivable if advisory (MERGE-1.6).
- **Lens never ran**: a gating lens with no recorded outcome, or one that was enabled and reached but returned nothing, fails `review_lenses_present` — human-waivable through the audited override path (MERGE-1.8).
