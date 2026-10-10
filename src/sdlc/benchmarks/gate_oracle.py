"""013 (data-model §4): each gate against the oracle (FR-029 to FR-032).

Pure aggregation + rendering, no I/O — mirrors grid.py / heatmap_render.py.
The input is `runs.build_runs` output; only graded runs enter (contract §6.1),
one row set per heatmap row `(case, harness, arm, generation)`, so pre-012 and
012 runs never share counts. A run's verdict of a gate follows research R-9
(`runs.gate_passed`): `analyze` and `merge` are run-level gates read off their
last record (merge `revise` is a pass); every other gate in `GATE_STAGES` is a
per-task gate that passes only when the last record of the stage passed for
every task that has one. The oracle verdict is `passed == total > 0` (§6.3).

Imports: `B/models.py`, `B/runs.py`, pydantic and the standard library only
(SG-7) — no temporalio, no report/cell/recorder. `sdlc benchmark score` runs
with no worker. Output files: `gate-oracle.html`, `gate-oracle.json`
(the markdown is the `## Gate versus oracle` section of `report.md`).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape

from pydantic import BaseModel

from .models import BenchmarkRecord, BenchmarkScope, is_pre012
from .runs import MIN_OBSERVATIONS, Run, attempt_sort_key, gate_passed

GATE_STAGES: tuple[str, ...] = (
    "qa",
    "review",
    "adversary",
    "deep_review",
    "handoff",
    "analyze",
    "merge",
)

# R-9: `analyze` and `merge` verdict a run as a whole (their last record);
# every other gate is decided per task.
_RUN_LEVEL_GATES = frozenset({"analyze", "merge"})

# The scopes a gate record counts: cell (status), oracle and oracle-task
# (grade) records are nobody's verdict (contract §3.4's rule, applied here).
_GATE_SCOPES = (BenchmarkScope.STAGE, BenchmarkScope.TASK_ATTEMPT)

_EPOCH = datetime.min


def _row_key(case_id: str, harness: str, arm: str, generation: str) -> str:
    """The heatmap row key (data-model §3 `HeatmapRow.key`), formed the same
    way `build_layers` forms it."""
    return f"{case_id} / {harness} / {arm} / {generation}"


class GateRow(BaseModel):
    """One heatmap row's counts of gate verdict against oracle verdict."""

    model_config = {"frozen": True}

    row: str
    gate: str
    pass_pass: int = 0
    pass_fail: int = 0
    reject_pass: int = 0
    reject_fail: int = 0
    n: int = 0
    agree_rate: float | None = None
    escape_rate: float | None = None
    false_reject_rate: float | None = None
    mean_credit_passed: float | None = None
    mean_credit_rejected: float | None = None
    low_n: dict[str, bool] = {}
    is_copy: bool = False


class GateOracle(BaseModel):
    """The gate-versus-oracle view over one selection's runs."""

    rows: tuple[GateRow, ...] = ()
    pre012_records: int = 0


def _run_gate_verdict(gate: str, run: Run) -> bool | None:
    """Contract §6.2 / R-9. None when the run has no verdict of the gate, or
    only `not_evaluated` ones — such a run enters no count."""
    recs = [r for r in run.records if r.stage == gate and r.scope in _GATE_SCOPES]
    if not recs:
        return None
    if gate in _RUN_LEVEL_GATES:
        last = max(recs, key=attempt_sort_key)
        return gate_passed(gate, last.outcome)
    by_task: dict[str | None, list[BenchmarkRecord]] = defaultdict(list)
    for r in recs:
        by_task[r.task_id].append(r)
    verdicts = [
        gate_passed(gate, max(group, key=attempt_sort_key).outcome) for group in by_task.values()
    ]
    if all(v is None for v in verdicts):
        return None
    return all(v is True for v in verdicts)


def _counted(runs: list[Run], gate: str) -> list[tuple[Run, bool]]:
    """The graded runs that carry a verdict of the gate, with it. The qa
    gate leaves `qa_is_copy` runs out (R-9); a row whose graded runs are all
    copies is the §6.6 copy row, decided by the caller."""
    out: list[tuple[Run, bool]] = []
    for run in runs:
        if run.status != "graded":
            continue
        if gate == "qa" and run.qa_is_copy:
            continue
        verdict = _run_gate_verdict(gate, run)
        if verdict is not None:
            out.append((run, verdict))
    return out


