"""S1-S4 emit one shape whose members are typed by kind (D13)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    CandidateMember, Confidence, EvidenceRef, MemberKind, ScanSignalId,
    SourceCandidate, signal_of,
)
from sdlc.measurement import Measurement


def _member() -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE,
                           value="POST /api/payments",
                           path="src/api/payments.py", line=42)


def _candidate(local_id: str = "S3-payments",
               signal: ScanSignalId = ScanSignalId.S3) -> SourceCandidate:
    return SourceCandidate(
        signal=signal, local_id=local_id, name="Payments",
        rule="s3_http_route", detail="Three routes under /api/payments.",
        confidence_contribution=Confidence.MEDIUM,
        members=[_member()],
        evidence=[EvidenceRef(path="src/api/payments.py", lines="42-78")])


def test_member_kinds_span_the_four_identity_tiers():
    """D13: the value set must be able to populate every
    CapabilityFingerprint tier, so E-48's mapping can be total."""
    kinds = {k.value for k in MemberKind}
    assert {"http_route", "cli_command", "db_table", "queue_topic",
            "grpc_method"} <= kinds                      # contract
    assert {"test_name", "entity_name"} <= kinds         # behavioral
    assert {"exported_symbol"} <= kinds                  # structural
    assert {"package_path", "file_path"} <= kinds        # locational


def test_local_id_must_be_prefixed_by_its_signal():
    """signal_of() parses the prefix, so the two cannot disagree."""
    c = _candidate()
    assert signal_of(c.local_id) is ScanSignalId.S3


def test_local_id_not_matching_its_signal_is_refused():
    with pytest.raises(ValidationError, match="local_id"):
        _candidate(local_id="S1-payments", signal=ScanSignalId.S3)


def test_signal_of_refuses_a_malformed_id():
    with pytest.raises(ValueError, match="malformed"):
        signal_of("payments")


def test_members_and_evidence_are_sorted_canonically():
    """NFR-10: discovery order must not change the artifact."""
    a = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /b")
    b = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /a")
    c = SourceCandidate(
        signal=ScanSignalId.S3, local_id="S3-x", name="X", rule="r",
        detail="d", confidence_contribution=Confidence.LOW,
        members=[a, b],
        evidence=[EvidenceRef(path="z.py"), EvidenceRef(path="a.py")])
    assert [m.value for m in c.members] == ["GET /a", "GET /b"]
    assert [e.path for e in c.evidence] == ["a.py", "z.py"]


def test_metrics_are_measurements_so_an_uncomputable_count_is_not_zero():
    c = _candidate()
    c2 = c.model_copy(update={"metrics": {
        "file_count": Measurement.measured(12.0),
        "loc_estimate": Measurement.not_collected("no parser for this language"),
    }})
    assert c2.metrics["loc_estimate"].value is None


def test_a_candidate_with_no_members_is_refused():
    """A candidate is a claim that something is there; an empty one is a
    silently-empty tier, which is exactly what D5 forbids."""
    with pytest.raises(ValidationError, match="at least one member"):
        SourceCandidate(
            signal=ScanSignalId.S1, local_id="S1-x", name="X", rule="r",
            detail="d", confidence_contribution=Confidence.LOW,
            members=[], evidence=[])
