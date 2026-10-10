"""task x arm reviewer-vs-adversary split matrix (spec 4.4; 013 FR-033).

Rows are tasks, columns are harness#model arms, one grid per metric.
Pure aggregation + rendering, no I/O -- mirrors waste_matrix.py.

This is the reviewer-adversary SPLIT view, not the gate-versus-oracle
agreement view (`B/gate_oracle.py`, 013): it shows where the adversary
disagreed with the primary reviewer, task by task, and says nothing about
the oracle. The page is titled "Reviewer vs adversary split" so the two
cannot be mistaken for each other.

Agreement with the oracle is NOT rework density either, so none of it
belongs in the heatmap: a split is a cause, and the retry it triggers is
already counted as fix_attempts on the code/qa rows.

What this matrix deliberately cannot tell you is whether the adversary was
RIGHT. Split rate is descriptive. "Was the extra call worth it" is a
counterfactual, answerable only by running a case with
adversarial_review_enabled on and off and comparing held-out oracle
pass-fraction against cost.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from .models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    arm_label,
    is_pre012,
)
from .tasks import TaskSuite

ADVERSARY_STAGE = "adversary"
AGREEMENT_METRICS: list[str] = ["split_rate", "cost_per_split"]


class AgreementCell(BaseModel):
    task_id: str
    arm_key: str
    metric: str
    value: float
    n_records: int


class AgreementMatrix(BaseModel):
    case_id: str
    metrics: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    arms: list[str] = Field(default_factory=list)
    cells: list[AgreementCell] = Field(default_factory=list)
    max_by_metric: dict[str, float] = Field(default_factory=dict)
    # 012 (contract §7.6): pre-012 records among this case's input
    # (cell-scope records excluded); rendered as the untrusted line.
    pre012_records: int = 0


def build_agreement_matrix(
    case_id: str, records: list[BenchmarkRecord], suite: TaskSuite | None = None
) -> AgreementMatrix:
    case_recs = [r for r in records if r.case_id == case_id and r.scope is not BenchmarkScope.CELL]
    # 012 (contract §7.8): a not_evaluated outcome is neither pass nor fail
    # nor a split — it enters neither n_records nor the split denominator.
    recs = [
        r
        for r in case_recs
        if r.task_id
        and r.stage == ADVERSARY_STAGE
        and r.outcome is not BenchmarkOutcome.NOT_EVALUATED
    ]
    if not recs:
        return AgreementMatrix(
            case_id=case_id,
            metrics=list(AGREEMENT_METRICS),
            pre012_records=sum(1 for r in case_recs if is_pre012(r)),
        )

    totals: dict[tuple[str, str], int] = defaultdict(int)
    splits: dict[tuple[str, str], int] = defaultdict(int)
    spend: dict[tuple[str, str], float] = defaultdict(float)
    for r in recs:
        assert r.task_id is not None
        # 012 (contract §7.7): arm_label — the arm for a 012 record, the
        # bare model for a pre-012 record, so pre-012 keys are unchanged.
        arm = f"{r.harness.value if r.harness else ''}#{arm_label(r)}"
        key = (r.task_id, arm)
        totals[key] += 1
        if r.outcome is BenchmarkOutcome.FAIL:
            splits[key] += 1
        if r.cost.usd is not None:
            spend[key] += r.cost.usd

    cells: list[AgreementCell] = []
    for key, n in totals.items():
        task_id, arm = key
        cells.append(
            AgreementCell(
                task_id=task_id,
                arm_key=arm,
                metric="split_rate",
                value=splits[key] / n,
                n_records=n,
            )
        )
        # No split means no cost PER split -- a blank cell, never a 0.0.
        if splits[key]:
            cells.append(
                AgreementCell(
                    task_id=task_id,
                    arm_key=arm,
                    metric="cost_per_split",
                    value=spend[key] / splits[key],
                    n_records=n,
                )
            )

    observed = {c.task_id for c in cells}
    if suite is not None:
        ordered = [t.id for t in suite.tasks if t.id in observed]
        task_ids = ordered + sorted(observed - set(ordered))
    else:
        task_ids = sorted(observed)

    max_by_metric = {
        m: max((c.value for c in cells if c.metric == m), default=0.0) for m in AGREEMENT_METRICS
    }
    return AgreementMatrix(
        case_id=case_id,
        metrics=list(AGREEMENT_METRICS),
        task_ids=task_ids,
        arms=sorted({c.arm_key for c in cells}),
        cells=cells,
        max_by_metric=max_by_metric,
        pre012_records=sum(1 for r in case_recs if is_pre012(r)),
    )


def render_agreement_matrix_json(am: AgreementMatrix) -> str:
    return am.model_dump_json(indent=2)


def _cell_color(value: float, max_value: float) -> str:
    ratio = 0.0 if max_value <= 0 else min(value / max_value, 1.0)
    g_b = round(255 - 229 * ratio)  # white (low) -> dark red (high)
    return f"rgb(255,{g_b},{g_b})"


def _grid(am: AgreementMatrix, metric: str) -> str:
    by = {(c.task_id, c.arm_key): c for c in am.cells if c.metric == metric}
    mx = am.max_by_metric.get(metric, 0.0)
    head = "".join(f"<th>{escape(a)}</th>" for a in am.arms)
    rows = []
    for task_id in am.task_ids:
        tds = [f"<th>{escape(task_id)}</th>"]
        for arm in am.arms:
            c = by.get((task_id, arm))
            if c is None:
                tds.append('<td class="empty"></td>')
                continue
            tip = f"{task_id} / {arm}: {c.value:.2f} {metric} over {c.n_records} adversary records"
            tds.append(
                f'<td title="{escape(tip)}" '
                f'style="background:{_cell_color(c.value, mx)}">'
                f"{c.value:.2f}</td>"
            )
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        f"<h2>{escape(metric)}</h2>"
        f"<table><tr><th>task \\ arm</th>{head}</tr>" + "".join(rows) + "</table>"
    )


def render_agreement_matrix_html(am: AgreementMatrix) -> str:
    if not am.cells:
        body = (
            "<p>No adversary records. The lens runs only when "
            "adversarial_review_enabled is set AND the primary reviewer "
            "approved.</p>"
        )
    else:
        body = "".join(_grid(am, m) for m in am.metrics)
        body += (
            "<p><em>Descriptive only: split rate does not say the "
            "adversary was right. That needs an on/off arm comparison "
            "against the held-out oracle.</em></p>"
        )
    untrusted = (
        f"\n<p>includes {am.pre012_records} pre-012 records (untrusted)</p>"
        if am.pre012_records
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Reviewer vs adversary split - {escape(am.case_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
th,td{{border:1px solid #ddd;padding:.3rem .5rem;text-align:right}}
th{{background:#f5f5f5;text-align:left}}
td.empty{{background:repeating-linear-gradient(45deg,#fafafa,#fafafa 4px,#f0f0f0 4px,#f0f0f0 8px)}}
</style></head><body>
<h1>Reviewer vs adversary split - {escape(am.case_id)}</h1>
{body}{untrusted}
</body></html>"""
