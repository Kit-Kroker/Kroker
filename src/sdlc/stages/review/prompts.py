"""Prompts for the review stage (spec A §3.5)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ...core.models import PipelineConfig


def _frozen_contract_block(assertions: Sequence[str]) -> str:
    return "Frozen contract assertions:\n- " + "\n- ".join(assertions)


def reviewer_prompt(assertions: Sequence[str], qa_raw_json: str, diff_patch: str) -> str:
    """Clean-context reviewer prompt (FR-204).

    Identical to the original in sdlc.prompts: frozen contract assertions,
    deterministic test results (qa_raw_json), and diff patch. No stat block.
    """
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff:\n{diff_patch}"
    )


def adversary_prompt(assertions: Sequence[str], qa_raw_json: str, diff_patch: str) -> str:
    """Clean-context adversary prompt (spec 3.2).

    Identical inputs to the primary reviewer: contract assertions, test results,
    and diff patch. Identical inputs make disagreement interpretable as model
    variance rather than information asymmetry.
    """
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff:\n{diff_patch}"
    )


def deep_review_prompt(
    assertions: Sequence[str], task_json: str, diff_patch: str, transcript: str
) -> str:
    """Advisory deep-review prompt (E-39).

    Receives frozen contract assertions, planned task, diff patch, and the
    scrubbed harness transcript.
    """
    return (
        _frozen_contract_block(assertions)
        + f"\nThe task as planned:\n{task_json}"
        + f"\nDiff:\n{diff_patch}"
        + "\nScrubbed harness transcript (how the diff was reached):\n"
        + transcript
    )


def prompt_digest(cfg: PipelineConfig) -> str:
    """Salt for the memoization key (spec A §3.5).

    PROMPT_SHAS hashes agents/<role>/instructions.md only, so a prompt living
    here is invisible to content_key and an edit would serve a stale memo.
    """
    h = hashlib.sha256()
    h.update(b"review_prompt_v1")
    for role in ("reviewer", "adversary", "deep_review"):
        rc = cfg.roles.get(role)
        if rc and rc.model:
            h.update(f":{role}:{rc.model}".encode())
    return f":review:{h.hexdigest()[:16]}"
