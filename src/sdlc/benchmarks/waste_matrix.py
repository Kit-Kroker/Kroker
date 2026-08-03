"""task x arm harness-waste matrix (BENCHMARK.md §4.3).

One stacked grid per waste metric: rows are tasks, columns are
harness#model arms, cell = mean-over-runs of the per-run summed metric.
Pure aggregation + rendering, no I/O -- mirrors error_matrix.py.

Rows come from task_ids observed on records that actually carry a
WasteBag, so a case with no tasks.yaml still gets a grid. A record with
waste=None contributes NOTHING: it was not measured, and a zero cell
would claim it was.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import BenchmarkRecord
from .tasks import TaskSuite

# The six metrics that measure work which did not advance the goal.
# file_reads / files_written / model_turns measure VOLUME (a task that
# legitimately touches more files is not thrashing) and `compacted` is a
# boolean; all four ride on the record and land in the JSON, but none gets
# a grid.
WASTE_METRICS: list[str] = [
    "tool_calls", "file_rereads", "rewrite_churn",
    "failed_commands", "denials", "escalations",
]


class WasteCell(BaseModel):
    task_id: str
    arm_key: str
    metric: str
    value: float          # mean over runs of the per-run summed metric
    n_runs: int


class WasteMatrix(BaseModel):
    case_id: str
    metrics: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    arms: list[str] = Field(default_factory=list)
    cells: list[WasteCell] = Field(default_factory=list)
    max_by_metric: dict[str, float] = Field(default_factory=dict)


def build_waste_matrix(case_id: str, records: list[BenchmarkRecord],
                       suite: TaskSuite | None = None) -> WasteMatrix:
    recs = [r for r in records
            if r.case_id == case_id and r.task_id and r.waste is not None]
    if not recs:
        return WasteMatrix(case_id=case_id, metrics=list(WASTE_METRICS))

    # sum within a run-instance, then mean across run-instances
    per_run: dict[tuple[str, str, str, str], float] = defaultdict(float)
    runs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in recs:
        arm = f"{r.harness.value if r.harness else ''}#{r.model}"
        for metric in WASTE_METRICS:
            per_run[(r.bench_run_id, r.task_id, arm, metric)] += float(
                getattr(r.waste, metric))
        runs[(r.task_id, arm, "")].add(r.bench_run_id)

    totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for (_bench, task_id, arm, metric), v in per_run.items():
        totals[(task_id, arm, metric)] += v

    cells: list[WasteCell] = []
    for (task_id, arm, metric), total in totals.items():
        n = len(runs[(task_id, arm, "")]) or 1
        cells.append(WasteCell(task_id=task_id, arm_key=arm, metric=metric,
                               value=total / n, n_runs=n))

    observed = {c.task_id for c in cells}
    if suite is not None:
        ordered = [t.id for t in suite.tasks if t.id in observed]
        task_ids = ordered + sorted(observed - set(ordered))
    else:
        task_ids = sorted(observed)

    max_by_metric = {
        m: max((c.value for c in cells if c.metric == m), default=0.0)
        for m in WASTE_METRICS}
    return WasteMatrix(
        case_id=case_id, metrics=list(WASTE_METRICS), task_ids=task_ids,
        arms=sorted({c.arm_key for c in cells}), cells=cells,
        max_by_metric=max_by_metric)


def render_waste_matrix_json(wm: WasteMatrix) -> str:
    return wm.model_dump_json(indent=2)


def _cell_color(value: float, max_value: float) -> str:
    ratio = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    g_b = round(255 - 229 * ratio)   # white (low) -> dark red (high)
    return f"rgb(255,{g_b},{g_b})"


def _grid(wm: WasteMatrix, metric: str) -> str:
    by = {(c.task_id, c.arm_key): c for c in wm.cells if c.metric == metric}
    mx = wm.max_by_metric.get(metric, 0.0)
    head = "".join(f"<th>{escape(a)}</th>" for a in wm.arms)
    rows = []
    for task_id in wm.task_ids:
        tds = [f"<th>{escape(task_id)}</th>"]
        for arm in wm.arms:
            c = by.get((task_id, arm))
            if c is None:
                # not measured on this arm -- blank, never 0
                tds.append('<td class="empty"></td>')
                continue
            tip = (f"{task_id} / {arm}: {c.value:.1f} {metric} per run "
                   f"over {c.n_runs} runs")
            tds.append(
                f'<td title="{escape(tip)}" '
                f'style="background:{_cell_color(c.value, mx)}">'
                f"{c.value:.1f}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f"<h2>{escape(metric)}</h2>"
            f"<table><tr><th>task \\ arm</th>{head}</tr>"
            + "".join(rows) + "</table>")


def render_waste_matrix_html(wm: WasteMatrix) -> str:
    if not wm.cells:
        body = "<p>No waste records. Sessions are captured only for coding "
        body += "tasks, so a case with no graded coding attempts has none.</p>"
    else:
        body = "".join(_grid(wm, m) for m in wm.metrics)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Harness waste - {escape(wm.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Harness waste - {escape(wm.case_id)}</h1>
<p>Cell = mean per run of that metric, summed across attempts within a run.
Whiter is cleaner; redder is more waste. A blank cell was never measured --
it is not a zero. Proposer stages (clarify, architect, planner, qa, reviewer,
analyst) have no harness transcript at all and never appear here.</p>
{body}
</body></html>"""
