"""case x stage rework-density heatmap (E-36).

Pure aggregation + rendering over BenchmarkRecords already on disk. No I/O,
no temporalio -- mirrors observability/export.py. The finalize activity
(report.py) owns the file writes.
"""
from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from .models import BenchmarkOutcome, BenchmarkRecord, BenchmarkScope

# Record-vocabulary stage order (SDLC-spec 15-stage DAG); the synthetic
# ``oracle`` column trails. Only columns with an observed cell are rendered.
CANONICAL_STAGES: list[str] = [
    "intake", "constitution", "context", "requirements", "research",
    "clarify", "architecture", "planning", "code", "review", "analyze",
    "qa", "quality_gate", "deploy", "retro",
]
ORACLE_STAGE = "oracle"

# A revise round re-enters a stage, so REVISED is rework alongside FAIL/ESCALATED.
REWORK_OUTCOMES: set[BenchmarkOutcome] = {
    BenchmarkOutcome.FAIL, BenchmarkOutcome.ESCALATED, BenchmarkOutcome.REVISED,
}


class HeatmapCell(BaseModel):
    case: str
    stage: str
    gate_rejects: int
    fix_attempts: int
    oracle_fails: int
    n_runs: int
    density: float


class Heatmap(BaseModel):
    cells: list[HeatmapCell] = Field(default_factory=list)
    cases: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    max_density: float = 0.0
    language_by_case: dict[str, str] = Field(default_factory=dict)


def build_heatmap(records: list[BenchmarkRecord],
                  language_by_case: dict[str, str] | None = None) -> Heatmap:
    language_by_case = language_by_case or {}

    runs_by_case: dict[str, set[str]] = defaultdict(set)
    for r in records:
        runs_by_case[r.case_id].add(r.run_id)

    acc: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"gate": 0, "fix": 0, "oracle": 0})
    for r in records:
        is_oracle = r.scope is BenchmarkScope.ORACLE
        stage = ORACLE_STAGE if is_oracle else r.stage
        key = (r.case_id, stage)
        if r.outcome in REWORK_OUTCOMES:
            acc[key]["oracle" if is_oracle else "gate"] += 1
        acc[key]["fix"] += r.fix_attempts

    cells: list[HeatmapCell] = []
    for (case, stage), a in acc.items():
        n_runs = max(len(runs_by_case[case]), 1)
        total = a["gate"] + a["fix"] + a["oracle"]
        cells.append(HeatmapCell(
            case=case, stage=stage, gate_rejects=a["gate"],
            fix_attempts=a["fix"], oracle_fails=a["oracle"],
            n_runs=n_runs, density=total / n_runs))

    cases = sorted({c.case for c in cells})
    present = {c.stage for c in cells}
    ordered = [s for s in CANONICAL_STAGES if s in present]
    unknown = sorted(present - set(CANONICAL_STAGES) - {ORACLE_STAGE})
    stages = ordered + unknown + ([ORACLE_STAGE] if ORACLE_STAGE in present else [])
    max_density = max((c.density for c in cells), default=0.0)
    lang = {c: language_by_case.get(c, "") for c in cases}
    return Heatmap(cells=cells, cases=cases, stages=stages,
                   max_density=max_density, language_by_case=lang)
