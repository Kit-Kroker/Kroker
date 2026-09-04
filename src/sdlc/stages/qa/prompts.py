"""Prompts for the qa stage (spec A §3.5)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ...core.models import PipelineConfig


def _frozen_contract_block(assertions: Sequence[str]) -> str:
    return "Frozen contract assertions:\n- " + "\n- ".join(assertions)


def qa_prompt(assertions: Sequence[str], qa_raw_json: str, diff_stat: str, diff_patch: str) -> str:
    """Compose the clean-context QA prompt.

    Contains frozen contract assertions, deterministic test results, diff stat,
    and the git patch.
    """
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff stat:\n{diff_stat}"
        + f"\nDiff:\n{diff_patch}"
    )


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5).

    PROMPT_SHAS hashes agents/<role>/instructions.md only, so a prompt living
    here is invisible to content_key and an edit would serve a stale memo.
    """
    h = hashlib.sha256()
    h.update(b"qa_prompt_v1")
    rc = cfg.roles.get("qa")
    if rc and rc.model:
        h.update(rc.model.encode("utf-8"))
    return f":qa:{h.hexdigest()[:16]}"
