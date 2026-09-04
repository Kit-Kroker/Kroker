"""Context stage prompt digest (spec A §5)."""

from __future__ import annotations

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Context is a deterministic mapping stage with no LLM proposer roles."""
    return ""
