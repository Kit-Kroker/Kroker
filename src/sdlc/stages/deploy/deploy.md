# Deploy Stage

The deploy stage (Stage 13 / E-67 / FR-1104) manages deployment to target environments behind configurable gates and smoke verification checks. It consults the human deploy gate, delegates deterministic apply/smoke/rollback execution to `DeploymentWorkflow`, handles failed deployment retries via human-in-the-loop review, records benchmark records, and emits stage status transitions.

The orchestrator (`FeatureWorkflow`) delegates deployment to `deploy.step`.

## Requirements

### DEPLOY-1.1
The deploy stage slice exports `step`, `prompt_digest`, and `ACTIVITIES = [deploy_apply, deploy_rollback, smoke_check, deploy_current_version]`. The step takes `ctx: StageContext` as first argument, takes required configuration and plan as keyword arguments, and never receives the workflow instance directly. [E-67, FR-1104]

### DEPLOY-1.2
When the deploy gate is rejected or when `cfg.deploy.enabled` is False, deployment fails closed without executing the deployment child workflow. It records the gate decision, emits benchmark records with outcome PASS (if approved but disabled) or REVISED (if rejected), and returns `merged-not-deployed:{pr_url}`. [E-67, FR-1104]

### DEPLOY-1.3
On approval and with deployment enabled, the deploy stage invokes `DeploymentWorkflow` child workflow. When smoke checks pass and `report.deployed` is True, it records benchmark outcome PASS, reports stage transition `("deployed", "deploy")`, and returns `deployed:{pr_url}`. [E-67, FR-1104]

### DEPLOY-1.4
When deployment or smoke checks fail, the deploy stage opens the `deploy_failed` human gate with rollback reasons and execution details. If the human gate decision is REVISE, it retries up to `cfg.max_gate_rounds`. If rollback succeeded, it records benchmark outcome FAIL, and returns `rolled-back:{pr_url}`. [E-67, FR-1104]

### DEPLOY-1.5
If a deployment fails and rollback cannot be completed (or auto-rollback was disabled), the environment remains in an unknown state. The deploy stage records benchmark outcome FAIL, emits stage transition `("deploy_failed", "deploy")`, and returns `deploy-broken:{pr_url}` so operators are alerted immediately. [E-67, FR-1104]

## Failure modes

- **Deploy gate rejection**: The operator rejects the deploy gate; changes remain merged but un-deployed.
- **Smoke verification failure with rollback**: Post-deployment smoke checks fail; stack automatically rolls back to prior version.
- **Rollback failure / broken deploy**: Post-deployment failure where rollback fails or has no prior target; leaves system in broken state requiring manual intervention.
