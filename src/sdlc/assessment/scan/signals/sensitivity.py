"""SS4 -- data sensitivity (FR-912).

Classifies ENTITIES, not files: the question E-49 asks is which capability
handles regulated data. The entity set is S2's declarations (one extractor,
two readers -- FR-902), and the accessor set is a NAME match against S3's
entry points, never a dataflow claim (P3-D6).

Two categories, because the two halves fail independently (P3-D12):
  * data_sensitivity -- the classification. Needs the tree and S2.
  * entity_access    -- which entry points touch the entity. Needs S3, and
                        reports not_collected naming it when S3 degraded, so
                        an empty accessed_by never reads as "no entry point
                        touches PII" (D5, section 5).

Pure: blobs and the declared upstream in, records out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ..models import (
    C_DATA_SENSITIVITY,
    C_ENTITY_ACCESS,
    Confidence,
    EvidenceRef,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    Sensitivity,
    SensitivityOrigin,
    SensitivityRecord,
    SignalOutput,
    SignalSource,
    family_of,
)
from ..naming import normalize
from .schema import TableDecl, declarations

SIGNAL_ID = "SS4"
VERSION = 1

# Ordered: the FIRST classification a field matches wins, so `password_hash`
# is authentication rather than PII. Order is the rule, and it is declared
# rather than discovered.
_FIELD_RULES: tuple[tuple[Sensitivity, str, frozenset[str]], ...] = (
    (
        Sensitivity.AUTHENTICATION,
        "ss4_authentication_field_name",
        frozenset(
            {
                "password",
                "passwd",
                "passwordhash",
                "password_hash",
                "secret",
                "token",
                "access_token",
                "accesstoken",
                "refresh_token",
                "refreshtoken",
                "session",
                "session_id",
                "sessionid",
                "api_key",
                "apikey",
                "mfa",
                "totp",
                "otp",
                "salt",
                "credential",
                "credentials",
            }
        ),
    ),
    (
        Sensitivity.FINANCIAL,
        "ss4_financial_field_name",
        frozenset(
            {
                "card",
                "card_number",
                "cardnumber",
                "pan",
                "cvv",
                "cvc",
                "iban",
                "bic",
                "swift",
                "account_number",
                "accountnumber",
                "routing_number",
                "routingnumber",
                "balance",
                "amount",
                "currency",
                "invoice",
                "transaction",
                "payment_method",
                "paymentmethod",
                "card_last4",
                "cardlast4",
                "sort_code",
                "sortcode",
            }
        ),
    ),
    (
        Sensitivity.HEALTH,
        "ss4_health_field_name",
        frozenset(
            {
                "diagnosis",
                "medication",
                "prescription",
                "patient",
                "icd",
                "allergy",
                "blood_type",
                "bloodtype",
                "medical_record",
                "medicalrecord",
                "nhs_number",
                "nhsnumber",
            }
        ),
    ),
    (
        Sensitivity.PII,
        "ss4_pii_field_name",
        frozenset(
            {
                "email",
                "e_mail",
                "phone",
                "phone_number",
                "phonenumber",
                "mobile",
                "first_name",
                "firstname",
                "last_name",
                "lastname",
                "full_name",
                "fullname",
                "address",
                "street",
                "postcode",
                "zip",
                "zipcode",
                "ssn",
                "national_id",
                "nationalid",
                "passport",
                "date_of_birth",
                "dateofbirth",
                "dob",
                "ip_address",
                "ipaddress",
                "latitude",
                "longitude",
            }
        ),
    ),
)

_REGULATORY = re.compile(r"\b(PCI[- ]?DSS|PCI\b|HIPAA|GDPR|SOC ?2|PSD2|CCPA|FERPA)\b")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(field: str) -> set[str]:
    """A field's comparable forms: its words, its whole lowercased name, and
    the same with separators removed.

    TOKENS, not substrings: 'company' contains 'pan', and a substring rule
    would classify an organisation table as cardholder data. A false PII
    finding in a report a client pays for is worse than a missed one, because
    it is the finding they will check first.
    """
    words = re.split(r"[_\-\s]+", _CAMEL.sub("_", field))
    lowered = field.lower()
    return {w.lower() for w in words if w} | {lowered, lowered.replace("_", "")}


def _origin(decl: TableDecl) -> SensitivityOrigin:
    """table | model | dto -- SS4's declared shape. A DTO is recognised by
    where it lives, which is the only thing that distinguishes it from a
    model at this depth."""
    if "dto" in decl.path.lower() or decl.name.lower().endswith("dto"):
        return "dto"
    return "table" if decl.origin == "table" else "model"


def _accessors(entity: str, upstream: ScanUpstream) -> list[str]:
    """S3 candidates whose normalized name equals the entity's (P3-D6)."""
    key = normalize(entity)
    return sorted(
        {
            c.local_id
            for c in upstream.sources
            if c.signal is ScanSignalId.S3 and normalize(c.name) == key
        }
    )


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS4,
            family=family_of(ScanSignalId.SS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_DATA_SENSITIVITY: nc, C_ENTITY_ACCESS: nc},
        )
    )


