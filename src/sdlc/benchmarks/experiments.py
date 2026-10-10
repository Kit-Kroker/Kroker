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
from .models import BenchmarkOutcome, CompositeWeights, arm_label, waste_measured
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
        # 012 (contract §7.7/§7.8): the arm component is arm_label — the
        # arm for a 012 record, the bare model for a pre-012 record, so
        # pre-012 keys are unchanged; a not_evaluated record enters no mean.
        # 013 (contract §10.2): an unmeasured waste bag (no session, or an
        # unmarked zero-tool opencode/crew capture) enters no mean either.
        # A record with no harness keys by its label alone (a proposer-side
        # cell's identity is the label; an empty-harness prefix would only
        # add noise to the column name).
        if r.outcome is BenchmarkOutcome.NOT_EVALUATED or not waste_measured(r):
            continue
        label = arm_label(r)
        key = (
            (r.case_id, r.stage, f"{r.harness.value}#{label}")
            if r.harness
            else (r.case_id, r.stage, label)
        )
        waste_n[key] += 1
        for m in WASTE_METRICS:
            waste_sum[key][m] += float(getattr(r.waste, m))

    out = {}
    for s in aggregate("", weights, _records=ev.records):
        # the summary join reads the same label: BenchmarkSummary.arm for a
        # 012 row, the bare model for a pre-012 row.
        label = s.arm or s.model
        key = (
            (s.case_id, s.stage, f"{s.harness.value}#{label}")
            if s.harness
            else (s.case_id, s.stage, label)
        )
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


def render_deltas_markdown(
    rows: list[DeltaRow], pre012_records: int = 0, *, show_composite: bool = False
) -> str:
    """ASCII only (report.py:70-74). The pre-012 count is the caller's to
    compute over its evidence records (contract §7.6): the line renders
    only when pre-012 records are included. `show_composite` carries the
    composite decision (013 contract §7.2): the column prints only when a
    compared case shows one, never inferred from empty columns."""
    if not rows:
        return "No overlapping cells between baseline and candidate.\n"

    def f(x: float | None) -> str:
        return "n/a" if x is None else f"{x:+.3f}"

    cols = ["case", "stage", "arm", "quality", "cost", "wall"]
    if show_composite:
        cols.append("composite")
    cols += ["tool_calls", "n", ""]
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    for r in rows:
        cells = [r.case, r.stage, r.arm, f(r.quality), f(r.cost_usd), f(r.wall_s)]
        if show_composite:
            cells.append(f(r.composite))
        cells += [f(r.waste.get("tool_calls")), str(r.n), r.note]
        lines.append("| " + " | ".join(cells) + " |")
    if pre012_records:
        lines += ["", f"includes {pre012_records} pre-012 records (untrusted)"]
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
