"""The requirements stage step (FR-113, plan Task 8): draft activity ->
workflow-side freeze -> priced usage -> events -> retain.

The step runs INSIDE the workflow (the graph handler in
workflows/graph_nodes/precode.py); the only model call crosses the
draft_requirements activity boundary (stage.py). Everything else is
deterministic workflow code: freeze() is a pure function that assigns the
ids and the digest here — never activity-side — and dollars are a
price_usage activity lookup exactly as constitution's drafting spends are
priced (pricing must stay replay-safe and must never fail a stage).

The stage holds NO gate: partial freeze means the opt-in flag can never
kill a run, so a degraded requirements draft fails soft into the empty
artifact (the constitution ruling, re-applied).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ...agents.roles import resolve_role_model
    from ...benchmarks.models import BenchmarkOutcome
    from ...core.context import StageContext
    from ...core.models import (
        IdeaBrief,
        PipelineConfig,
        ProjectMode,
        RoleUsage,
    )
    from ...memory.models import MemoryKind
    from ...observability.trace import RunEventKind
    from ...pricing import PriceUsageInput, price_usage
    from .deps import RequirementsDeps
    from .models import Requirements
    from .stage import DraftInput, draft_requirements
    from .verify import FreezeMode, freeze

DRAFT_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)

PRICE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=2)
)


def _workflow_id() -> str:
    try:
        return workflow.info().workflow_id
    except Exception:
        return ""


async def _price(ctx: StageContext, usage: RoleUsage) -> float | None:
    """Price one activity-returned RoleUsage (constitution's _price shape):
    the MODEL_USAGE event is how activity-side spend reaches the run's
    tracking — the run summary rolls roles up from these events. A
    zero-token usage (a run refused before its first request) prices
    nothing and emits nothing."""
    if not (usage.input_tokens or usage.output_tokens):
        return None
    try:
        usd = await workflow.execute_activity(
            price_usage,
            PriceUsageInput(
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
            ),
            **PRICE_ACT,
        )
    except Exception:
        usd = None
    ctx.emit(
        RunEventKind.MODEL_USAGE,
        stage="requirements",
        role=usage.role,
        model=usage.model,
        calls=str(usage.calls),
        input_tokens=str(usage.input_tokens),
        output_tokens=str(usage.output_tokens),
        cache_read_tokens=str(usage.cache_read_tokens),
        cache_write_tokens=str(usage.cache_write_tokens),
        **({"cost_usd": str(usd)} if usd is not None else {}),
    )
    return usd


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    repo_path: str | None,
) -> Requirements:
    """Run the requirements stage.

    Flag off → the empty artifact with ZERO activities scheduled: the `""`
    digest sentinel keys and prompts downstream exactly as no requirements
    stage at all (FR-010 byte-identity — the default graph replays
    unchanged). Flag on → one draft activity → pure freeze → priced usage
    → STAGE_ENDED (a warning when freeze dropped items or capped the
    stories, a FAIL outcome when nothing survived) → retain. The draft
    activity re-resolves the registry agent itself; the step hands it only
    the run's particulars.
    """
    if not cfg.requirements_enabled:
        return Requirements(drafted_by="empty", stories=[], digest="")

    ctx.stage("drafting", "requirements")
    # A StrEnum member is not a Literal to mypy; the explicit pair IS the
    # freeze contract (constitution's ruling e, re-applied): deps.mode is
    # exactly greenfield|brownfield. The activity's own workspace branch
    # stays the one source of truth for what the drafter can READ.
    mode: FreezeMode = "brownfield" if idea.mode is ProjectMode.BROWNFIELD else "greenfield"
    inp = DraftInput(
        idea_json=idea.model_dump_json(),
        repo_path=repo_path,
        deps=RequirementsDeps(
            run_id=_workflow_id(),
            mode=mode,
            max_stories=cfg.requirements.max_stories,
            max_requests=cfg.requirements.max_requests,
        ),
        model=resolve_role_model(cfg, "requirements"),
    )
    result = await workflow.execute_activity(draft_requirements, inp, **DRAFT_ACT)

    # Pure workflow code: ids and digest are assigned here, never by the
    # model. The freeze mode consumed is the deps' own (ruling e) — the same
    # mode the drafter's input carried, whatever the workspace branch did.
    frozen = freeze(result.draft, mode=inp.deps.mode, max_stories=cfg.requirements.max_stories)
    req = frozen.frozen
    usd = await _price(ctx, result.usage)

    data: dict[str, str] = {
        "role": "product",
        "outcome": (
            BenchmarkOutcome.FAIL.value if frozen.degraded else BenchmarkOutcome.PASS.value
        ),
    }
    if usd is not None:
        data["cost_usd"] = str(usd)
    if frozen.degraded:
        data["warning"] = "no story survived freeze"
    else:
        notes: list[str] = []
        if frozen.dropped:
            notes.append(
                f"dropped {len(frozen.dropped)} of {len(result.draft.stories)} drafted items"
            )
        if frozen.capped:
            notes.append(f"capped to {cfg.requirements.max_stories} stories")
        if notes:
            data["warning"] = "; ".join(notes) + " at freeze"
    ctx.emit(RunEventKind.STAGE_ENDED, stage="requirements", **data)

    if not frozen.degraded:
        text = "requirements: " + "; ".join(f"{s.id} {s.narrative}" for s in req.stories)
        await ctx.retain(
            cfg,
            MemoryKind.STAGE_SUMMARY,
            cfg.memory.project_bank,
            text=text,
            metadata={"stage": "requirements", "digest": req.digest, "run_id": inp.deps.run_id},
        )
    return req