def evaluate(
    blobs: Mapping[str, str], upstream: ScanUpstream, skipped: Sequence[str] = ()
) -> SignalOutput:
    """`blobs` is path -> text for readable source/schema blobs; `upstream`
    carries S2's and S3's candidates and row states (P3-D4). `skipped` names
    blobs over MAX_BLOB_BYTES; a partial entity set must not pass as a
    complete one (spec section 6)."""
    if skipped:
        return _gap(
            f"data_sensitivity: {len(skipped)} blob(s) over MAX_BLOB_BYTES "
            f"not read (first: {skipped[0]}); a partial entity set must not "
            f"pass as a complete one (spec section 6)"
        )
    if not upstream.measured(ScanSignalId.S2):
        return _gap(upstream.gap(ScanSignalId.S2, "data_sensitivity").reason)

    s3_ok = upstream.measured(ScanSignalId.S3)
    records: list[SensitivityRecord] = []

    for decl in declarations(blobs):
        regulated = bool(_REGULATORY.search(blobs.get(decl.path, "")))
        matched: dict[Sensitivity, tuple[str, list[str]]] = {}
        for field in decl.fields:
            tokens = _tokens(field)
            for classification, rule, terms in _FIELD_RULES:
                if tokens & terms:
                    matched.setdefault(classification, (rule, []))[1].append(field)
                    break
        accessed = _accessors(decl.name, upstream) if s3_ok else []
        for classification, (rule, fields) in matched.items():
            records.append(
                SensitivityRecord(
                    classification=classification,
                    entity=decl.name,
                    origin=_origin(decl),
                    fields=sorted(set(fields)),
                    accessed_by=accessed,
                    evidence=[EvidenceRef(path=decl.path, lines=str(decl.line))],
                    rule=rule,
                    confidence=(Confidence.HIGH if len(fields) > 1 else Confidence.MEDIUM),
                )
            )
        if regulated:
            records.append(
                SensitivityRecord(
                    classification=Sensitivity.REGULATORY,
                    entity=decl.name,
                    origin=_origin(decl),
                    fields=sorted(decl.fields),
                    accessed_by=accessed,
                    evidence=[EvidenceRef(path=decl.path, lines=str(decl.line))],
                    rule="ss4_declared_compliance_scope",
                    confidence=Confidence.MEDIUM,
                )
            )

    records.sort(key=lambda r: (r.classification.value, r.entity, r.rule))
    classified = Measurement.measured(float(len(records)))
    access = (
        Measurement.measured(float(sum(1 for r in records if r.accessed_by)))
        if s3_ok
        else upstream.gap(ScanSignalId.S3, "entity_access")
    )
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS4,
            family=family_of(ScanSignalId.SS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=classified,
            categories={C_DATA_SENSITIVITY: classified, C_ENTITY_ACCESS: access},
        ),
        data_sensitivity=records,
    )
