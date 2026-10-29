"""GET /api/compare (018 T068; R-9, read-routes.md, data-model A 2.4).

The v5 Compare read: arms x graphs with SC and $/case, the description
line (the SC weights and the judge from benchmarks/config.yaml), and the
rework-by-canonical-stage heatmap in CELL_STAGE_ORDER. Read-only: the
records load through the benchmarks evidence chain (never report.py at
module scope), a malformed JSONL line degrades its own run, and a root
without records answers ``available: False`` with the root path — never
a 500.
"""

from __future__ import annotations

import os
from pathlib import Path
from statistics import fmean
from typing import Literal

import yaml
from pydantic import BaseModel

from ..benchmarks.evidence import load_evidence
from ..benchmarks.grid import MIN_OBSERVATIONS
from ..benchmarks.models import CELL_STAGE_ORDER, BenchmarkRecord
from ..benchmarks.score import load_config_weights

_CONFIG = Path(__file__).resolve().parents[3] / "benchmarks" / "config.yaml"


class CompareCellWire(BaseModel):
    graph: str
    sc: float | None = None
    cost_per_case: float | None = None


class CompareArmWire(BaseModel):
    name: str
    harness: str
    model: str
    note: str | None = None
    cells: list[CompareCellWire]


class HeatCellWire(BaseModel):
    state: Literal["value", "low_n", "blank"]
    value: float | None = None
    n: int


class HeatRowWire(BaseModel):
    name: str
    cells: list[HeatCellWire]


class CompareWire(BaseModel):
    available: bool
    root: str
    description: str | None = None
    graphs: list[str]
    arms: list[CompareArmWire]
    heat_columns: list[str]
    heat_rows: list[HeatRowWire]


def _judge_model() -> str | None:
    """The judge id from benchmarks/config.yaml, None when unreadable."""
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
    except OSError:
        return None
    judge = data.get("default_judge_model")
    return str(judge) if judge else None


def _description() -> str | None:
    weights = load_config_weights()
    judge = _judge_model()
    parts = [f"SC weights quality {weights.quality} · cost {weights.cost} · speed {weights.speed}"]
    if judge:
        parts.append(f"judge {judge}")
    return ", ".join(parts)


def compare(runs_root: str | None = None) -> CompareWire:
    """The compare wire over the runs root ($SDLC_RUNS_ROOT or ./runs)."""
    root = Path(runs_root or os.environ.get("SDLC_RUNS_ROOT", "./runs"))
    evidence = load_evidence(all_=True, root=str(root))
    records = evidence.records
    if not records:
        return CompareWire(
            available=False,
            root=str(root),
            description=_description(),
            graphs=[],
            arms=[],
            heat_columns=[],
            heat_rows=[],
        )

    # A record without an arm cannot join a comparison row; the layer never
    # emits one, and the route does not invent a bucket for it.
    by_arm: dict[str, list[BenchmarkRecord]] = {}
    for r in records:
        arm = r.arm
        if arm is None:
            continue
        by_arm.setdefault(arm, []).append(r)
    records_by_stage = [r for group in by_arm.values() for r in group]
    graphs = sorted({r.graph.graph_sha for r in records_by_stage if r.graph is not None})
    arm_names = sorted(by_arm)
    arms: list[CompareArmWire] = []
    for name in arm_names:
        mine = by_arm[name]
        cells: list[CompareCellWire] = []
        for sha in graphs:
            group = [r for r in mine if r.graph is not None and r.graph.graph_sha == sha]
            scores = [
                r.quality.score
                for r in group
                if r.quality is not None and r.quality.score is not None
            ]
            costs = [r.cost.usd for r in group if r.cost is not None and r.cost.usd is not None]
            cases = {r.case_id for r in group}
            cells.append(
                CompareCellWire(
                    graph=sha,
                    sc=fmean(scores) if scores else None,
                    # An unpriced arm never folds a miss in as zero.
                    cost_per_case=(sum(costs) / len(cases)) if costs and cases else None,
                )
            )
        arms.append(
            CompareArmWire(
                name=name,
                harness=mine[0].harness or "",
                model=mine[0].model or "",
                note=None,
                cells=cells,
            )
        )

    def stage_of(r) -> str | None:
        return r.graph.node_stage if r.graph is not None else None

    heat_columns = [s for s in CELL_STAGE_ORDER if any(stage_of(r) == s for r in records_by_stage)]
    heat_rows: list[HeatRowWire] = []
    for name in arm_names:
        mine = by_arm[name]
        row: list[HeatCellWire] = []
        for col in heat_columns:
            at = [r for r in mine if stage_of(r) == col]
            n = len(at)
            fixes = [r.fix_attempts for r in at if r.fix_attempts is not None]
            if n == 0:
                row.append(HeatCellWire(state="blank", value=None, n=0))
            elif n < MIN_OBSERVATIONS:
                row.append(HeatCellWire(state="low_n", value=fmean(fixes) if fixes else None, n=n))
            else:
                row.append(HeatCellWire(state="value", value=fmean(fixes) if fixes else None, n=n))
        heat_rows.append(HeatRowWire(name=name, cells=row))

    return CompareWire(
        available=True,
        root=str(root),
        description=_description(),
        graphs=graphs,
        arms=arms,
        heat_columns=heat_columns,
        heat_rows=heat_rows,
    )
