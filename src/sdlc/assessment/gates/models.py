"""FR-917 (E-50): the risk gate's own contracts.

Pure by design -- Pydantic, measurement.py and gate.py's CheckResult/
CheckClass only. This module must never import assessment/models.py,
activities.py, or temporalio, exactly as risk/models.py and discover/map.py
must not: a dependency here would appear as a reviewable import.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from ...gate import CheckResult


class RiskGateVerdict(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    PASS = "pass"


class RiskGateReport(BaseModel):
    """FR-917's trichotomy over UnifiedRiskMap + dispositions (GD4).

    `checks` carries at most three rows -- one per CLAUSE, never one per
    capability or per finding (GD5): a clause with nothing to decide
    contributes no row, never a row with some third `passed` state.
    `deferred` names every clause, or per-capability/per-finding instance,
    that could not be evaluated, so a PASS with a non-empty `deferred` is
    visibly different from a clean one (FR-915).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    verdict: RiskGateVerdict
    checks: tuple[CheckResult, ...] = ()
    deferred: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _checks_are_sorted(self) -> RiskGateReport:
        names = [c.name for c in self.checks]
        if names != sorted(names):
            raise ValueError(
                f"checks must be sorted by name, got {names} -- a producer "
                f"emitting discovery order is an NFR-10 determinism bug, and "
                f"repairing it here would hide that bug"
            )
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate check name in {names}")
        return self

    @model_validator(mode="after")
    def _deferred_and_reasons_are_sorted_and_deduped(self) -> RiskGateReport:
        for field_name in ("deferred", "reasons"):
            values = list(getattr(self, field_name))
            if values != sorted(set(values)):
                raise ValueError(
                    f"{field_name} {values} is not sorted and deduped -- a "
                    f"producer emitting evaluation order is an NFR-10 "
                    f"determinism bug, and repairing it here would hide "
                    f"that bug"
                )
        return self


class RiskGateOverride(BaseModel):
    """FR-304: an audited decision to proceed despite a BLOCK verdict, for
    THIS run only (GD10) -- field-for-field on triage/models.py's
    ReadinessOverride, for the same reason: local and pure, so a
    GateDecision cannot appear here and AssessmentWorkflow maps one to the
    other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    approved_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    reason: str
    decided_at: datetime
    gate_round: int
