"""Scales and HTML rendering for the layered heatmap (013, contract 4).

Pure rendering over `B/heatmap.py`'s layered model: fixed colour steps
(4.1), cell states (4.2), one hue at five lightness levels plus a grey
class (4.4). The same value gives the same class in any report (SC-007).
No I/O, no temporalio; the file writes stay in `B/report.py`.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from .heatmap import (
    LAYERS,
    ORACLE_COLUMN,
    HeatmapRow,
    LayerCell,
    LayeredHeatmap,
    OracleMark,
)

# Contract 4.1: the four step edges per layer and the direction. For the
# three counting layers 0 is best and the fourth bound is the last edge
# before step 4; for `oracle` 1.0 is best and the bounds descend.
SCALES: dict[str, tuple[tuple[float, float, float, float], bool]] = {
    "attrition": ((0.0, 0.05, 0.10, 0.25), True),
    "first_attempt": ((0.0, 0.10, 0.25, 0.50), True),
    "wasted_tokens": ((0.0, 0.10, 0.25, 0.50), True),
    "oracle": ((1.0, 0.90, 0.75, 0.50), False),
}

_TD_EMPTY = '<td class="hm-empty"></td>'

# Contract 3.7, printed under the heatmap (one sentence, contiguous).
_NOTE = (
    "A stage record is written when the stage ends. A run that stopped "
    "inside a stage shows the stage before it as its last."
)


def step_for(layer: str, value: float) -> int:
    """The colour step (0 to 4) of a layer value per contract 4.1."""
    bounds, higher_is_worse = SCALES[layer]
    if higher_is_worse:
        for step, edge in enumerate(bounds):
            if value <= edge:
                return step
        return 4
    for step, edge in enumerate(bounds):
        if value >= edge:
            return step
    return 4


def _figure(x: float) -> str:
    """`2.0` prints as `2`, `0.25` as `0.25`."""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _cell_td(cell: LayerCell | None) -> str:
    if cell is None or cell.state == "blank":
        return _TD_EMPTY
    if cell.state == "copy":
        return "<td>copy of code</td>"
    value = cell.value if cell.value is not None else 0.0
    text = f"{value:.2f} ({_figure(cell.num)}/{_figure(cell.den)})"
    if cell.state == "low_n":
        return f'<td class="hm-low">{text}</td>'
    return f'<td class="hm-s{step_for(cell.layer, value)}">{text}</td>'


def _marks_td(marks: list[OracleMark]) -> str:
    if not marks:
        return _TD_EMPTY
    spans = ", ".join(
        f'<span class="hm-s{step_for("oracle", m.passed / m.total)}">{m.passed}/{m.total}</span>'
        for m in marks
    )
    return f"<td>{spans}</td>"


def _row_header(row: HeatmapRow) -> str:
    label = escape(row.key)
    if row.language:
        label = f"{label} [{escape(row.language)}]"
    lost_tokens = "not measured" if row.lost_tokens is None else str(row.lost_tokens)
    figures = (
        f"{row.started} started, {row.lost_before_code} lost before code, "
        f"lost tokens {lost_tokens}, {row.no_stage_recorded} no stage record"
    )
    return f"{label}<br><small>{figures}</small>"


def _table(hm: LayeredHeatmap, layer: str) -> str:
    cells = {(c.row, c.stage): c for c in hm.cells if c.layer == layer}
    marks: dict[str, list[OracleMark]] = defaultdict(list)
    for mark in hm.oracle_marks:
        marks[mark.row].append(mark)
    head = "".join(f"<th>{escape(stage)}</th>" for stage in hm.stages)
    body = []
    for row in hm.rows:
        tds = [f'<th scope="row">{_row_header(row)}</th>']
        for stage in hm.stages:
            if layer == ORACLE_COLUMN:
                tds.append(
                    _marks_td(marks.get(row.key, [])) if stage == ORACLE_COLUMN else _TD_EMPTY
                )
            else:
                tds.append(_cell_td(cells.get((row.key, stage))))
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><tr><th>row \\ stage</th>{head}</tr>{''.join(body)}</table>"


def render_heatmap_html(hm: LayeredHeatmap, calibration_html: str = "") -> str:
    """The four layers as tables on identical columns, the 3.7 note, the
    pre-012 untrusted line, and the calibration block appended (4.3)."""
    if hm.rows:
        body = "".join(f"<h2>{escape(layer)}</h2>\n{_table(hm, layer)}" for layer in LAYERS)
    else:
        body = "<p>No records.</p>"
    untrusted = (
        f"\n<p>includes {hm.pre012_records} pre-012 records (untrusted)</p>"
        if hm.pre012_records
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Benchmark heatmap</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} small{{font-weight:400;color:#555}}
.hm-s0{{background:hsl(35,75%,88%)}}
.hm-s1{{background:hsl(35,75%,76%)}}
.hm-s2{{background:hsl(35,75%,64%)}}
.hm-s3{{background:hsl(35,75%,52%)}}
.hm-s4{{background:hsl(35,75%,40%)}}
.hm-low{{background:hsl(0,0%,87%);color:#555}}
</style></head><body>
<h1>Benchmark heatmap</h1>
{body}
<p>{_NOTE}</p>
{untrusted}
{calibration_html}
</body></html>"""
