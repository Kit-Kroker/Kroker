"""Structured pending-decision types (E-6).

Workflow-side source of truth for what a human owes a decision on. Pure
pydantic so it imports inside the Temporal workflow sandbox
(``workflow.unsafe.imports_passed_through``): no agents, no I/O, no
``temporalio``. The interface/adapter layer (``sdlc.channels``) renders these;
it never reaches into workflow internals.

All four variants collapse to just two FR-302 signals on reply:
``clarify`` -> ``answer_question``; every gate variant -> ``submit_gate_decision``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .gate import CheckResult
from .models import OpenQuestion, gate_key


class ClarifyPending(BaseModel):
    """An open clarify question awaiting a human answer -> answer_question."""
    kind: Literal["clarify"] = "clarify"
    key: str                       # the question id
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    opened_at: datetime | None = None
    # The run this item BELONGS to, when the hosting workflow is a child
    # (E-88 §6). The renderer groups by it and falls back to the handle id.
    # A field rather than a parse of the workflow-id prefix: the prefix is a
    # fact about ids, not a contract for display.
    parent_run_id: str | None = None


class StageGatePending(BaseModel):
    """An architecture/planning gate awaiting a decision -> submit_gate_decision."""
    kind: Literal["stage_gate"] = "stage_gate"
    key: str                       # gate_key(gate, round)
    gate: str
    round: int
    spec_summary: str
    opened_at: datetime | None = None
    parent_run_id: str | None = None


class TaskEscalationPending(BaseModel):
    """A task the fix loop could not close, escalated to a human."""
    kind: Literal["task_escalation"] = "task_escalation"
    key: str
    gate: str
    round: int
    task_id: str
    analysis: str
    attempts: int
    opened_at: datetime | None = None
    parent_run_id: str | None = None


class MergeGatePending(BaseModel):
    """The merge gate awaiting a decision, carrying the quality-check table."""
    kind: Literal["merge_gate"] = "merge_gate"
    key: str
    gate: str
    round: int
    checks: list[CheckResult] = Field(default_factory=list)
    verdict: str | None = None
    opened_at: datetime | None = None
    parent_run_id: str | None = None


PendingDecision = Annotated[
    Union[ClarifyPending, StageGatePending,
          TaskEscalationPending, MergeGatePending],
    Field(discriminator="kind"),
]


class GateContext(BaseModel):
    """Optional render context a caller hands to ``_gate``; the gate name
    selects which variant is built from it."""
    spec_summary: str | None = None      # stage gates
    checks: list[CheckResult] = Field(default_factory=list)  # merge gate
    verdict: str | None = None           # merge gate
    analysis: str | None = None          # task escalation
    attempts: int | None = None          # task escalation
    task_id: str | None = None           # task escalation


def clarify_pending(
    open_questions: list[OpenQuestion], answered_ids: set[str],
    *, opened_at: datetime | None = None,
) -> list[ClarifyPending]:
    """One ClarifyPending per still-unanswered open question."""
    return [
        ClarifyPending(key=q.id, question=q.question,
                       why_it_matters=q.why_it_matters,
                       suggested_answer=q.suggested_answer,
                       opened_at=opened_at)
        for q in open_questions if q.id not in answered_ids
    ]


def gate_pending(
    name: str, round: int, context: GateContext | None = None,
    *, opened_at: datetime | None = None,
    parent_run_id: str | None = None,
) -> PendingDecision:
    """Build the render variant a gate wait should surface. The gate name is
    the discriminator: 'merge' -> MergeGatePending, 'task:<id>' ->
    TaskEscalationPending, anything else -> StageGatePending."""
    key = gate_key(name, round)
    ctx = context or GateContext()
    if name == "merge":
        return MergeGatePending(key=key, gate=name, round=round,
                                checks=ctx.checks, verdict=ctx.verdict,
                                opened_at=opened_at,
                                parent_run_id=parent_run_id)
    if name.startswith("task:"):
        return TaskEscalationPending(
            key=key, gate=name, round=round,
            task_id=ctx.task_id or name.removeprefix("task:"),
            analysis=ctx.analysis or "", attempts=ctx.attempts or 0,
            opened_at=opened_at, parent_run_id=parent_run_id)
    return StageGatePending(key=key, gate=name, round=round,
                            spec_summary=ctx.spec_summary or "",
                            opened_at=opened_at,
                            parent_run_id=parent_run_id)
