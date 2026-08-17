"""Pure trace -> RunSummary aggregation (E-32). No I/O, no temporalio: unit-
testable outside the workflow, called once from the retro stage."""
from __future__ import annotations

from ..models import (
    ClarificationOutcome, GateOutcomeSummary, RoleUsage, RunSummary,
    StageOutcome,
)
from .trace import RunEvent, RunEventKind
from .usage import merge_usage


def _stage_outcome(ev: RunEvent) -> StageOutcome:
    d = ev.data
    cost = d.get("cost_usd")
    return StageOutcome(
        stage=ev.stage or d.get("stage", "?"),
        role=d.get("role", "?"),
        outcome=d.get("outcome", "?"),
        duration_s=float(d.get("duration_s", "0")),
        cost_usd=float(cost) if cost is not None else None,
        fix_attempts=int(d.get("fix_attempts", "0")),
    )


def _gate_outcome(ev: RunEvent) -> GateOutcomeSummary:
    d = ev.data
    conf = d.get("confidence")
    ov = d.get("overrides", "")
    return GateOutcomeSummary(
        gate=d.get("gate", "?"),
        round=int(d.get("round", "1")),
        policy=d.get("policy", "?"),
        decided_by=d.get("decided_by", "?"),
        approved=d.get("approved") == "true",
        confidence=float(conf) if conf is not None else None,
        overrides=[c for c in ov.split(",") if c],
    )


def _role_rollup(trace: list[RunEvent]) -> list[RoleUsage]:
    bags: dict[str, RoleUsage] = {}
    for e in trace:
        if e.kind is not RunEventKind.MODEL_USAGE:
            continue
        d = e.data
        role = d.get("role", "?")
        model = d.get("model", "?")
        bag = bags.setdefault(role, RoleUsage(role=role, model=model))
        cost = d.get("cost_usd")
        merge_usage(
            bag, model=model,
            input_tokens=int(d.get("input_tokens", "0")),
            output_tokens=int(d.get("output_tokens", "0")),
            cache_read_tokens=int(d.get("cache_read_tokens", "0")),
            cache_write_tokens=int(d.get("cache_write_tokens", "0")),
            cost_usd=float(cost) if cost is not None else None)
    return list(bags.values())


def build_run_summary(
    *, run_id: str, mode: str, outcome: str,
    trace: list[RunEvent],
    memory_enabled: bool, memory_watermark: str | None,
    budget_usd: float | None = None,
    title: str = "",
    repo_url: str | None = None,
) -> RunSummary:
    stages = [_stage_outcome(e) for e in trace
              if e.kind is RunEventKind.STAGE_ENDED]

    # Dedup gates by (gate, round), last-wins: the merge stage emits a bare
    # GATE_DECIDED from _gate and then an enriched one carrying overrides;
    # distinct revision rounds keep distinct keys.
    gate_by_key: dict[tuple[str, int], GateOutcomeSummary] = {}
    for e in trace:
        if e.kind is RunEventKind.GATE_DECIDED:
            g = _gate_outcome(e)
            gate_by_key[(g.gate, g.round)] = g
    gates = list(gate_by_key.values())

    answered = {e.data.get("question_id"): e.data.get("answered_by", "unanswered")
                for e in trace if e.kind is RunEventKind.CLARIFICATION_ANSWERED}
    clarifications = [
        ClarificationOutcome(
            question_id=e.data.get("question_id", "?"),
            question=e.data.get("question", ""),
            answered_by=answered.get(e.data.get("question_id"), "unanswered"),
        )
        for e in trace if e.kind is RunEventKind.CLARIFICATION_ASKED
    ]

    terminal = next((e.stage for e in reversed(trace)
                     if e.kind is RunEventKind.STAGE_ENDED and e.stage),
                    "intake")
    roles = _role_rollup(trace)
    role_costs = [u.cost_usd for u in roles if u.cost_usd is not None]
    budget_crossings = sum(
        1 for e in trace
        if e.kind is RunEventKind.GATE_DECIDED
        and e.data.get("gate") == "budget")
    started = trace[0].at
    ended = trace[-1].at
    retains = sum(1 for e in trace if e.kind is RunEventKind.MEMORY_RETAINED)

    return RunSummary(
        run_id=run_id, mode=mode, outcome=outcome, terminal_stage=terminal,
        title=title, repo_url=repo_url,
        started_at=started, ended_at=ended,
        duration_s=(ended - started).total_seconds(),
        stages=stages, clarifications=clarifications, gates=gates,
        roles=roles,
        cost_usd_total=(sum(role_costs) if role_costs else None),
        budget_usd=budget_usd, budget_crossings=budget_crossings,
        memory_enabled=memory_enabled, memory_watermark=memory_watermark,
        memory_retains=retains,
    )
