"""SS3 -- configuration and infrastructure, computed half (FR-912).

BrownKit reads (never executes) the deployment's own declarations. Four
categories here; framework defaults are triage's `misconfig`, inherited and
folded in by the workflow (D2/D7) rather than re-implemented.

  * exposed_ports   -- EXPOSE, compose port maps, k8s service types.
  * env_divergence  -- what one environment declares and another does not.
                       Needs TWO environment files: with one there is nothing
                       to compare, which is unmeasurable rather than "no
                       divergence" (P3-D11).
  * db_security     -- SSL, credential placement, trust auth, default admins.
  * log_masking     -- sensitive field names reaching a log call.

Log-masking scanning runs over source blobs as well as config, because a log
call lives in code -- so the activity hands this signal both, and
`is_config_path` decides which rules a path is eligible for.

Pure: blobs in, records out.
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping

from ....measurement import Measurement
from ....triage.models import evidence_key
from ..models import (
    C_DB_SECURITY, C_ENV_DIVERGENCE, C_EXPOSED_PORTS, C_FRAMEWORK_DEFAULTS,
    C_LOG_MASKING, Confidence, ScanSignalId, ScanSignalResult,
    SecurityObservation, SignalOutput, SignalSource, family_of,
    inherited_pending,
)

SIGNAL_ID = "SS3"
VERSION = 1

_MAX_EVIDENCE = 400

_CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)Dockerfile[\w.-]*$"),
    re.compile(r"(^|/)docker-compose[\w.-]*\.ya?ml$"),
    re.compile(r"(^|/)\.env[\w.-]*$"),
    re.compile(r"(^|/)appsettings(\.\w+)?\.json$"),
    re.compile(r"(^|/)application(-[\w]+)?\.(ya?ml|properties)$"),
    re.compile(r"(^|/)(k8s|kubernetes|deploy|deployment|helm|charts)/.*"
               r"\.(ya?ml|tpl)$"),
    re.compile(r"\.tf$|\.tfvars$|\.bicep$"),
    re.compile(r"(^|/)(nginx|haproxy)[\w.-]*\.conf$"),
)

_ENV_FILE = re.compile(
    r"(^|/)(\.env[\w.-]*|appsettings(\.\w+)?\.json"
    r"|application(-\w+)?\.(ya?ml|properties))$")
_PRODUCTION = re.compile(r"(?i)(prod|production|live)")

# Ports whose exposure is a materially different fact from exposing a web
# port: a datastore reachable from outside the deployment is the finding.
_DATASTORE_PORTS: frozenset[str] = frozenset({
    "1433", "1521", "3306", "5432", "5984", "6379", "7000", "7001", "8086",
    "9042", "9200", "11211", "27017", "27018", "5672", "15672", "2379",
})

_EXPOSE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("ss3_dockerfile_expose",
     re.compile(r"(?im)^\s*EXPOSE\s+(\d+)"),
     "The image declares this port."),
    ("ss3_compose_published_port",
     re.compile(r"""(?m)^\s*-\s*["']?(\d{2,5}):\d{2,5}["']?\s*$"""),
     "The compose file publishes this host port."),
    ("ss3_kubernetes_node_port",
     re.compile(r"(?m)^\s*nodePort:\s*(\d+)"),
     "A NodePort service publishes this port on every node."),
    ("ss3_kubernetes_load_balancer",
     re.compile(r"(?m)^\s*type:\s*(LoadBalancer)\s*$"),
     "A LoadBalancer service is addressable from outside the cluster."),
)

