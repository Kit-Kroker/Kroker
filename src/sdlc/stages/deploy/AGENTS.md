# AGENTS.md — deploy

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: deploy receives deploy_plan and executes deployment independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = [deploy_apply, deploy_rollback, smoke_check, deploy_current_version]`.
- Deploy execution is deterministic: child `DeploymentWorkflow` sequences apply -> smoke -> rollback.

## Temporal notes for this slice

- `ACTIVITIES = [deploy_apply, deploy_rollback, smoke_check, deploy_current_version]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `gate`, `pending`, `workflows/deployment.py`.
- Eager exports in `__init__.py` ensure worker boot registers activities and models without sandbox errors.

## State

- `StageContext` provides access to `gate`, `record`, `stage`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/deploy/ -q
