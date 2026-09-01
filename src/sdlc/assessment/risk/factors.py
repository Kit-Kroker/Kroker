"""The inputs to each composite, each carrying its own Measurement.

Per-factor Measurements are what make `partial` derivable (RD3): the
composite reads partiality off its factors rather than storing it.

Every factor is normalized so that HIGHER MEANS WORSE, because the composites
are risk scores. coverage_gap rather than coverage is the visible consequence.

Pure by design -- see the package docstring in models.py.
"""

from __future__ import annotations

from ...measurement import CollectionState, Measurement
from ..discover.map import Capability
from .models import ControlCoverage, ControlState, Criticality, CriticalityRating, Factor
from .rules import (
    F_CHANGE_VELOCITY,
    F_COVERAGE_GAP,
    F_DEFECT_DENSITY,
    F_EXPOSURE,
    F_IMPACT,
    F_LIKELIHOOD,
    F_TESTABILITY,
    QA_WEIGHTS,
    SECURITY_WEIGHTS,
    UNSOURCED_QA,
)
from .severity import REACHABLE_KINDS

_IMPACT_BY_CRITICALITY = {
    Criticality.HIGH: 1.0,
    Criticality.MEDIUM: 0.5,
    Criticality.LOW: 0.2,
}
_TESTABILITY_WEIGHT = {"blocks": 1.0, "impedes": 0.5, "smell": 0.2}


def _f(key: str, value: Measurement, weights: dict[str, float]) -> Factor:
    return Factor(key=key, value=value, weight=weights[key])


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def security_factors(
    cap: Capability,
    *,
    rating: CriticalityRating,
    controls_rows: tuple[ControlCoverage, ...],
    collected_categories: frozenset[str],
) -> tuple[Factor, ...]:
    """likelihood, impact, exposure -- FR-916's three security terms."""
    # Likelihood: how much security evidence this capability actually carries,
    # saturating rather than growing without bound.
    if collected_categories:
        n = len(cap.security)
        likelihood = Measurement.measured(_clamp(n / 5.0))
    else:
        likelihood = Measurement.not_collected(
            "likelihood needs at least one security category to have reported; none did"
        )

    # Impact: what the capability would cost if compromised. Derived from
    # criticality, so an unrated capability yields an uncollected impact
    # rather than a default (RD4).
    if rating.level is None:
        impact = Measurement.not_collected(
            f"impact is derived from criticality, which did not collect: {rating.collected.reason}"
        )
    else:
        impact = Measurement.measured(_IMPACT_BY_CRITICALITY[rating.level])

    # Exposure: reachable surface, raised by controls known to be absent.
    reachable = sum(1 for m in cap.members if m.kind in REACHABLE_KINDS)
    absent = sum(1 for c in controls_rows if c.state is ControlState.ABSENT)
    exposure = Measurement.measured(
        _clamp(0.5 * _clamp(reachable / 3.0) + 0.5 * _clamp(absent / 3.0))
    )

    return tuple(
        sorted(
            (
                _f(F_LIKELIHOOD, likelihood, SECURITY_WEIGHTS),
                _f(F_IMPACT, impact, SECURITY_WEIGHTS),
                _f(F_EXPOSURE, exposure, SECURITY_WEIGHTS),
            ),
            key=lambda f: f.key,
        )
    )


def qa_factors(
    cap: Capability, *, coverage_collected: bool, testability_collected: bool
) -> tuple[Factor, ...]:
    """coverage gap, testability, defect density, change velocity.

    The last two are RD3's: no signal supplies them, so they report
    not_collected naming what would, and the composite derives partial.
    """
    if not coverage_collected:
        gap = Measurement.not_collected("coverage_gap needs QS2, which did not collect")
    elif not cap.coverage:
        gap = Measurement.not_collected(
            "coverage_gap: QS2 collected but produced no record for this capability's files"
        )
    else:
        rates = [
            v
            for r in cap.coverage
            if r.covered.state is CollectionState.MEASURED and (v := r.covered.value) is not None
        ]
        gap = (
            Measurement.measured(_clamp(1.0 - (sum(rates) / len(rates)) / 100.0))
            if rates
            else Measurement.not_collected(
                "coverage_gap: every coverage record for this capability is itself uncollected"
            )
        )

    if not testability_collected:
        test = Measurement.not_collected("testability needs QS3, which did not collect")
    else:
        weights = [_TESTABILITY_WEIGHT[f.severity] for f in cap.testability]
        test = Measurement.measured(_clamp(sum(weights) / 3.0) if weights else 0.0)

    return tuple(
        sorted(
            (
                _f(F_COVERAGE_GAP, gap, QA_WEIGHTS),
                _f(F_TESTABILITY, test, QA_WEIGHTS),
                _f(
                    F_DEFECT_DENSITY,
                    Measurement.not_collected(UNSOURCED_QA[F_DEFECT_DENSITY]),
                    QA_WEIGHTS,
                ),
                _f(
                    F_CHANGE_VELOCITY,
                    Measurement.not_collected(UNSOURCED_QA[F_CHANGE_VELOCITY]),
                    QA_WEIGHTS,
                ),
            ),
            key=lambda f: f.key,
        )
    )