def _mean_credit(runs: list[Run]) -> float | None:
    credits = [r.partial_credit for r in runs if r.partial_credit is not None]
    return sum(credits) / len(credits) if credits else None


def _gate_row(row: str, gate: str, counted: list[tuple[Run, bool]]) -> GateRow:
    pass_pass = pass_fail = reject_pass = reject_fail = 0
    passed_side: list[Run] = []
    rejected_side: list[Run] = []
    for run, verdict in counted:
        oracle = run.all_pass
        if verdict:
            passed_side.append(run)
            if oracle:
                pass_pass += 1
            else:
                pass_fail += 1
        else:
            rejected_side.append(run)
            if oracle:
                reject_pass += 1
            else:
                reject_fail += 1
    n = pass_pass + pass_fail + reject_pass + reject_fail
    escape_den = pass_pass + pass_fail
    reject_den = reject_pass + reject_fail
    return GateRow(
        row=row,
        gate=gate,
        pass_pass=pass_pass,
        pass_fail=pass_fail,
        reject_pass=reject_pass,
        reject_fail=reject_fail,
        n=n,
        agree_rate=(pass_pass + reject_fail) / n if n else None,
        escape_rate=pass_fail / escape_den if escape_den else None,
        false_reject_rate=reject_pass / reject_den if reject_den else None,
        mean_credit_passed=_mean_credit(passed_side),
        mean_credit_rejected=_mean_credit(rejected_side),
        low_n={
            "agree_rate": n < MIN_OBSERVATIONS,
            "escape_rate": escape_den < MIN_OBSERVATIONS,
            "false_reject_rate": reject_den < MIN_OBSERVATIONS,
        },
    )


def build_gate_oracle(runs: list[Run]) -> GateOracle:
    """Contract §6: one `GateRow` per heatmap row `(case, harness, arm,
    generation)` and gate in `GATE_STAGES` that has a verdict in at least one
    graded run of the row; the qa gate of an all-copy row is the §6.6 copy
    row."""
    by_row: dict[tuple[str, str, str, str], list[Run]] = defaultdict(list)
    for run in runs:
        by_row[(run.case_id, run.harness, run.arm, run.generation)].append(run)
    keys = sorted(
        by_row,
        key=lambda k: (
            k[0],
            k[2],
            k[3],
            min(r.started_at or _EPOCH for r in by_row[k]),
        ),
    )

    rows: list[GateRow] = []
    for key in keys:
        case_id, harness, arm, generation = key
        members = by_row[key]
        graded = [r for r in members if r.status == "graded"]
        row = _row_key(case_id, harness, arm, generation)
        for gate in GATE_STAGES:
            counted = _counted(graded, gate)
            if gate == "qa" and not counted:
                if graded and all(r.qa_is_copy for r in graded):
                    rows.append(GateRow(row=row, gate=gate, is_copy=True))
                continue
            if counted:
                rows.append(_gate_row(row, gate, counted))

    pre012 = sum(
        1
        for run in runs
        for r in run.records
        if r.scope is not BenchmarkScope.CELL and is_pre012(r)
    )
    return GateOracle(rows=tuple(rows), pre012_records=pre012)


# --- rendering -----------------------------------------------------------------

_HEADER = (
    "row",
    "gate",
    "n",
    "pass/pass",
    "pass/fail",
    "reject/pass",
    "reject/fail",
    "agree",
    "escape",
    "false reject",
    "credit passed",
    "credit rejected",
)


def _rate_num_den(row: GateRow, rate: str) -> tuple[int, int]:
    """(numerator, denominator) of a rate from the counts — the markdown and
    HTML print `k/d`, the JSON keeps the float."""
    if rate == "agree_rate":
        return row.pass_pass + row.reject_fail, row.n
    if rate == "escape_rate":
        return row.pass_fail, row.pass_pass + row.pass_fail
    return row.reject_pass, row.reject_pass + row.reject_fail


def _fmt_credit(x: float | None) -> str:
    return f"{x:.3f}" if x is not None else "n/a"


