# tests/helpers_risk.py
"""One Capability builder shared by every risk test, so a contract change
lands in one place rather than in nine test files."""

from __future__ import annotations

from sdlc.assessment.discover.map import (
    CandidateDisposition,
    Capability,
    DiscoverAction,
    DispositionSource,
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
