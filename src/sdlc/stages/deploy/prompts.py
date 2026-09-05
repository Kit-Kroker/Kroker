"""Deploy stage prompt generation and digest (spec A §5)."""

from __future__ import annotations

import hashlib

from ...core.models import PipelineConfig


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"deploy_prompt_v1")
    rc = cfg.roles.get("devops") or cfg.roles.get("deploy")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":deploy:{h.hexdigest()[:16]}"
