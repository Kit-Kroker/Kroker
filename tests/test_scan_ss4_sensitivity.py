"""SS4: which entities hold regulated data, and which entry points touch
them. The classification is the answer E-49 scores per capability."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_DATA_SENSITIVITY,
    C_ENTITY_ACCESS,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanUpstream,
    Sensitivity,
    SourceCandidate,
)
from sdlc.assessment.scan.signals import sensitivity
from sdlc.measurement import CollectionState, Measurement

BLOBS = {
    "migrations/0001_customers.sql": (
        "CREATE TABLE customers (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  email VARCHAR(255),\n"
        "  phone VARCHAR(32),\n"
        "  password_hash VARCHAR(128)\n"
        ");\n"
    ),
    "app/models/payment.py": (
        "class Payment(Base):\n"
        "    __tablename__ = 'payments'\n"
        "    card_last4 = Column(String(4))\n"
        "    amount = Column(Numeric)\n"
    ),
}


def _upstream(s2_ok=True, s3_ok=True) -> ScanUpstream:
    sources = []
    collected = {}
    if s2_ok:
        collected[ScanSignalId.S2] = Measurement.measured(2.0)
        sources.append(
            SourceCandidate(
                signal=ScanSignalId.S2,
                local_id="S2-customer",
                name="customers",
                rule="s2_schema_cluster",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[CandidateMember(kind=MemberKind.DB_TABLE, value="customers")],
            )
        )
    else:
        collected[ScanSignalId.S2] = Measurement.not_collected("S2 failed")
    if s3_ok:
        collected[ScanSignalId.S3] = Measurement.measured(1.0)
        sources.append(
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-customer",
                name="customer",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /api/customers")],
            )
        )
    else:
        collected[ScanSignalId.S3] = Measurement.not_collected("S3 failed")
    return ScanUpstream(sources=sources, collected=collected)


def test_pii_and_authentication_are_distinct_classifications():
    out = sensitivity.evaluate(BLOBS, _upstream())
    by_class = {(r.classification, r.entity) for r in out.data_sensitivity}
    assert (Sensitivity.PII, "customers") in by_class
    assert (Sensitivity.AUTHENTICATION, "customers") in by_class
    pii = next(r for r in out.data_sensitivity if r.classification is Sensitivity.PII)
    assert set(pii.fields) == {"email", "phone"}
    assert pii.origin == "table"


def test_a_financial_model_is_classified_from_its_fields():
    out = sensitivity.evaluate(BLOBS, _upstream())
    fin = next(r for r in out.data_sensitivity if r.classification is Sensitivity.FINANCIAL)
    assert fin.entity == "payments"
    assert fin.origin == "model"
    assert "card_last4" in fin.fields


def test_accessed_by_cites_the_matching_entry_point_by_local_id():
    """P3-D6: a NAME match, and the rule says so. A read/write dataflow
    analysis is not available to a blob-reading scan, and asserting one would
    be the fabrication FR-914 exists to prevent."""
    out = sensitivity.evaluate(BLOBS, _upstream())
    pii = next(r for r in out.data_sensitivity if r.classification is Sensitivity.PII)
    assert pii.accessed_by == ["S3-customer"]


def test_entity_access_is_a_gap_when_s3_did_not_collect():
    """P3-D12: an empty accessed_by must never read as 'no entry point
    touches PII' -- the owing category says why it is empty."""
    out = sensitivity.evaluate(BLOBS, _upstream(s3_ok=False))
    assert out.row.categories[C_ENTITY_ACCESS].state is CollectionState.NOT_COLLECTED
    assert "S3" in out.row.categories[C_ENTITY_ACCESS].reason
    # the classification half still measured
    assert out.row.categories[C_DATA_SENSITIVITY].state is CollectionState.MEASURED
    assert all(r.accessed_by == [] for r in out.data_sensitivity)


def test_the_whole_signal_is_a_gap_when_s2_did_not_collect():
    """Section 5: without the table set the entity set is partial, and a
    partial sensitivity map that says 'no PII' is the dangerous conflation."""
    out = sensitivity.evaluate(BLOBS, _upstream(s2_ok=False))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.data_sensitivity == []
    assert "S2" in out.row.collected.reason


def test_a_compliance_marker_makes_the_entity_regulatory():
    blobs = dict(BLOBS)
    blobs["app/models/card.py"] = (
        "# PCI-DSS scope: cardholder data\n"
        "class Card(Base):\n"
        "    __tablename__ = 'cards'\n"
        "    pan = Column(String(19))\n"
    )
    out = sensitivity.evaluate(blobs, _upstream())
    assert any(
        r.classification is Sensitivity.REGULATORY and r.entity == "cards"
        for r in out.data_sensitivity
    )


def test_a_field_named_company_is_not_a_card_number():
    """Substring matching would classify 'company' as financial because it
    contains 'pan'. Tokens, not substrings."""
    blobs = {
        "app/models/org.py": (
            "class Org(Base):\n    __tablename__ = 'orgs'\n    company = Column(String(80))\n"
        )
    }
    out = sensitivity.evaluate(blobs, _upstream())
    assert out.data_sensitivity == []
    assert out.row.categories[C_DATA_SENSITIVITY].state is CollectionState.MEASURED
    assert out.row.categories[C_DATA_SENSITIVITY].value == 0.0


def test_output_is_byte_identical_across_input_orderings():
    reference = sensitivity.evaluate(BLOBS, _upstream()).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert sensitivity.evaluate(reordered, _upstream()).model_dump_json() == reference
