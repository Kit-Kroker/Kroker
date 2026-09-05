"""The code stage slice."""

from __future__ import annotations

from .activities import (
    ACTIVITIES,
    CodingTaskInput,
    _resolve_containment,
    run_coding_task,
)
from .models import HandoffClaim, HandoffSummary, IntegrityFlag
from .prompts import prompt_digest
from .step import (
    _execute_coding_task,
    _record_escalation,
    _run_adversary,
    _run_deep_review,
    _run_handoff,
    step,
)

__all__ = [
    "ACTIVITIES",
    "CodingTaskInput",
    "HandoffClaim",
    "HandoffSummary",
    "IntegrityFlag",
    "_execute_coding_task",
    "_record_escalation",
    "_resolve_containment",
    "_run_adversary",
    "_run_deep_review",
    "_run_handoff",
    "prompt_digest",
    "run_coding_task",
    "step",
]
