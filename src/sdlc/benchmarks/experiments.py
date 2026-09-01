"""The improvement cycle's memory: what was tried, what it did, what was
decided.

Stored in benchmarks/experiments/ and COMMITTED TO GIT -- not under runs/,
which is disposable output. The whole value is that negative results
survive; a rolled-back experiment that is not in version control gets
re-tried by whoever forgot.

The tool computes the delta. The human writes the verdict. BENCHMARK.md
section 0 commits this project to the ADR-11 stance -- the instrument is
fixed and versioned, never self-modifying -- and an auto-verdict would
quietly promote it to decision-maker.

Pure: no I/O beyond explicit load/save on a caller-supplied path.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .evidence import Evidence
from .models import CompositeWeights
from .waste_matrix import WASTE_METRICS

# Below this many observations of a cell, a delta IS noise. No p-values on
# n=2 -- statistical theatre over a three-case corpus is worse than no claim.
NOISE_FLOOR = 3

EXPERIMENT_AXES: tuple[str, ...] = ("prompt", "model", "harness", "schema", "tool_org", "memory")

_REPO_ROOT = Path(__file__).resolve().parents[3]


class DeltaRow(BaseModel):
    """candidate minus baseline for one (case, stage, arm) cell. None where
    the cell exists on only one side."""

    case: str
    stage: str
    arm: str
    quality: float | None = None
    cost_usd: float | None = None
    wall_s: float | None = None
    composite: float | None = None
    waste: dict[str, float] = Field(default_factory=dict)
    n: int = 0
    note: str = ""  # "within-noise" when n < NOISE_FLOOR


class Experiment(BaseModel):
    id: str
    axis: str
    change: str
    commit: str = ""
    hypothesis: str = ""
    baseline: str
    candidate: str = ""
    verdict: Literal["keep", "rollback", ""] = ""
    notes: str = ""
    deltas: list[DeltaRow] = Field(default_factory=list)


def experiments_dir() -> Path:
    return Path(
        os.environ.get("SDLC_EXPERIMENTS_ROOT", str(_REPO_ROOT / "benchmarks" / "experiments"))
    )


def new_experiment(
    *,
    name: str,
    axis: str,
    change: str,
    baseline: str,
    commit: str = "",
    hypothesis: str = "",
    today: _dt.date | None = None,
) -> Experiment:
    if axis not in EXPERIMENT_AXES:
        raise ValueError(f"unknown axis {axis!r}; must be one of {list(EXPERIMENT_AXES)}")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    day = (today or _dt.date.today()).isoformat()
    return Experiment(
        id=f"{day}-{slug}",
        axis=axis,
        change=change,
        commit=commit,
        hypothesis=hypothesis,
        baseline=baseline,
    )


def _cells(ev: Evidence, weights: CompositeWeights):
    """{(case, stage, arm): (summary, n, {metric: mean waste})}"""
    from collections import defaultdict

    from .report import aggregate

    waste_sum: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {m: 0.0 for m in WASTE_METRICS}
    )
    waste_n: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in ev.records:
        if r.waste is None:
            continue
        key = (r.case_id, r.stage, f"{r.harness.value if r.harness else ''}#{r.model}")
        waste_n[key] += 1
        for m in WASTE_METRICS:
            waste_sum[key][m] += float(getattr(r.waste, m))

    out = {}
    for s in aggregate("", weights, _records=ev.records):
        key = (s.case_id, s.stage, f"{s.harness.value if s.harness else ''}#{s.model}")
        n = waste_n.get(key, 0)
        waste = {m: waste_sum[key][m] / n for m in WASTE_METRICS} if n else {}
        out[key] = (s, n, waste)
    return out


def compute_deltas(
    baseline: Evidence, candidate: Evidence, weights: CompositeWeights
) -> list[DeltaRow]:
    """candidate minus baseline, per cell. A cell present on only one side
    is still reported, with None deltas -- an appearing or vanishing cell is
    itself a result."""
    b = _cells(baseline, weights)
    c = _cells(candidate, weights)

    rows: list[DeltaRow] = []
    for key in sorted(set(b) | set(c)):
        case, stage, arm = key
        bs, _bn, bw = b.get(key, (None, 0, {}))
        cs, cn, cw = c.get(key, (None, 0, {}))
        n = min(x.n for x in (bs, cs) if x is not None)

        def d(attr: str, bs=bs, cs=cs) -> float | None:
            if bs is None or cs is None:
                return None
            bv, cv = getattr(bs, attr), getattr(cs, attr)
            return None if bv is None or cv is None else cv - bv

        waste = {m: cw[m] - bw[m] for m in WASTE_METRICS if m in bw and m in cw}
        rows.append(
            DeltaRow(
                case=case,
                stage=stage,
                arm=arm,
                quality=d("mean_quality"),
                cost_usd=d("mean_cost_usd"),
                wall_s=d("mean_wall_clock_s"),
                composite=d("composite"),
                waste=waste,
                n=n,
                note="within-noise" if n < NOISE_FLOOR else "",
            )
        )
    return rows


def render_deltas_markdown(rows: list[DeltaRow]) -> str:
    """ASCII only (report.py:70-74)."""
    if not rows:
        return "No overlapping cells between baseline and candidate.\n"

    def f(x: float | None) -> str:
        return "n/a" if x is None else f"{x:+.3f}"

    lines = [
        "| case | stage | arm | quality | cost | wall | composite | tool_calls | n | |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.case} | {r.stage} | {r.arm} | {f(r.quality)} | "
            f"{f(r.cost_usd)} | {f(r.wall_s)} | {f(r.composite)} | "
            f"{f(r.waste.get('tool_calls'))} | {r.n} | {r.note} |"
        )
    return "\n".join(lines) + "\n"


def save_experiment(exp: Experiment, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = exp.model_dump()
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return path


def load_experiment(path: Path) -> Experiment:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Experiment(**data)
