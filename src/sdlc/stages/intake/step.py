"""Intake stage step execution (spec A §3.3).

Stage 0 intake verifies whether the repository tree exists, is accessible,
and satisfies the declared ProjectMode (greenfield vs brownfield).
Purely deterministic repository probing with no LLM proposer role.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from ...context.classify import classify
from ...core.context import StageContext
from ...core.models import IdeaBrief, PipelineConfig
from ...observability.trace import RunEventKind
from ..context.activities import RepoProbeInput, classify_repo

_INTAKE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=3),
)


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    repo_path: str | None = None,
) -> str | None:
    """Execute the intake stage.

    Returns None if the intake check passes, or a rejection string
    'rejected:intake (<reason>)' if validation fails.
    """
    ctx.stage("intake")
    target_repo = repo_path or idea.repo_url or "/var/sdlc/repo"
    observed = await workflow.execute_activity(
        classify_repo,
        RepoProbeInput(repo_dir=target_repo, base_branch=idea.base_branch),
        **_INTAKE_ACT,
    )
    verdict = classify(observed, idea.mode)
    if verdict.warning:
        ctx.emit(RunEventKind.STAGE_ENDED, stage="intake", warning=verdict.warning)
    if not verdict.ok:
        return f"rejected:intake ({verdict.reason})"
    return None
