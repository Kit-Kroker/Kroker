"""Code stage prompt generation and digest (spec A §5)."""

from __future__ import annotations

import hashlib

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"code_prompt_v1")
    rc = cfg.roles.get("dev") or cfg.roles.get("code")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":code:{h.hexdigest()[:16]}"
