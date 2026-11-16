"""Cross-run success-criteria rates (ROADMAP SC-1/3/4/6).

ROADMAP says of each of these: "the cross-run aggregation remains the
benchmark's job." It names the criteria but not the formulas, so the
definitions here are CHOICES, documented per rate.

Pure aggregation + rendering, no I/O -- mirrors heatmap.py.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape
from statistics import median

from pydantic import BaseModel, Field

from ..core.models import (
    RunSummary,
)
from .models import BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, is_pre012
from .operator_time import RunOperatorTime, operator_time
from .runs import MIN_OBSERVATIONS, attempt_sort_key

# Below this many runs a percentage is noise dressed as a result. A single
# green run rendering "100%" WILL be quoted; n/a cannot be. One floor for
# the whole round (research R-8): an alias of runs.MIN_OBSERVATIONS.
MIN_RUNS = MIN_OBSERVATIONS

# The merge gate's registered name (workflows/feature.py:1754).
MERGE_GATE = "merge"

# Run outcomes that reached the merge gate. The criterion is REACHING it,
# not passing it, so a merge-time rejection counts (feature.py:1757, 1791,
# 1828, 1836).
REACHED_PREFIXES: tuple[str, ...] = ("deployed:", "merged-not-deployed:", "rejected:merge")

# 025 (FR-012): SC-2's population is SHIPPED runs only — narrower than
# SC-1's REACHED_PREFIXES by rejected:merge (research R6).
SHIPPED_PREFIXES: tuple[str, ...] = ("deployed:", "merged-not-deployed:")

# 025 FR-015: the tier line SC-1/SC-2 carry when no gate ever asked a human
# unless it escalated (GATE 2: SOFT stands, with the weakness explicit).
EVIDENCE_WEAK_SOFT = "weak evidence (SOFT: no gate asked a human unless it escalated)"


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


class SC2Extra(BaseModel):
    """025 FR-013: the companions rendered beside the SC-2 rows, over the
    all-scored measured population (zeros are measured; not-measured runs
    are excluded like they are from every SC-2 number)."""

    zero_runs: int = 0
    human_touched_median_min: float | None = None  # engaged > 0 only
    human_touched_max_min: float | None = None
    wait_median_min: float | None = None  # UNCAPPED wait, zeros included


class SCRollup(BaseModel):
    rates: list[SCRate] = Field(default_factory=list)
    sc4_series: list[SC4Point] = Field(default_factory=list)
    # 012 (contract §7.6): pre-012 records among the input (cell-scope
    # records excluded); rendered as the untrusted line.
    pre012_records: int = 0
    # 013 (contract §9.3): how many runs the selection covers and how many
    # of them left a run summary; rendered as the opening line.
    summary_runs: int = 0
    selection_runs: int = 0
    # 025 (FR-013/015): SC-2 companions, the runs' gate-policy mix, and the
    # evidence tier line when every gate ran SOFT.
    sc2_extra: SC2Extra = Field(default_factory=SC2Extra)
    policy_mix: str = ""
    evidence_tier: str | None = None


def _rate(n_hits: int, n: int) -> float | None:
    if n < MIN_RUNS or n == 0:
        return None
    return n_hits / n


def build_sc_rollup(
    summaries: list[RunSummary],
    records: list[BenchmarkRecord],
    *,
    selection_runs: int = 0,
) -> SCRollup:
    ordered = sorted(summaries, key=lambda s: (s.started_at, s.run_id))
    data = [r for r in records if r.scope is not BenchmarkScope.CELL]
    ots = [(s, operator_time(s)) for s in ordered]
    policies = sorted({g.policy for s in ordered for g in s.gates})
    return SCRollup(
        rates=[_sc1(ordered), *_sc2_rows(ots), _sc3(data), _sc4(ordered), *_sc6(ordered)],
        sc4_series=_sc4_series(ordered),
        pre012_records=sum(1 for r in data if is_pre012(r)),
        summary_runs=len(summaries),
        selection_runs=selection_runs,
        sc2_extra=_sc2_extra(ots),
        policy_mix="+".join(policies),
        # FR-015: the tier exists only when gates ran AND all were SOFT.
        evidence_tier=EVIDENCE_WEAK_SOFT if policies == ["soft"] else None,
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


def _sc2_rows(ots: list[tuple[RunSummary, RunOperatorTime]]) -> list[SCRate]:
    """025 FR-006/012: SC-2 (shipped) and SC-2-all (all scored), the median
    engaged operator minutes per run. Each row floors on its OWN n; zero
    runs are measured (in n and in the median) while not-measured runs are
    excluded and named in the note (FR-005/007)."""

    def row(criterion: str, label: str, base: list[tuple[RunSummary, RunOperatorTime]]) -> SCRate:
        measured = [(s, ot) for s, ot in base if ot.state != "not_measured"]
        engaged = [ot.engaged_s / 60.0 for _, ot in measured]
        zero = sum(1 for _, ot in measured if ot.state == "zero")
        note = (
            f"median engaged operator minutes per {label}; engaged caps at "
            f"600 s (10 min) per interaction; {zero} zero-interaction runs "
            f"of {len(measured)} measured; "
            f"{len(base) - len(measured)} not measured (excluded)"
        )
        return SCRate(
            criterion=criterion,
            label=f"median operator minutes per {label}",
            rate=median(engaged) if len(engaged) >= MIN_RUNS else None,
            n=len(engaged),
            target="<=15 min",
            note=note,
        )

    shipped = [(s, ot) for s, ot in ots if s.outcome.startswith(SHIPPED_PREFIXES)]
    return [row("SC-2", "shipped run", shipped), row("SC-2-all", "scored run", ots)]


def _sc2_extra(ots: list[tuple[RunSummary, RunOperatorTime]]) -> SC2Extra:
    measured = [ot for _, ot in ots if ot.state != "not_measured"]
    touched = [ot.engaged_s / 60.0 for ot in measured if ot.engaged_s > 0]
    waits = [ot.wait_s / 60.0 for ot in measured]
    return SC2Extra(
        zero_runs=sum(1 for ot in measured if ot.state == "zero"),
        human_touched_median_min=median(touched) if touched else None,
        human_touched_max_min=max(touched) if touched else None,
        wait_median_min=median(waits) if waits else None,
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
        recs = sorted(recs, key=attempt_sort_key)
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
<p>Rates below n={MIN_RUNS} render n/a rather than a percentage: a single
run displaying 100% would be quoted as a result.</p>
<table><tr><th>criterion</th><th>measure</th><th>rate</th><th>n</th>
<th>target</th><th></th></tr>{rows}</table>
<p>{escape(_sc2_companions_line(r))}</p>
{tier}<h2>Definitions</h2><ul>{notes}</ul>{untrusted}
</body></html>"""
