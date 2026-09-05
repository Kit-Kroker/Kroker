"""The deploy stage slice."""

from __future__ import annotations

from .activities import (
    ACTIVITIES,
    ApplyResult,
    CurrentVersionResult,
    DeployActivityInput,
    RollbackInput,
    SmokeCheckInput,
    SmokeCheckOutput,
    deploy_apply,
    deploy_current_version,
    deploy_rollback,
    smoke_check,
)
from .models import (
    DeploymentResult,
    DeployPlan,
    DeployReport,
    FeatureFlag,
    RollbackPolicy,
    SmokeCheck,
    SmokeCheckResult,
    SmokeState,
)
from .prompts import prompt_digest
from .step import (
    _deploy_plan,
    _deploy_result,
    _deploy_verdict,
    _execute_deployment_workflow,
    _sanitize_tag,
    step,
)

__all__ = [
    "ACTIVITIES",
    "ApplyResult",
    "CurrentVersionResult",
    "DeployActivityInput",
    "DeployPlan",
    "DeployReport",
    "DeploymentResult",
    "FeatureFlag",
    "RollbackInput",
    "RollbackPolicy",
    "SmokeCheck",
    "SmokeCheckInput",
    "SmokeCheckOutput",
    "SmokeCheckResult",
    "SmokeState",
    "_deploy_plan",
    "_deploy_result",
    "_deploy_verdict",
    "_execute_deployment_workflow",
    "_sanitize_tag",
    "deploy_apply",
    "deploy_current_version",
    "deploy_rollback",
    "prompt_digest",
    "smoke_check",
    "step",
]
