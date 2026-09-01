"""Cross-run success-criteria rates (ROADMAP SC-1/3/4/6).

ROADMAP says of each of these: "the cross-run aggregation remains the
benchmark's job." It names the criteria but not the formulas, so the
definitions here are CHOICES, documented per rate.

Pure aggregation + rendering, no I/O -- mirrors heatmap.py.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from pydantic import BaseModel, Field

from ..models import RunSummary
from .models import BenchmarkOutcome, BenchmarkRecord

# Below this many runs a percentage is noise dressed as a result. A single
# green run rendering "100%" WILL be quoted; n/a cannot be.
MIN_RUNS = 5

# The merge gate's registered name (workflows/feature.py:1754).
MERGE_GATE = "merge"

# Run outcomes that reached the merge gate. The criterion is REACHING it,
# not passing it, so a merge-time rejection counts (feature.py:1757, 1791,
# 1828, 1836).
REACHED_PREFIXES: tuple[str, ...] = ("deployed:", "merged-not-deployed:", "rejected:merge")


class SCRate(BaseModel):
    criterion: str
    label: str
    rate: float | None  # None when n < MIN_RUNS -- renders n/a
    n: int
    target: str
    proxy: bool = False
    note: str = ""


class SC4Point(BaseModel):
    index: int
    run_id: str
    human_rate: float


class SCRollup(BaseModel):
    rates: list[SCRate] = Field(default_factory=list)
    sc4_series: list[SC4Point] = Field(default_factory=list)


def _rate(n_hits: int, n: int) -> float | None:
    if n < MIN_RUNS or n == 0:
        return None
    return n_hits / n


def build_sc_rollup(summaries: list[RunSummary], records: list[BenchmarkRecord]) -> SCRollup:
    ordered = sorted(summaries, key=lambda s: (s.started_at, s.run_id))
    return SCRollup(
        rates=[_sc1(ordered), _sc3(records), _sc4(ordered), *_sc6(ordered)],
        sc4_series=_sc4_series(ordered),
    )


def _reached_merge(s: RunSummary) -> bool:
    return s.outcome.startswith(REACHED_PREFIXES)


def _unattended_to_merge(s: RunSummary) -> bool:
    """No human-decided gate BEFORE the merge gate. A human answering the
    merge gate itself does not disqualify the run -- by then it had already
    reached the gate."""
    for g in s.gates:
        if g.gate == MERGE_GATE:
            return True
        if g.decided_by == "human":
            return False
    return True


def _sc1(summaries: list[RunSummary]) -> SCRate:
    hits = sum(1 for s in summaries if _reached_merge(s) and _unattended_to_merge(s))
    return SCRate(
        criterion="SC-1",
        label="runs reaching the merge gate unattended",
        rate=_rate(hits, len(summaries)),
        n=len(summaries),
        target=">=0.80",
        note="reached = outcome in deployed/merged-not-deployed/rejected:merge; "
        "unattended = no human-decided gate before the merge gate",
    )


def _sc3(records: list[BenchmarkRecord]) -> SCRate:
    """A fix loop existed for a (run, task) where any attempt has
    fix_attempts > 0; it succeeded if the LAST attempt passed."""
    attempts: dict[tuple[str, str], list[BenchmarkRecord]] = defaultdict(list)
    for r in records:
        if r.stage == "code" and r.task_id:
            attempts[(r.run_id, r.task_id)].append(r)

    loops = successes = 0
    for recs in attempts.values():
        recs = sorted(recs, key=lambda r: (r.attempt or 0, r.speed.started_at))
        if not any(r.fix_attempts > 0 for r in recs):
            continue
        loops += 1
        if recs[-1].outcome is BenchmarkOutcome.PASS:
            successes += 1
    # The denominator is LOOPS, not runs -- but the floor is one rule for
    # every rate: below MIN_RUNS observations, n/a rather than a percentage.
    return SCRate(
        criterion="SC-3",
        label="fix loops that resolved",
        rate=_rate(successes, loops),
        n=loops,
        target=">=0.70",
        note="a loop = a (run, task) with any attempt at fix_attempts>0; "
        "success = the final attempt passed; denominator is loops, "
        f"and the n/a floor of {MIN_RUNS} applies to loops",
    )


def _sc4(summaries: list[RunSummary]) -> SCRate:
    total = sum(len(s.clarifications) for s in summaries)
    human = sum(1 for s in summaries for c in s.clarifications if c.answered_by == "human")
    n_runs = sum(1 for s in summaries if s.clarifications)
    return SCRate(
        criterion="SC-4",
        label="clarifications a human had to answer",
        rate=(human / total) if (total and n_runs >= MIN_RUNS) else None,
        n=n_runs,
        target="<0.10 by run 10",
        proxy=True,
        note="PROXY: measures questions memory could not answer, which is the "
        "intent of the criterion, but it is not literal repeat detection "
        "-- ClarificationOutcome.question_id is not established as stable "
        "across runs",
    )


def _sc4_series(summaries: list[RunSummary]) -> list[SC4Point]:
    out: list[SC4Point] = []
    for s in summaries:
        if not s.clarifications:
            continue
        human = sum(1 for c in s.clarifications if c.answered_by == "human")
        out.append(
            SC4Point(index=len(out), run_id=s.run_id, human_rate=human / len(s.clarifications))
        )
    return out


def _sc6(summaries: list[RunSummary]) -> list[SCRate]:
    soft = [g for s in summaries for g in s.gates if g.policy == "soft"]
    human = sum(1 for g in soft if g.decided_by == "human")
    waved = sum(1 for g in soft if g.overrides)
    n = len(soft)
    return [
        SCRate(
            criterion="SC-6",
            label="soft gates a human decided",
            rate=_rate(human, n),
            n=n,
            target="<0.05",
            note=f"denominator is soft gates, not runs; the n/a floor of "
            f"{MIN_RUNS} applies to soft gates",
        ),
        SCRate(
            criterion="SC-6-advisory",
            label="soft gates with waved advisory checks",
            rate=_rate(waved, n),
            n=n,
            target="<0.05",
            note="reported separately from human decisions: different "
            "failures, and one average would hide both",
        ),
    ]


# ------------------------------------------------------------- rendering


def render_sc_rollup_json(r: SCRollup) -> str:
    return r.model_dump_json(indent=2)


def _fmt(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.2f}"


def render_sc_rollup_markdown(r: SCRollup) -> str:
    """ASCII only (report.py:70-74)."""
    lines = [
        "",
        "## Success criteria",
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
<p>Rates below n={MIN_RUNS} render n/a rather than a percentage: a single
run displaying 100% would be quoted as a result.</p>
<table><tr><th>criterion</th><th>measure</th><th>rate</th><th>n</th>
<th>target</th><th></th></tr>{rows}</table>
<h2>Definitions</h2><ul>{notes}</ul>
</body></html>"""
