"""The deterministic half of the handoff (spec 2.3).

Pure functions -- no I/O, no Temporal, no LLM. A claim may reference only
files the diff actually touched; anything else is the extractor attributing
work to a file the task never opened, and is dropped rather than trusted.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .grounding import Profile, verify_quote
from .measurement import Measurement
from .models import HandoffClaim, IntegrityFlag

# A path-ish token: at least one separator and a dotted final segment.
# Deliberately narrow -- prose like "the API" must not read as a path.
_PATH_RE = re.compile(r"[\w.\-/\\]*[/\\][\w.\-]+\.\w+")


def _normalise(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def _paths_in(text: str) -> set[str]:
    return {_normalise(m) for m in _PATH_RE.findall(text or "")}


class CrossCheckResult(BaseModel):
    """Kept claims plus the two drop reasons, counted separately: a claim
    naming a file the diff never touched and a claim quoting something nobody
    said are different extractor failures, and the waste metrics should not
    average them together."""
    kept: list[HandoffClaim] = Field(default_factory=list)
    dropped_paths: int = 0
    dropped_quotes: int = 0


def cross_check_claims(
    claims: list[HandoffClaim],
    files_touched: list[str],
    session_text: str | None = None,
) -> CrossCheckResult:
    """Keep claims whose referenced paths are all in `files_touched` AND whose
    evidence quote appears in `session_text`.

    A claim naming NO path survives: design decisions ("chose cookie sessions
    over JWT") legitimately reference no file, and dropping them would discard
    exactly the content the diff cannot supply. A claim with NO evidence text
    survives on the same rationale -- absence of a quote is not a fabricated
    quote.

    `session_text=None` skips quote verification entirely (E-43, spec §5): if
    capture failed there is no haystack, and absence of the haystack is not
    evidence against the quote. Dropping every quoted claim over an
    infrastructure failure would silently empty the handoff, which is a
    delivery failure by another name.

    VERBATIM_BYTES profile: a stored transcript is bytes we wrote, not
    third-party extractor output, so none of EXTRACTED_TEXT's loosenings apply.
    """
    allowed = {_normalise(f) for f in files_touched}
    result = CrossCheckResult()
    for c in claims:
        referenced = _paths_in(c.text) | _paths_in(c.evidence)
        if not referenced <= allowed:
            result.dropped_paths += 1
            continue
        if (session_text is not None and c.evidence.strip()
                and not verify_quote(c.evidence, session_text,
                                     Profile.VERBATIM_BYTES)):
            result.dropped_quotes += 1
            continue
        result.kept.append(c)
    return result


def claim_survival_score(kept: int, dropped: int) -> Measurement:
    """Fraction of claims that survived the cross-check.

    NOT_COLLECTED when there were no claims at all -- nothing was measured,
    and a 0.0 would claim it was (FR-915; waste_matrix.py's rule).
    """
    total = kept + dropped
    if total == 0:
        return Measurement.not_collected("no claims extracted")
    return Measurement.measured(kept / total)


def verified_integrity_flags(
    flags: list[IntegrityFlag],
    session_text: str | None,
) -> tuple[list[IntegrityFlag], int]:
    """Drop deep-review integrity flags whose evidence quote is not in the
    transcript (E-43). Returns (kept, dropped).

    Same three rules as cross_check_claims: an empty quote survives, a missing
    haystack skips verification, and the profile is VERBATIM_BYTES because a
    stored transcript is bytes we wrote.

    This lens NEVER gates, so a dropped flag only reduces what is recorded and
    retained -- it can never fail a task.
    """
    if session_text is None:
        return list(flags), 0
    kept: list[IntegrityFlag] = []
    dropped = 0
    for f in flags:
        if f.evidence.strip() and not verify_quote(
                f.evidence, session_text, Profile.VERBATIM_BYTES):
            dropped += 1
            continue
        kept.append(f)
    return kept, dropped
