"""Pure verification of a ResearchBrief against bytes fetched this run, plus the
canonical brief_digest. No network, no provider — just page files and strings.

The rule (spec §5): `grounded` means the quote is a substring of the page fetched
THIS run for its source_url. Whitespace runs collapse to a single space before
comparison; case is preserved. Every further loosening is a hole in the check —
add none without a test proving the specific false-failure it fixes."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from temporalio import activity

from ..models import ResearchBrief

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace runs to one space; preserve case."""
    return _WS.sub(" ", text).strip()


def page_filename(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest() + ".txt"


def pages_dir(run_id: str) -> Path:
    """runs/<run_id>/research/pages. Root from $SDLC_RUNS_ROOT (default 'runs').
    Resolved activity-side only — the workflow never computes this."""
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    return root / run_id / "research" / "pages"


class Violation(BaseModel):
    kind: Literal["quote_not_found", "source_never_fetched"]
    source_url: str
    quote: str


def verify_brief(brief: ResearchBrief, run_id: str) -> list[Violation]:
    d = pages_dir(run_id)
    violations: list[Violation] = []
    for f in brief.grounded_findings:
        page = d / page_filename(f.source_url)
        if not page.is_file():
            violations.append(Violation(kind="source_never_fetched",
                                        source_url=f.source_url, quote=f.quote))
            continue
        haystack = normalize(page.read_text(encoding="utf-8"))
        if normalize(f.quote) not in haystack:
            violations.append(Violation(kind="quote_not_found",
                                        source_url=f.source_url, quote=f.quote))
    return violations


def brief_digest(brief: ResearchBrief) -> str:
    """The brief's contribution to downstream content_key (spec §7): a canonical
    hash of (source_url, claim) pairs only. Prose, ordering, and confidence drop
    out; facts remain. Same facts -> same digest -> clarify's memo hits."""
    pairs = sorted((f.source_url, f.claim) for f in brief.grounded_findings)
    payload = json.dumps(pairs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class GroundingViolation(Exception):
    """Raised by verify_brief_activity when a ResearchBrief has grounded_findings
    that cannot be verified against bytes fetched this run. The workflow (Task 8)
    catches this and fails the research stage closed — it is NOT a ModelRetry,
    because TemporalAgent silently drops @agent.output_validator (Task 1 finding
    A); a hard stage failure is the authorized post-run fallback semantics."""

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(
            f"- {v.kind}: {v.source_url}: {v.quote!r}" for v in violations)
        super().__init__(
            "Grounded findings are not verified against bytes fetched this run. "
            "The research stage fails closed. Fix the quote to a verbatim span "
            "from a page fetched this run, or move the claim to "
            "inferred_findings. Violations:\n" + lines)


@activity.defn
async def verify_brief_activity(brief: ResearchBrief, run_id: str) -> None:
    """Temporal activity: verify a ResearchBrief's grounded_findings against the
    page files fetched this run. Raises GroundingViolation on any violation;
    returns None otherwise. Registered on the worker and called from the
    research workflow (Task 8) AFTER the research agent produces its brief.

    This is the authorized fallback for Task 1 finding A: the original design
    used @agent.output_validator + ModelRetry, which TemporalAgent silently
    drops. This activity runs activity-side (where reading page files is legal
    I/O), fails the stage closed on a violation, and gives the model no retry
    — stricter than ModelRetry, but correct under temporalization."""
    violations = verify_brief(brief, run_id)
    if violations:
        raise GroundingViolation(violations)
