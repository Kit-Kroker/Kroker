# tests/test_risk_prompt.py
"""Bounded, deterministic rendering of the baseline for the proposer."""
from __future__ import annotations

import random

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.discover.models import (
    AttributionReport, FileBucket, ReferenceGraph,
)
from sdlc.assessment.risk.build import build
from sdlc.assessment.risk.prompt import render_risk_prompt
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, C_DATA_SENSITIVITY, C_DB_SECURITY, C_INPUT_VALIDATION,
    C_TLS, CandidateMember, Confidence, MemberKind, ScanSignalId,
    SecurityObservation, Sensitivity, SensitivityRecord,
)
from sdlc.measurement import Measurement

from tests.helpers_risk import capability

ALL = frozenset([C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY,
                 C_DATA_SENSITIVITY])


def _obs(rule: str, path: str = "a.py") -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1, category=C_AUTHN_AUTHZ, rule=rule,
        detail="d", severity_hint="high", path=path, line=3,
        confidence=Confidence.HIGH)


def _cmap(*caps) -> CapabilityMap:
    """`by_action` is DERIVED and validated against the rows: CapabilityMap
    raises on "capabilities carry actions absent from by_action", so an empty
    dict is not a shortcut here."""
    actions: dict = {}
    for c in caps:
        a = c.disposition.action
        actions[a] = actions.get(a, 0) + 1
    return CapabilityMap(capabilities=tuple(caps), by_action=actions,
                         collected=Measurement.measured(1.0))


def _rendered(*caps, **kw) -> str:
    cmap = _cmap(*caps)
    return render_risk_prompt(cmap, build(cmap, collected_categories=ALL),
                              **kw)


def test_it_names_every_capability_and_its_five_control_families():
    out = _rendered(capability("BC-001", security=(_obs("r1"),)))
    assert "BC-001" in out and "Payments" in out
    for family in ("authentication", "authorization", "validation",
                   "monitoring", "encryption"):
        assert family in out


def test_an_uncollected_family_renders_its_reason_not_a_state():
    """RD5: the model must not read authorization's silence as 'present'."""
    out = _rendered(capability("BC-001", security=(_obs("r1"),)))
    assert "authorization: (not collected:" in out


def test_it_renders_the_computed_severity_so_the_model_never_assigns_one():
    out = _rendered(capability("BC-001", security=(_obs("r1"),)))
    assert "severity=" in out


def test_members_beyond_the_cap_are_announced_not_dropped_silently():
    caps = capability("BC-001",
                      security=tuple(_obs(f"r{i}") for i in range(5)))
    out = _rendered(caps, max_vulnerabilities=2)
    assert "3 more vulnerability row(s) not shown" in out


def test_rendering_is_order_independent():
    """NFR-10."""
    caps = [capability("BC-001", security=(_obs("a"),)),
            capability("BC-002", security=(_obs("b"),)),
            capability("BC-003")]
    first = None
    for _ in range(5):
        random.shuffle(caps)
        out = _rendered(*caps)
        first = first if first is not None else out
        assert out == first


def _attribution(edges, parsed=("a.py", "b.py")) -> AttributionReport:
    return AttributionReport(
        files=(), counts={b: 0 for b in FileBucket},
        coverage=Measurement.measured(1.0), meets_floor=True,
        graph=ReferenceGraph(
            edges=tuple(edges), parsed=tuple(parsed),
            unresolved_relative_rate=Measurement.not_collected("no imports")))


def _world():
    entry = capability(
        "BC-001", member_paths=("a.py",),
        members=(CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="GET /orders", path="a.py"),),
        security=(_obs("a.py"),))
    store = capability(
        "BC-002", member_paths=("b.py",), security=(_obs("b.py"),),
        sensitivity=(SensitivityRecord(
            classification=Sensitivity.PII, entity="customer", origin="table",
            fields=["email"], rule="ss4_field_name",
            confidence=Confidence.HIGH),))
    return [entry, store], _attribution([("a.py", "b.py")])


def test_the_prompt_renders_the_system_candidates():
    """The proposer cannot disposition a candidate it was never shown."""
    caps, attribution = _world()
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    cmap = CapabilityMap(capabilities=tuple(caps), by_action=actions,
                         attribution=attribution,
                         collected=Measurement.measured(1.0))
    baseline = build(cmap, collected_categories=ALL)
    text = render_risk_prompt(cmap, baseline)
    assert "# System View" in text
    assert "BC-001 -> BC-002" in text
    assert "BC-001->BC-002" in text


def test_an_uncollected_system_family_renders_its_reason_not_a_zero():
    caps, _ = _world()
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    cmap = CapabilityMap(capabilities=tuple(caps), by_action=actions,
                         collected=Measurement.measured(1.0))
    text = render_risk_prompt(cmap, build(cmap, collected_categories=ALL))
    assert "not collected" in text

