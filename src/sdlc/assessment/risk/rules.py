"""The tables, and the sha that makes them a memo input (E-49).

Every number that can move a score lives here or in a module named by
RULE_MODULES. Retuning a weight must invalidate exactly the assessments it
would move, which a hand-maintained version int does not achieve -- E-46's
D10 records why.
"""
from __future__ import annotations

import hashlib

from ..scan.models import (
    C_AUTHN_AUTHZ, C_DB_SECURITY, C_INPUT_VALIDATION, C_TLS, CATEGORIES,
    ScanSignalId,
)
from ..scan.rules import module_sha
from .models import ControlFamily, Criticality, Severity

# --- severity (RD4) -----------------------------------------------------
# A table, not a formula: it is auditable in the FR-921 bundle and reviewable
# as a diff. Read as (severity_hint, capability criticality) -> Severity.
_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH,
          Severity.CRITICAL)
_HINT_INDEX = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_CRIT_SHIFT = {Criticality.HIGH: 1, Criticality.MEDIUM: 0, Criticality.LOW: -1}

SEVERITY_TABLE: dict[tuple[str, Criticality], Severity] = {
    (hint, crit): _ORDER[min(len(_ORDER) - 1, max(0, i + shift))]
    for hint, i in _HINT_INDEX.items()
    for crit, shift in _CRIT_SHIFT.items()
}

# Confidence never RAISES severity; a LOW-confidence pattern match drops one
# step. Applied after the table, in severity.py.
LOW_CONFIDENCE_SHIFT = -1

# --- control coverage (RD5) ---------------------------------------------
# Two families have no source and say so HERE rather than by absence: a
# missing key would read as an oversight, an empty tuple reads as a finding.
CONTROL_SOURCES: dict[ControlFamily, tuple[str, ...]] = {
    ControlFamily.AUTHENTICATION: (C_AUTHN_AUTHZ,),
    ControlFamily.VALIDATION: (C_INPUT_VALIDATION,),
    ControlFamily.ENCRYPTION: (C_TLS, C_DB_SECURITY),
    ControlFamily.AUTHORIZATION: (),    # SS1 collapses authn and authz
    ControlFamily.MONITORING: (),       # log_masking is masking, not presence
}

NO_SOURCE_REASON: dict[ControlFamily, str] = {
    ControlFamily.AUTHORIZATION: (
        "SS1 collapses authentication and authorization into one "
        "authn_authz category, so authorization has no separate source "
        "(E-49 RD5); an SS1 v2 that separates them is the follow-up"),
    ControlFamily.MONITORING: (
        "no scan signal collects monitoring presence -- log_masking is "
        "masking, not presence (E-49 RD5)"),
}

# --- composites ---------------------------------------------------------
F_LIKELIHOOD = "likelihood"
F_IMPACT = "impact"
F_EXPOSURE = "exposure"
F_COVERAGE_GAP = "coverage_gap"
F_TESTABILITY = "testability"
F_DEFECT_DENSITY = "defect_density"
F_CHANGE_VELOCITY = "change_velocity"
F_SECURITY = "security"
F_QA = "qa"

SECURITY_WEIGHTS: dict[str, float] = {
    F_EXPOSURE: 0.25, F_IMPACT: 0.4, F_LIKELIHOOD: 0.35,
}
QA_WEIGHTS: dict[str, float] = {
    F_CHANGE_VELOCITY: 0.15, F_COVERAGE_GAP: 0.35,
    F_DEFECT_DENSITY: 0.15, F_TESTABILITY: 0.35,
}
UNIFIED_WEIGHTS: dict[str, float] = {F_QA: 0.4, F_SECURITY: 0.6}

# The two QA factors with no collected source (RD3).
UNSOURCED_QA: dict[str, str] = {
    F_DEFECT_DENSITY: (
        "defect_density: no issue-tracker input; /enrich (E-56) is the "
        "declared stage input that would supply it"),
    F_CHANGE_VELOCITY: (
        "change_velocity: no signal reads git history, and E-41b found "
        "history least reliable on this repository population"),
}

# --- cross-capability caps (RD10) ---------------------------------------
# The scan categories that PRODUCE SecurityObservation rows, derived from
# scan's own CATEGORIES rather than hand-listed: a second list of the same
# categories is the duplicate registry ADR-6 already cost us.
SECURITY_CATEGORIES: frozenset[str] = frozenset(
    CATEGORIES[ScanSignalId.SS1] + CATEGORIES[ScanSignalId.SS3])

SHARED_MAX_ROWS = 100
CASCADE_MAX_DEPTH = 4
CASCADE_MAX_PATHS = 50

# build.py is here for the reason the others are: it carries the baseline
# STRIDE category and the POTENTIAL classification, so editing it moves every
# score. prompt.py, apply.py and assessment/verification.py join with plan 2
# (P2-D7): the renderer decides what the model sees, apply decides what
# survives, the verifier decides what is dropped -- all three can move a
# STORED map. models.py joins because it carries MAX_DRIVERS and EDGE_EVIDENCE_MAX:
# caps in a contract module are still caps, and a stored map of an older
# contract shape would otherwise be reused under an unchanged key.
RULE_MODULES: tuple[str, ...] = (
    "sdlc.assessment.risk.rules",
    "sdlc.assessment.risk.models",
    "sdlc.assessment.risk.severity",
    "sdlc.assessment.risk.controls",
    "sdlc.assessment.risk.factors",
    "sdlc.assessment.risk.composites",
    "sdlc.assessment.risk.crosscap",
    "sdlc.assessment.risk.build",
    "sdlc.assessment.risk.prompt",
    "sdlc.assessment.risk.apply",
    "sdlc.assessment.verification",
)


def rules_sha() -> str:
    """Hashed over module BYTES, transitively across every module that can
    move a score. scan/rules.py's module_sha is reused rather than
    reimplemented: it uses find_spec so hashing never executes the module."""
    payload = "|".join(["risk", *(module_sha(m) for m in RULE_MODULES)])
    return hashlib.sha256(payload.encode()).hexdigest()
