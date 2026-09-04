"""FR-902 framework-default misconfiguration (E-41c).

Framework-scoped and FILE-SHAPED: every rule is a pattern a deterministic
scan can defend. Two boundaries are load-bearing.

`secrets` owns credential MATERIAL; this signal owns generator DEFAULTS. The
`django-insecure-` prefix is written by `django-admin startproject`, so it
belongs here, and `secrets` excludes it so one line never yields two findings.

`unauthenticated_app` is WHOLE-APPLICATION scoped, never per-route. Deciding
whether a particular route should be authenticated is semantic analysis and
belongs to E-46/E-49; a per-route rule computed from decorators would be a
false-positive generator, and a triage report a client cannot trust is worse
than a shorter one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from sdlc.triage.models import (
    FindingSeverity,
    FixClass,
    SignalResult,
    TriageFinding,
    dedupe_by_identity,
    evidence_key,
)

from ...measurement import Measurement

SIGNAL_ID = "misconfig"
VERSION = 2

M_FRAMEWORKS = "frameworks_detected"

_FRAMEWORKS: dict[str, re.Pattern[str]] = {
    "fastapi": re.compile(r"\b(?:from|import)\s+fastapi\b"),
    "flask": re.compile(r"\b(?:from|import)\s+flask\b", re.IGNORECASE),
    "django": re.compile(r"\b(?:from|import)\s+django\b"),
}

# (rule, pattern, severity, fix_class, detail)
_RULES: tuple[tuple[str, re.Pattern[str], FindingSeverity, FixClass, str], ...] = (
    (
        "permissive_cors",
        re.compile(
            r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]"
            r"|CORS\([^)]*origins\s*=\s*[\"']\*[\"']"
        ),
        "high",
        FixClass.MECHANICAL,
        "CORS is configured to accept every origin.",
    ),
    (
        "debug_enabled",
        re.compile(r"^\s*DEBUG\s*=\s*True\b|\.run\([^)]*debug\s*=\s*True", re.MULTILINE),
        "high",
        FixClass.MECHANICAL,
        "Debug mode is enabled in committed configuration. It serves stack "
        "traces to clients and, in Django, an settings dump.",
    ),
    (
        "allowed_hosts_wildcard",
        re.compile(r"ALLOWED_HOSTS\s*=\s*\[\s*[\"']\*[\"']\s*\]"),
        "medium",
        FixClass.MECHANICAL,
        "ALLOWED_HOSTS accepts every host, which defeats Host-header validation.",
    ),
    (
        "django_insecure_secret_key",
        re.compile(r"SECRET_KEY\s*=\s*[\"']django-insecure-"),
        "critical",
        FixClass.JUDGEMENT,
        "The generator's placeholder SECRET_KEY is still in use and committed. "
        "Rotate it; deleting the literal does not invalidate already-signed "
        "cookies.",
    ),
    (
        "world_readable_storage",
        re.compile(
            r"allow\s+read\s*,\s*write\s*:\s*if\s+true"
            r"|[\"']Principal[\"']\s*:\s*[\"']\*[\"']"
        ),
        "critical",
        FixClass.MECHANICAL,
        "Storage rules grant read and write to everyone.",
    ),
)

# Credentialed wildcard CORS is the one combination worth escalating: it is
# the configuration people reach for when a wildcard alone stopped working.
_CREDENTIALED = re.compile(
    r"allow_credentials\s*=\s*True"
    r"|supports_credentials\s*=\s*True"
)

_AUTH_MARKERS = re.compile(
    r"login_required|LoginRequiredMixin|IsAuthenticated|permission_classes"
    r"|HTTPBearer|OAuth2PasswordBearer|APIKeyHeader|jwt_required"
    r"|AuthenticationMiddleware|flask_login|verify_token|current_user"
)

_MUTATING_ROUTE = re.compile(
    r"@\w+\.(?:post|put|patch|delete)\s*\("
    r"|methods\s*=\s*\[[^\]]*[\"'](?:POST|PUT|PATCH|DELETE)[\"']"
)


def detect_frameworks(blobs: Mapping[str, str]) -> set[str]:
    """Which web frameworks the repository imports anywhere."""
    return {
        name
        for name, pattern in _FRAMEWORKS.items()
        if any(pattern.search(text) for text in blobs.values())
    }


def _finding(
    rule: str,
    severity: FindingSeverity,
    detail: str,
    fix_class: FixClass,
    path: str = "",
    line: int | None = None,
    evidence: str = "",
    key: str = "",
) -> TriageFinding:
    return TriageFinding(
        signal=SIGNAL_ID,
        rule=rule,
        severity=severity,
        detail=detail,
        fix_class=fix_class,
        path=path,
        line=line,
        evidence=evidence,
        key=key,
    )


def evaluate(blobs: Mapping[str, str]) -> SignalResult:
    """Every rule against every readable blob, plus the one whole-application
    rule."""
    findings: list[TriageFinding] = []

    for path in sorted(blobs):
        text = blobs[path]
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern, severity, fix_class, detail in _RULES:
                if not pattern.search(line):
                    continue
                if rule == "permissive_cors" and _CREDENTIALED.search(line):
                    severity = "critical"
                    detail = detail + " Credentials are allowed alongside the wildcard."
                findings.append(
                    _finding(
                        rule,
                        severity,
                        detail,
                        fix_class,
                        path,
                        lineno,
                        line.strip()[:400],
                        key=evidence_key(line.strip()[:400]),
                    )
                )

    frameworks = detect_frameworks(blobs)
    if frameworks:
        has_auth = any(_AUTH_MARKERS.search(t) for t in blobs.values())
        mutating = sorted(p for p, t in blobs.items() if _MUTATING_ROUTE.search(t))
        if mutating and not has_auth:
            findings.append(
                _finding(
                    "unauthenticated_app",
                    "high",
                    f"The application ({', '.join(sorted(frameworks))}) declares "
                    f"no authentication mechanism anywhere, and defines mutating "
                    f"routes in {', '.join(mutating[:5])}. Reported once for the "
                    f"repository: deciding which individual route needs auth is "
                    f"design work, not a scan.",
                    FixClass.STRUCTURAL,
                    mutating[0],
                )
            )

    findings = dedupe_by_identity(findings)
    return SignalResult(
        signal=SIGNAL_ID,
        version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_FRAMEWORKS: Measurement.measured(float(len(frameworks)))},
    )
