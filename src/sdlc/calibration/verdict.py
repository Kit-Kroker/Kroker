"""C7: the agreement statistic behind a gate's confidence.

Reuses benchmarks/calibration.py's compute_agreement rather than inventing a
second statistic (spec 4.1) -- but over a different population: self-reported
confidence vs. a realized-outcome label, not judge score vs. human score.
"""

from __future__ import annotations

from ..benchmarks.calibration import compute_agreement
from .models import INSUFFICIENT, CalibrationVerdict, LabelSource

# Ruling OQ3: a bucket must produce this many labelled samples before its
# confidence may skip a human. Sample-level, not run-level.
MIN_SAMPLES = 20

# Ruling OQ5: rolling, so a prompt or model change can earn trust back
# instead of being outvoted forever by stale samples.
WINDOW = 200

# Ruling OQ9(3): inherited from the rubric-judge loop at cold start, to be
# re-derived from real collected samples once the ledger has them. They were
# tuned against a different population; treat them as a starting position.
THRESHOLD = 0.75
EPSILON = 0.15


def bucket_key(author_model: str | None, source: LabelSource) -> str:
    """Ruling OQ4 + OQ6. The source is folded IN rather than kept as a filter
    the caller could forget: pooling the two populations then requires
    building a different key on purpose."""
    return f"{author_model or '_unknown'}|{source.value}"


def verdict_for(pairs: list[tuple[float, float]]) -> CalibrationVerdict:
    """`pairs` are (confidence, outcome_label). Below MIN_SAMPLES the answer
    is insufficient_data -- not 'uncalibrated', which would be a claim the
    data cannot support either."""
    if len(pairs) < MIN_SAMPLES:
        return CalibrationVerdict(verdict="insufficient_data", n=len(pairs))
    stats = compute_agreement(pairs, epsilon=EPSILON, threshold=THRESHOLD)
    return CalibrationVerdict(verdict=stats.verdict, n=stats.n, agreement_rate=stats.agreement_rate)


__all__ = [
    "EPSILON",
    "INSUFFICIENT",
    "MIN_SAMPLES",
    "THRESHOLD",
    "WINDOW",
    "bucket_key",
    "verdict_for",
]
