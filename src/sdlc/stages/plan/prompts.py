"""Prompts and prompt digesting for the plan stage slice."""

from __future__ import annotations

import hashlib

from ...core.models import PipelineConfig
from ...prompts import planner_prompt

__all__ = ["planner_prompt", "prompt_digest"]


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"plan_prompt_v1")
    rc = cfg.roles.get("plan")
    if rc and rc.model:
        h.update(f":plan:{rc.model}".encode())
    return h.hexdigest()
