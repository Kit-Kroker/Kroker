# src/sdlc/assessment/discover/verify.py
"""FR-913/FR-914 (E-48 DD8 items 4-5): references resolved, quotes verified.

The row-level logic moved to assessment/verification.py with E-49 RD6, so
one fail-closed grounding invariant serves both proposers. What stays here is
the TYPED wrapper: E-48's call sites do not change shape, and RefVerification
is still what the verify_discover_refs activity returns across the Temporal
boundary.

A violation drops the ITEM, never the phase (DD8). The phase-level guard
lives in the workflow, which is the only place that can turn a rate into a
not_collected PhaseResult.
"""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from ..verification import cited_paths_of, verify_rows
from .map import DiscoverProposal, ProposedDisposition  # noqa: F401


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


def verify_refs(proposal: DiscoverProposal,
                blobs: Mapping[str, str | None]) -> RefVerification:
    """DD8 items 4-5 over every disposition.

    `blobs` maps every path the proposal cited to its bytes at the pinned
    commit, or None when it did not resolve. The caller reads them;
    verification.verify_rows decides.
    """
    out = verify_rows(proposal.dispositions, blobs,
                      id_of=lambda row: row.candidate_id)
    return RefVerification(
        proposal=DiscoverProposal(dispositions=list(out.survivors)),
        refusals=out.refusals, total_references=out.total_references,
        unresolved_references=out.unresolved_references)


def cited_paths(proposal: DiscoverProposal) -> tuple[str, ...]:
    """Every path the proposal cites, sorted and deduped -- the activity's
    read list."""
    return cited_paths_of(proposal.dispositions)
