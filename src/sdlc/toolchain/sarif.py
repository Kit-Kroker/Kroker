"""SARIF -> SecurityReport normalizer (ADR-15 security seam, FR-108).

The canonical security-finding shape is SecurityReport/SecurityFinding
(models.py); the gate's security_no_critical check reads it unchanged. Today's
default security_scan keeps its offline regex ruleset; an OPT-IN semgrep path
shells `semgrep --sarif` and feeds its output through findings_from_sarif ->
the SAME SecurityReport. This module is only the normalizer half of that seam.

Fail-safe: a malformed/partial SARIF yields NOT_COLLECTED (never raises),
mirroring measure_coverage's Measurement discipline — a broken scan must never
fabricate a blocking finding OR crash the gate, and must not read as a passing
absolute floor.
"""
from __future__ import annotations

from ..measurement import CollectionState
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
    """A malformed or partial SARIF yields NOT_COLLECTED, never a clean-looking
    zero-critical report (FR-915). findings_from_sarif stays fail-safe-empty:
    a broken scan must not fabricate a blocking finding OR crash the gate --
    but it must also not read as a passing absolute floor."""
    if not _is_well_formed(doc):
        return SecurityReport(critical=0, state=CollectionState.NOT_COLLECTED,
                              reason="SARIF document malformed or partial")
    findings = findings_from_sarif(doc)
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings,
                          state=CollectionState.MEASURED)


def _is_well_formed(doc: dict) -> bool:
    """A document is well-formed when it has a `runs` list whose every entry
    is a dict carrying a `results` list. Anything else means we did not read a
    scan, whatever findings_from_sarif managed to salvage."""
    if not isinstance(doc, dict):
        return False
    runs = doc.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("results"), list):
            return False
    return True
