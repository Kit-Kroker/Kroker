"""Clarify stage step execution (spec A §3.3).

Executes the clarify stage: recalls prior memories, runs either single or fan-out
clarify proposer role with memoization caching, resolves open questions via human
signals (or suggested defaults when gate policy is OFF), judges and records the
outcome, and returns the ClarifiedRequirements artifact.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from temporalio import workflow

from ...benchmarks.models import BenchmarkOutcome
from ...benchmarks.record_builder import stage_record
from ...context.models import CodebaseMap
from ...context.render import render_for_prompt
from ...core.context import StageContext
from ...core.models import (
    ClarificationDimension,
    GateConfig,
    GatePolicy,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleUsage,
)
from ...observability.trace import RunEventKind
from .merge import merge_clarification
from .models import ClarifiedRequirements, ProbeResult
from .prompts import (
    _clarify_memo_extra,
    clarify_prompt,
    probe_prompt,
    prompt_digest,
)
from .routing import grounded_dimensions, live_dimensions


def _probe_results_from(
    dimensions: Sequence[ClarificationDimension],
    results: Sequence[ProbeResult | BaseException],
) -> list[ProbeResult]:
    """Pair each probed dimension with its result, discarding the dead ones.

    An exception means the probe never produced an answer, so the dimension
    is ABSENT from the output -- and therefore absent from dimensions_probed,
    which is what distinguishes "never ran" from "ran and abstained".

    The asked-for dimension overrides whatever the model reported: the burst
    knows which probe it dispatched, and a mislabelled result would attribute
    questions to a dimension that never ran.
    """
    out: list[ProbeResult] = []
    for dim, res in zip(dimensions, results, strict=False):
        if isinstance(res, BaseException):
            continue
        out.append(res if res.dimension is dim else res.model_copy(update={"dimension": dim}))
    return out


async def _clarify_fanout(
    run_role: Any,
    *,
    route_agent: Any,
    probe_agent: Any,
    route_prompt: str,
    idea_json: str,
    grounding: str,
    mode: ProjectMode,
    cap: int,
) -> ClarifiedRequirements:
    """The E-85 clarify orchestration: route, fan out, merge."""
    route = (await run_role(route_agent, route_prompt)).output
    dims = live_dimensions(route.live_dimensions, mode)
    reqs_json = route.model_dump_json()

    async def _probe(d: ClarificationDimension) -> Any:
        return (
            await run_role(
                probe_agent,
                probe_prompt(
                    d, idea_json=idea_json, requirements_json=reqs_json, grounding=grounding
                ),
            )
        ).output

    # return_exceptions=True IS the degrade-alone rule here: a probe that
    # times out, loses its worker or exhausts its bounded retries raises
    # inside its own coroutine and gather captures it, leaving every sibling's
    # result intact. _probe_results_from turns each captured exception into
    # a dropped dimension.
    results = await asyncio.gather(*[_probe(d) for d in dims], return_exceptions=True)
    return merge_clarification(
        route, _probe_results_from(dims, results), cap=cap, grounded=grounded_dimensions(mode)
    )


def _now() -> datetime:
    try:
        return workflow.now()
    except Exception:
        return datetime.now(UTC)


async def step(
    ctx: StageContext,
    *,
    cfg: PipelineConfig,
    idea: IdeaBrief,
    codebase_map: CodebaseMap | None = None,
    brief_digest: str = "",
    clarify_agent: Any,
    route_agent: Any,
    probe_agent: Any,
    clarify_model: str = "",
) -> ClarifiedRequirements:
    ctx.stage("clarifying", "clarify")
    _started = _now()
    snapshot = await ctx.recall(
        cfg,
        cfg.memory.project_bank,
        query=f"clarify:{idea.title}",
        filters={"stage": "clarify"},
    )

    if not clarify_model:
        rc = cfg.roles.get("clarify")
        if rc is not None and rc.model is not None:
            clarify_model = rc.model
        elif hasattr(clarify_agent, "model"):
            m = clarify_agent.model
            clarify_model = getattr(m, "model_name", None) or getattr(m, "name", None) or str(m)
        else:
            clarify_model = "unknown"

    clarify_spend = RoleUsage(role="clarify", model=clarify_model)

    async def _run_clarify_single() -> ClarifiedRequirements:
        """Pre-E-85 path: one call, one prompt. Byte-identical to before."""
        return (
            await ctx.run_role(
                cfg,
                "clarify",
                clarify_model,
                clarify_agent,
                clarify_prompt(idea.model_dump_json(), snapshot.items),
                into=clarify_spend,
            )
        ).output

    async def _run_clarify_fanout() -> ClarifiedRequirements:
        """E-85: supervisor routes and asks C1/C2, probes fan out per
        dimension, pure merge ranks and caps."""

        async def _egress(agent: Any, prompt: str) -> Any:
            return await ctx.run_role(
                cfg,
                "clarify",
                clarify_model,
                agent,
                prompt,
                into=clarify_spend,
            )

        return await _clarify_fanout(
            _egress,
            route_agent=route_agent,
            probe_agent=probe_agent,
            route_prompt=clarify_prompt(idea.model_dump_json(), snapshot.items),
            idea_json=idea.model_dump_json(),
            grounding=(render_for_prompt(codebase_map) if codebase_map is not None else ""),
            mode=idea.mode,
            cap=cfg.clarify_question_cap,
        )

    _clarify_key_extra = _clarify_memo_extra(cfg, codebase_map)
    _salt = prompt_digest(cfg)

    reqs, _ = await ctx.cached_stage(
        cfg,
        "clarify",
        idea.model_dump_json() + brief_digest + _clarify_key_extra,
        ClarifiedRequirements,
        _run_clarify_fanout if cfg.clarify_probes_enabled else _run_clarify_single,
        prompt_digest=_salt,
    )

    if reqs.open_questions:
        clarify_policy = cfg.gates.get("clarify", GateConfig()).policy
        if clarify_policy == GatePolicy.OFF:
            for q in reqs.open_questions:
                ctx.emit(
                    RunEventKind.CLARIFICATION_ASKED,
                    stage="clarify",
                    question_id=q.id,
                    question=q.question,
                    dimension=q.dimension.value if q.dimension else "",
                )
            for q in reqs.open_questions:
                q.answer = q.suggested_answer
            for q in reqs.open_questions:
                answered = "suggested" if q.answer is not None else "unanswered"
                ctx.emit(
                    RunEventKind.CLARIFICATION_ANSWERED,
                    stage="clarify",
                    question_id=q.id,
                    answered_by=answered,
                )
        else:
            answers = await ctx.ask_and_wait(
                reqs.open_questions,
                stage="clarify",
                timeout_hours=cfg.gate_timeout_hours,
            )
            for q in reqs.open_questions:
                q.answer = answers.get(q.id)

    _ended = _now()
    _quality = await ctx.judge(
        cfg,
        reqs.model_dump_json(),
        "clarifier",
        author_model=clarify_model,
    )
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="clarify",
            role="clarify",
            started=_started,
            ended=_ended,
            quality_score=_quality.score,
            judge=_quality.judge,
            outcome=BenchmarkOutcome.PASS,
            model=clarify_model,
            spend=clarify_spend,
        ),
    )

    # Note: _board_publish and retain run in _pipeline after return because
    # _board_publish sits between record and retain in the replay invariant sequence.
    return reqs
