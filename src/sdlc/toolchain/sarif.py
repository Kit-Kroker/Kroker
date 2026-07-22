"""SARIF -> SecurityReport normalizer (ADR-15 security seam, FR-108).

The canonical security-finding shape is SecurityReport/SecurityFinding
(models.py); the gate's security_no_critical check reads it unchanged. Today's
default security_scan keeps its offline regex ruleset; an OPT-IN semgrep path
shells `semgrep --sarif` and feeds its output through findings_from_sarif ->
the SAME SecurityReport. This module is only the normalizer half of that seam.

Fail-safe: a malformed/partial SARIF yields [] (never raises), mirroring
measure_coverage's measured=False discipline — a broken scan must never
fabricate a blocking finding OR crash the gate.
"""
from __future__ import annotations

from ..models import SecurityFinding, SecurityReport

# SARIF result.level -> our severity scale (SecurityFinding.severity Literal).
# semgrep emits "error" for its blocking rules, so error -> critical keeps the
# SC-5 absolute floor biting. Unknown levels fall back to "high" (conservative).
_LEVEL_TO_SEVERITY = {
    "error": "critical",
    "warning": "high",
    "note": "medium",
    "none": "low",
}


def _first_location_path(res: dict) -> str:
    locs = res.get("locations")
    if not isinstance(locs, list) or not locs:
        return ""
    loc = locs[0]
    if not isinstance(loc, dict):
        return ""
    phys = loc.get("physicalLocation")
    if not isinstance(phys, dict):
        return ""
    art = phys.get("artifactLocation")
    if not isinstance(art, dict):
        return ""
    return str(art.get("uri", "") or "")


def findings_from_sarif(doc: dict) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    if not isinstance(doc, dict):
        return findings
    runs = doc.get("runs")
    if not isinstance(runs, list):
        return findings
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for res in results:
            if not isinstance(res, dict):
                continue
            severity = _LEVEL_TO_SEVERITY.get(res.get("level", "warning"), "high")
            message = res.get("message")
            detail = message.get("text", "") if isinstance(message, dict) else ""
            findings.append(SecurityFinding(
                severity=severity,
                rule=str(res.get("ruleId") or "sarif"),
                detail=str(detail or ""),
                path=_first_location_path(res)))
    return findings


def report_from_sarif(doc: dict) -> SecurityReport:
    findings = findings_from_sarif(doc)
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings)
