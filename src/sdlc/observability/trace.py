"""Domain run-trace types (E-32).

Pure pydantic, sandbox-safe: no temporalio, no I/O. The workflow accumulates
a list[RunEvent] in state (already durable in Temporal history); events.jsonl
is a rendering of it, not a second source of truth.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RunEventKind(str, Enum):
    STAGE_STARTED = "stage_started"
    STAGE_ENDED = "stage_ended"
    GATE_AWAITED = "gate_awaited"
    GATE_DECIDED = "gate_decided"
    CLARIFICATION_ASKED = "clarification_asked"
    CLARIFICATION_ANSWERED = "clarification_answered"
    FIX_ATTEMPT = "fix_attempt"
    TOOL_ESCALATION = "tool_escalation"
    MODEL_USAGE = "model_usage"
    MEMORY_RETAINED = "memory_retained"
    RUN_FINISHED = "run_finished"


class RunEvent(BaseModel):
    """One domain event. `data` is a flat str->str map so events.jsonl stays a
    stable, greppable line format; numeric values are stringified at emit."""
    seq: int
    at: datetime
    kind: RunEventKind
    stage: str | None = None
    data: dict[str, str] = Field(default_factory=dict)
