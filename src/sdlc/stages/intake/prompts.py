"""Intake stage prompt digest (spec A §5)."""

from __future__ import annotations

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Intake is a purely mechanical probe stage with no LLM proposer roles."""
    return ""
