# tests/test_risk_factors.py
"""The composite inputs. Two QA factors have no source and stay that way."""

from __future__ import annotations

import random

from sdlc.assessment.risk.controls import controls
from sdlc.assessment.risk.factors import qa_factors, security_factors
from sdlc.assessment.risk.models import Criticality, CriticalityRating
from sdlc.assessment.risk.rules import (
    F_CHANGE_VELOCITY,
    F_COVERAGE_GAP,
    F_DEFECT_DENSITY,
    F_EXPOSURE,
    F_IMPACT,
    F_LIKELIHOOD,
    F_TESTABILITY,
)
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_DB_SECURITY,
    C_INPUT_VALIDATION,
    C_TLS,
    CandidateMember,
    Confidence,
    CoverageRecord,
    MemberKind,
    TestabilityFinding,
)
from sdlc.measurement import CollectionState, Measurement
from tests.helpers_risk import capability

ALL = frozenset({C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY})
RATED = CriticalityRating(level=Criticality.HIGH, collected=Measurement.measured(1.0))


def _keys(factors):
    return [f.key for f in factors]


def _get(factors, key):
    return next(f for f in factors if f.key == key)


def test_security_factors_are_the_three_fr916_names_sorted():
    rows = controls(capability(), collected_categories=ALL)
    out = security_factors(capability(), rating=RATED, controls_rows=rows, collected_categories=ALL)
    assert _keys(out) == sorted([F_EXPOSURE, F_IMPACT, F_LIKELIHOOD])


def test_qa_factors_are_the_four_fr916_names_sorted():
    out = qa_factors(capability(), coverage_collected=True, testability_collected=True)
    assert _keys(out) == sorted(
        [F_CHANGE_VELOCITY, F_COVERAGE_GAP, F_DEFECT_DENSITY, F_TESTABILITY]
    )


def test_defect_density_and_change_velocity_never_collect():
    """RD3. These two are the whole reason the QA composite is partial."""
    out = qa_factors(capability(), coverage_collected=True, testability_collected=True)
    for key in (F_DEFECT_DENSITY, F_CHANGE_VELOCITY):
        f = _get(out, key)
        assert f.value.state is CollectionState.NOT_COLLECTED
        assert f.value.reason


def test_defect_density_names_enrich_as_what_would_supply_it():
    out = qa_factors(capability(), coverage_collected=True, testability_collected=True)
    assert "E-56" in _get(out, F_DEFECT_DENSITY).value.reason


def test_coverage_gap_is_one_minus_coverage():
    cap = capability(
        coverage=(
            CoverageRecord(
                scope="file",
                path="src/a.py",
                covered=Measurement.measured(80.0),
                source="report",
                tool="cobertura",
                confidence=Confidence.HIGH,
            ),
        )
    )
    out = qa_factors(cap, coverage_collected=True, testability_collected=True)
    assert abs(_get(out, F_COVERAGE_GAP).value.value - 0.2) < 1e-9


def test_coverage_gap_is_not_collected_when_qs2_did_not_collect():
    out = qa_factors(capability(), coverage_collected=False, testability_collected=True)
    f = _get(out, F_COVERAGE_GAP)
    assert f.value.state is CollectionState.NOT_COLLECTED
    assert "QS2" in f.value.reason


def test_a_blocking_testability_finding_scores_higher_than_a_smell():
    def score(sev):
        cap = capability(
            testability=(
                TestabilityFinding(
                    severity=sev,
                    pattern="static-clock",
                    detail="d",
                    recommended_seam="inject",
                    path="src/a.py",
                ),
            )
        )
        return _get(
            qa_factors(cap, coverage_collected=True, testability_collected=True), F_TESTABILITY
        ).value.value

    assert score("blocks") > score("smell")


def test_exposure_rises_with_a_reachable_route():
    rows = controls(capability(), collected_categories=ALL)
    bare = security_factors(
        capability(), rating=RATED, controls_rows=rows, collected_categories=ALL
    )
    routed = security_factors(
        capability(
            members=(CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /a", path="src/a.py"),)
        ),
        rating=RATED,
        controls_rows=rows,
        collected_categories=ALL,
    )
    assert _get(routed, F_EXPOSURE).value.value > _get(bare, F_EXPOSURE).value.value


def test_impact_is_not_collected_when_criticality_is_not_collected():
    rows = controls(capability(), collected_categories=ALL)
    unrated = CriticalityRating(collected=Measurement.not_collected("SS4 did not collect"))
    out = security_factors(
        capability(), rating=unrated, controls_rows=rows, collected_categories=ALL
    )
    assert _get(out, F_IMPACT).value.state is CollectionState.NOT_COLLECTED


def test_factors_are_order_independent():
    """NFR-10."""
    findings = [
        TestabilityFinding(
            severity="blocks", pattern="a", detail="d", recommended_seam="s", path="src/a.py"
        ),
        TestabilityFinding(
            severity="smell", pattern="b", detail="d", recommended_seam="s", path="src/b.py"
        ),
    ]
    first = None
    for _ in range(5):
        random.shuffle(findings)
        out = "|".join(
            f.model_dump_json()
            for f in qa_factors(
                capability(testability=tuple(findings)),
                coverage_collected=True,
                testability_collected=True,
            )
        )
        first = first if first is not None else out
        assert out == first
