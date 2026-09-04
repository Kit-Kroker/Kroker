"""Analyze stage prompt generation and digest (spec A §5)."""

from __future__ import annotations

import hashlib

from ...core.models import PipelineConfig


def analyst_prompt(criteria_lines: str, qa_lines: str, diff_stat: str, diff_patch: str) -> str:
    """Clean-context prompt for the Analyst role (FR-106)."""
    return (
        "Acceptance criteria (task_id in brackets):\n"
        + criteria_lines
        + "\nAggregate test output:\n"
        + qa_lines
        + f"\nIntegration diff stat:\n{diff_stat}"
        + f"\nIntegration diff:\n{diff_patch}"
    )


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"analyst_prompt_v1")
    rc = cfg.roles.get("analyze") or cfg.roles.get("analyst")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":analyze:{h.hexdigest()[:16]}"
