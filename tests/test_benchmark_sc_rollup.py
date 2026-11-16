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
from sdlc.core.models import (
    ClarificationOutcome,
    GateOutcomeSummary,
    HarnessKind,
    RunSummary,
)

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


# --- 012 T010 (RED): rollup immunity + the pre-012 line (contract §7.6/7.8) -


def _cell_scope_rec(run="run-1"):
    from sdlc.benchmarks.models import CellStatus

    r = _code(run, "t-x", BenchmarkOutcome.PASS, 0)
    return r.model_copy(
        update={
            "scope": BenchmarkScope.CELL,
            "stage": "cell",
            "role": "cell",
            "task_id": None,
            "attempt": None,
            "quality": QualityScore(score=None, judge="contract"),
            "cell": CellStatus(
                pipeline_finished=True,
                code_finished=True,
                completed=True,
                last_stage="merge",
                grading="graded",
                child_result="ok",
            ),
            "kroker_commit": "abc123",
        }
    )


def _not_evaluated_merge_rec(run="run-1"):
    """A gate recorded as not evaluated in benchmark mode: neither pass nor
    fail -- the SC-3 code-stage grouping must not see it."""
    r = _code(run, "t-x", BenchmarkOutcome.FAIL, 0)
    return r.model_copy(
        update={
            "stage": "merge",
            "task_id": None,
            "attempt": None,
            "outcome": BenchmarkOutcome.NOT_EVALUATED,
            "quality": QualityScore(score=None, judge="contract"),
        }
    )


def test_cell_and_not_evaluated_records_change_no_rate():
    """Both records ride an EXISTING run id, so the invariant is about
    aggregation, not run discovery."""
    summaries = _n_summaries(MIN_RUNS)
    recs = []
    for i in range(MIN_RUNS):
        recs += _loop(f"run-{i}", f"t{i}", BenchmarkOutcome.PASS)
    base = build_sc_rollup(summaries, recs)
    with_extra = build_sc_rollup(
        summaries, recs + [_cell_scope_rec("run-1"), _not_evaluated_merge_rec("run-1")]
    )
    assert [(x.criterion, x.n, x.rate) for x in with_extra.rates] == [
        (x.criterion, x.n, x.rate) for x in base.rates
    ]
    assert with_extra.sc4_series == base.sc4_series


def test_sc_rollup_markdown_and_html_state_the_pre012_count_when_present():
    """The count comes from the records handed to build_sc_rollup: three
    pre-012 code records (plus one 012) must put the exact line in BOTH
    renderers; with only 012 records the line is absent."""
    summaries = _n_summaries(MIN_RUNS)
    pre = [_code(f"run-{i}", f"p{i}", BenchmarkOutcome.PASS, 0) for i in range(3)]
    only_012 = [pre[0].model_copy(update={"kroker_commit": "abc123"})]
    line = "includes 3 pre-012 records (untrusted)"
    rollup = build_sc_rollup(summaries, pre + only_012)
    assert line in render_sc_rollup_markdown(rollup)
    assert line in render_sc_rollup_html(rollup)
    plain = build_sc_rollup(summaries, only_012)
    assert "pre-012" not in render_sc_rollup_markdown(plain)
    assert "pre-012" not in render_sc_rollup_html(plain)


# --- 013 T010 (RED): run-summary scoping and counts (contract §9) ------------


def test_rollup_carries_the_counts_and_renders_the_line_first():
    """§9.3: the section opens with `N of M runs left a run summary`, in
    markdown and in HTML, before anything else the section says."""
    rollup = build_sc_rollup(_n_summaries(3), [], selection_runs=7)
    assert rollup.summary_runs == 3
    assert rollup.selection_runs == 7
    line = "3 of 7 runs left a run summary"
    md = render_sc_rollup_markdown(rollup)
    html = render_sc_rollup_html(rollup)
    assert line in md and line in html
    assert md.index(line) < md.index("Rates below")
    assert html.index(line) < html.index("Rates below")


def test_zero_summaries_leave_summary_criteria_na_but_sc3_from_records():
    """§9.4: SC-1, SC-4 and SC-6 take only the loaded summaries (none here
    -> n/a with n=0); SC-3 is still computed from the selection's
    records."""
    recs = []
    for i in range(MIN_RUNS):
        recs += _loop("r1", f"t{i}", BenchmarkOutcome.PASS)
    rollup = build_sc_rollup([], recs, selection_runs=MIN_RUNS)
    for criterion in ("SC-1", "SC-4", "SC-6", "SC-6-advisory"):
        r = _rate(rollup, criterion)
        assert r.rate is None and r.n == 0, criterion
    sc3 = _rate(rollup, "SC-3")
    assert sc3.n == MIN_RUNS and sc3.rate == 1.0
    assert rollup.summary_runs == 0
    assert rollup.selection_runs == MIN_RUNS


