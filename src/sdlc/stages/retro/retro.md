# Retro Stage

The retro stage (Stage 14, E-32) fires on every terminal execution path of `FeatureWorkflow`.
It finalizes run observability, records the terminal stage outcome, updates episodic memory,
and exports all run artifacts and session logs for auditing and dashboards.

The caller (`FeatureWorkflow.run` / `_retro`) coordinates top-level workflow completion,
builds the `RunSummary` envelope from in-flight run trace events, and handles top-level return strings.
The retro stage owns emitting terminal lifecycle events, memory retention of the run summary,
nightly reflection triggers, artifact bundle export, and session retention policy enforcement.
Retro is strictly best-effort: failures within retro activities or retention operations are
trapped and never modify the final workflow outcome string.

## Requirements

### RETRO-1.1
The retro step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or calls a gate directly. [FR-101]

### RETRO-1.2
The retro step emits a `RUN_FINISHED` event recording the final run outcome, and when memory
is enabled, emits a `MEMORY_RETAINED` event for `run_summary`. [E-32]

### RETRO-1.3
When memory is enabled, the retro step retains the `RunSummary` via `ctx.retain` and triggers
episodic reflection for the project memory bank via the `reflect` activity. [E-32, E-13]

### RETRO-1.4
The retro step invokes `export_run_artifacts` and executes `apply_session_retention`, applying
retention rules (`keep_full_transcripts`) to preserve full transcripts on non-deployed runs,
runs with fix attempts, or benchmark executions. [E-32, E-38]

### RETRO-1.5
The slice exports `step` and `ACTIVITIES = []`. All retro operations execute under best-effort
guarantees: internal activity failures or exceptions are trapped so the run outcome is never changed. [E-32]

### RETRO-1.6
Retro scores the run's own SOFT auto-approvals. For every gate in `RunSummary.gates` with `policy == "soft"`, `decided_by == "policy"` and a non-`None` confidence, it computes a realized-outcome label from the run's retained signals — plan-drift ratio for the plan gate, capped fix-attempt ratio for the architecture gate, the judge score in preference to either when benchmarking — and appends `(gate, bucket_key, confidence, outcome_label)` to the calibration ledger. Best-effort like every other retro side effect: a ledger outage is swallowed and the run's outcome is unchanged (RETRO-1.4). Gates a human decided are not evidence, and neither are OFF-policy approvals, which carry `decided_by == "policy"` too. [C7]

## Failure modes

- **Memory backend down**: `reflect` or `retain` fails due to network or service unavailability; trapped so the workflow completes successfully.
- **Export directory write failure**: `export_run_artifacts` fails due to disk space or permission errors; trapped so the run return string is unchanged.
- **Retention activity failure**: `apply_session_retention` fails; trapped so the run outcome is preserved.
