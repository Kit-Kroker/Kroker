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

Two properties make the gate fail closed on its own inputs. `MERGE_REQUIRED_CHECKS`
is the manifest of checks the merge gate must see: any name absent from the
evaluated list is synthesized as a failing MISCONFIGURED check at its manifest
classification, so a check that silently stopped being produced blocks instead of
passing quietly. And `ABSOLUTE_FLOOR` is re-asserted on input rather than only at
construction, so a directly-constructed CheckResult cannot demote a floor check
and waive it with a single override.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, Field


class CheckClass(StrEnum):
    ABSOLUTE = "absolute"  # never overridable (lint, build, critical security)
    ADVISORY = "advisory"  # overridable by an audited human decision


class CheckResult(BaseModel):
    name: str
    passed: bool
    classification: CheckClass
    detail: str = ""


class GateOverride(BaseModel):
    """An audited human override of a failed advisory check."""

    check: str
    approved_by: str  # human identity (retained as calibration signal)
    reason: str


class GateReport(BaseModel):
    passed: bool
    blocking: list[str] = Field(default_factory=list)  # check names still blocking
    overridden: list[str] = Field(default_factory=list)  # advisory checks waved through
    checks: list[CheckResult]


class QualityGateInput(BaseModel):
    """Input contract for the `evaluate_gate` activity. Lives next to the
    gate types it references (CheckResult/GateOverride) so the pure gate
    module is the single home for the gate's data model."""

    checks: list[CheckResult]
    overrides: list[GateOverride] | None = None


# Never demotable to advisory, whatever a project configures.
ABSOLUTE_FLOOR: frozenset[str] = frozenset(
    {
        "security_no_critical",
        # FR-915: "the scan could not run" is as absolute as "the scan found a
        # critical". Outside the floor, a call site could request ADVISORY and
        # reopen the bypass this check exists to close.
        "security_scan_collected",
    }
)

# The checks the merge gate must see. Absence is as severe as failure: a name
# missing from the evaluated input is synthesized as a failing check at the
# classification it carries here. Edits deserve ABSOLUTE_FLOOR-grade scrutiny —
# after C3, deleting an entry is the only way to make a dropped check quiet
# again, so the pressure point moved from the producer to this constant.
MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]] = MappingProxyType(
    {
        "build_integration_green": CheckClass.ABSOLUTE,
        "lint_clean": CheckClass.ABSOLUTE,
        "security_scan_collected": CheckClass.ABSOLUTE,
        "security_no_critical": CheckClass.ABSOLUTE,
        "review_severity": CheckClass.ADVISORY,
        "traceability": CheckClass.ADVISORY,
        "coverage": CheckClass.ADVISORY,
    }
)


def build_check(name: str, passed: bool, requested: CheckClass, detail: str = "") -> CheckResult:
    """Construct a CheckResult, forcing floor checks to ABSOLUTE."""
    classification = CheckClass.ABSOLUTE if name in ABSOLUTE_FLOOR else requested
    return CheckResult(name=name, passed=passed, classification=classification, detail=detail)


def _normalized(checks: list[CheckResult]) -> list[CheckResult]:
    """Re-assert the floor on checks that were handed in, not built.

    `build_check` forces ABSOLUTE_FLOOR names to ABSOLUTE at construction, but
    `CheckResult` is a plain model: a caller can construct one directly, demote
    a floor check to ADVISORY, and waive it with a single override. Rebuilding
    here — before the loop, not inside it — means the loop, the echoed
    `GateReport.checks`, and the merge step's absolute/advisory split all read
    the same classification.
    """
    return [
        build_check(c.name, c.passed, c.classification, c.detail) if c.name in ABSOLUTE_FLOOR else c
        for c in checks
    ]


def _synthesized(present: set[str]) -> list[CheckResult]:
    """A failing check for every required name the caller did not hand in.

    FR-915 ruled once that "the scan could not run" is as absolute as "the scan
    found a critical"; this generalizes that ruling from one check to the
    manifest. Built through `build_check` so a manifest entry that named a floor
    check ADVISORY would still come back ABSOLUTE.
    """
    return [
        build_check(
            name,
            False,
            MERGE_REQUIRED_CHECKS[name],
            detail=f"MISCONFIGURED: required check {name!r} absent from gate input",
        )
        for name in MERGE_REQUIRED_CHECKS
        if name not in present
    ]


def evaluate_quality_gate(
    checks: list[CheckResult],
    overrides: list[GateOverride] | None = None,
) -> GateReport:
    normalized = _normalized(checks)
    # Copy-then-append: the caller's list is never mutated. merge/step.py hands
    # the same list object to both of its evaluations (:316-318, :378-380).
    evaluated = normalized + _synthesized({c.name for c in normalized})
    override_names = {o.check for o in (overrides or [])}
    blocking: list[str] = []
    overridden: list[str] = []
    for c in evaluated:
        if c.passed:
            continue
        if c.classification is CheckClass.ABSOLUTE:
            blocking.append(c.name)  # absolute: override ignored
        elif c.name in override_names:
            overridden.append(c.name)  # advisory: audited waiver
        else:
            blocking.append(c.name)
    return GateReport(
        passed=not blocking, blocking=blocking, overridden=overridden, checks=evaluated
    )
