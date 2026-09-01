"""Task-history matrix (task x run-over-time). Scans every bench_run_id's
ORACLE_TASK records for one case (report.py::scan_case_records feeds this)
and renders a persistent, cross-run pass/fail grid. Pure aggregation +
rendering -- no I/O, mirrors heatmap.py.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord, BenchmarkScope
from .tasks import TaskSuite


class TaskMatrixColumn(BaseModel):
    bench_run_id: str
    cell_id: str
    harness: str
    model: str
    started_at: datetime
    mean_score: float | None


class TaskMatrix(BaseModel):
    case_id: str
    task_ids: list[str] = Field(default_factory=list)
    columns: list[TaskMatrixColumn] = Field(default_factory=list)
    scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)


def _column_key(col: TaskMatrixColumn) -> str:
    return f"{col.bench_run_id}#{col.cell_id}"


def build_task_matrix(case_id: str, records: list[BenchmarkRecord], suite: TaskSuite) -> TaskMatrix:
    task_ids = [t.id for t in suite.tasks]
    recs = [r for r in records if r.scope is BenchmarkScope.ORACLE_TASK and r.case_id == case_id]

    by_col: dict[tuple[str, str], list[BenchmarkRecord]] = defaultdict(list)
    for r in recs:
        h = r.harness.value if r.harness else ""
        if r.lead_harness:
            h = f"{h}:{r.lead_harness.value}"
        cell_id = f"{case_id}#{h}#{r.model}"
        by_col[(r.bench_run_id, cell_id)].append(r)

    columns: list[TaskMatrixColumn] = []
    scores: dict[str, dict[str, float | None]] = {tid: {} for tid in task_ids}
    for (bench_run_id, cell_id), col_recs in by_col.items():
        started = min(r.speed.started_at for r in col_recs)
        by_task = {r.task_id: r.quality.score for r in col_recs if r.task_id}
        present = [s for s in by_task.values() if s is not None]
        mean_score = sum(present) / len(present) if present else None
        harness = next((r.harness.value for r in col_recs if r.harness), "")
        model = col_recs[0].model
        col = TaskMatrixColumn(
            bench_run_id=bench_run_id,
            cell_id=cell_id,
            harness=harness,
            model=model,
            started_at=started,
            mean_score=mean_score,
        )
        columns.append(col)
        key = _column_key(col)
        for tid in task_ids:
            scores[tid][key] = by_task.get(tid)

    columns.sort(key=lambda c: c.started_at)
    return TaskMatrix(case_id=case_id, task_ids=task_ids, columns=columns, scores=scores)


def render_task_matrix_json(tm: TaskMatrix) -> str:
    return tm.model_dump_json(indent=2)


def _cell_style(score: float | None) -> tuple[str, str]:
    """(inline CSS, cell label) for one task-matrix cell."""
    if score is None:
        return "background:#e5e5e5", ""
    if score >= 1.0:
        return "background:#3aa757;color:#fff", "1"
    if score <= 0.0:
        return "background:#c0392b;color:#fff", "0"
    return "background:#e0a13a;color:#111", f"{score:.2f}"


def render_task_matrix_html(tm: TaskMatrix) -> str:
    if not tm.columns:
        body = "<p>No task records.</p>"
    else:
        head_cells = []
        sum_cells = []
        for col in tm.columns:
            key = _column_key(col)
            ts = col.started_at.strftime("%m-%d %H:%M")
            score_label = f"{col.mean_score:.2f}" if col.mean_score is not None else "n/a"
            head_cells.append(
                f"<th>{escape(ts)}<br>score {score_label}<br>{escape(col.model)}</th>"
            )
            total = sum(
                v for v in (tm.scores[tid].get(key) for tid in tm.task_ids) if v is not None
            )
            sum_cells.append(f"<th>{total:.2f}</th>")
        rows = []
        for tid in tm.task_ids:
            tds = [f"<th>{escape(tid)}</th>"]
            for col in tm.columns:
                key = _column_key(col)
                score = tm.scores[tid].get(key)
                style, label = _cell_style(score)
                tds.append(f'<td style="{style}">{label}</td>')
            rows.append("<tr>" + "".join(tds) + "</tr>")
        body = (
            "<table><tr><th>task</th>" + "".join(head_cells) + "</tr>"
            "<tr><th>sum</th>" + "".join(sum_cells) + "</tr>" + "".join(rows) + "</table>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Task history - {escape(tm.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}}
</style></head><body>
<h1>Task history - {escape(tm.case_id)}</h1>
{body}
</body></html>"""
