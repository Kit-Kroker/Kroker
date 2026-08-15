# tests/test_risk_build.py
"""RD8: an absent capability set is not_collected, never an empty map."""
from __future__ import annotations

import random

from sdlc.assessment.risk.build import build, no_risk
from sdlc.assessment.risk.models import (
    ControlFamily, RiskSource, StrideCategory,
)
from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, C_DB_SECURITY, C_INPUT_VALIDATION, C_TLS, Confidence,
    ScanSignalId, SecurityObservation, security_identity,
)
from sdlc.measurement import CollectionState, Measurement

from tests.helpers_risk import capability

ALL = frozenset({C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY})


def _cmap(*caps) -> CapabilityMap:
    actions = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(capabilities=tuple(caps),
                         by_action=actions,
                         collected=Measurement.measured(1.0))


def _obs(rule="hardcoded-secret", path="src/a.py") -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1, category=C_AUTHN_AUTHZ, rule=rule,
        detail="d", severity_hint="high", path=path,
        confidence=Confidence.HIGH)


def test_a_capability_yields_one_risk_row_with_every_structure():
    m = build(_cmap(capability()), collected_categories=ALL)
    assert m.collected.state is CollectionState.MEASURED
    row = m.capabilities[0]
    assert tuple(t.category for t in row.threats) == tuple(StrideCategory)
    assert tuple(c.family for c in row.controls) == tuple(ControlFamily)


def test_an_uncollected_capability_map_yields_not_collected_never_empty():
    """RD8 -- the malformed-SARIF hole, one tier up. Zero vulnerabilities
    over zero capabilities renders as a clean risk map."""
    m = build(CapabilityMap(collected=Measurement.not_collected("no scan")),
              collected_categories=ALL)
    assert m.collected.state is CollectionState.NOT_COLLECTED
    assert m.capabilities == ()
    assert "discover" in m.collected.reason


def test_a_measured_but_empty_capability_map_is_still_not_collected():
    """A discover phase that measured and found nothing has nothing to
    score, and a map over zero capabilities would read as clean."""
    m = build(_cmap(), collected_categories=ALL)
    assert m.collected.state is CollectionState.NOT_COLLECTED


def test_vulnerabilities_keep_the_scan_identity():
    obs = _obs()
    m = build(_cmap(capability(security=(obs,))), collected_categories=ALL)
    v = m.capabilities[0].vulnerabilities[0]
    assert v.key == security_identity(obs)
    assert v.source is RiskSource.BASELINE


def test_baseline_threats_are_all_present_and_none_are_applicable():
    """Plan 1 has no proposer: STRIDE applicability is judgment, so the
    baseline says so rather than guessing."""
    m = build(_cmap(capability(security=(_obs(),))), collected_categories=ALL)
    threats = m.capabilities[0].threats
    assert all(not t.applicable for t in threats)
    assert all("E-49 plan 2" in t.rationale for t in threats)


def test_baseline_vulnerabilities_are_potential_not_confirmed():
    """Classification is the proposer's disposition. A pattern match is
    POTENTIAL until something judges it."""
    m = build(_cmap(capability(security=(_obs(),))), collected_categories=ALL)
    v = m.capabilities[0].vulnerabilities[0]
    assert v.classification.value == "potential"


def test_capabilities_are_sorted_by_bc_id():
    m = build(_cmap(capability("BC-002"), capability("BC-001")),
              collected_categories=ALL)
    assert [c.bc_id for c in m.capabilities] == ["BC-001", "BC-002"]


def test_no_risk_carries_no_capabilities():
    m = no_risk("discover did not collect")
    assert m.capabilities == ()
    assert m.collected.state is CollectionState.NOT_COLLECTED


def test_build_is_order_independent():
    """NFR-10."""
    caps = [capability("BC-001", security=(_obs("a"),)),
            capability("BC-002", security=(_obs("b"),)),
            capability("BC-003")]
    first = None
    for _ in range(5):
        random.shuffle(caps)
        out = build(_cmap(*caps), collected_categories=ALL).model_dump_json()
        first = first if first is not None else out
        assert out == first
