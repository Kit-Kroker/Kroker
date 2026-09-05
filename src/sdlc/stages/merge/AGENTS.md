# AGENTS.md — merge

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: merge evaluates quality and safety gates on the integration worktree independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Absolute checks are non-overridable: on failure, the stage fails closed immediately.
- Advisory checks may be overridden only by human approval via `ctx.gate("merge", ...)`.
- MergeVerdict is advisory and consulted ONLY under SOFT gate policy after the deterministic gate passes clean.
- The slice exports `step`, `prompt_digest`, `merge_verdict_prompt`, and `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`.

## Temporal notes for this slice

- `ACTIVITIES = [measure_coverage, run_integration_checks, open_pull_request, evaluate_gate]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `gate`, `measurement`, `memory`, `pending`, `stages/qa/activities.py` (`run_lint`, `security_scan`), `stages/qa/models.py` (`SecurityReport`).
- The lazy `__init__` export keeps `sdlc.stages.merge` importable framework-free (agent loader imports models at boot without evaluating Temporal activity definitions).

## State

- `StageContext` provides access to `gate`, `run_role`, `record`, `retain`, `emit`, `stage`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/merge/ -q
