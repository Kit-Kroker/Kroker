"""SS4 and QS3 payloads. Typed apart from SourceCandidate because their
shapes share nothing with it (E-45's no-untyped-bag rule, applied within
scan)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    Confidence,
    EvidenceRef,
    Sensitivity,
    SensitivityRecord,
    TestabilityFinding,
    testability_identity,
)


def test_sensitivity_record_carries_its_accessors_by_local_id():
    r = SensitivityRecord(
        classification=Sensitivity.PII,
        entity="customers",
        origin="table",
        fields=["email", "phone"],
        accessed_by=["S3-customers"],
        evidence=[EvidenceRef(path="migrations/0002_customers.sql")],
        rule="ss4_pii_field_name",
        confidence=Confidence.MEDIUM,
    )
    assert r.accessed_by == ["S3-customers"]
    assert r.fields == ["email", "phone"]


def test_empty_accessed_by_is_allowed_and_means_unknown_not_none():
    """When S3 reported not_collected, SS4 has no accessors to cite. The
    owing category's reason says so; this field must not be read as
    'no entry point touches PII' (D5, section 5)."""
    r = SensitivityRecord(
        classification=Sensitivity.FINANCIAL,
        entity="Payment",
        origin="model",
        fields=["card_last4"],
        evidence=[],
        rule="ss4_financial_field_name",
        confidence=Confidence.LOW,
    )
    assert r.accessed_by == []


def test_testability_severity_is_brownkit_three_valued():
    f = TestabilityFinding(
        severity="blocks",
        pattern="static-clock-access",
        detail="DateTime.Now read inside a branch.",
        recommended_seam="Inject a clock",
        path="src/sched.py",
        line=142,
    )
    assert f.severity == "blocks"
    with pytest.raises(ValidationError):
        f.model_copy(update={"severity": "critical"}).model_validate(
            f.model_dump() | {"severity": "critical"}
        )


def test_testability_identity_is_delta_stable_and_ignores_line():
    """E-44 D3: a fix landing above a finding shifts its line, and an identity
    keyed on line would report a phantom resolved+new pair."""
    a = TestabilityFinding(
        severity="impedes",
        pattern="global-state",
        detail="d",
        recommended_seam="s",
        path="src/a.py",
        line=10,
        key="CACHE",
    )
    b = a.model_copy(update={"line": 99})
    assert testability_identity(a) == testability_identity(b)
    assert "src/a.py" in testability_identity(a)
    assert "CACHE" in testability_identity(a)


def test_two_patterns_on_one_path_need_distinct_keys():
    a = TestabilityFinding(
        severity="smell", pattern="p", detail="d", recommended_seam="s", path="src/a.py", key="X"
    )
    b = a.model_copy(update={"key": "Y"})
    assert testability_identity(a) != testability_identity(b)


# --- plan 3: the five payload types the spec's SignalOutput note owes ------

from sdlc.assessment.scan.models import (  # noqa: E402
    PAYLOAD_FIELD,
    CiStageRecord,
    CoverageRecord,
    EnvironmentRecord,
    ScanSignalId,
    SecurityObservation,
    TestFileRecord,
    TestLevel,
    security_identity,
)
from sdlc.measurement import CollectionState, Measurement  # noqa: E402


def test_a_security_observation_declares_which_signal_owns_it():
    """P3-D1: SS1 and SS3 share ScanResult.security, and
    _unmeasured_carries_no_payload discriminates a row's own records by
    exactly this attribute."""
    o = SecurityObservation(
        signal=ScanSignalId.SS1,
        category="tls_enforcement",
        rule="ss1_tls_verification_disabled",
        detail="verify=False",
        severity_hint="high",
        path="src/client.py",
        line=12,
        evidence="requests.get(url, verify=False)",
        key="abc123",
        confidence=Confidence.HIGH,
    )
    assert o.signal is ScanSignalId.SS1
    assert security_identity(o) == "SS1:ss1_tls_verification_disabled:src/client.py:abc123"


def test_a_security_observation_must_name_a_category_its_signal_owes():
    """The row-level rule one level down: a category nobody declared cannot
    be reported, so CATEGORIES stays the one declaration."""
    with pytest.raises(ValidationError):
        SecurityObservation(
            signal=ScanSignalId.SS1,
            category="db_security",  # SS3's
            rule="r",
            detail="d",
            severity_hint="low",
            path="p",
            confidence=Confidence.LOW,
        )


def test_security_identity_ignores_line_like_its_two_siblings():
    o = SecurityObservation(
        signal=ScanSignalId.SS3,
        category="exposed_ports",
        rule="r",
        detail="d",
        severity_hint="info",
        path="Dockerfile",
        line=3,
        key="K",
        confidence=Confidence.LOW,
    )
    assert security_identity(o) == security_identity(o.model_copy(update={"line": 99}))


def test_an_unclassifiable_test_file_is_unknown_never_unit():
    """P3-D8's contract half: defaulting to unit would silently inflate the
    unit-test count, which is a measurement product's worst kind of bug."""
    r = TestFileRecord(
        path="tests/weird.py",
        level=TestLevel.UNKNOWN,
        rule="qs1_no_level_signature",
        mapping_rule="unmapped",
        confidence=Confidence.LOW,
    )
    assert r.level is TestLevel.UNKNOWN
    assert r.covers == []


