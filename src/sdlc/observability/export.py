"""Pure renderers for the retro export (E-32). No I/O: the activity in
activities.py owns the file writes; these turn state into strings.

report.html is deliberately a deterministic, dependency-free template — the
retro stage is `(deterministic + reflect)`, no LLM (SDLC-spec §58)."""
from __future__ import annotations

from html import escape

from ..models import RunSummary
from .trace import RunEvent


def render_events_jsonl(trace: list[RunEvent]) -> str:
    lines = [e.model_dump_json()
             for e in sorted(trace, key=lambda e: e.seq)]
    return "\n".join(lines) + ("\n" if lines else "")


def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>"


def render_report_html(s: RunSummary) -> str:
    stage_rows = "".join(
        _row([st.stage, st.role, st.outcome, f"{st.duration_s:.1f}s",
              "-" if st.cost_usd is None else f"${st.cost_usd:.4f}",
              str(st.fix_attempts)])
        for st in s.stages)
    gate_rows = "".join(
        _row([g.gate, str(g.round), g.policy, g.decided_by,
              "yes" if g.approved else "no",
              "-" if g.confidence is None else f"{g.confidence:.2f}",
              ", ".join(g.overrides) or "-"])
        for g in s.gates)
    clar_rows = "".join(
        _row([c.question_id, c.question, c.answered_by])
        for c in s.clarifications)
    cost = "-" if s.cost_usd_total is None else f"${s.cost_usd_total:.4f}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Run {escape(s.run_id)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} table{{border-collapse:collapse;margin:.5rem 0 1.5rem}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:left}}
th{{background:#f3f3f3}} .meta{{color:#555}}
</style></head><body>
<h1>Run {escape(s.run_id)}</h1>
<p class="meta">mode={escape(s.mode)} &middot; outcome=<b>{escape(s.outcome)}</b>
&middot; terminal_stage={escape(s.terminal_stage)}
&middot; duration={s.duration_s:.1f}s &middot; cost={cost}</p>
<h2>Stages</h2>
<table><tr><th>stage</th><th>role</th><th>outcome</th><th>duration</th>
<th>cost</th><th>fix_attempts</th></tr>{stage_rows}</table>
<h2>Gates</h2>
<table><tr><th>gate</th><th>round</th><th>policy</th><th>decided_by</th>
<th>approved</th><th>confidence</th><th>overrides</th></tr>{gate_rows}</table>
<h2>Clarifications</h2>
<table><tr><th>id</th><th>question</th><th>answered_by</th></tr>{clar_rows}</table>
<p class="meta">memory_enabled={s.memory_enabled}
&middot; watermark={escape(str(s.memory_watermark))}
&middot; retains={s.memory_retains}</p>
</body></html>"""
