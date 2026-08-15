# tests/test_risk_severity.py
"""RD4: criticality is derived, severity is a table, and absence never
becomes a rating."""
from __future__ import annotations

import random

from sdlc.assessment.risk.models import Criticality, Severity
from sdlc.assessment.risk.severity import criticality, severity
from sdlc.assessment.scan.models import (
    CandidateMember, Confidence, MemberKind, Sensitivity, SensitivityRecord,
)
from sdlc.measurement import CollectionState

from tests.helpers_risk import capability


def _sens(kind: Sensitivity) -> SensitivityRecord:
    return SensitivityRecord(classification=kind, entity="customer",
                             origin="table", fields=["email"], rule="r",
                             confidence=Confidence.HIGH)


def _route(value: str = "POST /api/pay") -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value,
                           path="src/a.py")


def test_regulated_data_plus_a_reachable_route_is_high():
    r = criticality(capability(sensitivity=(_sens(Sensitivity.HEALTH),),
                               members=(_route(),)),
                    sensitivity_collected=True)
    assert r.level is Criticality.HIGH


def test_no_sensitivity_and_no_route_is_low_when_ss4_collected():
    r = criticality(capability(), sensitivity_collected=True)
    assert r.level is Criticality.LOW


def test_no_sensitivity_is_not_collected_when_ss4_did_not_collect():
    """RD4: SensitivityRecord.accessed_by warns that an empty list must never
    read as 'no entry point touches PII'. A criticality derived from that
    emptiness would launder the warning into a rating."""
    r = criticality(capability(), sensitivity_collected=False)
    assert r.level is None
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "SS4" in r.collected.reason


def test_a_high_hint_on_a_high_criticality_capability_is_critical():
    r = criticality(capability(sensitivity=(_sens(Sensitivity.PII),),
                               members=(_route(),)),
                    sensitivity_collected=True)
    assert severity("high", r, Confidence.HIGH) is Severity.CRITICAL


def test_low_confidence_never_raises_severity():
    r = criticality(capability(), sensitivity_collected=True)
    high = severity("high", r, Confidence.HIGH)
    low = severity("high", r, Confidence.LOW)
    order = [s.value for s in Severity]
    assert order.index(low.value) >= order.index(high.value)


def test_uncollected_criticality_scores_the_hint_at_medium_criticality():
    """An unrated capability must not silently score as LOW -- that would be
    the same conflation, one layer down."""
    r = criticality(capability(), sensitivity_collected=False)
    assert severity("high", r, Confidence.HIGH) is Severity.HIGH


def test_criticality_is_order_independent():
    """NFR-10."""
    records = [_sens(Sensitivity.PII), _sens(Sensitivity.FINANCIAL)]
    members = [_route("POST /a"), _route("GET /b")]
    first = None
    for _ in range(5):
        random.shuffle(records)
        random.shuffle(members)
        out = criticality(
            capability(sensitivity=tuple(records), members=tuple(members)),
            sensitivity_collected=True).model_dump_json()
        first = first if first is not None else out
        assert out == first
