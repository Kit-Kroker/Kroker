"""Retro-time session retention (E-38, OQ-B7 decided half).

Full transcript is kept on fail / benchmark / any fix-loop retry — "green
after a retry" keeps full, because HOW the agent recovered is the point.
Only clean-green non-benchmark runs are downgraded to digest-only. The
digest file is never deleted. TTL on kept transcripts stays open (OQ-B7).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from temporalio import activity

from ..core.models import (
    ArtifactRef,
)

_log = logging.getLogger(__name__)


def keep_full_transcripts(outcome: str, had_fix_attempts: bool, is_benchmark: bool) -> bool:
    """Pure policy — called from workflow code, so: no IO, no env."""
    clean_green = outcome.startswith("deployed") and not had_fix_attempts
    return is_benchmark or not clean_green


class RetentionInput(BaseModel):
    refs: list[ArtifactRef] = Field(default_factory=list)
    keep_full: bool


@activity.defn
async def apply_session_retention(inp: RetentionInput) -> str:
    if inp.keep_full:
        return f"kept:{len(inp.refs)}"
    from .store import LocalFileStore

    store = LocalFileStore()
    for ref in inp.refs:
        store.delete(ref)  # digests are not in refs — never deleted
    return f"downgraded:{len(inp.refs)}"
