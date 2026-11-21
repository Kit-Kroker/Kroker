"""FR-918 (E-51): the FINISH phase -- the 14 acceptance criteria as code.

`evaluate_finish` is the phase's one entry point: it walks the typed ids
once (`xref_domains` is called exactly here and nowhere else -- checks.py
only receives its results), feeds the walk to `evaluate_criteria` alongside
the per-phase exits from `evaluate_exits`, and merges everything into one
FinishReport. There are no separate finish rows: the 14 criteria plus the
walk ARE finish's exits (design section 5, FD14). `collected` is the honest
ratio -- passed ABSOLUTE rows over total ABSOLUTE rows across criteria +
exits; owed rows are not rows and never count (FD3).

Pure by design -- this package's own modules, `...gate` and `...measurement`
only. This module must never import assessment/models.py, activities.py, or
temporalio: the workflow (Task 5) imports FROM here, so a dependency
outward would be circular as well as impure.
"""

from __future__ import annotations

from ...gate import CheckClass
from ...measurement import Measurement
from ..discover.map import CapabilityMap
from ..risk.models import UnifiedRiskMap
from ..scan.models import ScanResult
from .checks import evaluate_criteria
from .crossref import xref_domains
from .exits import evaluate_exits
from .models import FinishReport

__all__ = ["evaluate_finish"]


def evaluate_finish(
    *,
    scan: ScanResult | None,
    scan_state: Measurement,
    discover: CapabilityMap | None,
    discover_state: Measurement,
    risk: UnifiedRiskMap | None,
    risk_state: Measurement,
) -> FinishReport:
    """The FINISH verdict over the three producer phases' artifacts.

    FD13's short-circuit (nothing measured at all) happens above this call --
    the workflow owes it, because a run that assessed nothing must not read
    as one that assessed something. Here at least one producer measured, so
    the ABSOLUTE row count is non-zero and `collected` is a real ratio --
    guarded anyway: an empty denominator stays vacuously whole, matching
    FinishReport.passed's empty-is-true semantics.
    """
    xref_checks, xref_owed = xref_domains(
        discover=discover, discover_state=discover_state, risk=risk, risk_state=risk_state
    )
    criteria, criteria_owed = evaluate_criteria(
        scan=scan,
        scan_state=scan_state,
        discover=discover,
        discover_state=discover_state,
        risk=risk,
        risk_state=risk_state,
        xref_checks=xref_checks,
        xref_owed=xref_owed,
    )
    evaluated, exit_owed = evaluate_exits(
        scan=scan,
        scan_state=scan_state,
        discover=discover,
        discover_state=discover_state,
        risk=risk,
        risk_state=risk_state,
    )
    # xref rows ARE exits (FD14): one merge, sorted, so FinishReport's
    # NFR-10 validator sees order, not discovery order.
    exits = tuple(sorted((*evaluated, *xref_checks), key=lambda c: c.name))
    owed = tuple(sorted((*criteria_owed, *xref_owed, *exit_owed)))
    absolutes = [r for r in (*criteria, *exits) if r.classification is CheckClass.ABSOLUTE]
    total = len(absolutes)
    ratio = (sum(1 for r in absolutes if r.passed) / total) if total else 1.0
    return FinishReport(
        collected=Measurement.measured(ratio), criteria=criteria, owed=owed, exits=exits
    )
