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


class StageGatePending(BaseModel):
    """An architecture/planning gate awaiting a decision -> submit_gate_decision."""
    kind: Literal["stage_gate"] = "stage_gate"
    key: str                       # gate_key(gate, round)
    gate: str
    round: int
    spec_summary: str


class TaskEscalationPending(BaseModel):
    """A task the fix loop could not close, escalated to a human."""
    kind: Literal["task_escalation"] = "task_escalation"
    key: str
    gate: str
    round: int
    task_id: str
    analysis: str
    attempts: int


class MergeGatePending(BaseModel):
    """The merge gate awaiting a decision, carrying the quality-check table."""
    kind: Literal["merge_gate"] = "merge_gate"
    key: str
    gate: str
    round: int
    checks: list[CheckResult] = Field(default_factory=list)
    verdict: str | None = None


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
