"""SS1's computed half. The inherited half (credential storage from triage's
secrets, app-level auth from misconfig) is derived in workflow code and folded
in by fold_row -- this signal never touches it (D7)."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    C_TLS,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanUpstream,
    SourceCandidate,
)
from sdlc.assessment.scan.signals import security_static
from sdlc.measurement import CollectionState, Measurement

BLOBS = {
    "src/client.py": ("import requests\ndef fetch(u):\n    return requests.get(u, verify=False)\n"),
    # NOT example.com/org/net: those are IETF documentation domains and the
    # rule excludes them, so a fixture using one would assert the opposite of
    # what it reads as.
    "src/config.py": "BASE = 'http://api.internal.acme/v1'\n",
    "src/routes/orders.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/orders')\n"
        "def create(payload: dict):\n    return payload\n"
    ),
    "src/routes/payments.py": (
        "from fastapi import APIRouter\n"
        "from pydantic import BaseModel\n"
        "class Payment(BaseModel):\n    amount: int\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create(payload: Payment):\n    return payload\n"
    ),
}


def _upstream(s3_ok: bool = True) -> ScanUpstream:
    if not s3_ok:
        return ScanUpstream(collected={ScanSignalId.S3: Measurement.not_collected("S3 failed")})
    return ScanUpstream(
        sources=[
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-order",
                name="orders",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/orders",
                        path="src/routes/orders.py",
                        line=3,
                    )
                ],
            ),
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-payment",
                name="payments",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/payments",
                        path="src/routes/payments.py",
                        line=6,
                    )
                ],
            ),
        ],
        collected={ScanSignalId.S3: Measurement.measured(2.0)},
    )


def test_disabled_certificate_verification_is_a_high_hint():
    out = security_static.evaluate(BLOBS, _upstream())
    tls = [o for o in out.security if o.category == C_TLS]
    rules = {o.rule for o in tls}
    assert "ss1_tls_verification_disabled" in rules
    finding = next(o for o in tls if o.rule == "ss1_tls_verification_disabled")
    assert finding.severity_hint == "high"
    assert finding.signal is ScanSignalId.SS1
    assert finding.evidence.strip().startswith("return requests.get")


def test_a_plaintext_url_is_recorded_and_localhost_is_not():
    out = security_static.evaluate(
        dict(BLOBS, **{"src/dev.py": "LOCAL = 'http://localhost:8000'\n"}), _upstream()
    )
    paths = {o.path for o in out.security if o.rule == "ss1_plaintext_http_url"}
    assert "src/config.py" in paths
    assert "src/dev.py" not in paths


def test_an_entry_point_without_a_validation_marker_is_recorded():
    out = security_static.evaluate(BLOBS, _upstream())
    missing = [o for o in out.security if o.category == C_INPUT_VALIDATION]
    assert {o.path for o in missing} == {"src/routes/orders.py"}
    assert missing[0].rule == "ss1_entry_point_without_validation"


def test_input_validation_is_a_gap_when_s3_did_not_collect():
    """Section 5: the dependent category reports not_collected naming S3, and
    never a zero -- 'no entry point lacks validation' would be a lie."""
    out = security_static.evaluate(BLOBS, _upstream(s3_ok=False))
    category = out.row.categories[C_INPUT_VALIDATION]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "S3" in category.reason
    # TLS is independent of S3 and still measured.
    assert out.row.categories[C_TLS].state is CollectionState.MEASURED
    assert not any(o.category == C_INPUT_VALIDATION for o in out.security)


def test_the_two_inherited_categories_are_declared_as_pending():
    """D7: a row must declare every category it owes, and the activity
    computes only its own half."""
    out = security_static.evaluate(BLOBS, _upstream())
    for key in (C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ):
        assert out.row.categories[key].state is CollectionState.NOT_COLLECTED
        assert "D7" in out.row.categories[key].reason


def test_output_is_byte_identical_across_input_orderings():
    reference = security_static.evaluate(BLOBS, _upstream()).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert security_static.evaluate(reordered, _upstream()).model_dump_json() == reference


def test_a_tls_finding_in_a_test_file_is_not_attributed_to_the_product():
    """QS3's rule, one signal over: a verify=False inside a test is the test's
    own business, and flagging it would bury the findings that matter (and
    E-49 would score it, E-52 would bundle it)."""
    blobs = dict(
        BLOBS,
        **{
            "tests/test_client.py": (
                "import requests\ndef test_fetch():\n    requests.get('https://x', verify=False)\n"
            )
        },
    )
    out = security_static.evaluate(blobs, _upstream())
    assert all(o.path != "tests/test_client.py" for o in out.security)
