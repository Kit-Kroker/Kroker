# src/sdlc/assessment/discover/verify.py
"""FR-913/FR-914 (E-48 DD8 items 4-5): references resolved, quotes verified.

Pure by design -- Pydantic, grounding.py and this package only. The blobs are
read by the `verify_discover_refs` ACTIVITY and passed in, exactly as
discover/context.py receives its inputs rather than reading the tree.

A violation drops the ITEM, never the phase (DD8). The phase-level guard lives
in the workflow, which is the only place that can turn a rate into a
not_collected PhaseResult.
"""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from ...grounding import Profile, verify_quote
from .map import DiscoverProposal, EvidenceRef, ProposedDisposition


class RefVerification(BaseModel):
    """What survived, what was refused, and the guard's two terms.

    `refusals` is candidate_id -> (rule, detail) rather than a rewritten
    disposition: stamp() owns the disposition shape, and building one here
    would be a second producer of the same row (P3-D1).
    """
    proposal: DiscoverProposal
    refusals: dict[str, tuple[str, str]] = {}
    total_references: int = 0
    unresolved_references: int = 0

    @property
    def fabrication_rate(self) -> float:
        """Zero references is a zero rate, never a division. A proposer that
        cited nothing fabricated nothing -- it is unevidenced, which is a
        different complaint and not this guard's."""
        if self.total_references == 0:
            return 0.0
        return self.unresolved_references / self.total_references


def _line_span(text: str) -> int:
    """Lines in the file. A file with no trailing newline still has its last
    line, and "" is one empty line -- both match how a reader counts."""
    return len(text.splitlines()) or 1


def _range_refusal(ref: EvidenceRef, body: str) -> str:
    """"" when the range lies inside the file. `lines` is "" for a whole-file
    reference, "42" for one line, "42-78" for a span."""
    if not ref.lines:
        return ""
    raw = ref.lines.split("-")
    try:
        start = int(raw[0])
        end = int(raw[-1])
    except ValueError:
        return "dropped_ref_line_range"
    if start < 1 or end < start or end > _line_span(body):
        return "dropped_ref_line_range"
    return ""


def _refuse(row: ProposedDisposition,
            blobs: Mapping[str, str | None]) -> tuple[str, str, int]:
    """(rule, detail, unresolved_count) for one disposition.

    ("", "", 0) means every reference resolved. The unresolved count is over
    REFERENCES (P3-D2), so a row citing three fabricated paths contributes
    three -- the guard measures citation quality, not row count.
    """
    unresolved = 0
    first_rule = ""
    first_detail = ""

    for ref in row.evidence:
        body = blobs.get(ref.path)
        # None is unresolved; "" is a resolved EMPTY file. Truthiness would
        # collapse them (read_committed_bytes' docstring states the rule).
        if body is None:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_ref_unresolved"
                first_detail = (
                    f"evidence path {ref.path!r} does not resolve at the "
                    f"pinned commit")
            continue
        refusal = _range_refusal(ref, body)
        if refusal:
            unresolved += 1
            if not first_rule:
                first_rule = refusal
                first_detail = (
                    f"evidence lines {ref.lines!r} lie outside {ref.path!r}, "
                    f"which has {_line_span(body)} line(s)")

    if row.quote:
        if not row.quote.strip():
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_empty"
                first_detail = (
                    "the quote is blank, and an empty quote grounds trivially "
                    "against any file (E-43)")
        elif not row.evidence:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_unanchored"
                first_detail = (
                    "the quote names no evidence path, so there is nothing to "
                    "verify it against")
        else:
            body = blobs.get(row.evidence[0].path)
            if body is None or not verify_quote(
                    row.quote, body, Profile.VERBATIM_BYTES):
                unresolved += 1
                if not first_rule:
                    first_rule = "dropped_quote_unverified"
                    first_detail = (
                        f"the quote does not byte-verify against "
                        f"{row.evidence[0].path!r} under VERBATIM_BYTES")

    return first_rule, first_detail, unresolved


def verify_refs(proposal: DiscoverProposal,
                blobs: Mapping[str, str | None]) -> RefVerification:
    """DD8 items 4-5 over every disposition.

    `blobs` maps every path the proposal cited to its bytes at the pinned
    commit, or None when it did not resolve. The caller reads them; this
    function decides.
    """
    survivors: list[ProposedDisposition] = []
    refusals: dict[str, tuple[str, str]] = {}
    total = 0
    unresolved_total = 0

    for row in proposal.dispositions:
        total += len(row.evidence)
        rule, detail, unresolved = _refuse(row, blobs)
        unresolved_total += unresolved
        if rule:
            # Last writer wins is fine: stamp() refuses a duplicated
            # candidate_id anyway, so two refusals for one id cannot both
            # reach the artifact.
            refusals[row.candidate_id] = (rule, detail)
        else:
            survivors.append(row)

    return RefVerification(
        proposal=DiscoverProposal(dispositions=survivors),
        refusals=refusals, total_references=total,
        unresolved_references=unresolved_total)


def cited_paths(proposal: DiscoverProposal) -> tuple[str, ...]:
    """Every path the proposal cites, sorted and deduped -- the activity's
    read list. Sorted because the activity's git reads must not depend on
    disposition order (NFR-10)."""
    return tuple(sorted({ref.path
                         for row in proposal.dispositions
                         for ref in row.evidence}))