_DB_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("ss3_db_ssl_disabled", "high", re.compile(
        r"sslmode\s*=\s*(?:disable|allow)|[?&]ssl\s*=\s*false"
        r"|Encrypt\s*=\s*false|tls\s*=\s*false"),
     "The database connection disables transport encryption."),
    ("ss3_db_credentials_in_url", "high", re.compile(
        r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)"
        r"://[^:/\s]+:[^@/\s]+@"),
     "A database URL carries an inline username and password."),
    ("ss3_db_trust_auth", "critical", re.compile(
        r"POSTGRES_HOST_AUTH_METHOD\s*[:=]\s*[\"']?trust"
        r"|MYSQL_ALLOW_EMPTY_PASSWORD\s*[:=]\s*[\"']?(?:yes|true|1)"
        r"|ALLOW_EMPTY_PASSWORD\s*[:=]\s*[\"']?(?:yes|true|1)"),
     "The database accepts connections without authenticating them."),
    ("ss3_db_default_admin_user", "medium", re.compile(
        r"POSTGRES_USER\s*[:=]\s*[\"']?postgres\b"
        r"|MONGO_INITDB_ROOT_USERNAME\s*[:=]\s*[\"']?(?:root|admin)\b"
        r"|MYSQL_USER\s*[:=]\s*[\"']?root\b"),
     "The application connects as the database's default superuser."),
)

# Keys whose presence or value differs meaningfully between environments.
_SECURITY_KEY_FRAGMENTS: tuple[str, ...] = (
    "DEBUG", "SSL", "TLS", "VERIFY", "SECRET", "TOKEN", "PASSWORD", "KEY",
    "ALLOWED_HOSTS", "CORS", "AUTH", "DATABASE_URL", "SENTRY", "LOG_LEVEL",
)

# (key fragment, unsafe value pattern, detail) -- checked only in a file whose
# name says production.
_UNSAFE_IN_PRODUCTION: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("DEBUG", re.compile(r"(?i)^(true|1|yes|on)$"),
     "DEBUG is enabled in a production configuration."),
    ("SSL", re.compile(r"(?i)^(false|0|no|off|disable[d]?|none)$"),
     "TLS is disabled in a production configuration."),
    ("TLS", re.compile(r"(?i)^(false|0|no|off|disable[d]?|none)$"),
     "TLS is disabled in a production configuration."),
    ("VERIFY", re.compile(r"(?i)^(false|0|no|off)$"),
     "Certificate verification is disabled in a production configuration."),
    ("ALLOWED_HOSTS", re.compile(r"^\s*\*\s*$"),
     "ALLOWED_HOSTS accepts every host in a production configuration."),
    ("CORS", re.compile(r"^\s*\*\s*$"),
     "CORS accepts every origin in a production configuration."),
)

_LOG_CALL = re.compile(
    r"(?i)\b(?:log(?:ger)?\.\w+|logging\.\w+|console\.(?:log|info|warn|error)"
    r"|print|fmt\.Print\w*)\s*\([^)\n]*"
    r"\b(password|passwd|secret|token|api[_-]?key|card|pan|cvv|ssn"
    r"|authorization|credential)\w*\b")

_KEY_VALUE = re.compile(
    r"""(?m)^\s*["']?([A-Za-z_][\w.\-]*)["']?\s*[:=]\s*["']?([^"'\n#]*)""")


def is_config_path(path: str) -> bool:
    """Whether SS3's configuration and infrastructure rules apply to a path.
    Log masking runs everywhere; everything else runs only here."""
    return any(pattern.search(path) for pattern in _CONFIG_PATTERNS)


def _observation(category: str, rule: str, severity: str, detail: str,
                 path: str, line: int, quote: str,
                 confidence: Confidence) -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS3, category=category, rule=rule, detail=detail,
        severity_hint=severity, path=path, line=line,
        evidence=quote[:_MAX_EVIDENCE],
        key=evidence_key(quote[:_MAX_EVIDENCE]), confidence=confidence)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _ports(path: str, text: str) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for rule, pattern, detail in _EXPOSE_RULES:
        for match in pattern.finditer(text):
            value = match.group(1)
            severity = "high" if value in _DATASTORE_PORTS else "info"
            extra = (" This is a datastore port, which is a materially "
                     "different exposure from a web port."
                     if severity == "high" else "")
            out.append(_observation(
                C_EXPOSED_PORTS, rule, severity, f"{detail}{extra}", path,
                _line_of(text, match.start()), match.group(0).strip(),
                Confidence.HIGH))
    return out


