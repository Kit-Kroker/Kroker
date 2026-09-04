"""RoleHost -- model execution, staging, memoization, and budget checks (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Consumes: ReportHost._track_usage, GateHost._gate via the MRO.
Owns: _budget_threshold, _budget_crossings.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeVar

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import PROMPT_SHAS, resolve_role_model
    from ..core.models import (
        GateConfig,
        GateDecision,
        GateOutcome,
        GatePolicy,
        PipelineConfig,
        RoleUsage,
    )
    from ..memoization.activities import (
        CacheGetInput,
        CachePutInput,
        cache_get,
        cache_put,
    )
    from ..memoization.cache import content_key
    from ..pending import GateContext
    from ..pricing import PriceUsageInput, price_usage
    from .memory_host import MEM_ACT

# E-33: pricing is a deterministic local table lookup — retrying cannot
# change the outcome (VERIFY_ACT rationale); the caller treats failure as
# "price unknown", so 1 attempt, short timeout.
PRICE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=1)
)

StageT = TypeVar("StageT", bound=BaseModel)


class _BudgetRejected(Exception):
    """Raised at a budget-gate reject; caught in run() so the terminal
    outcome is the ordinary string "rejected:budget" and retro still runs."""


def _auto_decision_for(
    name: str, cfg: PipelineConfig, confidence: float | None
) -> GateDecision | None:
    """FR-301: SOFT + confidence >= threshold -> an APPROVE decision _gate()
    can short-circuit on. None confidence (missing/legacy artifact) or below
    threshold -> None, falling through to the human wait -- never a silent
    auto-approve on absent data (same defensive stance as
    HarnessRunResult.near_context_ceiling())."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    return GateDecision(
        gate=name,
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments=f"auto-approved: confidence={confidence:.2f} "
        f">= threshold={gate_cfg.threshold:.2f}",
    )


def _spec_summary(artifact: object) -> str:
    """Best-effort one-field summary of a proposer artifact for gate render.
    ClarifiedRequirements has `summary`; ArchitectureSpec has `overview`;
    fall back to the type name so the field is never empty."""
    return (
        getattr(artifact, "summary", None)
        or getattr(artifact, "overview", None)
        or type(artifact).__name__
    )


class RoleHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        self._budget_threshold: float = 0.0
        self._budget_crossings: int = 0

    async def _cached_stage(
        self,
        cfg: PipelineConfig,
        stage: str,
        input_json: str,
        output_type: type[StageT],
        run_fn: Callable[[], Awaitable[StageT]],
        *,
        prompt_digest: str = "",
    ) -> tuple[StageT, bool]:
        """Skips `run_fn()` (a no-arg async callable invoking the proposer
        agent) when an identical (stage, input, prompt, model,
        upstream-recall-watermark) combination was already computed — the
        ADR-5 dev-loop cache. Returns (output, was_cache_hit).

        The stage's model is resolved per-run (resolve_role_model): a per-role
        override MUST move the key, or a stale result computed by a different
        model would be served."""
        if not cfg.memoization_enabled:
            return await run_fn(), False
        key = content_key(
            stage,
            input_json,
            PROMPT_SHAS[stage] + prompt_digest,
            resolve_role_model(cfg, stage),
            getattr(self, "_memory_watermark", None) or "none",
        )
        cached = await workflow.execute_activity(cache_get, CacheGetInput(key=key), **MEM_ACT)
        if cached is not None:
            return output_type.model_validate_json(cached), True
        result = await run_fn()
        await workflow.execute_activity(
            cache_put, CachePutInput(key=key, payload_json=result.model_dump_json()), **MEM_ACT
        )
        return result, False

    async def _run_role(
        self,
        cfg: PipelineConfig,
        role: str,
        model: str,
        agent: Any,
        *args: Any,
        into: RoleUsage | None = None,
        **kwargs: Any,
    ) -> Any:
        """E-33 single model-egress point (folds E-19): run a proposer
        agent, capture its usage, price it (replay-safe: in an activity),
        accumulate per role. Returns the AgentRunResult — callers keep
        taking .output. Pricing failure of ANY kind degrades to usd=None;
        it must never fail the stage."""
        result = await agent.run(*args, **kwargs)
        u = result.usage
        usd: float | None = None
        if u.input_tokens or u.output_tokens:
            try:
                usd = await workflow.execute_activity(
                    price_usage,
                    PriceUsageInput(
                        model=model,
                        input_tokens=u.input_tokens or 0,
                        output_tokens=u.output_tokens or 0,
                        cache_read_tokens=u.cache_read_tokens or 0,
                        cache_write_tokens=u.cache_write_tokens or 0,
                    ),
                    **PRICE_ACT,
                )
            except Exception:
                usd = None
        self._track_usage(  # type: ignore[attr-defined]
            role=role,
            model=model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=u.cache_read_tokens or 0,
            cache_write_tokens=u.cache_write_tokens or 0,
            cost_usd=usd,
            into=into,
        )
        return result

    async def _check_budget(self, cfg: PipelineConfig) -> None:
        """E-33/FR-701 run-budget enforcement. Called at SERIAL points only
        (stage boundaries + the task loop after merges) — never inside a
        wave-mode gather, so gate rounds cannot race. Approve grants one
        more increment; the while-loop re-gates a spend that jumped
        multiple increments at once."""
        if cfg.run_budget_usd <= 0:
            return
        role_usage = getattr(self, "_role_usage", {})
        total = sum(u.cost_usd or 0.0 for u in role_usage.values())
        while total >= self._budget_threshold:
            self._budget_crossings += 1
            rows = "\n".join(
                f"  {u.role} ({u.model}): ${u.cost_usd:.4f}"
                for u in role_usage.values()
                if u.cost_usd is not None
            )
            decision = await self._gate(  # type: ignore[attr-defined]
                "budget",
                cfg.gate_settings(),
                round=self._budget_crossings,
                context=GateContext(
                    spec_summary=(
                        f"Run cost ${total:.4f} >= budget ${self._budget_threshold:.2f}\n{rows}"
                    )
                ),
                default_policy=GatePolicy.HARD,
            )
            if decision.outcome is not GateOutcome.APPROVE:
                # REVISE has nothing to revise here — any non-approve
                # terminates (spec §5).
                raise _BudgetRejected()
            self._budget_threshold += cfg.run_budget_usd

    async def _revisable_stage(
        self, name: str, cfg: PipelineConfig, run_fn: Callable[[str | None], Awaitable[StageT]]
    ) -> tuple[StageT, GateDecision]:
        """Run a proposer stage, gate it, and on REVISE re-run with the
        human's guidance at round+1, up to cfg.max_gate_rounds. Past that,
        escalate to a final human gate (the configured policy still applies,
        but no auto_decision is passed, so SOFT also waits) (FR-301).
        `run_fn(guidance: str | None)` must re-execute the producer with the
        guidance injected."""
        guidance: str | None = None
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            auto = _auto_decision_for(name, cfg, getattr(artifact, "confidence", None))
            decision = await self._gate(  # type: ignore[attr-defined]
                name,
                cfg.gate_settings(),
                auto_decision=auto,
                round=round,
                context=GateContext(spec_summary=_spec_summary(artifact)),
                confidence=getattr(artifact, "confidence", None),
            )
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
        # Exhausted: one final HARD gate decides accept-anyway vs abandon.
        artifact = await run_fn(guidance)
        decision = await self._gate(  # type: ignore[attr-defined]
            name,
            cfg.gate_settings(),
            round=cfg.max_gate_rounds + 1,
            context=GateContext(spec_summary=_spec_summary(artifact)),
        )
        return artifact, decision
