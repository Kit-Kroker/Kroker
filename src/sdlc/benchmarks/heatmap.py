"""case x stage rework-density heatmap (E-36).

Pure aggregation + rendering over BenchmarkRecords already on disk. No I/O,
no temporalio -- mirrors observability/export.py. The finalize activity
(report.py) owns the file writes.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkOutcome, BenchmarkRecord, BenchmarkScope

# 'review', 'adversary', 'handoff' and 'deep_review' are LENSES, not DAG
# stages. They are listed so they render in a sensible column order rather
# than the trailing unknown bucket. Their records carry fix_attempts=0 --
# retry volume belongs to code/qa, and counting it here too would treat one
# disagreement as three units of rework. If more lenses accumulate, this axis
# stops being the SDLC DAG (spec OQ-A3).
# Record-vocabulary stage order (SDLC-spec 15-stage DAG); the synthetic
# ``oracle`` column trails. Only columns with an observed cell are rendered.
CANONICAL_STAGES: list[str] = [
    "intake", "constitution", "context", "requirements", "research",
    "clarify", "architecture", "planning", "code", "review", "adversary",
    "handoff", "deep_review", "analyze", "qa", "quality_gate", "deploy",
    "retro",
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
        if r.scope is BenchmarkScope.ORACLE_TASK:
            # task-level detail belongs in the task/error matrices (E-36
            # follow-on), not this case x stage rework-density heatmap.
            # ORACLE_TASK records share stage="oracle" with the case-level
            # ORACLE record but there is no gate on the oracle stage, so
            # counting them here would double the reported rework density.
            continue
        is_oracle = r.scope is BenchmarkScope.ORACLE
        stage = ORACLE_STAGE if is_oracle else r.stage
        key = (r.case_id, stage)
        if is_oracle:
            if r.outcome is BenchmarkOutcome.FAIL:
                acc[key]["oracle"] += 1
        elif r.outcome in REWORK_OUTCOMES:
            acc[key]["gate"] += 1
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


def render_heatmap_json(hm: Heatmap) -> str:
    return hm.model_dump_json(indent=2)


def _cell_color(density: float, max_density: float) -> str:
    ratio = 0.0 if max_density <= 0 else min(density / max_density, 1.0)
    hue = 120 * (1 - ratio)          # 120=green (low) -> 0=red (high)
    return f"hsl({hue:.0f},70%,{85 - 25 * ratio:.0f}%)"


def _grid(hm: Heatmap, cases: list[str]) -> str:
    by = {(c.case, c.stage): c for c in hm.cells}
    head = "".join(f"<th>{escape(s)}</th>" for s in hm.stages)
    rows = []
    for case in cases:
        tds = [f"<th>{escape(case)}</th>"]
        for stage in hm.stages:
            c = by.get((case, stage))
            if c is None:
                tds.append('<td class="empty"></td>')
                continue
            tip = (f"{case}/{stage}: {c.gate_rejects} rejects, "
                   f"{c.fix_attempts} fix-attempts, {c.oracle_fails} "
                   f"oracle-fails over {c.n_runs} runs = {c.density:.2f}/run")
            tds.append(
                f'<td title="{escape(tip)}" '
                f'style="background:{_cell_color(c.density, hm.max_density)}">'
                f"{c.density:.2f}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f"<table><tr><th>case \\ stage</th>{head}</tr>"
            + "".join(rows) + "</table>")


def render_heatmap_html(hm: Heatmap, calibration_html: str = "") -> str:
    if not hm.cells:
        body = "<p>No records.</p>"
    else:
        sections = [f"<h2>All cases</h2>{_grid(hm, hm.cases)}"]
        langs = sorted({v for v in hm.language_by_case.values() if v})
        for lang in langs:
            cases = [c for c in hm.cases if hm.language_by_case.get(c) == lang]
            sections.append(f"<h2>{escape(lang)}</h2>{_grid(hm, cases)}")
        body = "".join(sections)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Benchmark heatmap</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Rework-density heatmap</h1>
<p>Cell = (gate rejections + fix-loop attempts + oracle failures) per run.
Greener is cleaner; redder is more rework.</p>
{body}
{calibration_html}
</body></html>"""
