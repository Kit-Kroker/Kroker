# tests/test_risk_controls.py
"""RD5: five families over three sources, and the two gaps say so."""
from __future__ import annotations

import random

from sdlc.assessment.risk.controls import controls
from sdlc.assessment.risk.models import (
    ControlFamily, ControlState,
)
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, C_DB_SECURITY, C_INPUT_VALIDATION, C_TLS, Confidence,
    ScanSignalId, SecurityObservation,
)
from sdlc.measurement import CollectionState

from tests.helpers_risk import capability

ALL = frozenset({C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY})


def _obs(category: str, rule: str = "r",
         signal: ScanSignalId = ScanSignalId.SS1) -> SecurityObservation:
    return SecurityObservation(
        signal=signal, category=category, rule=rule, detail="d",
        severity_hint="medium", path="src/a.py", confidence=Confidence.HIGH)


def _by(rows, family):
    return next(r for r in rows if r.family is family)


def test_always_five_families_in_declaration_order():
    rows = controls(capability(), collected_categories=ALL)
    assert tuple(r.family for r in rows) == tuple(ControlFamily)


def test_authorization_has_no_source_and_does_not_mirror_authentication():
    rows = controls(capability(security=(_obs(C_AUTHN_AUTHZ),)),
                    collected_categories=ALL)
    authz = _by(rows, ControlFamily.AUTHORIZATION)
    assert authz.state is None
    assert authz.collected.state is CollectionState.NOT_COLLECTED
    assert "collapses" in authz.collected.reason


def test_monitoring_has_no_source():
    rows = controls(capability(), collected_categories=ALL)
    mon = _by(rows, ControlFamily.MONITORING)
    assert mon.state is None
    assert "monitoring presence" in mon.collected.reason


def test_an_observation_in_a_family_marks_it_absent():
    """A security observation IS a weakness, so its presence means the
    control is not doing its job."""
    rows = controls(capability(security=(_obs(C_INPUT_VALIDATION),)),
                    collected_categories=ALL)
    assert _by(rows, ControlFamily.VALIDATION).state is ControlState.ABSENT


def test_no_observation_in_a_collected_family_is_present():
    rows = controls(capability(), collected_categories=ALL)
    assert _by(rows, ControlFamily.VALIDATION).state is ControlState.PRESENT


def test_a_family_whose_category_did_not_collect_is_not_collected():
    """A signal that did not report is not a clean control."""
    rows = controls(capability(), collected_categories=frozenset({C_TLS}))
    val = _by(rows, ControlFamily.VALIDATION)
    assert val.state is None
    assert C_INPUT_VALIDATION in val.collected.reason


def test_encryption_needs_every_one_of_its_categories():
    rows = controls(capability(), collected_categories=frozenset({C_TLS}))
    enc = _by(rows, ControlFamily.ENCRYPTION)
    assert enc.state is None
    assert C_DB_SECURITY in enc.collected.reason


def test_controls_are_order_independent():
    """NFR-10."""
    obs = [_obs(C_INPUT_VALIDATION, "a"), _obs(C_TLS, "b"),
           _obs(C_AUTHN_AUTHZ, "c")]
    first = None
    for _ in range(5):
        random.shuffle(obs)
        rows = controls(capability(security=tuple(obs)),
                        collected_categories=ALL)
        out = "|".join(r.model_dump_json() for r in rows)
        first = first if first is not None else out
        assert out == first