def test_min_runs_is_the_one_under_five_threshold():
    """Data-model §6: MIN_RUNS aliases runs.MIN_OBSERVATIONS -- one floor
    for the round, not two that could drift."""
    from sdlc.benchmarks.runs import MIN_OBSERVATIONS

    assert MIN_RUNS is MIN_OBSERVATIONS


def test_sc3_orders_attempts_with_the_shared_key():
    """Data-model §1.2: `sc_rollup` uses `runs.attempt_sort_key`, not a
    private lambda -- one attempt ordering for the round."""
    import inspect

    import sdlc.benchmarks.sc_rollup as m

    src = inspect.getsource(m._sc3)
    assert "attempt_sort_key" in src
    assert "lambda" not in src


def _unnumbered(run, task, outcome, started, fix):
    """A code record whose attempt number is absent (pre-012 shape); the
    loop marker rides on `fix_attempts` alone."""
    return _code(run, task, outcome, fix).model_copy(
        update={
            "attempt": None,
            "speed": SpeedBag(wall_clock_s=1.0, started_at=started, ended_at=started),
        }
    )


def test_sc3_orders_unnumbered_attempts_by_start_time():
    """The behaviour behind the shared key: with attempt numbers absent,
    start time decides which attempt is last -- and the last one decides
    the loop."""

    def _corpus(first, last):
        recs = []
        for i in range(MIN_RUNS):
            base = T + timedelta(hours=10 * i)
            recs += [
                _unnumbered("r1", f"t{i}", first, base, fix=0),
                _unnumbered("r1", f"t{i}", last, base + timedelta(hours=1), fix=1),
            ]
        return recs

    ok = _corpus(BenchmarkOutcome.FAIL, BenchmarkOutcome.PASS)
    resolved = _rate(build_sc_rollup([], ok), "SC-3")
    assert resolved.n == MIN_RUNS and resolved.rate == 1.0
    bad = _corpus(BenchmarkOutcome.PASS, BenchmarkOutcome.FAIL)
    broken = _rate(build_sc_rollup([], bad), "SC-3")
    assert broken.n == MIN_RUNS and broken.rate == 0.0


# --- 025 T007 (RED): SC-2 rows and companions (FR-006/007/008/012/013/015) ---

_SC2_TARGET = "<=15 min"
_EVIDENCE_TEXT = "weak evidence (SOFT: no gate asked a human unless it escalated)"


def _ot_summary(
    run_id,
    offset=0,
    outcome="deployed:pr",
    waits_min=(),
    instrumented=True,
    policy="soft",
):
    """A summary whose human gates were each raised at T and decided
    `wait` minutes later; no waits means no human interaction (state zero)."""
    gates = [
        GateOutcomeSummary(
            gate=f"g{i}",
            round=1,
            policy=policy,
            decided_by="human",
            approved=True,
            raised_at=T,
            decided_at=T + timedelta(minutes=w),
        )
        for i, w in enumerate(waits_min)
    ]
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome=outcome,
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset),
        duration_s=0.0,
        gates=gates,
        operator_instrumented=instrumented,
    )


def _ot_runs(n, waits_min=(10,), start=0, **kw):
    return [_ot_summary(f"ot-{start + i}", offset=start + i, waits_min=waits_min, **kw) for i in range(n)]


def test_sc2_median_engaged_minutes_over_shipped_measured_runs():
    rollup = build_sc_rollup(_ot_runs(5), [])
    sc2 = _rate(rollup, "SC-2")
    assert sc2.rate == 10.0 and sc2.n == 5 and sc2.target == _SC2_TARGET
    assert "operator minutes" in sc2.label
    all_ = _rate(rollup, "SC-2-all")
    assert all_.rate == 10.0 and all_.n == 5 and all_.target == _SC2_TARGET


def test_sc2_shipped_is_narrower_than_sc1_and_the_cap_bounds_engaged():
    runs = _ot_runs(5) + [
        _ot_summary("ot-rej", offset=9, outcome="rejected:merge", waits_min=(600,))
    ]
    rollup = build_sc_rollup(runs, [])
    sc2 = _rate(rollup, "SC-2")
    all_ = _rate(rollup, "SC-2-all")
    assert sc2.n == 5 and sc2.rate == 10.0
    assert all_.n == 6 and all_.rate == 10.0  # capped engaged, not the 600 min wait


