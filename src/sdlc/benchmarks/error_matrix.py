"""Error-class x arm failure-density matrix, scoped to one case.
Scans every bench_run_id's ORACLE_TASK records for that case
(report.py::scan_case_records feeds this) and renders which fixed error
class an arm (harness#model) fails most, averaged per run. Pure
aggregation + rendering -- no I/O, mirrors heatmap.py / task_matrix.py.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord, BenchmarkScope
from .tasks import ERROR_CLASSES, TaskSuite


class ErrorMatrixCell(BaseModel):
    error_class: str
    arm_key: str
    avg_failure_mass: float
    n_runs: int


class ErrorMatrix(BaseModel):
    case_id: str
    error_classes: list[str] = Field(default_factory=list)
    arms: list[str] = Field(default_factory=list)
    cells: list[ErrorMatrixCell] = Field(default_factory=list)
    max_value: float = 0.0


def build_error_matrix(case_id: str, records: list[BenchmarkRecord],
                       suite: TaskSuite) -> ErrorMatrix:
    class_by_task = {t.id: t.error_class for t in suite.tasks}
    recs = [r for r in records
           if r.scope is BenchmarkScope.ORACLE_TASK and r.case_id == case_id
           and r.task_id in class_by_task and r.quality.score is not None]

    # failure mass per (bench_run_id, arm_key, error_class) run-instance
    mass: dict[tuple[str, str, str], float] = defaultdict(float)
    runs_by_arm: dict[str, set[str]] = defaultdict(set)
    for r in recs:
        arm_key = f"{r.harness.value if r.harness else ''}#{r.model}"
        cls = class_by_task[r.task_id]
        mass[(r.bench_run_id, arm_key, cls)] += (1.0 - r.quality.score)
        runs_by_arm[arm_key].add(r.bench_run_id)

    totals: dict[tuple[str, str], float] = defaultdict(float)
    for (bench_run_id, arm_key, cls), m in mass.items():
        totals[(arm_key, cls)] += m

    cells: list[ErrorMatrixCell] = []
    for (arm_key, cls), total in totals.items():
        n_runs = max(len(runs_by_arm[arm_key]), 1)
        cells.append(ErrorMatrixCell(
            error_class=cls, arm_key=arm_key,
            avg_failure_mass=total / n_runs, n_runs=n_runs))

    arms = sorted({c.arm_key for c in cells})
    present = {c.error_class for c in cells}
    classes = [c for c in ERROR_CLASSES if c in present]
    max_value = max((c.avg_failure_mass for c in cells), default=0.0)
    return ErrorMatrix(case_id=case_id, error_classes=classes, arms=arms,
                       cells=cells, max_value=max_value)


def render_error_matrix_json(em: ErrorMatrix) -> str:
    return em.model_dump_json(indent=2)


def _cell_color(value: float, max_value: float) -> str:
    ratio = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    g_b = round(255 - 229 * ratio)   # white (low) -> dark red (high)
    return f"rgb(255,{g_b},{g_b})"


def render_error_matrix_html(em: ErrorMatrix) -> str:
    if not em.cells:
        body = "<p>No task records.</p>"
    else:
        by = {(c.error_class, c.arm_key): c for c in em.cells}
        head = "".join(f"<th>{escape(a)}</th>" for a in em.arms)
        rows = []
        for cls in em.error_classes:
            tds = [f"<th>{escape(cls)}</th>"]
            for arm in em.arms:
                c = by.get((cls, arm))
                if c is None:
                    tds.append('<td class="empty"></td>')
                    continue
                tip = (f"{cls} / {arm}: {c.avg_failure_mass:.2f} avg failure "
                      f"mass/run over {c.n_runs} runs")
                tds.append(
                    f'<td title="{escape(tip)}" '
                    f'style="background:{_cell_color(c.avg_failure_mass, em.max_value)}">'
                    f"{c.avg_failure_mass:.2f}</td>")
            rows.append("<tr>" + "".join(tds) + "</tr>")
        body = (f"<table><tr><th>error class \\ arm</th>{head}</tr>"
               + "".join(rows) + "</table>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Error-class matrix - {escape(em.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Error-class matrix - {escape(em.case_id)}</h1>
<p>Cell = average per-task failure mass (sum of 1-score) per run, for that
error class on that harness#model arm. Whiter is cleaner; redder is more
failure-prone.</p>
{body}
</body></html>"""
