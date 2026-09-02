# tests/helpers_risk.py
"""One Capability builder shared by every risk test, so a contract change
lands in one place rather than in nine test files."""

from __future__ import annotations

from sdlc.assessment.discover.map import (
    CandidateDisposition,
    Capability,
    CapabilityMap,
    DiscoverAction,
    DispositionSource,
)
from sdlc.assessment.risk.models import (
    CapabilityRisk,
    Composite,
    ControlCoverage,
    ControlFamily,
    CriticalityRating,
    StrideCategory,
    ThreatAssessment,
)
from sdlc.assessment.scan.models import Confidence
from sdlc.measurement import Measurement


def capability(bc_id: str = "BC-001", **kw) -> Capability:
    base = dict(
        bc_id=bc_id,
        local_key="c1",
        name="Payments",
        confidence=Confidence.HIGH,
        members=(),
        member_paths=(),
        cohesion=Measurement.measured(0.8),
        coupling=Measurement.measured(0.2),
        disposition=CandidateDisposition(
            candidate_id="c1",
            action=DiscoverAction.CONFIRM,
            source=DispositionSource.BASELINE,
            rule="baseline",
        ),
    )
    base.update(kw)
    return Capability(**base)


def capability_risk(bc_id: str = "BC-001", **kw) -> CapabilityRisk:
    """A structurally complete CapabilityRisk with sensible defaults,
    shared by every gates test so a contract change lands in one place."""
    no_score = Composite(value=Measurement.not_collected("no factors"))
    base = dict(
        bc_id=bc_id,
        criticality=CriticalityRating(collected=Measurement.not_collected("SS4 did not collect")),
        threats=tuple(
            ThreatAssessment(category=c, applicable=False, rationale="no data flow of this shape")
            for c in StrideCategory
        ),
        controls=tuple(
            ControlCoverage(family=f, collected=Measurement.not_collected("x"), rule="r")
            for f in ControlFamily
        ),
        security=no_score,
        qa=no_score,
        unified=no_score,
    )
    base.update(kw)
    return CapabilityRisk(**base)


def capability_map(*caps) -> CapabilityMap:
    """A CapabilityMap with by_action derived from the given capabilities'
    dispositions -- `_counts_are_derived` rejects an action present on a
    capability but absent from by_action, so every fixture must supply it
    (mirrors test_risk_build.py's _cmap)."""
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(
        capabilities=tuple(caps), by_action=actions, collected=Measurement.measured(1.0)
    )
