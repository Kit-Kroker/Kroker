"""S5 -- cross-source merge and confidence (FR-912, D8/D9).

Runs in WORKFLOW code (in_workflow=True): it is a pure derivation over other
signals' output and reads no tree, so an activity would buy nothing and cost
a round trip. Same reason compute_readiness runs inside TriageWorkflow.

Two merge rules and no more:

  1. Merge on normalized name (naming.normalize -- strip layer suffix,
     lowercase, singularize).
  2. Overlapping members under different names -> do NOT merge. Emit both,
     flag each with possible_duplicate_of.

Rule 2 is BrownKit's non-collapse rule ported verbatim, and it is what makes
S5 safe: it never has to be RIGHT, only never silently wrong. Deciding a
genuine merge is E-48's D2 (CONFIRM | SPLIT | MERGE | DE-SCOPE | FLAG), a
proposer with the context to do it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from ...measurement import CollectionState, Measurement
from .models import (
    CandidateMember, ScanCandidate, ScanSignalId, SourceCandidate,
    confidence_from, signal_of,
)
from .naming import normalize

SIGNAL_ID = "S5"
VERSION = 1

# D11: BrownKit hard-gates /scan on producing 15-25 candidates and re-extracts
# when under. Ported as an ADVISORY only -- its band comes from enterprise
# Java monoliths, and Tier 0's rationale is that target repositories are small
# and vibe-coded, where a 40-file Next.js application legitimately has four
# capabilities. A binding version belongs in E-51's CheckResults.
CANDIDATE_BAND: tuple[int, int] = (15, 25)


class MergeOutput(BaseModel):
    candidates: list[ScanCandidate] = Field(default_factory=list)
    collected: Measurement


def _overlaps(a: frozenset[CandidateMember],
              b: frozenset[CandidateMember]) -> bool:
    """Sharing ANY member is enough to flag. Deliberately generous: an
    over-flag costs E-48 one decision it was going to make anyway, while an
    under-flag is a silent collapse -- the exact failure rule 2 exists to
    prevent."""
    return bool(a & b)


def merge(sources: Sequence[SourceCandidate],
          upstream: Mapping[ScanSignalId, Measurement]) -> MergeOutput:
    """`upstream` is each consumed signal's row-level `collected`, which is
    what separates "merged zero because there was nothing" (a gap) from
    "merged zero because the sources found none" (a real zero)."""
    groups: dict[str, list[SourceCandidate]] = {}
    for candidate in sources:
        key = normalize(candidate.name) or candidate.name.strip().lower()
        groups.setdefault(key, []).append(candidate)

    ordered = sorted(groups.items())
    member_sets = [frozenset(m for c in group for m in c.members)
                   for _, group in ordered]
    ids = [f"C-{i:02d}" for i in range(1, len(ordered) + 1)]

    candidates: list[ScanCandidate] = []
    for index, (key, group) in enumerate(ordered):
        local_ids = sorted({c.local_id for c in group})
        candidates.append(ScanCandidate(
            candidate_id=ids[index],
            # The alphabetically-first raw name, so the display name is a
            # name a source actually used rather than one this function
            # invented from the normalized key.
            name=sorted(c.name for c in group)[0],
            sources=local_ids,
            confidence=confidence_from(signal_of(i) for i in local_ids),
            members=sorted(member_sets[index],
                           key=CandidateMember.sort_key),
            possible_duplicate_of=sorted(
                ids[other] for other in range(len(ordered))
                if other != index
                and _overlaps(member_sets[index], member_sets[other]))))

    if candidates:
        return MergeOutput(candidates=candidates,
                           collected=Measurement.measured(float(len(candidates))))

    unmeasured = sorted(
        s.value for s, m in upstream.items()
        if m.state is not CollectionState.MEASURED)
    if unmeasured:
        # Merging nothing because every source failed is not a measured zero
        # (FR-915). Naming the signals is what tells an operator whether the
        # repository has no capabilities or the scan could not see them.
        return MergeOutput(collected=Measurement.not_collected(
            f"candidate_merge: no source candidates, and {unmeasured} did "
            f"not collect -- a merge over nothing is not a measured zero"))
    return MergeOutput(collected=Measurement.measured(0.0))
