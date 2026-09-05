"""Prompts and prompt digesting for the architecture stage slice."""

from __future__ import annotations

import hashlib

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"architecture_prompt_v1")
    rc = cfg.roles.get("architect")
    if rc and rc.model:
        h.update(f":architect:{rc.model}".encode())
    return h.hexdigest()
