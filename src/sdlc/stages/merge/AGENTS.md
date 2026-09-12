# AGENTS.md — merge

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: merge evaluates quality and safety gates on the integration worktree independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Absolute checks are non-overridable: on failure, the stage fails closed immediately. The floor is re-asserted on input inside `evaluate_quality_gate`, so a directly-constructed `CheckResult` cannot demote a floor check to advisory.
- A required check that never reaches the gate is a failing check, not a silent pass: `MERGE_REQUIRED_CHECKS` (`gate.py`) is the authoritative list, and absence synthesizes a failing `MISCONFIGURED` result at the manifest classification.
- Advisory checks may be overridden only by human approval via `ctx.gate("merge", ...)`.
- MergeVerdict is advisory and consulted ONLY under SOFT gate policy after the deterministic gate passes clean.
- The absolute checks judge the change: each is built from a scoped report (`ScopedTestReport`, `ScopedLintReport`, `ScopedSecurityReport`) measured between the pinned `base_sha` and the integration head, and passes only when that report is MEASURED with nothing introduced (MERGE-1.10).
- The slice exports `step`, `prompt_digest`, `merge_verdict_prompt`, and `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`.

## Temporal notes for this slice

- `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `gate`, `measurement`, `memory`, `pending`, `stages/qa/activities.py` (`run_lint`, `scoped_security_scan`), `stages/qa/models.py` (`ScopedSecurityReport`), `vcs` (`prepare_base_worktree`).
- The lazy `__init__` export keeps `sdlc.stages.merge` importable framework-free (agent loader imports models at boot without evaluating Temporal activity definitions).
- **Replay: diff-scoped gates (2026-09-11) is declared incompatible with in-flight runs — no `workflow.patched`.** The change replaced `security_scan` with `scoped_security_scan`, inserted `prepare_base_worktree`, and changed the `IntegrationChecks` payload. Before deploying a worker built from it, `temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='FeatureWorkflow' OR WorkflowType='TidyUpWorkflow')"` must print nothing; terminate or finish those runs first. Rationale: a patched branch would keep the retired whole-tree gate alive as a second code path, and could not protect the payload change anyway.

## State

- `StageContext` provides access to `gate`, `run_role`, `record`, `retain`, `emit`, `stage`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/merge/ -q
