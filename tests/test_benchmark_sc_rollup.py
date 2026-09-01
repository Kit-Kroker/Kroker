from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.sc_rollup import (
    MIN_RUNS,
    build_sc_rollup,
    render_sc_rollup_html,
    render_sc_rollup_json,
    render_sc_rollup_markdown,
)
from sdlc.models import ClarificationOutcome, GateOutcomeSummary, HarnessKind, RunSummary

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _summary(run_id, outcome="deployed:pr", gates=(), clars=(), offset=0):
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome=outcome,
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset),
        duration_s=0.0,
        gates=list(gates),
        clarifications=list(clars),
    )


def _gate(name, decided_by="policy", policy="soft", overrides=(), rnd=1):
    return GateOutcomeSummary(
        gate=name,
        round=rnd,
        policy=policy,
        decided_by=decided_by,
        approved=True,
        overrides=list(overrides),
    )


def _clar(qid, answered_by):
    return ClarificationOutcome(question_id=qid, question="q?", answered_by=answered_by)


def _code(run, task, outcome, fix, bench="b1"):
    return BenchmarkRecord(
        run_id=run,
        bench_run_id=bench,
        case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id=task,
        attempt=fix,
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=outcome,
        fix_attempts=fix,
    )


def _rate(rollup, criterion):
    return next(r for r in rollup.rates if r.criterion == criterion)


def _n_summaries(n, **kw):
    return [_summary(f"run-{i}", offset=i, **kw) for i in range(n)]


# ---------------------------------------------------------------- SC-1


def test_sc1_counts_runs_that_reached_merge_unattended():
    runs = [_summary(f"run-{i}", outcome="deployed:pr", offset=i) for i in range(4)]
    runs.append(_summary("run-4", outcome="rejected:plan", offset=4))
    r = _rate(build_sc_rollup(runs, []), "SC-1")
    assert r.n == 5 and r.rate == 0.8


def test_sc1_rejected_at_merge_still_counts_as_reached():
    """The criterion is REACHING the merge gate, not passing it."""
    runs = _n_summaries(4) + [_summary("run-4", outcome="rejected:merge:advisory", offset=4)]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


def test_sc1_merged_not_deployed_counts_as_reached():
    runs = _n_summaries(4) + [_summary("run-4", outcome="merged-not-deployed:http://pr", offset=4)]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


def test_sc1_early_terminals_did_not_reach():
    runs = [
        _summary(f"run-{i}", offset=i, outcome=o)
        for i, o in enumerate(
            [
                "rejected:research",
                "rejected:architecture",
                "rejected:plan",
                "failed:dependency-cycle",
                "failed:quarantined-tasks",
            ]
        )
    ]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 0.0


def test_sc1_human_gate_before_merge_disqualifies():
    runs = _n_summaries(4) + [
        _summary(
            "run-4", offset=4, gates=[_gate("architecture", decided_by="human"), _gate("merge")]
        )
    ]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 0.8


def test_sc1_human_at_the_merge_gate_itself_still_counts():
    """By then the run had already reached the gate unattended."""
    runs = _n_summaries(4) + [
        _summary(
            "run-4", offset=4, gates=[_gate("architecture"), _gate("merge", decided_by="human")]
        )
    ]
    assert _rate(build_sc_rollup(runs, []), "SC-1").rate == 1.0


# ---------------------------------------------------------------- SC-3


def _loop(run, task, final):
    """One fix loop: a failed first attempt, then a second ending `final`."""
    return [_code(run, task, BenchmarkOutcome.FAIL, 0), _code(run, task, final, 1)]


def test_sc3_counts_only_tasks_that_entered_a_fix_loop():
    recs = [_code("r1", "t00", BenchmarkOutcome.PASS, 0)]  # no loop
    for i in range(3):
        recs += _loop("r1", f"ok{i}", BenchmarkOutcome.PASS)
    for i in range(3):
        recs += _loop("r1", f"bad{i}", BenchmarkOutcome.FAIL)
    r = _rate(build_sc_rollup(_n_summaries(MIN_RUNS), recs), "SC-3")
    assert r.n == 6 and r.rate == 0.5


def test_sc3_floor_applies_to_loops_not_runs():
    """One floor rule for every rate, applied to that rate's own
    denominator. One loop is not a fix-loop success rate."""
    r = _rate(
        build_sc_rollup(_n_summaries(MIN_RUNS), _loop("r1", "t01", BenchmarkOutcome.PASS)), "SC-3"
    )
    assert r.n == 1 and r.rate is None