def _db(path: str, text: str) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for rule, severity, pattern, detail in _DB_RULES:
        match = pattern.search(text)
        if match:
            out.append(_observation(
                C_DB_SECURITY, rule, severity, detail, path,
                _line_of(text, match.start()), match.group(0).strip(),
                Confidence.MEDIUM))
    return out


def _logs(path: str, text: str) -> list[SecurityObservation]:
    match = _LOG_CALL.search(text)
    if not match:
        return []
    return [_observation(
        C_LOG_MASKING, "ss3_sensitive_value_logged", "high",
        "A log call names a sensitive field, so the value may be written to "
        "wherever logs are forwarded. Whether it is masked at the sink is "
        "not readable from the tree.",
        path, _line_of(text, match.start()), match.group(0).strip(),
        Confidence.MEDIUM)]


def _env_keys(text: str) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for match in _KEY_VALUE.finditer(text):
        key = match.group(1).upper()
        if any(fragment in key for fragment in _SECURITY_KEY_FRAGMENTS):
            out.setdefault(key, (match.group(2).strip(),
                                 _line_of(text, match.start())))
    return out


def _divergence(env_files: dict[str, dict[str, tuple[str, int]]]
                ) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    declared = sorted({key for keys in env_files.values() for key in keys})
    for path in sorted(env_files):
        keys = env_files[path]
        for key in declared:
            if key in keys:
                continue
            out.append(_observation(
                C_ENV_DIVERGENCE, "ss3_env_key_missing", "low",
                f"{key} is declared in another environment file and absent "
                f"here, so the two environments do not configure the same "
                f"surface.",
                path, 1, f"{key} (absent)", Confidence.MEDIUM))
        if not _PRODUCTION.search(posixpath.basename(path)):
            continue
        for key, (value, line) in sorted(keys.items()):
            for fragment, unsafe, detail in _UNSAFE_IN_PRODUCTION:
                if fragment in key and unsafe.match(value):
                    out.append(_observation(
                        C_ENV_DIVERGENCE, "ss3_unsafe_value_in_environment",
                        "high", detail, path, line, f"{key}={value}",
                        Confidence.HIGH))
    return out


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for readable config, infrastructure and source
    blobs. Config rules apply to config paths; log masking applies to all."""
    ports: list[SecurityObservation] = []
    database: list[SecurityObservation] = []
    logs: list[SecurityObservation] = []
    env_files: dict[str, dict[str, tuple[str, int]]] = {}

    for path in sorted(blobs):
        text = blobs[path]
        logs.extend(_logs(path, text))
        if not is_config_path(path):
            continue
        ports.extend(_ports(path, text))
        database.extend(_db(path, text))
        if _ENV_FILE.search(path):
            env_files[path] = _env_keys(text)

    divergence = _divergence(env_files) if len(env_files) > 1 else []
    if len(env_files) > 1:
        divergence_metric = Measurement.measured(float(len(divergence)))
    else:
        divergence_metric = Measurement.not_collected(
            f"env_divergence: {len(env_files)} environment file(s) found; "
            f"divergence needs at least two to compare, so this is "
            f"unmeasurable rather than absent (P3-D11)")

    observations = sorted(
        ports + database + logs + divergence,
        key=lambda o: (o.category, o.path, o.rule, o.line or 0))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS3, family=family_of(ScanSignalId.SS3),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(observations))),
            categories={
                C_EXPOSED_PORTS: Measurement.measured(float(len(ports))),
                C_DB_SECURITY: Measurement.measured(float(len(database))),
                C_LOG_MASKING: Measurement.measured(float(len(logs))),
                C_ENV_DIVERGENCE: divergence_metric,
                C_FRAMEWORK_DEFAULTS: inherited_pending(C_FRAMEWORK_DEFAULTS),
            }),
        security=observations)
