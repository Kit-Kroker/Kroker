"""FR-913 (E-47a): per-tier Jaccard and the weighted, renormalized score.

Pure. The per-tier contributions returned alongside the total ARE the
evidence trail an attachment records -- they fall out of scoring rather than
being assembled separately, so evidence cannot drift from the decision.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import CapabilityFingerprint, SignalTier

from ..measurement import CollectionState


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """|A n B| / |A u B|. Two empty sets score 0.0 rather than raising: the
    caller never passes a pair of empty tiers, because score() drops tiers
    that are not non-empty on BOTH sides before calling this."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def score(a: CapabilityFingerprint, b: CapabilityFingerprint,
          weights: Mapping[SignalTier, float]
          ) -> tuple[float, dict[SignalTier, float]] | None:
    """Weighted Jaccard over tiers present on BOTH sides, or None when the
    pair is not comparable.

    None -- not 0.0 -- in two cases, and the distinction is FR-915's:

      * either fingerprint is not_collected. A fingerprint that could not be
        computed has not been shown to differ from anything.
      * no tier is non-empty on both sides. There is no evidence either way.

    Returning 0.0 for these would assert "definitely not the same", which is
    a claim neither case supports.

    Weights renormalize over the mutually-present tiers. Counting an absent
    Contract tier as zero would bias systematically against internal
    capabilities -- exactly those whose other signals are weakest too.
    """
    if a.collected.state is not CollectionState.MEASURED:
        return None
    if b.collected.state is not CollectionState.MEASURED:
        return None

    shared = [t for t in SignalTier
              if a.tiers.get(t) and b.tiers.get(t)]
    if not shared:
        return None

    denominator = sum(weights[t] for t in shared)
    if denominator <= 0.0:
        return None

    contributions: dict[SignalTier, float] = {
        t: jaccard(a.tiers[t], b.tiers[t]) for t in shared}
    total = sum(weights[t] * contributions[t] for t in shared) / denominator
    return total, contributions