def _rate_text(row: GateRow, rate: str) -> str:
    if getattr(row, rate) is None:
        return "n/a (0)"
    num, den = _rate_num_den(row, rate)
    text = f"{num}/{den}"
    return f"{text} (low n)" if row.low_n[rate] else text


def _row_cells(row: GateRow) -> list[str]:
    if row.is_copy:
        return [row.row, row.gate, "copy of code (pre-012)"] + [""] * (len(_HEADER) - 3)
    return [
        row.row,
        row.gate,
        str(row.n),
        str(row.pass_pass),
        str(row.pass_fail),
        str(row.reject_pass),
        str(row.reject_fail),
        _rate_text(row, "agree_rate"),
        _rate_text(row, "escape_rate"),
        _rate_text(row, "false_reject_rate"),
        _fmt_credit(row.mean_credit_passed),
        _fmt_credit(row.mean_credit_rejected),
    ]


def _row_line(row: GateRow) -> str:
    """A table line. The copy row's empty cells render as bare pipes (the
    line the tests pin), not the ` | ` join's double spaces."""
    if row.is_copy:
        return f"| {row.row} | {row.gate} | copy of code (pre-012) |" + " |" * (len(_HEADER) - 3)
    return "| " + " | ".join(_row_cells(row)) + " |"


def render_gate_oracle_markdown(go: GateOracle) -> str:
    """One pipe table, ASCII only, no separator row and no `---` anywhere
    (the grid's rule, contract §2.5, kept here too)."""
    if not go.rows:
        return ""
    lines = ["| " + " | ".join(_HEADER) + " |"]
    lines += [_row_line(r) for r in go.rows]
    if go.pre012_records:
        lines += ["", f"includes {go.pre012_records} pre-012 records (untrusted)"]
    return "\n".join(lines)


def render_gate_oracle_json(go: GateOracle) -> str:
    return go.model_dump_json(indent=2)


def _rate_html(row: GateRow, rate: str) -> str:
    text = _rate_text(row, rate)
    if row.low_n[rate] and getattr(row, rate) is not None:
        return f'<span class="low_n">{text}</span>'
    return text


def _html_row(row: GateRow) -> str:
    if row.is_copy:
        cells = (
            [f"<th>{escape(row.row)}</th>", "<th>qa</th>"]
            + ['<td class="copy">copy of code (pre-012)</td>']
            + ["<td></td>"] * (len(_HEADER) - 3)
        )
        return "<tr>" + "".join(cells) + "</tr>"
    cells = [
        f"<th>{escape(row.row)}</th>",
        f"<th>{escape(row.gate)}</th>",
        f"<td>{row.n}</td>",
        f"<td>{row.pass_pass}</td>",
        f"<td>{row.pass_fail}</td>",
        f"<td>{row.reject_pass}</td>",
        f"<td>{row.reject_fail}</td>",
        f"<td>{_rate_html(row, 'agree_rate')}</td>",
        f"<td>{_rate_html(row, 'escape_rate')}</td>",
        f"<td>{_rate_html(row, 'false_reject_rate')}</td>",
        f"<td>{escape(_fmt_credit(row.mean_credit_passed))}</td>",
        f"<td>{escape(_fmt_credit(row.mean_credit_rejected))}</td>",
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def render_gate_oracle_html(go: GateOracle) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in _HEADER)
    if go.rows:
        body = f"<table><tr>{head}</tr>" + "".join(_html_row(r) for r in go.rows) + "</table>"
    else:
        body = "<p>No graded runs with a gate verdict.</p>"
    untrusted = (
        f"\n<p>includes {go.pre012_records} pre-012 records (untrusted)</p>"
        if go.pre012_records
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Gate versus oracle</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
th,td{{border:1px solid #ddd;padding:.3rem .5rem;text-align:right}}
th{{background:#f5f5f5;text-align:left}}
span.low_n{{color:#888}}
td.copy{{color:#888}}
</style></head><body>
<h1>Gate versus oracle</h1>
<p>Every gate against the held-out oracle, over graded runs that carry a
verdict of the gate. Rates read k/d; a rate whose denominator is zero reads
n/a (0).</p>
{body}{untrusted}
</body></html>"""
