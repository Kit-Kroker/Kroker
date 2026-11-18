"""SC-rollup renderers (markdown, HTML, JSON).

Moved verbatim from sc_rollup.py in 026 T006: that module crossed its
470-line plan budget once the no-summary accounting landed, and the plan's
stated contingency is exactly this move (render-only code, its own seam).
sc_rollup re-exports the three render functions lazily (PEP 562) so
every existing import site — `from .sc_rollup import render_sc_rollup_*`
— keeps working; a module-level re-export would cycle, since the
renderers need sc_rollup's own MIN_RUNS.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from .sc_rollup import MIN_RUNS

if TYPE_CHECKING:  # annotations only: no runtime import cycle
    from .sc_rollup import SCRollup


def render_sc_rollup_json(r: SCRollup) -> str:
    return r.model_dump_json(indent=2)


def _fmt(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.2f}"


def _mins(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}"


def _sc2_companions_line(r: SCRollup) -> str:
    e = r.sc2_extra
    return (
        f"SC-2 companions: human-touched median {_mins(e.human_touched_median_min)} "
        f"and max {_mins(e.human_touched_max_min)} min; "
        f"uncapped wait median {_mins(e.wait_median_min)} min; "
        f"{e.zero_runs} zero-interaction runs (measured); "
        f"gate policy mix: {r.policy_mix or 'none'}."
    )


def render_sc_rollup_markdown(r: SCRollup) -> str:
    """ASCII only (report.py:70-74)."""
    lines = [
        "",
        "## Success criteria",
        "",
        f"{r.summary_runs} of {r.selection_runs} runs left a run summary",
    ]
    if r.roots_line:
        lines.append(r.roots_line)
    lines += [
        "",
        f"Rates below n={MIN_RUNS} render n/a rather than a percentage.",
        "",
        "| criterion | measure | rate | n | target | |",
        "|---|---|---|---|---|---|",
    ]
    for x in r.rates:
        flag = "PROXY" if x.proxy else ""
        lines.append(
            f"| {x.criterion} | {x.label} | {_fmt(x.rate)} | n={x.n} | {x.target} | {flag} |"
        )
    if r.sc4_series:
        lines += ["", "SC-4 series (human-answered fraction, by run order):", ""]
        lines += [f"- {p.index}: {p.run_id} {p.human_rate:.2f}" for p in r.sc4_series]
    lines += ["", "Definitions:", ""]
    lines += [f"- **{x.criterion}**: {x.note}" for x in r.rates if x.note]
    # 025 (FR-013/015): the SC-2 companions and the evidence tier ride the
    # same section in every renderer.
    lines += ["", _sc2_companions_line(r)]
    if r.evidence_tier:
        lines += [f"Evidence tier: {r.evidence_tier}."]
    # FR-024: provenance renders only when broken — a clean fleet shows no
    # commit noise, a broken one shows the set and the flag.
    if r.commit_flag:
        lines += [
            "",
            f"Commit set: {'+'.join(sorted(r.commits))}. FLAG: {r.commit_flag}.",
        ]
    if r.pre012_records:
        lines += ["", f"includes {r.pre012_records} pre-012 records (untrusted)"]
    return "\n".join(lines) + "\n"


def render_sc_rollup_html(r: SCRollup) -> str:
    rows = "".join(
        f"<tr><th>{escape(x.criterion)}</th><td>{escape(x.label)}</td>"
        f"<td>{_fmt(x.rate)}</td><td>{x.n}</td>"
        f"<td>{escape(x.target)}</td>"
        f"<td>{'PROXY' if x.proxy else ''}</td></tr>"
        for x in r.rates
    )
    notes = "".join(
        f"<li><b>{escape(x.criterion)}</b>: {escape(x.note)}</li>" for x in r.rates if x.note
    )
    untrusted = (
        f"<p>includes {r.pre012_records} pre-012 records (untrusted)</p>"
        if r.pre012_records
        else ""
    )
    tier = f"<p>Evidence tier: {escape(r.evidence_tier)}</p>" if r.evidence_tier else ""
    commit_html = (
        f"<p>Commit set: {escape('+'.join(sorted(r.commits)))}. FLAG: {escape(r.commit_flag)}.</p>"
        if r.commit_flag
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Success criteria</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} li{{margin:.3rem 0}}
</style></head><body>
<h1>Success criteria</h1>
<p>{r.summary_runs} of {r.selection_runs} runs left a run summary</p>
{f"<p>{escape(r.roots_line)}</p>" if r.roots_line else ""}
<p>Rates below n={MIN_RUNS} render n/a rather than a percentage: a single
run displaying 100% would be quoted as a result.</p>
<table><tr><th>criterion</th><th>measure</th><th>rate</th><th>n</th>
<th>target</th><th></th></tr>{rows}</table>
<p>{escape(_sc2_companions_line(r))}</p>
{tier}{commit_html}<h2>Definitions</h2><ul>{notes}</ul>{untrusted}
</body></html>"""