def test_an_unmapped_test_covers_nothing_and_a_mapped_one_covers_something():
    with pytest.raises(ValidationError):
        TestFileRecord(
            path="t.py",
            level=TestLevel.UNIT,
            rule="r",
            mapping_rule="unmapped",
            covers=["src/a.py"],
            confidence=Confidence.LOW,
        )
    with pytest.raises(ValidationError):
        TestFileRecord(
            path="t.py",
            level=TestLevel.UNIT,
            rule="r",
            mapping_rule="naming_convention",
            covers=[],
            confidence=Confidence.LOW,
        )


def test_a_proxy_coverage_record_is_low_confidence_by_construction():
    """D12 + BrownKit's own rule: a proxy is not a measurement of coverage,
    and a HIGH-confidence proxy would read as one."""
    with pytest.raises(ValidationError):
        CoverageRecord(
            scope="package",
            path="src/app",
            covered=Measurement.measured(80.0),
            source="proxy",
            confidence=Confidence.HIGH,
        )
    ok = CoverageRecord(
        scope="package",
        path="src/app",
        covered=Measurement.measured(80.0),
        source="proxy",
        confidence=Confidence.LOW,
    )
    assert ok.tool == ""


def test_a_report_coverage_record_must_name_its_tool():
    """Acceptance gate 5 of BrownKit's scan: coverage records carry source
    and confidence, never a bare percentage."""
    with pytest.raises(ValidationError):
        CoverageRecord(
            scope="file",
            path="src/a.py",
            covered=Measurement.measured(50.0),
            source="report",
            confidence=Confidence.HIGH,
        )


def test_a_ci_stage_records_blocking_as_unreadable_at_a_commit():
    """A required check is a branch-protection setting, not a tracked file.
    FR-915 says that is not_collected, not False."""
    s = CiStageRecord(
        workflow=".github/workflows/ci.yml",
        stage="test",
        order=0,
        runs_tests=True,
        test_levels=[TestLevel.UNIT],
        blocking=Measurement.not_collected(
            "required checks are a branch-protection setting, not a tracked file"
        ),
    )
    assert s.blocking.state is CollectionState.NOT_COLLECTED


def test_an_environment_must_be_declared_somewhere():
    with pytest.raises(ValidationError):
        EnvironmentRecord(name="staging", in_ci=False, in_config=False)
    drifted = EnvironmentRecord(name="staging", in_ci=True, in_config=False)
    assert drifted.drifted is True
    assert EnvironmentRecord(name="prod", in_ci=True, in_config=True).drifted is False


def test_payload_field_covers_every_signal_that_can_produce_records():
    """P3-D2: QS4 owns two payload fields, so the map is signal -> tuple.
    SS2 owns none (D12 cut its computed half)."""
    assert PAYLOAD_FIELD[ScanSignalId.QS4] == ("ci", "environments")
    assert ScanSignalId.SS2 not in PAYLOAD_FIELD
    assert PAYLOAD_FIELD[ScanSignalId.SS1] == ("security",)
    assert PAYLOAD_FIELD[ScanSignalId.SS3] == ("security",)
