"""Corpus acceptance record, offline verdict, and YAML persistence (Phase 4)."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from sdlc.benchmarks.models import CaseRole, CaseVisibility

SEPARATION_MARGIN = 0.15
MIN_RUNS_PER_ARM = 3

Exposure = Literal["repo_public", "isolated"]


class Verdict(StrEnum):
    ACCEPTED = "accepted"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"
    NOT_ASSESSED = "not_assessed"


class Reason(StrEnum):
    REFERENCE = "reference"
    FLOOR = "floor"
    SATURATED = "saturated"
    DEGENERATE = "degenerate"
    NO_SEPARATION = "no_separation"


class SuiteCheck(BaseModel):
    passed: bool | None = None
    tests_passed: int = 0
    tests_total: int = 0
    detail: str = ""


class ArmEvidence(BaseModel):
    arm: str
    run_ids: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    mean: float | None = None


class SeparationCheck(BaseModel):
    passed: bool | None = None
    strong: ArmEvidence | None = None
    weak: ArmEvidence | None = None
    margin: float | None = None
    not_comparable: int = 0
    detail: str = ""


class AcceptanceRecord(BaseModel):
    case_id: str
    verdict: Verdict
    reason: Reason | None = None
    note: str | None = None
    oracle_id: str | None = None
    oracle_tests: int = 0
    reference: SuiteCheck | None = None
    floor: SuiteCheck | None = None
    separation: SeparationCheck | None = None
    role: CaseRole = CaseRole.CORPUS
    visibility: CaseVisibility | None = None
    exposure: Exposure = "repo_public"
    kroker_commit: str = "unknown"
    updated: str = ""


def decide(
    reference: SuiteCheck,
    floor: SuiteCheck,
    separation: SeparationCheck | None = None,
) -> tuple[Verdict, Reason | None, str | None]:
    """Decides the acceptance verdict in the order of FR-009 / D-7:
    reference, floor, then separation branches. Until T014, when reference
    and floor pass, not_assessed is returned."""
    if reference.passed is None:
        return (Verdict.REJECTED, Reason.REFERENCE, reference.detail or "no reference/")
    if not reference.passed:
        return (Verdict.REJECTED, Reason.REFERENCE, reference.detail or None)
    if floor.passed is False or floor.tests_passed >= reference.tests_passed:
        return (Verdict.REJECTED, Reason.FLOOR, floor.detail or None)
    # The separation branches return not_assessed until T014
    return (Verdict.NOT_ASSESSED, None, None)


def save_acceptance(record: AcceptanceRecord, target: Path) -> Path:
    """Saves AcceptanceRecord as ASCII YAML with fixed key order."""
    path = target / "acceptance.yaml" if target.is_dir() else target
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.model_dump(mode="json")
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    path.write_text(text, encoding="ascii")
    return path


def load_acceptance(target: Path) -> AcceptanceRecord | None:
    """Loads AcceptanceRecord from <target> or <target>/acceptance.yaml.
    Returns None when the file does not exist."""
    path = target / "acceptance.yaml" if target.is_dir() else target
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not raw or not isinstance(raw, dict):
        return None
    return AcceptanceRecord.model_validate(raw)
