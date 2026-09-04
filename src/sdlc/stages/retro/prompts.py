"""Retro stage prompt digest (spec A §5)."""

from __future__ import annotations

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Retro stage is best-effort summary and reflection with no proposer roles."""
    return ""
