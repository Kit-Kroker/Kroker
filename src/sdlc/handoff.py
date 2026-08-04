"""The deterministic half of the handoff (spec 2.3).

Pure functions -- no I/O, no Temporal, no LLM. A claim may reference only
files the diff actually touched; anything else is the extractor attributing
work to a file the task never opened, and is dropped rather than trusted.
"""
from __future__ import annotations

import re

from .models import HandoffClaim

# A path-ish token: at least one separator and a dotted final segment.
# Deliberately narrow -- prose like "the API" must not read as a path.
_PATH_RE = re.compile(r"[\w.\-/\\]*[/\\][\w.\-]+\.\w+")


def _normalise(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def _paths_in(text: str) -> set[str]:
    return {_normalise(m) for m in _PATH_RE.findall(text or "")}


def cross_check_claims(
    claims: list[HandoffClaim],
    files_touched: list[str],
) -> tuple[list[HandoffClaim], int]:
    """Keep claims whose referenced paths are all in `files_touched`.

    A claim naming NO path survives: design decisions ("chose cookie
    sessions over JWT") legitimately reference no file, and dropping them
    would discard exactly the content the diff cannot supply.

    Returns (kept, dropped_count).
    """
    allowed = {_normalise(f) for f in files_touched}
    kept: list[HandoffClaim] = []
    dropped = 0
    for c in claims:
        referenced = _paths_in(c.text) | _paths_in(c.evidence)
        if referenced <= allowed:
            kept.append(c)
        else:
            dropped += 1
    return kept, dropped


def claim_survival_score(kept: int, dropped: int) -> float | None:
    """Fraction of claims that survived the cross-check.

    None when there were no claims at all -- nothing was measured, and a
    0.0 would claim it was (waste_matrix.py's rule).
    """
    total = kept + dropped
    if total == 0:
        return None
    return kept / total
