"""The code stage slice."""

from __future__ import annotations

from .activities import (
    ACTIVITIES,
    CodingTaskInput,
    DriftGlobs,
    DriftGlobsInput,
    _resolve_containment,
    load_drift_globs,
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
    "DriftGlobs",
    "DriftGlobsInput",
    "HandoffClaim",
    "HandoffSummary",
    "IntegrityFlag",
    "_execute_coding_task",
    "_record_escalation",
    "_resolve_containment",
    "_run_adversary",
    "_run_deep_review",
    "_run_handoff",
    "load_drift_globs",
    "prompt_digest",
    "run_coding_task",
    "step",
]