def test_sc2_merged_not_deployed_counts_as_shipped():
    runs = _ot_runs(4) + [
        _ot_summary("ot-m", offset=9, outcome="merged-not-deployed:http://pr", waits_min=(10,))
    ]
    sc2 = _rate(build_sc_rollup(runs, []), "SC-2")
    assert sc2.n == 5 and sc2.rate == 10.0


def test_sc2_is_na_below_the_floor_and_each_row_floors_on_its_own_n():
    runs = _ot_runs(4)
    rollup = build_sc_rollup(runs, [])
    sc2 = _rate(rollup, "SC-2")
    assert sc2.rate is None and sc2.n == 4
    assert _rate(rollup, "SC-2-all").rate is None

    # 4 shipped + 1 rejected:merge: SC-2-all reaches the floor, SC-2 does not.
    mixed = runs + [_ot_summary("ot-rej", offset=9, outcome="rejected:merge", waits_min=(10,))]
    rollup = build_sc_rollup(mixed, [])
    assert _rate(rollup, "SC-2").rate is None and _rate(rollup, "SC-2").n == 4
    assert _rate(rollup, "SC-2-all").rate == 10.0 and _rate(rollup, "SC-2-all").n == 5


def test_sc2_not_measured_runs_are_excluded_from_n_and_counted_in_the_note():
    runs = _ot_runs(5) + _ot_runs(2, start=5, instrumented=False)
    rollup = build_sc_rollup(runs, [])
    for name in ("SC-2", "SC-2-all"):
        r = _rate(rollup, name)
        assert r.n == 5, name
        assert "2 not measured" in r.note, name
        assert "excluded" in r.note, name
    note = _rate(rollup, "SC-2").note
    assert "600" in note or "10 min" in note  # the cap is stated
    assert "median" in note  # the definition is stated


def test_sc2_zero_interaction_runs_are_measured_and_counted():
    runs = _ot_runs(3) + _ot_runs(2, waits_min=(), start=3)
    rollup = build_sc_rollup(runs, [])
    sc2 = _rate(rollup, "SC-2")
    assert sc2.n == 5
    assert sc2.rate == 10.0  # sorted 0, 0, 10, 10, 10
    assert rollup.sc2_extra.zero_runs == 2
    assert "2" in sc2.note and "zero" in sc2.note.lower()

    # and with the zeros in the majority the median really is zero
    low = build_sc_rollup(_ot_runs(2) + _ot_runs(3, waits_min=(), start=2), [])
    assert _rate(low, "SC-2").rate == 0.0


def test_sc2_companions_human_touched_and_uncapped_wait():
    import json

    # engaged minutes 2, 4, 10, 10, 20 -- the last two capped from 9 h waits;
    # the 20 is one run with two capped 9 h gates.
    runs = [
        _ot_summary("c0", offset=0, waits_min=(2,)),
        _ot_summary("c1", offset=1, waits_min=(4,)),
        _ot_summary("c2", offset=2, waits_min=(540,)),
        _ot_summary("c3", offset=3, waits_min=(540,)),
        _ot_summary("c4", offset=4, waits_min=(540, 540)),
        _ot_summary("c5", offset=5, waits_min=()),  # a measured zero
    ]
    rollup = build_sc_rollup(runs, [])
    extra = rollup.sc2_extra
    assert extra.zero_runs == 1
    # human-touched = engaged > 0 only: 2, 4, 10, 10, 20
    assert extra.human_touched_median_min == 10.0
    assert extra.human_touched_max_min == 20.0
    # wait is uncapped and counts the zero run: 0, 2, 4, 540, 540, 1080
    assert extra.wait_median_min == 272.0
    assert extra.wait_median_min > extra.human_touched_median_min

    parsed = json.loads(render_sc_rollup_json(rollup))
    for key in (
        "zero_runs",
        "human_touched_median_min",
        "human_touched_max_min",
        "wait_median_min",
    ):
        assert key in parsed["sc2_extra"]


def test_sc2_policy_mix_and_evidence_tier_all_soft():
    rollup = build_sc_rollup(_ot_runs(5), [])
    assert "soft" in rollup.policy_mix and "hard" not in rollup.policy_mix
    assert rollup.evidence_tier == _EVIDENCE_TEXT


def test_sc2_policy_mix_names_both_policies_and_drops_the_tier_when_mixed():
    runs = _ot_runs(4) + _ot_runs(1, start=4, policy="hard")
    rollup = build_sc_rollup(runs, [])
    assert "soft" in rollup.policy_mix and "hard" in rollup.policy_mix
    assert rollup.evidence_tier is None


