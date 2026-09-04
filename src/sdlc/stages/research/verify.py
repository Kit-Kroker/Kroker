"""Verification of a ResearchBrief against bytes fetched this run, plus the
canonical brief_digest. The substring match itself lives in `sdlc/grounding.py`
(EXTRACTED_TEXT profile); this module owns the page lookup that decides which
bytes each quote is checked against. No network, no provider — just page files
and strings.

The rule (spec §5): `grounded` means the quote is a substring of the page fetched
THIS run for its source_url, under grounding's EXTRACTED_TEXT profile. Every
further loosening is a hole in the check — add none without a test proving the
specific false-failure it fixes."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path

from temporalio import activity

from ...grounding import Profile, Violation, quote_violation
from .models import ResearchBrief

_TMP_COUNTER = itertools.count()


def page_filename(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest() + ".txt"


def pages_dir(run_id: str) -> Path:
    """runs/<run_id>/research/pages. Root from $SDLC_RUNS_ROOT (default 'runs').
    Resolved activity-side only — the workflow never computes this."""
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / "pages"


def write_page(run_id: str, url: str, text: str) -> Path:
    """Write a fetched page atomically and return its path.

    os.replace() is atomic on POSIX and Windows alike, so a concurrent reader
    sees either the complete old file or the complete new one. Plain
    write_text() truncates first, and a reader interleaved between truncate
    and write gets a partial file -- which verify_brief reports as
    quote_not_found, failing the stage closed for no reason. Fan-out makes
    two sub-questions fetching the same URL an ordinary event, so this is
    load-bearing rather than defensive.

    The temp file carries the PID and a counter so two processes writing the
    same URL cannot collide on the temp path itself.
    """
    d = pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    final = d / page_filename(url)
    tmp = final.with_suffix(f".{os.getpid()}.{next(_TMP_COUNTER)}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return final


def verify_brief(brief: ResearchBrief, run_id: str) -> list[Violation]:
    """Verify every grounded finding against the page fetched THIS run for its
    source_url. EXTRACTED_TEXT profile: these bytes came out of a third-party
    HTML/PDF extractor, which is what justifies its two loosenings."""
    d = pages_dir(run_id)
    violations: list[Violation] = []
    for f in brief.grounded_findings:
        page = d / page_filename(f.source_url)
        if not page.is_file():
            violations.append(
                Violation(kind="source_unavailable", source=f.source_url, quote=f.quote)
            )
            continue
        v = quote_violation(
            f.quote, page.read_text(encoding="utf-8"), Profile.EXTRACTED_TEXT, source=f.source_url
        )
        if v is not None:
            violations.append(v)
    return violations


def brief_digest(brief: ResearchBrief) -> str:
    """The brief's contribution to downstream content_key (spec §7): a canonical
    hash of (source_url, claim) pairs only. Prose, ordering, and confidence drop
    out; facts remain. Same facts -> same digest -> clarify's memo hits."""
    pairs = sorted((f.source_url, f.claim) for f in brief.grounded_findings)
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class GroundingViolation(Exception):
    """Exception form of the Violation list returned by verify_brief.

    verify_brief_activity RETURNS list[Violation] (does not raise) so the
    calling workflow can inspect the result directly — temporalio's
    execute_activity wraps activity-raised exceptions in
    ActivityError(ApplicationError), which would prevent a typed
    `except GroundingViolation` from matching on the workflow side. A DIRECT
    (non-activity) caller that prefers an exception interface can raise
    GroundingViolation(violations) from the returned list.

    The workflow (Task 8) treats a non-empty violations list as a hard stage
    failure: it is NOT a ModelRetry, because TemporalAgent silently drops
    @agent.output_validator (Task 1 finding A); a hard stage failure is the
    authorized post-run fallback semantics."""

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(f"- {v.kind}: {v.source}: {v.quote!r}" for v in violations)
        super().__init__(
            "Grounded findings are not verified against bytes fetched this run. "
            "The research stage fails closed. Fix the quote to a verbatim span "
            "from a page fetched this run, or move the claim to "
            "inferred_findings. Violations:\n" + lines
        )


@activity.defn
async def verify_brief_activity(brief: ResearchBrief, run_id: str) -> list[Violation]:
    """Temporal activity: verify a ResearchBrief's grounded_findings against the
    page files fetched this run. Returns the list of violations (empty if the
    brief is clean). The calling workflow inspects the result and fails the
    stage closed if non-empty.

    Returns (does not raise) so the workflow can inspect the result directly:
    temporalio's execute_activity wraps activity-raised exceptions in
    ActivityError(ApplicationError), which would prevent the workflow from
    catching a typed GroundingViolation. A direct (non-activity) caller that
    wants an exception interface can raise GroundingViolation(violations)
    from the returned list."""
    return verify_brief(brief, run_id)
