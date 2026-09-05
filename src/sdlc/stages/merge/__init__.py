"""The merge stage slice."""

from __future__ import annotations

from .activities import (
    ACTIVITIES,
    evaluate_gate,
    measure_coverage,
    open_pull_request,
    run_integration_checks,
)
from .models import CoverageReport, MergeVerdict
from .prompts import merge_verdict_prompt, prompt_digest
from .step import _merge_evidence_all_green, step

__all__ = [
    "ACTIVITIES",
    "CoverageReport",
    "MergeVerdict",
    "_merge_evidence_all_green",
    "evaluate_gate",
    "measure_coverage",
    "merge_verdict_prompt",
    "open_pull_request",
    "prompt_digest",
    "run_integration_checks",
    "step",
]