def test_sc2_evidence_tier_is_none_when_no_gate_exists():
    rollup = build_sc_rollup(_ot_runs(5, waits_min=()), [])
    assert rollup.evidence_tier is None


def test_sc2_rendering_markdown_html_and_json_carry_rows_and_companions():
    import json

    rollup = build_sc_rollup(_ot_runs(5), [])
    md = render_sc_rollup_markdown(rollup)
    html = render_sc_rollup_html(rollup)
    for out in (md, html):
        assert "SC-2" in out and "SC-2-all" in out
        assert _SC2_TARGET in out or "&lt;=15 min" in out
        low = out.lower()
        for needle in ("human-touched", "wait", "zero", "policy mix"):
            assert needle in low, needle
        assert _EVIDENCE_TEXT in out

    parsed = json.loads(render_sc_rollup_json(rollup))
    assert {"SC-2", "SC-2-all"} <= {r["criterion"] for r in parsed["rates"]}
    assert "sc2_extra" in parsed
    assert "soft" in parsed["policy_mix"]
    assert parsed["evidence_tier"] == _EVIDENCE_TEXT


# --- 025 T007 (RED, chaos/edge cases): SC-2 rollup ---


def test_sc2_missing_raise_time_makes_a_shipped_run_not_measured():
    broken = RunSummary(
        run_id="ot-broken",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T + timedelta(hours=9),
        ended_at=T + timedelta(hours=9),
        duration_s=0.0,
        gates=[
            GateOutcomeSummary(
                gate="g0",
                round=1,
                policy="soft",
                decided_by="human",
                approved=True,
                raised_at=None,
                decided_at=T + timedelta(minutes=10),
            )
        ],
        operator_instrumented=True,
    )
    rollup = build_sc_rollup(_ot_runs(5) + [broken], [])
    for name in ("SC-2", "SC-2-all"):
        r = _rate(rollup, name)
        assert r.n == 5, name
        assert "1 not measured" in r.note, name


def test_sc2_and_sc2_all_populations_diverge_on_shipped_vs_all_scored():
    # engaged is capped at 10 min per interaction, so 500 engaged minutes is
    # fifty 10-minute human gates in one run.
    rejected = [
        _ot_summary(
            f"ot-rej-{i}",
            offset=10 + i,
            outcome="rejected:merge",
            waits_min=tuple([10] * 50),
        )
        for i in range(6)
    ]
    shipped = _ot_runs(5, waits_min=(5,))
    rollup = build_sc_rollup(shipped + rejected, [])
    sc2 = _rate(rollup, "SC-2")
    all_ = _rate(rollup, "SC-2-all")
    assert sc2.n == 5 and sc2.rate == 5.0
    assert all_.n == 11 and all_.rate == 500.0


def test_sc2_clarification_batch_only_run_contributes_its_engaged_minutes():
    batch_run = RunSummary(
        run_id="ot-clar",
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T + timedelta(hours=9),
        ended_at=T + timedelta(hours=9),
        duration_s=0.0,
        clarifications=[
            ClarificationOutcome(
                question_id=f"q{i}",
                question="q?",
                answered_by="human",
                raised_at=T,
                answered_at=T + timedelta(minutes=8),
            )
            for i in range(3)
        ],
        operator_instrumented=True,
    )
    runs = _ot_runs(2, waits_min=(2,)) + _ot_runs(2, waits_min=(20,), start=2) + [batch_run]
    # engaged: 2, 2, 10(cap), 10(cap), 8 -> sorted 2, 2, 8, 10, 10 -> median 8.0
    rollup = build_sc_rollup(runs, [])
    sc2 = _rate(rollup, "SC-2")
    assert sc2.n == 5
    assert sc2.rate == 8.0


def test_sc2_human_touched_excludes_zero_runs_from_median_and_max():
    # 12 engaged minutes = two 6-minute gates (a single gate caps at 10)
    runs = _ot_runs(4, waits_min=()) + _ot_runs(1, waits_min=(6, 6), start=4)
    extra = build_sc_rollup(runs, []).sc2_extra
    assert extra.zero_runs == 4
    assert extra.human_touched_median_min == 12.0
    assert extra.human_touched_max_min == 12.0


def test_sc2_even_n_median_averages_the_middle_pair():
    runs = [
        _ot_summary(f"ot-e{i}", offset=i, waits_min=m)
        for i, m in enumerate([(2,), (4,), (6,), (8,), (5, 5), (6, 6)])
    ]
    assert _rate(build_sc_rollup(runs, []), "SC-2").rate == 7.0
