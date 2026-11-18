"""Cross-run success-criteria rates (ROADMAP SC-1/3/4/6).

ROADMAP says of each of these: "the cross-run aggregation remains the
benchmark's job." It names the criteria but not the formulas, so the
definitions here are CHOICES, documented per rate.

Pure aggregation + rendering, no I/O -- mirrors heatmap.py.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from pydantic import BaseModel, Field

from ..core.models import (
    GateOutcome,
    GateOutcomeSummary,
    RunSummary,
)
from ..runs_paths import RootsReport
from .evidence import NoSummaryRun
from .models import BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, is_pre012
from .operator_time import RunOperatorTime, operator_time
from .runs import MIN_OBSERVATIONS, attempt_sort_key
from .sc_stats import ci95_label

# Below this many runs a percentage is noise dressed as a result. A single
# green run rendering "100%" WILL be quoted; n/a cannot be. One floor for
# the whole round (research R-8): an alias of runs.MIN_OBSERVATIONS.
MIN_RUNS = MIN_OBSERVATIONS

# The merge gate's registered name (workflows/feature.py:1754).
MERGE_GATE = "merge"

# 026 A-2 (FR-006, research R3): SC-1's planned gates are a STATIC
# allowlist — the six stage gates a fleet configures. It cannot be config
# membership: `research` resolves through default_gate_policy exactly like
# `task:<id>`, and the summary carries no config. Unknown gate names fail
# closed (unplanned); `deploy_failed` is outside the set and post-merge.
STAGE_GATES = frozenset(("research", "clarify", "architecture", "plan", "merge", "deploy"))

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
    # 026 A-5: the exact 95% Clopper-Pearson interval beside SC-1 ("CI95
    # [lo, hi]"; "" when no rate). n is the floor, not proof of reliability.
    ci95: str = ""


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
    # 025 (FR-014/024): the fleet's commit provenance — the distinct
    # commits joined to these summaries by run_id, and the flag naming a
    # mixed set and/or a summary no record vouches for ("" = clean).
    commits: set[str] = Field(default_factory=set)
    commit_flag: str = ""
    # 026 (FR-002/003/004): the scored selection's full accounting. Every
    # run is either summarized or named in no_summary with its terminal
    # class (an SC-1 miss, SC-2 not-measured); smoke runs are excluded and
    # named; the roots line states which roots were read and how (FR-001).
    no_summary: list[NoSummaryRun] = Field(default_factory=list)
    excluded_smoke: list[str] = Field(default_factory=list)
    roots: RootsReport | None = None
    roots_line: str = ""


def _rate(n_hits: int, n: int) -> float | None:
    if n < MIN_RUNS or n == 0:
        return None
    return n_hits / n


def build_sc_rollup(
    summaries: list[RunSummary],
    records: list[BenchmarkRecord],
    *,
    selection_runs: int = 0,
    no_summary: list[NoSummaryRun] | None = None,
    roots: RootsReport | None = None,
    excluded_smoke: list[str] | None = None,
) -> SCRollup:
    no_summary = no_summary or []
    excluded_smoke = excluded_smoke or []
    ordered = sorted(summaries, key=lambda s: (s.started_at, s.run_id))
    data = [r for r in records if r.scope is not BenchmarkScope.CELL]
    ots = [(s, operator_time(s)) for s in ordered]
    policies = sorted({g.policy for s in ordered for g in s.gates})
    commits, commit_flag = _commit_provenance(ordered, data)
    # 026 (FR-003, research R2): SC-1's denominator is the distinct
    # (non-smoke) run_ids records vouch for, plus every no-summary run as
    # a miss. A summary no record vouches for stays under the commit flag
    # and never enters n. With no records at all there is no vouching
    # evidence, so summaries stand on their own (the 013 behavior, kept
    # for the records-less call path).
    record_run_ids = {r.run_id for r in records}
    vouched = [s for s in ordered if s.run_id in record_run_ids] if record_run_ids else ordered
    sc1 = _sc1(vouched, no_summary)
    return SCRollup(
        rates=[
            sc1,
            _sc1_strict(vouched, no_summary),
            *_sc2_rows(ots, no_summary),
            _sc3(data),
            _sc4(ordered),
            *_sc6(ordered),
        ],
        sc4_series=_sc4_series(ordered),
        pre012_records=sum(1 for r in data if is_pre012(r)),
        summary_runs=len(summaries),
        selection_runs=selection_runs,
        sc2_extra=_sc2_extra(ots),
        policy_mix="+".join(policies),
        # FR-015: the tier exists only when gates ran AND all were SOFT.
        evidence_tier=EVIDENCE_WEAK_SOFT if policies == ["soft"] else None,
        commits=commits,
        commit_flag=commit_flag,
        no_summary=no_summary,
        excluded_smoke=excluded_smoke,
        roots=roots,
        roots_line=_roots_line(roots, sc1.n, len(no_summary), no_summary, excluded_smoke),
    )


def _roots_line(
    roots: RootsReport | None,
    n_scored: int,
    n_no_summary: int,
    no_summary: list[NoSummaryRun],
    excluded_smoke: list[str],
) -> str:
    """FR-001's stated-roots line, rendered in every format ("" when the
    caller supplied no roots: legacy callers see no new text)."""
    if roots is None:
        return ""
    ns = ", ".join(f"{x.run_id}: {x.terminal_class}" for x in no_summary) or "none"
    sm = ", ".join(excluded_smoke) or "none"
    return (
        f"records: {roots.records} ({roots.records_how}); "
        f"summaries: {roots.export} ({roots.export_how}); "
        f"{n_scored - n_no_summary} of {n_scored} scored runs summarized; "
        f"no-summary: {ns}; smoke excluded: {sm}"
    )


def _commit_provenance(
    summaries: list[RunSummary], records: list[BenchmarkRecord]
) -> tuple[set[str], str]:
    """FR-014/024: join each summary to its records on run_id. Only records
    that JOIN a selected summary contribute commits — a record for a run
    outside the selection vouches for nothing here. Two independent breaks,
    both flagged: a mixed commit set, and any summary no record carries a
    commit for (no records at all, or only pre-012 None commits)."""
    commits_by_run: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.kroker_commit:
            commits_by_run[r.run_id].add(r.kroker_commit)
    commits: set[str] = set()
    unknown = 0
    for s in summaries:
        joined = commits_by_run.get(s.run_id)
        if joined:
            commits |= joined
        else:
            unknown += 1
    parts: list[str] = []
    if len(commits) > 1:
        parts.append(f"multiple commits ({'+'.join(sorted(commits))})")
    if unknown:
        parts.append(f"{unknown} run(s) commit unknown")
    return commits, "; ".join(parts)


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


def _unplanned(g: GateOutcomeSummary) -> bool:
    """026 A-2/D3: a gate the run did not configure, or a SOFT gate a
    person had to answer. `decided_by != "policy"` also covers `timeout`
    (an escalation was raised) and reviewer-named merge overrides."""
    return g.decided_by != "policy" and (g.gate not in STAGE_GATES or g.policy == "soft")


def _steered(g: GateOutcomeSummary) -> bool:
    """The steering guard: a planned gate a person decided with anything
    but `approve` (revise or reject) steered the run."""
    return (
        g.gate in STAGE_GATES
        and g.decided_by != "policy"
        and g.outcome is not None
        and g.outcome is not GateOutcome.APPROVE
    )


def _pre_merge_gates(s: RunSummary) -> list[GateOutcomeSummary]:
    """Every gate before the FIRST `merge` entry (a clean HARD merge opens
    no merge gate at all, so such a run's every gate is pre-merge)."""
    out: list[GateOutcomeSummary] = []
    for g in s.gates:
        if g.gate == MERGE_GATE:
            break
        out.append(g)
    return out


def _sc1_n(vouched: list[RunSummary], no_summary: list[NoSummaryRun]) -> int:
    """026 FR-003 (research R2): n is the distinct run_ids the vouched
    summaries cover plus every no-summary run — a crashed, timed-out,
    terminated or summary-missing run counts in the denominator as a miss,
    never drops out silently."""
    return len({s.run_id for s in vouched} | {x.run_id for x in no_summary})


def _sc1(vouched: list[RunSummary], no_summary: list[NoSummaryRun]) -> SCRate:
    """026 FR-006 (Q1-A): the PRD rule — reach the merge gate with no
    UNPLANNED escalation and no steering. Configured HARD stage gates an
    attendant answered do not count against the run."""
    hits = sum(
        1
        for s in vouched
        if _reached_merge(s) and not any(_unplanned(g) or _steered(g) for g in _pre_merge_gates(s))
    )
    n = _sc1_n(vouched, no_summary)
    planned = sum(1 for s in vouched for g in s.gates if g.gate in STAGE_GATES)
    return SCRate(
        criterion="SC-1",
        label="runs reaching the merge gate with no unplanned escalation",
        rate=_rate(hits, n),
        n=n,
        target=">=0.80",
        ci95=ci95_label(hits, n),
        note="reached = outcome in deployed/merged-not-deployed/rejected:merge; "
        f"planned gates = STAGE_GATES {{{', '.join(sorted(STAGE_GATES))}}} "
        f"(this fleet: {planned} planned gates); steering = a planned gate a "
        "person decided with anything but approve; unplanned = any other gate "
        "a non-policy decider answered, or a SOFT gate a person answered",
    )


def _sc1_strict(vouched: list[RunSummary], no_summary: list[NoSummaryRun]) -> SCRate:
    """The 025 rule, rendered beside the headline: any human-decided gate
    before merge disqualifies, configured or not."""
    hits = sum(1 for s in vouched if _reached_merge(s) and _unattended_to_merge(s))
    n = _sc1_n(vouched, no_summary)
    return SCRate(
        criterion="SC-1-strict",
        label="runs reaching the merge gate unattended (025 rule)",
        rate=_rate(hits, n),
        n=n,
        target=">=0.80",
        note="no human-decided gate before the merge gate, planned or not",
    )


def _sc2_rows(
    ots: list[tuple[RunSummary, RunOperatorTime]], no_summary: list[NoSummaryRun] | None = None
) -> list[SCRate]:
    """025 FR-006/012: SC-2 (shipped) and SC-2-all (all scored), the median
    engaged operator minutes per run. Each row floors on its OWN n; zero
    runs are measured (in n and in the median) while not-measured runs are
    excluded and named in the note (FR-005/007). 026 (FR-002): runs with
    no summary are named as not measured with their terminal class."""

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
        if ns_named := [f"{x.run_id}: {x.terminal_class}" for x in no_summary or []]:
            note += f"; no summary, not measured: {', '.join(ns_named)}"
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


# 026 T006: the render functions live in sc_render.py (moved verbatim; this
# module crossed its plan budget). Re-exported lazily (PEP 562) because a
# module-level import would cycle — sc_render imports MIN_RUNS from here.
_RENDERERS = ("render_sc_rollup_html", "render_sc_rollup_json", "render_sc_rollup_markdown")


def __getattr__(name: str):  # noqa: ANN202
    if name in _RENDERERS:
        from . import sc_render

        return getattr(sc_render, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_RENDERERS))
