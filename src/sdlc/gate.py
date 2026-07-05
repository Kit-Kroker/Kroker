"""DeterministicQualityGate (Finding #5).

Pure code — no LLM. Consumes typed evidence (proposer ReviewReport /
AnalysisReport findings, coverage number, lint, traceability) reduced to
CheckResults, and decides pass/fail:

  * absolute checks  — block the merge unconditionally; never overridable.
  * advisory checks  — block only until an audited human override is recorded.

The critical-security check is a floor: it is forced ABSOLUTE even if a
project's config marks it advisory. The advisory LLM `MergeVerdict` is NOT
consulted here — it is only ever an advisory input to a SOFT merge gate,
after this gate has already passed.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CheckClass(str, Enum):
    ABSOLUTE = "absolute"    # never overridable (lint, build, critical security)
    ADVISORY = "advisory"    # overridable by an audited human decision


class CheckResult(BaseModel):
    name: str
    passed: bool
    classification: CheckClass
    detail: str = ""


class GateOverride(BaseModel):
    """An audited human override of a failed advisory check."""
    check: str
    approved_by: str          # human identity (retained as calibration signal)
    reason: str


class GateReport(BaseModel):
    passed: bool
    blocking: list[str] = Field(default_factory=list)     # check names still blocking
    overridden: list[str] = Field(default_factory=list)   # advisory checks waved through
    checks: list[CheckResult]


class QualityGateInput(BaseModel):
    """Input contract for the `evaluate_gate` activity. Lives next to the
    gate types it references (CheckResult/GateOverride) so the pure gate
    module is the single home for the gate's data model."""
    checks: list[CheckResult]
    overrides: list[GateOverride] | None = None


# Never demotable to advisory, whatever a project configures.
ABSOLUTE_FLOOR: frozenset[str] = frozenset({"security_no_critical"})


def build_check(name: str, passed: bool, requested: CheckClass,
                detail: str = "") -> CheckResult:
    """Construct a CheckResult, forcing floor checks to ABSOLUTE."""
    classification = (CheckClass.ABSOLUTE if name in ABSOLUTE_FLOOR
                      else requested)
    return CheckResult(name=name, passed=passed,
                       classification=classification, detail=detail)


def evaluate_quality_gate(
    checks: list[CheckResult],
    overrides: list[GateOverride] | None = None,
) -> GateReport:
    override_names = {o.check for o in (overrides or [])}
    blocking: list[str] = []
    overridden: list[str] = []
    for c in checks:
        if c.passed:
            continue
        if c.classification is CheckClass.ABSOLUTE:
            blocking.append(c.name)                 # absolute: override ignored
        elif c.name in override_names:
            overridden.append(c.name)               # advisory: audited waiver
        else:
            blocking.append(c.name)
    return GateReport(passed=not blocking, blocking=blocking,
                      overridden=overridden, checks=checks)
