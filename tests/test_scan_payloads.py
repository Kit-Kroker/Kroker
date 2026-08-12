"""SS4 and QS3 payloads. Typed apart from SourceCandidate because their
shapes share nothing with it (E-45's no-untyped-bag rule, applied within
scan)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    Confidence, EvidenceRef, Sensitivity, SensitivityRecord,
    TestabilityFinding, testability_identity,
)


def test_sensitivity_record_carries_its_accessors_by_local_id():
    r = SensitivityRecord(
        classification=Sensitivity.PII, entity="customers", origin="table",
        fields=["email", "phone"], accessed_by=["S3-customers"],
        evidence=[EvidenceRef(path="migrations/0002_customers.sql")],
        rule="ss4_pii_field_name", confidence=Confidence.MEDIUM)
    assert r.accessed_by == ["S3-customers"]
    assert r.fields == ["email", "phone"]


def test_empty_accessed_by_is_allowed_and_means_unknown_not_none():
    """When S3 reported not_collected, SS4 has no accessors to cite. The
    owing category's reason says so; this field must not be read as
    'no entry point touches PII' (D5, section 5)."""
    r = SensitivityRecord(
        classification=Sensitivity.FINANCIAL, entity="Payment",
        origin="model", fields=["card_last4"], evidence=[],
        rule="ss4_financial_field_name", confidence=Confidence.LOW)
    assert r.accessed_by == []


def test_testability_severity_is_brownkit_three_valued():
    f = TestabilityFinding(
        severity="blocks", pattern="static-clock-access",
        detail="DateTime.Now read inside a branch.",
        recommended_seam="Inject a clock", path="src/sched.py", line=142)
    assert f.severity == "blocks"
    with pytest.raises(ValidationError):
        f.model_copy(update={"severity": "critical"}).model_validate(
            f.model_dump() | {"severity": "critical"})


def test_testability_identity_is_delta_stable_and_ignores_line():
    """E-44 D3: a fix landing above a finding shifts its line, and an identity
    keyed on line would report a phantom resolved+new pair."""
    a = TestabilityFinding(
        severity="impedes", pattern="global-state", detail="d",
        recommended_seam="s", path="src/a.py", line=10, key="CACHE")
    b = a.model_copy(update={"line": 99})
    assert testability_identity(a) == testability_identity(b)
    assert "src/a.py" in testability_identity(a)
    assert "CACHE" in testability_identity(a)


def test_two_patterns_on_one_path_need_distinct_keys():
    a = TestabilityFinding(severity="smell", pattern="p", detail="d",
                           recommended_seam="s", path="src/a.py", key="X")
    b = a.model_copy(update={"key": "Y"})
    assert testability_identity(a) != testability_identity(b)
