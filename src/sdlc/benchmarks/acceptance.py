"""Corpus acceptance record, offline verdict, and YAML persistence (Phase 4)."""

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, Field

from sdlc.benchmarks.models import CaseRole, CaseVisibility, StageReach

if TYPE_CHECKING:
    from sdlc.benchmarks.runs import Run

SEPARATION_MARGIN = 0.15
STALL_EPSILON = 0.05
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
    STALLED = "stalled"
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
    stall_points: list[str] = Field(default_factory=list)
    reaches: list[StageReach | None] = Field(default_factory=list, exclude=True)


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


def separation(
    runs: list["Run"],
    strong: str | None,
    weak: str | None,
    oracle_id: str | None,
) -> SeparationCheck:
    """Computes separation check between strong and weak arms for a given oracle identity.

    Only graded runs matching oracle_id are considered; lost or grading-failed runs enter nothing.
    Runs matching other oracle IDs or other arms increment not_comparable.
    """
    if strong is None:
        return SeparationCheck(passed=None, detail="no strong_arm configured")

    strong_runs: list[str] = []
    strong_scores: list[float] = []
    strong_stall_points: list[str] = []
    strong_reaches: list[StageReach | None] = []
    weak_runs: list[str] = []
    weak_scores: list[float] = []
    weak_stall_points: list[str] = []
    weak_reaches: list[StageReach | None] = []
    not_comparable = 0

    for r in runs:
        if r.status != "graded":
            continue
        if r.oracle_id != oracle_id:
            not_comparable += 1
            continue

        if r.arm == strong:
            strong_runs.append(r.run_id)
            strong_scores.append(r.partial_credit if r.partial_credit is not None else 0.0)
            if r.stage_reach is not None and r.stage_reach.last_stage is not None:
                strong_stall_points.append(r.stage_reach.last_stage)
            strong_reaches.append(r.stage_reach)
        elif weak is not None and r.arm == weak:
            weak_runs.append(r.run_id)
            weak_scores.append(r.partial_credit if r.partial_credit is not None else 0.0)
            if r.stage_reach is not None and r.stage_reach.last_stage is not None:
                weak_stall_points.append(r.stage_reach.last_stage)
            weak_reaches.append(r.stage_reach)
        else:
            not_comparable += 1

    strong_mean = sum(strong_scores) / len(strong_scores) if strong_scores else None
    weak_mean = sum(weak_scores) / len(weak_scores) if weak_scores else None

    margin: float | None = None
    passed: bool | None = None
    if strong_mean is not None and weak_mean is not None:
        margin = strong_mean - weak_mean
        passed = margin >= (SEPARATION_MARGIN - 1e-9)

    strong_ev = ArmEvidence(
        arm=strong,
        run_ids=strong_runs,
        scores=strong_scores,
        mean=strong_mean,
        stall_points=strong_stall_points,
        reaches=strong_reaches,
    )
    weak_ev = (
        ArmEvidence(
            arm=weak,
            run_ids=weak_runs,
            scores=weak_scores,
            mean=weak_mean,
            stall_points=weak_stall_points,
            reaches=weak_reaches,
        )
        if weak is not None
        else None
    )

    return SeparationCheck(
        passed=passed,
        strong=strong_ev,
        weak=weak_ev,
        margin=margin,
        not_comparable=not_comparable,
    )


def decide(
    reference: SuiteCheck,
    floor: SuiteCheck,
    separation: SeparationCheck | None = None,
) -> tuple[Verdict, Reason | None, str | None]:
    """Decides the acceptance verdict in the order of FR-009 / D-7:
    reference, floor, saturated, degenerate, then separation branches.
    """
    if reference.passed is None:
        return (Verdict.REJECTED, Reason.REFERENCE, reference.detail or "no reference/")
    if not reference.passed:
        return (Verdict.REJECTED, Reason.REFERENCE, reference.detail or None)
    if floor.passed is False or floor.tests_passed >= reference.tests_passed:
        return (Verdict.REJECTED, Reason.FLOOR, floor.detail or None)

    if separation is None:
        return (Verdict.NOT_ASSESSED, None, None)

    if separation.detail and "not assessed for" in separation.detail:
        return (Verdict.NOT_ASSESSED, None, separation.detail)

    if separation.passed is None and (not separation.strong or not separation.strong.scores):
        return (Verdict.NOT_ASSESSED, None, separation.detail or "no strong arm runs")

    if separation.strong and separation.strong.scores:
        if all(s == 1.0 for s in separation.strong.scores):
            return (Verdict.REJECTED, Reason.SATURATED, None)

        # Stalled verdict (017 FR-024, C-4, D-7, advisor-unlock-21):
        # Fires between SATURATED and DEGENERATE when all four hold:
        # 1. every graded run in both arms has stage_reach;
        # 2. every run's partial credit is <= STALL_EPSILON (0.05);
        # 3. all runs share one last_stage (and that stage is not None);
        # 4. that stage did not complete: for all runs, last_stage_outcome != "pass"
        #    or last_stage != final_stage.
        if (
            separation.weak
            and separation.weak.scores
            and separation.strong.reaches
            and separation.weak.reaches
            and all(r is not None for r in separation.strong.reaches + separation.weak.reaches)
        ):
            all_scores = separation.strong.scores + separation.weak.scores
            if all(s <= (STALL_EPSILON + 1e-9) for s in all_scores):
                all_reaches = [
                    r
                    for r in (separation.strong.reaches + separation.weak.reaches)
                    if r is not None
                ]
                all_stages = [r.last_stage for r in all_reaches]
                if all_stages and all_stages[0] is not None and len(set(all_stages)) == 1:
                    stalled_stage = all_stages[0]
                    if all(
                        r.last_stage_outcome != "pass" or r.last_stage != r.final_stage
                        for r in all_reaches
                    ):
                        return (
                            Verdict.NOT_ASSESSED,
                            Reason.STALLED,
                            f"not separable: stalled at {stalled_stage}",
                        )

        if all(s == 0.0 for s in separation.strong.scores):
            return (Verdict.REJECTED, Reason.DEGENERATE, None)

    if not separation.weak or not separation.weak.scores:
        return (Verdict.NOT_ASSESSED, None, "no weak arm runs")

    if separation.passed is False or (
        separation.margin is not None and separation.margin < (SEPARATION_MARGIN - 1e-9)
    ):
        s_mean = separation.strong.mean if separation.strong else None
        w_mean = separation.weak.mean if separation.weak else None
        note = (
            f"strong {s_mean:.4f}, weak {w_mean:.4f}, margin {separation.margin:.4f}"
            if (s_mean is not None and w_mean is not None and separation.margin is not None)
            else "no separation"
        )
        return (Verdict.REJECTED, Reason.NO_SEPARATION, note)

    if separation.passed is True:
        strong_n = len(separation.strong.scores) if separation.strong else 0
        weak_n = len(separation.weak.scores) if separation.weak else 0
        if strong_n >= MIN_RUNS_PER_ARM and weak_n >= MIN_RUNS_PER_ARM:
            return (Verdict.ACCEPTED, None, None)
        return (Verdict.PROVISIONAL, None, None)

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
