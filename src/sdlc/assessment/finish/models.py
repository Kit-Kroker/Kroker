"""FR-918 (E-51): the finish phase's contracts -- the 14-criterion manifest
and the report that carries them.

Pure by design -- Pydantic, measurement.py and gate.py's CheckResult/
CheckClass only. This module must never import assessment/models.py,
activities.py, or temporalio, exactly as gates/models.py must not.
FD2: evaluated criteria and phase exits are CheckResults; a criterion whose
producer did not collect is a row in `owed` instead.
FD3: owed is neither pass nor fail -- an absent producer never reads as
either, and all 14 stay addressable as a fixed manifest.
FD11: a criterion's state derives from its inputs -- producer phase absent
means owed; a measured producer with a not_collected sub-artifact means an
evaluated fail; measured inputs mean pass/fail by predicate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from ...gate import CheckClass, CheckResult
from ...measurement import Measurement

# Wire names (FD10): never renamed once landed -- the GUARD_PATCH_ID rule.
CRITERIA_MANIFEST: tuple[str, ...] = (
    "c01_security_context",
    "c02_qa_context",
    "c03_stride_per_capability",
    "c04_vulnerabilities_mapped",
    "c05_security_scoring",
    "c06_qa_scoring",
    "c07_unified_drivers",
    "c08_findings_traceable",
    "c09_cross_capability_risks",
    "c10_coverage_floor",
    "c11_blueprint_comparison",
    "c12_domain_model_traceability",
    "c13_five_reports",
    "c14_cross_reference_integrity",
)


class FinishReport(BaseModel):
    """The FINISH phase's verdict over the assembled typed artifacts.

    `criteria` carries the evaluated members of `CRITERIA_MANIFEST` only;
    `owed` names every criterion whose producer could not be evaluated (the
    `RiskGateReport.deferred` precedent, promoted to a first-class field
    because the 14 are a fixed manifest), and `exits` carries the per-phase
    exit rows plus the `xref:<domain>` walk. `passed` reads ABSOLUTE rows
    only -- owed rows are not rows and never fail it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    collected: Measurement
    criteria: tuple[CheckResult, ...] = ()
    owed: tuple[str, ...] = ()
    exits: tuple[CheckResult, ...] = ()

    @model_validator(mode="after")
    def _rows_are_sorted_and_unique(self) -> FinishReport:
        for field_name in ("criteria", "exits"):
            names = [r.name for r in getattr(self, field_name)]
            if names != sorted(names):
                raise ValueError(
                    f"{field_name} must be sorted by name, got {names} -- a "
                    f"producer emitting discovery order is an NFR-10 "
                    f"determinism bug, and repairing it here would hide "
                    f"that bug"
                )
            if len(set(names)) != len(names):
                raise ValueError(f"duplicate {field_name} name in {names}")
        return self

    @model_validator(mode="after")
    def _owed_is_sorted_and_deduped(self) -> FinishReport:
        values = list(self.owed)
        if values != sorted(set(values)):
            raise ValueError(
                f"owed {values} is not sorted and deduped -- a producer "
                f"emitting evaluation order is an NFR-10 determinism bug, "
                f"and repairing it here would hide that bug"
            )
        return self

    @property
    def passed(self) -> bool:
        """Every ABSOLUTE row in criteria + exits passed. Empty is vacuously
        true: orchestration guarantees rows exist before `passed` means
        anything."""
        return all(
            row.passed
            for row in self.criteria + self.exits
            if row.classification is CheckClass.ABSOLUTE
        )
