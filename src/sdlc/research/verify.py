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
