"""DeploymentWorkflow (E-67) -- DAG stage 13's apply -> smoke -> rollback.

Deterministic by construction: no model call, no gate. It sequences four
activities and returns a DeployReport. The HITL `deploy_failed` gate lives in
FeatureWorkflow (D-6): a Temporal human-in-the-loop interaction targets a
workflow id, and operators know their run's id, not a child's.

This is also the seam E-70 attaches to: an ObservationWorkflow starts here
with ParentClosePolicy.ABANDON, so a multi-day observation window outlives
the feature run instead of pinning it open.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..deploy.activities import (
        DeployActivityInput,
        RollbackInput,
        SmokeCheckInput,
        deploy_apply,
        deploy_current_version,
        deploy_rollback,
        smoke_check,
    )
    from ..models import (
        DeployConfig,
        DeployPlan,
        DeployReport,
        SmokeCheckResult,
    )

# Read-only and idempotent -- retrying is free.
VERSION_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)
# Build failures are deterministic and will not improve; the second attempt
# exists for registry/network blips.
APPLY_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=1),
    heartbeat_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=2),
)
# ONE attempt on purpose: retrying a smoke check would mask the very reading
# being collected. Readiness polling is the activity's own job.
SMOKE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=15),
    heartbeat_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=1),
)
# The safety operation, retried hardest.
ROLLBACK_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=1),
    retry_policy=RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=2)),
)


class DeploymentInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    attempt: int = 1


def needs_rollback(results: list[SmokeCheckResult]) -> bool:
    """Any check that is not PASSED. `errored` counts -- 'we could not tell'
    is not permission to ship (D-3)."""
    return any(not r.passed for r in results)


@workflow.defn
class DeploymentWorkflow:
    @workflow.run
    async def run(self, inp: DeploymentInput) -> DeployReport:
        act_in = DeployActivityInput(plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path)

        # BEFORE anything changes, so a rollback target exists even if apply
        # blows up. None means first-ever deploy: nothing to restore.
        previous = (
            await workflow.execute_activity(deploy_current_version, act_in, **VERSION_ACT)
        ).version

        def _report(**over: Any) -> DeployReport:
            base = dict(
                deployed=False,
                environment=inp.plan.environment,
                version=inp.plan.version,
                adapter=inp.cfg.adapter,
                apply_detail=apply_detail,
            )
            base.update(over)
            return DeployReport.model_validate(base)

        async def _rollback(reason: str) -> DeployReport:
            if previous is None:
                # A first deploy that fails smoke leaves a broken service up.
                # Saying so beats pretending a rollback happened.
                return _report(
                    rolled_back=False,
                    rollback_reason=f"no previous version to restore; {reason}",
                    checks=checks,
                )
            if not inp.plan.rollback.auto:
                return _report(
                    rolled_back=False,
                    rollback_reason=f"auto-rollback disabled; {reason}",
                    checks=checks,
                )
            try:
                await workflow.execute_activity(
                    deploy_rollback,
                    RollbackInput(
                        plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path, to_version=previous
                    ),
                    **ROLLBACK_ACT,
                )
            except Exception as e:
                # The worst outcome in the system: the environment is now in
                # an unknown state. The parent turns this into deploy-broken:.
                return _report(
                    rolled_back=False,
                    rollback_reason=f"rollback exhausted: {e}; {reason}",
                    checks=checks,
                )
            return _report(
                rolled_back=True, rolled_back_to=previous, rollback_reason=reason, checks=checks
            )

        checks: list[SmokeCheckResult] = []
        apply_detail = ""

        try:
            applied = await workflow.execute_activity(deploy_apply, act_in, **APPLY_ACT)
        except Exception as e:
            # A partially-applied stack is exactly why rollback runs on apply
            # failure too, not only on smoke failure.
            return await _rollback(f"apply failed: {e}")

        apply_detail = applied.detail

        checks = (
            await workflow.execute_activity(
                smoke_check,
                SmokeCheckInput(
                    plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path, endpoint=applied.endpoint
                ),
                **SMOKE_ACT,
            )
        ).results

        if needs_rollback(checks):
            failed = ", ".join(f"{r.name}={r.state.value}" for r in checks if not r.passed)
            return await _rollback(f"smoke checks not passed: {failed}")

        return _report(deployed=True, endpoint=applied.endpoint, checks=checks)