def test_sc3_final_attempt_decides():
    recs = []
    for i in range(MIN_RUNS):
        recs += [
            _code("r1", f"t{i}", BenchmarkOutcome.FAIL, 0),
            _code("r1", f"t{i}", BenchmarkOutcome.FAIL, 1),
            _code("r1", f"t{i}", BenchmarkOutcome.PASS, 2),
        ]
    assert _rate(build_sc_rollup(_n_summaries(MIN_RUNS), recs), "SC-3").rate == 1.0


# ---------------------------------------------------------------- SC-4


def test_sc4_is_the_human_answered_fraction_and_is_flagged_a_proxy():
    runs = _n_summaries(
        MIN_RUNS,
        clars=[
            _clar("q1", "human"),
            _clar("q2", "suggested"),
            _clar("q3", "suggested"),
            _clar("q4", "suggested"),
        ],
    )
    r = _rate(build_sc_rollup(runs, []), "SC-4")
    assert r.rate == 0.25
    assert r.proxy is True
    assert "not literal repeat detection" in r.note


def test_sc4_series_is_ordered_by_run_start():
    runs = [
        _summary("late", offset=5, clars=[_clar("q1", "suggested")]),
        _summary("early", offset=0, clars=[_clar("q1", "human")]),
    ]
    series = build_sc_rollup(runs, []).sc4_series
    assert [p.run_id for p in series] == ["early", "late"]
    assert [p.human_rate for p in series] == [1.0, 0.0]


def test_sc4_skips_runs_with_no_clarifications():
    runs = [_summary("r1", offset=0), _summary("r2", offset=1, clars=[_clar("q1", "human")])]
    assert [p.run_id for p in build_sc_rollup(runs, []).sc4_series] == ["r2"]


# ---------------------------------------------------------------- SC-6


def test_sc6_counts_human_decisions_on_soft_gates_only():
    """A hard gate decided by a human is not a soft-gate override; it is
    the policy working as configured."""
    soft = [_gate(f"g{i}", decided_by="human", policy="soft", rnd=i) for i in range(3)]
    soft += [_gate(f"g{i}", decided_by="policy", policy="soft", rnd=i) for i in range(3, 6)]
    hard = [_gate("deploy", decided_by="human", policy="hard")]
    runs = _n_summaries(MIN_RUNS - 1) + [_summary("run-x", offset=9, gates=soft + hard)]
    r = _rate(build_sc_rollup(runs, []), "SC-6")
    assert r.n == 6 and r.rate == 0.5


def test_sc6_waved_advisories_are_a_separate_number():
    gates = [_gate(f"g{i}", policy="soft", overrides=["coverage"], rnd=i) for i in range(3)]
    gates += [_gate(f"g{i}", policy="soft", rnd=i) for i in range(3, 6)]
    runs = _n_summaries(MIN_RUNS - 1) + [_summary("run-x", offset=9, gates=gates)]
    rollup = build_sc_rollup(runs, [])
    assert _rate(rollup, "SC-6-advisory").rate == 0.5
    # human decisions and waved advisories are different failures
    assert _rate(rollup, "SC-6").rate == 0.0


def test_sc6_floor_applies_to_soft_gates():
    runs = _n_summaries(MIN_RUNS - 1) + [
        _summary(
            "run-x", offset=9, gates=[_gate("architecture", decided_by="human", policy="soft")]
        )
    ]
    r = _rate(build_sc_rollup(runs, []), "SC-6")
    assert r.n == 1 and r.rate is None


# ------------------------------------------------------- denominator rule


def test_rate_is_na_below_the_floor():
    runs = _n_summaries(MIN_RUNS - 1)
    r = _rate(build_sc_rollup(runs, []), "SC-1")
    assert r.rate is None and r.n == MIN_RUNS - 1


def test_floor_is_five_runs():
    assert MIN_RUNS == 5


def test_no_evidence_yields_rates_with_zero_n():
    rollup = build_sc_rollup([], [])
    assert all(r.rate is None and r.n == 0 for r in rollup.rates)


# ------------------------------------------------------------- rendering


def test_markdown_shows_n_beside_every_rate_and_is_ascii():
    md = render_sc_rollup_markdown(build_sc_rollup(_n_summaries(MIN_RUNS), []))
    assert "n=" in md
    md.encode("ascii")


def test_markdown_prints_na_not_a_percentage_below_floor():
    md = render_sc_rollup_markdown(build_sc_rollup(_n_summaries(1), []))
    assert "n/a" in md
    assert "100" not in md


def test_html_and_json_render():
    import json

    rollup = build_sc_rollup(_n_summaries(MIN_RUNS), [])
    assert "<!doctype html>" in render_sc_rollup_html(rollup)
    assert json.loads(render_sc_rollup_json(rollup))["rates"]
