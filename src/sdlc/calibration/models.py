"""C7: the types the calibration ledger is made of.

Pure. No temporalio, no I/O -- these travel through activity boundaries and
into workflow code, so they must be importable from both.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, Field


class LabelSource(StrEnum):
    """Which kind of evidence produced a sample's outcome label.

    Ruling OQ6: these two populations are never pooled. A judge-backed label
    and a proxy-backed label are not the same measurement, and letting the
    stronger authorize auto-approvals the weaker actually supports is the
    substitution this ledger exists to prevent.
    """

    BENCHMARK = "benchmark"
    PRODUCTION_PROXY = "production-proxy"


class CalibrationSample(BaseModel):
    """One past auto-approve, scored against what actually happened next."""

    gate: str
    bucket_key: str
    confidence: float = Field(ge=0.0, le=1.0)
    outcome_label: float = Field(ge=0.0, le=1.0)
    run_id: str


class CalibrationVerdict(BaseModel):
    """Whether a bucket's self-reported confidence has earned the right to
    skip a human.

    `insufficient_data` is a first-class third state, not an error: it is what
    a cold-start bucket, an unknown model, and a failed lookup all resolve to,
    and it is treated exactly like `uncalibrated` at the decision. Collapsing
    it into either of the other two would be the "check that did not run, read
    as a check that passed" defect one layer up.
    """

    verdict: Literal["calibrated", "uncalibrated", "insufficient_data"]
    n: int = 0
    agreement_rate: float = 0.0


INSUFFICIENT: Final[CalibrationVerdict] = CalibrationVerdict(verdict="insufficient_data")
