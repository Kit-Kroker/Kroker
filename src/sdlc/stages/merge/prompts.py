"""Merge stage prompt generation and digest (spec A §5)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ...core.models import PipelineConfig


def merge_verdict_prompt(task_results: Sequence[dict]) -> str:
    """feature.py:2361-2362. The f-string interpolates the LIST, so Python's
    repr of list-of-dicts is what reaches the model. Do not "fix" this to
    JSON -- it would change the prompt."""
    return (
        f"Advisory only — the deterministic gate already passed. Task results: {list(task_results)}"
    )


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5)."""
    h = hashlib.sha256()
    h.update(b"merge_verdict_prompt_v1")
    rc = cfg.roles.get("merge_verdict") or cfg.roles.get("merge")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":merge:{h.hexdigest()[:16]}"
