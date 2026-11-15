"""Clarify stage step execution (spec A §3.3).

Executes the clarify stage: recalls prior memories, runs either single or fan-out
clarify proposer role with memoization caching, resolves open questions via human
signals (or suggested defaults when gate policy is OFF), judges and records the
outcome, and returns the ClarifiedRequirements artifact.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

# This module executes inside the workflow sandbox (feature.py's
# pipeline calls clarify.step) and shares model classes with it — without
# the marker the sandbox re-imports them isolated, duplicating classes
# pydantic then rejects (first post-B0 brownfield run, DS12).
with workflow.unsafe.imports_passed_through():
    from ...agents.loader import model_id
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
    from ...validators import path_like_tokens
    from ...validators.activities import paths_exist
    from ..constitution.models import Constitution
    from ..constitution.prompts import render_constitution
    from ..requirements.models import Requirements
    from ..requirements.prompts import render_requirements
    from .merge import merge_clarification
    from .models import ClarifiedRequirements, ProbeResult
    from .prompts import (
        _clarify_memo_extra,
        clarify_prompt,
        probe_prompt,
        prompt_digest,
    )
    from .routing import grounded_dimensions, live_dimensions


# 023/FR-205: a wire name recorded in histories -- never renamed after deploy.
CLARIFY_EVIDENCE_PATCH = "023-clarify-evidence-paths"


def _evidence_paths_enabled() -> bool:
    """Whether the brownfield evidence-path check may run.

    The inverse of plan's `_DRIFT_V2` on purpose: OUTSIDE a workflow it is
    False, because the check's only action is a real activity call and a
    unit test must never schedule one (017's helper returns True there
    because its check is pure). Inside a workflow the patch id decides:
    histories recorded before 023 replay with the check off.
    """
    if not workflow.in_workflow():
        return False
    return workflow.patched(CLARIFY_EVIDENCE_PATCH)


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
    repo_path: str | None = None,
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
    probes = _probe_results_from(dims, results)

    # 023/FR-205: a grounded question must cite something checkable. When the
    # patch is on, the project is brownfield and there is a repo, collect the
    # path-like tokens every question's evidence cites (route + probes) and
    # settle them against the repo in ONE batched read. Zero tokens -> zero
    # new commands; every skipped gate condition leaves missing_paths empty,
    # so merge behaves byte-identically to the pre-023 fan-out. The sorted
    # token list pins the command's input, so a replay re-issues the
    # identical call and the recorded result replays unchanged.
    missing_paths: frozenset[str] = frozenset()
    if _evidence_paths_enabled() and mode is ProjectMode.BROWNFIELD and repo_path:
        tokens: set[str] = set()
        for q in route.questions:
            tokens.update(path_like_tokens(q.evidence or ""))
        for probe in probes:
            for q in probe.questions:
                tokens.update(path_like_tokens(q.evidence or ""))
        if tokens:
            exists = await workflow.execute_activity(
                paths_exist,
                args=[repo_path, sorted(tokens)],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            missing_paths = frozenset(p for p, ok in exists.items() if not ok)

    return merge_clarification(
        route, probes, cap=cap, grounded=grounded_dimensions(mode), missing_paths=missing_paths
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
    constitution_digest: str = "",
    constitution: Constitution | None = None,
    requirements: Requirements | None = None,
    requirements_digest: str = "",
    clarify_agent: Any,
    route_agent: Any,
    probe_agent: Any,
    clarify_model: str = "",
    repo_path: str | None = None,
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
            # 003/FR-014: a plain agent keeps the registry's provider-prefixed
            # model STRING; the pre-migration wrapper exposed the CONCRETE
            # model's provider-stripped name. Normalize the string so
            # price_usage inputs and spend records stay byte-identical (T046).
            clarify_model = (
                getattr(m, "model_name", None)
                or getattr(m, "name", None)
                or (model_id(m) if isinstance(m, str) else None)
                or "unknown"
            )
        else:
            clarify_model = "unknown"

    clarify_spend = RoleUsage(role="clarify", model=clarify_model)

    # FR-112: the bounded constitution block ("" when there is no
    # constitution — flag off or nothing survived freeze), so default-path
    # prompts stay byte-identical (FR-010).
    _constitution_block = render_constitution(constitution) if constitution is not None else ""

    # FR-113: the bounded requirements block, same rule. It renders after
    # the constitution block and before the map/recall — the spec
    # hierarchy idea -> constitution -> requirements -> codebase map ->
    # recall. The blocks compose with one blank line between whichever
    # are present; at the defaults the composition is "" and prompts stay
    # byte-identical (FR-010).
    _requirements_block = render_requirements(requirements) if requirements is not None else ""
    _blocks = "\n\n".join(b for b in (_constitution_block, _requirements_block) if b)

    async def _run_clarify_single() -> ClarifiedRequirements:
        """Pre-E-85 path: one call, one prompt. Byte-identical to before."""
        return (
            await ctx.run_role(
                cfg,
                "clarify",
                clarify_model,
                clarify_agent,
                clarify_prompt(idea.model_dump_json(), snapshot.items, _blocks),
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
            route_prompt=clarify_prompt(idea.model_dump_json(), snapshot.items, _blocks),
            idea_json=idea.model_dump_json(),
            grounding=(render_for_prompt(codebase_map) if codebase_map is not None else ""),
            mode=idea.mode,
            cap=cfg.clarify_question_cap,
            repo_path=repo_path,
        )

    _clarify_key_extra = _clarify_memo_extra(cfg, codebase_map)
    _salt = prompt_digest(cfg)

    # FR-112: constitution_digest joins the memo inputs beside brief_digest
    # (the FR-103 precedent); FR-113: requirements_digest follows it.
    # Omitted-while-"" is the string seam's form of
    # ResearchDeps.research_model's omit-when-default serializer: an empty
    # digest concatenates to the identity, so a run that never saw a
    # constitution — or a requirements draft — keys byte-identically to
    # today (FR-010).
    _memo_input = idea.model_dump_json() + brief_digest
    reqs, _ = await ctx.cached_stage(
        cfg,
        "clarify",
        _memo_input + constitution_digest + requirements_digest + _clarify_key_extra,
        ClarifiedRequirements,
        _run_clarify_fanout if cfg.clarify_probes_enabled else _run_clarify_single,
        prompt_digest=_salt,
        # 021 FR-004: the recall snapshot the prompt consumed is a declared
        # input — its content hash joins the memo key's recall slot.
        recall_ref=snapshot.snapshot_hash,
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
            error=(_quality.detail if _quality.judge == "error" else None),
            outcome=BenchmarkOutcome.PASS,
            model=clarify_model,
            spend=clarify_spend,
        ),
    )

    # Note: _board_publish and retain run in _pipeline after return because
    # _board_publish sits between record and retain in the replay invariant sequence.
    return reqs
