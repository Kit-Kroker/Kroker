"""Pure trace -> RunSummary aggregation (E-32). No I/O, no temporalio: unit-
testable outside the workflow, called once from the retro stage."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from ..core.models import (
    ClarificationDimension,
    ClarificationOutcome,
    GateOutcome,
    GateOutcomeSummary,
    RoleUsage,
    RunSummary,
    StageOutcome,
)
from .trace import RunEvent, RunEventKind
from .usage import merge_usage


def _stage_outcome(ev: RunEvent) -> StageOutcome:
    d = ev.data
    cost = d.get("cost_usd")
    drift = d.get("plan_drift")
    quality = d.get("quality_score")
    return StageOutcome(
        stage=ev.stage or d.get("stage", "?"),
        role=d.get("role", "?"),
        outcome=d.get("outcome", "?"),
        duration_s=float(d.get("duration_s", "0")),
        cost_usd=float(cost) if cost is not None else None,
        fix_attempts=int(d.get("fix_attempts", "0")),
        plan_drift=float(drift) if drift is not None else None,
        quality_score=float(quality) if quality is not None else None,
        quality_judge=d.get("quality_judge") or None,
    )


def _gate_outcome(ev: RunEvent) -> GateOutcomeSummary:
    d = ev.data
    conf = d.get("confidence")
    ov = d.get("overrides", "")
    when = d.get("decided_at")
    return GateOutcomeSummary(
        gate=d.get("gate", "?"),
        round=int(d.get("round", "1")),
        policy=d.get("policy", "?"),
        decided_by=d.get("decided_by", "?"),
        approved=d.get("approved") == "true",
        # FR-304 fields: absent on events emitted before this change.
        outcome=GateOutcome(d["outcome"]) if d.get("outcome") else None,
        comments=d.get("comments") or None,
        reviewer=d.get("reviewer") or None,
        decided_at=datetime.fromisoformat(when) if when else None,
        confidence=float(conf) if conf is not None else None,
        author_model=d.get("author_model") or None,
        overrides=[c for c in ov.split(",") if c],
    )


# Optional (None-able) GateOutcomeSummary fields an enrich-merge fills from
# the earlier record when a later emit omits them.
_ENRICH_OPTIONALS = (
    "outcome",
    "comments",
    "reviewer",
    "decided_at",
    "confidence",
    "author_model",
)


def _enrich(prev: GateOutcomeSummary, new: GateOutcomeSummary) -> GateOutcomeSummary:
    """FR-304: a repeated (gate, round) key enriches rather than replaces.
    The merge stage emits a bare GATE_DECIDED from _gate and then an
    enriched one carrying overrides; a replace would drop whichever half the
    other emit carried. Always-present fields take the later event's value;
    an optional the later event omits keeps the earlier value; so do earlier
    overrides when the later emit carries none."""
    update = {
        f: getattr(new, f) if getattr(new, f) is not None else getattr(prev, f)
        for f in _ENRICH_OPTIONALS
    }
    if not new.overrides and prev.overrides:
        update["overrides"] = prev.overrides
    return new.model_copy(update=update)


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
            bag,
            model=model,
            input_tokens=int(d.get("input_tokens", "0")),
            output_tokens=int(d.get("output_tokens", "0")),
            cache_read_tokens=int(d.get("cache_read_tokens", "0")),
            cache_write_tokens=int(d.get("cache_write_tokens", "0")),
            cost_usd=float(cost) if cost is not None else None,
        )
    return list(bags.values())


def build_run_summary(
    *,
    run_id: str,
    mode: str,
    outcome: str,
    trace: list[RunEvent],
    memory_enabled: bool,
    memory_watermark: str | None,
    budget_usd: float | None = None,
    budget_counted_usd: float | None = None,
    title: str = "",
    repo_url: str | None = None,
    graph_sha: str | None = None,
    project_key: str | None = None,
) -> RunSummary:
    stages = [_stage_outcome(e) for e in trace if e.kind is RunEventKind.STAGE_ENDED]

    # Dedup gates by (gate, round), enriching on repeats: the merge stage
    # emits a bare GATE_DECIDED from _gate and then an enriched one carrying
    # overrides; distinct revision rounds keep distinct keys. See _enrich.
    gate_by_key: dict[tuple[str, int], GateOutcomeSummary] = {}
    for e in trace:
        if e.kind is RunEventKind.GATE_DECIDED:
            g = _gate_outcome(e)
            key = (g.gate, g.round)
            gate_by_key[key] = _enrich(gate_by_key[key], g) if key in gate_by_key else g

    # 025 (FR-001/002): when each (gate, round) OPENED, from its
    # GATE_AWAITED event. Stamped after the dedup loop — deliberately not
    # part of _ENRICH_OPTIONALS: a repeated emit never rewrites the open,
    # and a gate with no AWAITED event keeps None (never opened for a
    # human). A later AWAITED on the same key wins, matching trace order.
    gate_raised_at = {
        (e.data.get("gate", "?"), int(e.data.get("round", "1"))): e.at
        for e in trace
        if e.kind is RunEventKind.GATE_AWAITED
    }
    gates = [
        g.model_copy(update={"raised_at": gate_raised_at.get((g.gate, g.round))})
        for g in gate_by_key.values()
    ]

    answered_events = {
        e.data.get("question_id"): e
        for e in trace
        if e.kind is RunEventKind.CLARIFICATION_ANSWERED
    }
    clarifications: list[ClarificationOutcome] = []
    for e in trace:
        if e.kind is not RunEventKind.CLARIFICATION_ASKED:
            continue
        ans = answered_events.get(e.data.get("question_id"))
        # The ANSWERED event is emitted for every question in a batch; its
        # answered_by says whether an answer exists at all ("unanswered" is
        # the deadline path). Absent event means the same.
        by = ans.data.get("answered_by", "unanswered") if ans is not None else "unanswered"
        clarifications.append(
            ClarificationOutcome(
                question_id=e.data.get("question_id", "?"),
                question=e.data.get("question", ""),
                # Event data is untyped at this boundary; the model validates
                # the Literal at construction, the cast only states that
                # contract.
                answered_by=cast(Literal["human", "suggested", "unanswered"], by),
                # E-85. Absent on pre-E-85 runs, "" on the flag-off path;
                # both mean "no dimension", and "" is not a valid enum
                # member.
                dimension=cast(ClarificationDimension | None, e.data.get("dimension") or None),
                # 025 (FR-001): raw times for the SC-2 instrument — the
                # question's ASKED at, and the ANSWERED at only when an
                # answer exists; unanswered keeps None so the deadline
                # event's time never masquerades as an answer.
                raised_at=e.at,
                answered_at=ans.at if by != "unanswered" else None,
            )
        )

    terminal = next(
        (e.stage for e in reversed(trace) if e.kind is RunEventKind.STAGE_ENDED and e.stage),
        "intake",
    )
    roles = _role_rollup(trace)
    role_costs = [u.cost_usd for u in roles if u.cost_usd is not None]
    budget_crossings = sum(
        1 for e in trace if e.kind is RunEventKind.GATE_DECIDED and e.data.get("gate") == "budget"
    )
    started = trace[0].at
    ended = trace[-1].at
    retains = sum(1 for e in trace if e.kind is RunEventKind.MEMORY_RETAINED)

    return RunSummary(
        run_id=run_id,
        mode=mode,
        outcome=outcome,
        terminal_stage=terminal,
        title=title,
        repo_url=repo_url,
        started_at=started,
        ended_at=ended,
        duration_s=(ended - started).total_seconds(),
        stages=stages,
        clarifications=clarifications,
        gates=gates,
        roles=roles,
        cost_usd_total=(sum(role_costs) if role_costs else None),
        budget_usd=budget_usd,
        budget_crossings=budget_crossings,
        budget_counted_usd=budget_counted_usd,
        memory_enabled=memory_enabled,
        memory_watermark=memory_watermark,
        memory_retains=retains,
        graph_sha=graph_sha,
        project_key=project_key,
        # 025 (FR-005): every summary this builder writes is instrumented;
        # False marks a pre-025 summary (not-measured, never zero).
        operator_instrumented=True,
    )
