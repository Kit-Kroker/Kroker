"""The weighted sums, and RD9's drivers.

Pure by design -- see the package docstring in models.py.
"""
from __future__ import annotations

from ...measurement import Measurement
from .models import MAX_DRIVERS, Composite, Driver, Factor
from .rules import F_QA, F_SECURITY, UNIFIED_WEIGHTS


def _drivers(factors: tuple[Factor, ...]) -> tuple[Driver, ...]:
    """The three largest contributors among the COLLECTED factors.

    Sorted by contribution descending then key ascending, so ties break
    deterministically (NFR-10) rather than by input order.
    """
    rows = [
        Driver(factor_key=f.key, value=f.value.value,
               contribution=f.value.value * f.weight)
        for f in factors if f.collected
    ]
    rows.sort(key=lambda d: (-d.contribution, d.factor_key))
    return tuple(rows[:MAX_DRIVERS])


def compose(factors: tuple[Factor, ...], *, label: str) -> Composite:
    """A weighted sum over `factors`, or the reason it is not one.

    A factor that did not collect makes the composite valueless -- averaging
    over the subset would produce a number that means something different
    per run, which is FR-915's exact target. The drivers survive, because the
    collected factors are real (RD9).
    """
    missing = [f.key for f in factors if not f.collected]
    if missing:
        value = Measurement.not_collected(
            f"{label} composite: factor(s) {sorted(missing)} did not collect")
    else:
        total = sum(f.weight for f in factors)
        # A zero total weight is a rules.py bug, not a runtime condition; the
        # weight tables are asserted to sum to 1.0 in test_risk_rules_sha.
        value = Measurement.measured(
            sum(f.value.value * f.weight for f in factors) / total)
    return Composite(value=value, factors=factors,
                     drivers=_drivers(factors))


def unified(security: Composite, qa: Composite) -> Composite:
    """FR-916's unified composite over the two halves.

    Partial propagates (RD3): with defect density and change velocity
    unsourced, the QA half is valueless, so this is too -- and says which
    half. FR-916 specifies exactly this latitude.
    """
    factors = tuple(sorted(
        (Factor(key=F_SECURITY, value=security.value,
                weight=UNIFIED_WEIGHTS[F_SECURITY]),
         Factor(key=F_QA, value=qa.value, weight=UNIFIED_WEIGHTS[F_QA])),
        key=lambda f: f.key))
    return compose(factors, label="unified")
