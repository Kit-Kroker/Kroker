"""SS1 -- static security signals, computed half (FR-912).

Two categories here; two more are inherited from triage and folded in by the
workflow (D2/D7): credential storage from `secrets`, app-level authentication
from `misconfig`. This module never touches those -- one implementation per
signal, cited rather than copied (FR-902, extended cross-tier).

  * tls_enforcement   -- a function of the tree alone.
  * input_validation  -- a function of S3's entry points: does the file that
                         declares a route show a validation marker? When S3
                         did not collect, this category reports not_collected
                         naming S3, never a zero (section 5, D5).

`severity_hint`, never `severity`: deciding what a missing validator is worth
is E-49's job, and deciding whether a route SHOULD be authenticated is
explicitly out of scope (spec section 10).

Pure: blobs and the declared upstream in, records out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ....triage.models import evidence_key
from ..models import (
    C_AUTHN_AUTHZ,
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    C_TLS,
    Confidence,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    SecurityObservation,
    SignalOutput,
    SignalSource,
    family_of,
    inherited_pending,
)
from ..testpaths import is_test_path

SIGNAL_ID = "SS1"
VERSION = 1

_MAX_EVIDENCE = 400

# (rule, severity_hint, confidence, pattern, detail)
TLS_RULES: tuple[tuple[str, str, Confidence, re.Pattern[str], str], ...] = (
    (
        "ss1_tls_verification_disabled",
        "high",
        Confidence.HIGH,
        re.compile(
            r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"
            r"|InsecureSkipVerify\s*:\s*true|_create_unverified_context\s*\("
            r"|CURLOPT_SSL_VERIFYPEER\s*,\s*(?:false|0)"
            r"|ServerCertificateValidationCallback"
        ),
        "Certificate verification is switched off, so the connection is "
        "authenticated against nothing.",
    ),
    (
        "ss1_weak_tls_version",
        "medium",
        Confidence.HIGH,
        re.compile(
            r"PROTOCOL_TLSv1(?:_1)?\b|SSLv[23]\b|VersionTLS1[01]\b"
            r"|SecurityProtocolType\.(?:Ssl3|Tls|Tls11)\b"
        ),
        "A TLS version below 1.2 is selected explicitly.",
    ),
    (
        "ss1_plaintext_http_url",
        "medium",
        Confidence.MEDIUM,
        re.compile(
            r"""['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]"""
            r"""|example\.(?:com|org|net)|schemas?\.|www\.w3\.org)"""
        ),
        "A cleartext http:// endpoint is hardcoded.",
    ),
)

# Markers that SOME validation happens in a file. Presence-based, deliberately:
# whether the validation is CORRECT is semantic analysis, and the spec puts
# that in E-49.
VALIDATION_MARKERS = re.compile(
    r"\bBaseModel\b|\bpydantic\b|@validator\b|@field_validator\b"
    r"|\bmarshmallow\b|\bcerberus\b|\bvoluptuous\b"
    r"|\bz\.(?:object|string|number)\s*\(|\bzod\b|class-validator"
    r"|\bjoi\b|\byup\b|express-validator"
    r"|@Valid\b|@Validated\b|FluentValidation|DataAnnotations"
    r"|\bvalidator\.\w+\(|\bvalidate\w*\s*\("
)


def _observation(
    category: str,
    rule: str,
    severity: str,
    confidence: Confidence,
    detail: str,
    path: str,
    line: int | None,
    quote: str,
) -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1,
        category=category,
        rule=rule,
        detail=detail,
        severity_hint=severity,
        path=path,
        line=line,
        evidence=quote[:_MAX_EVIDENCE],
        key=evidence_key(quote[:_MAX_EVIDENCE]),
        confidence=confidence,
    )


def _tls(blobs: Mapping[str, str]) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for path in sorted(blobs):
        if is_test_path(path):
            continue
        lines = blobs[path].splitlines()
        for index, line in enumerate(lines, start=1):
            for rule, severity, confidence, pattern, detail in TLS_RULES:
                if pattern.search(line):
                    out.append(
                        _observation(
                            C_TLS, rule, severity, confidence, detail, path, index, line.strip()
                        )
                    )
    return out


def _entry_point_files(upstream: ScanUpstream) -> dict[str, int | None]:
    """path -> the first entry-point line in it, over S3's members only."""
    out: dict[str, int | None] = {}
    for candidate in upstream.sources:
        if candidate.signal is not ScanSignalId.S3:
            continue
        for member in candidate.members:
            if not member.path:
                continue
            current = out.get(member.path)
            if member.path not in out or (
                member.line is not None and (current is None or member.line < current)
            ):
                out[member.path] = member.line
    return out


def _validation(blobs: Mapping[str, str], upstream: ScanUpstream) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for path, line in sorted(_entry_point_files(upstream).items()):
        if is_test_path(path):
            continue
        text = blobs.get(path)
        if text is None or VALIDATION_MARKERS.search(text):
            continue
        lines = text.splitlines()
        quote = lines[line - 1].strip() if line and line <= len(lines) else path
        out.append(
            SecurityObservation(
                signal=ScanSignalId.SS1,
                category=C_INPUT_VALIDATION,
                rule="ss1_entry_point_without_validation",
                detail="This file declares an entry point and shows no schema or "
                "validator marker, so its input reaches the handler "
                "unchecked. Whether that matters is E-49's call.",
                severity_hint="medium",
                path=path,
                line=line,
                evidence=quote[:_MAX_EVIDENCE],
                key="",
                confidence=Confidence.MEDIUM,
            )
        )
    return out


def evaluate(
    blobs: Mapping[str, str], upstream: ScanUpstream, skipped: Sequence[str] = ()
) -> SignalOutput:
    """`blobs` is path -> text for readable source blobs; `upstream` carries
    S3's candidates and row state (P3-D4). `skipped` names blobs over
    MAX_BLOB_BYTES; a partial TLS/input-validation scan must not pass as a
    complete one (spec section 6)."""
    if skipped:
        nc = Measurement.not_collected(
            f"tls_enforcement: {len(skipped)} blob(s) over MAX_BLOB_BYTES "
            f"not read (first: {skipped[0]}); a partial scan must not pass "
            f"as a complete one (spec section 6)"
        )
        return SignalOutput(
            row=ScanSignalResult(
                signal=ScanSignalId.SS1,
                family=family_of(ScanSignalId.SS1),
                version=VERSION,
                source=SignalSource.COMPUTED,
                collected=nc,
                categories={
                    C_TLS: nc,
                    C_INPUT_VALIDATION: nc,
                    C_CREDENTIAL_STORAGE: inherited_pending(C_CREDENTIAL_STORAGE),
                    C_AUTHN_AUTHZ: inherited_pending(C_AUTHN_AUTHZ),
                },
            )
        )
    tls = _tls(blobs)
    s3_ok = upstream.measured(ScanSignalId.S3)
    validation = _validation(blobs, upstream) if s3_ok else []

    observations = sorted(tls + validation, key=lambda o: (o.category, o.path, o.rule, o.line or 0))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS1,
            family=family_of(ScanSignalId.SS1),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(observations))),
            categories={
                C_TLS: Measurement.measured(float(len(tls))),
                C_INPUT_VALIDATION: (
                    Measurement.measured(float(len(validation)))
                    if s3_ok
                    else upstream.gap(ScanSignalId.S3, C_INPUT_VALIDATION)
                ),
                C_CREDENTIAL_STORAGE: inherited_pending(C_CREDENTIAL_STORAGE),
                C_AUTHN_AUTHZ: inherited_pending(C_AUTHN_AUTHZ),
            },
        ),
        security=observations,
    )
