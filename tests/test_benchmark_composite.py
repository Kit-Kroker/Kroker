"""Composite-axis tests, split from tests/test_benchmark_scoring.py.

013 SG-3 ruling (orchestrator): the composite tests moved here so both
files stay under the 800-line tripwire. Test names and assertions are
unchanged; the shared fixtures are copied, not shared, so each file
stands alone.
"""

from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.scoring import compute_summaries
from sdlc.core.models import (
    HarnessKind,
)


def _rec(
    case,
    harness,
    model,
    q,
    usd,
    secs,
    lead_harness=None,
    *,
    stage="code",
    judge="contract",
    arm="a1",
):
    # 013 (R-11): rows key on the run, so every fixture record carries a
    # stored-shape run id `<bench>/<case>#<harness[:lead]>#<arm>`.
    tag = (
        f"{harness.value}:{lead_harness.value}"
        if harness is not None and lead_harness is not None
        else harness.value
        if harness is not None
        else "proposer"
    )
    return BenchmarkRecord(
        run_id=f"b/{case}#{tag}#{arm}",
        bench_run_id="b",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage=stage,
        role="dev",
        harness=harness,
        lead_harness=lead_harness,
        model=model,
        prompt_sha="",
        quality=QualityScore(score=q, judge=judge),
        cost=CostBag(usd=usd, input_tokens=10, output_tokens=5),
        speed=SpeedBag(
            wall_clock_s=secs,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10) + timedelta(seconds=secs),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _summarize(records, weights=None):
    # 013 (R-11): keyed by (stage, model) -- the row key no longer holds
    # the model, so a run's stage rows and its oracle row can share one.
    return {(s.stage, s.model): s for s in compute_summaries(records, weights)}


def _graded(case, harness, model, arm, *, q, usd, secs):
    """A graded pre-012 run (FR-034): a rubric-judged stage record, a
    post-code (merge) record so code finished, and an oracle record with
    a score -- the shape a case needs on two arms for a composite."""
    return [
        _rec(
            case,
            harness,
            model,
            q,
            usd,
            secs,
            stage="architecture",
            judge="llm_judge",
            arm=arm,
        ),
        _rec(case, harness, model, None, None, 1.0, stage="merge", arm=arm),
        _oracle_rec(case, harness, model, 1.0, arm=arm),
    ]


def _oracle_rec(
    case,
    harness,
    model,
    q,
    *,
    scope=BenchmarkScope.ORACLE,
    task_id=None,
    arm="a1",
    components=None,
):
    t = datetime(2026, 7, 27, 10)
    return BenchmarkRecord(
        run_id=f"b/{case}#{harness.value}#{arm}",
        bench_run_id="b",
        case_id=case,
        scope=scope,
        stage="oracle",
        task_id=task_id,
        role="oracle",
        harness=harness,
        model=model,
        quality=QualityScore(score=q, judge="oracle", components=components or {}),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )


def test_composite_ranks_better_quality_higher_even_if_pricier():
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.9, usd=1.0, secs=100) + (
        _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.5, usd=0.5, secs=50)
    )
    s = _summarize(recs)
    assert s[("architecture", "sonnet")].composite > s[("architecture", "opus")].composite


def test_cost_axis_dropped_when_fewer_than_two_costed():
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.9, usd=None, secs=100) + (
        _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.5, usd=None, secs=50)
    )
    s = _summarize(recs)
    # both composites still produced; quality + speed only (renormalized)
    assert s[("architecture", "sonnet")].composite is not None
    assert s[("architecture", "opus")].composite is not None


def test_judge_error_records_excluded_from_composite():
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.9, usd=1.0, secs=100) + (
        _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=None, usd=2.0, secs=200)
    )
    # The opus run's architecture record had a judge error (q=None). It still
    # appears as a summary row but its quality and composite are None.
    s = _summarize(recs)
    assert s[("architecture", "opus")].composite is None
    assert s[("architecture", "opus")].mean_quality is None


def test_custom_weights_change_ranking():
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.9, usd=1.0, secs=100) + (
        _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.5, usd=0.1, secs=10)
    )
    # weight cost heavily -> cheap opus wins
    s = _summarize(recs, CompositeWeights(quality=0.1, cost=0.8, speed=0.1))
    assert s[("architecture", "opus")].composite > s[("architecture", "sonnet")].composite


# --- 013 T005 (RED): composite across arms, or none (contract 7) -------------
# Names: data-model §1.2 (composite_shown, CompositeDecision), contract §7,
# research R-10. Cost and speed are normalised against the largest ARM MEAN
# of the (case, stage) -- never record maxima; an axis counts only when two
# or more arms of the (case, stage) have data; the shown decision comes
# from composite_shown(runs), never inferred from row values.


def test_composite_none_when_the_case_has_one_arm():
    """contract §7.1: one (harness, arm) pair with a graded run is short
    of two -- every row's composite is None."""
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=1.0, secs=100)
    assert all(s.composite is None for s in compute_summaries(recs))


def test_composite_normalises_cost_and_speed_against_the_largest_arm_mean():
    """contract §7.3 + R-10: the axes normalise against the larger ARM MEAN
    of the (case, stage). Arm a1 has two architecture records (arm means
    q 0.7, usd 1.5, wall 150), arm a2 one (q 0.4, usd 0.5, wall 50). a1
    holds both largest means, so its axis terms are 0:
    a1 = 0.6*0.7 = 0.42; a2 = 0.6*0.4 + 0.2*(1-0.5/1.5) + 0.2*(1-50/150)
       = 0.24 + 0.1333 + 0.1333 = 0.5067 (38/75)."""
    recs = (
        _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=1.0, secs=100)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.6, usd=2.0, secs=200)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.4, usd=0.5, secs=50)
    )
    s = _summarize(recs)
    assert abs(s[("architecture", "sonnet")].composite - 0.42) < 1e-9
    assert abs(s[("architecture", "opus")].composite - 38 / 75) < 1e-9


def test_composite_leaves_an_axis_out_when_only_one_arm_has_data():
    """contract §7.3: an axis counts when two or more arms have it. Cost
    has data on a1 only, so quality+speed renormalise to 0.75/0.25:
    a1 = 0.75*0.8 = 0.6; a2 = 0.75*0.4 + 0.25*(1-50/100) = 0.425."""
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=1.0, secs=100) + (
        _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.4, usd=None, secs=50)
    )
    s = _summarize(recs)
    assert abs(s[("architecture", "sonnet")].composite - 0.60) < 1e-9
    assert abs(s[("architecture", "opus")].composite - 0.425) < 1e-9


def test_composite_none_when_two_arms_are_of_different_generations():
    """contract §7.1: the two (harness, arm) pairs must sit within ONE
    generation; a pre-012 arm and a 012 arm never share a composite."""
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=1.0, secs=100) + [
        r.model_copy(update={"kroker_commit": "abc123"})
        for r in _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.4, usd=0.5, secs=50)
    ]
    assert all(s.composite is None for s in compute_summaries(recs))


def test_composite_none_rows_but_decision_shown_for_two_arm_graded_case():
    """contract §7.1 + R-10: two graded arms make the decision shown even
    when no row has quality data (contract-judged records only) -- the
    rows read composite None and composite_shown says shown, arms 2."""
    from sdlc.benchmarks.runs import build_runs, composite_shown

    recs = []
    for arm, model in [("a1", "sonnet"), ("a2", "opus")]:
        recs.append(
            _rec(
                "c1",
                HarnessKind.CLAUDE_CODE,
                model,
                0.8,
                1.0,
                100,
                stage="architecture",
                judge="contract",
                arm=arm,
            )
        )
        recs.append(
            _rec(
                "c1",
                HarnessKind.CLAUDE_CODE,
                model,
                None,
                None,
                1.0,
                stage="merge",
                judge="contract",
                arm=arm,
            )
        )
        recs.append(_oracle_rec("c1", HarnessKind.CLAUDE_CODE, model, 1.0, arm=arm))
    assert all(s.composite is None for s in compute_summaries(recs))
    decision = composite_shown(build_runs(recs))["c1"]
    assert decision.shown is True
    assert decision.arms == 2


# --- 013 T005 chaos (RED): arm-counted axes -----------------------------------
# contract 7.3 + R-10 edges the main section misses: an axis counts when two
# or more ARMS of the (case, stage) have data (never two records of one arm),
# and the normalisers are the largest ARM MEANS, never record maxima.


def test_cost_axis_out_when_only_one_arm_has_cost_data():
    """contract 7.3: a1 carries two costed records, a2 none -- cost is OUT
    even though two records have usd (the record-counting rule would keep
    it). Quality+speed renormalise to 0.75/0.25 against the largest arm
    mean wall (150):
    sonnet = 0.75*0.7 + 0.25*(1-150/150) = 0.525
    opus   = 0.75*0.4 + 0.25*(1-50/150)  = 0.4666666666666667."""
    recs = (
        _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=2.0, secs=100)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.6, usd=2.0, secs=200)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.4, usd=None, secs=50)
    )
    s = _summarize(recs)
    assert abs(s[("architecture", "sonnet")].composite - 0.525) < 1e-9
    assert abs(s[("architecture", "opus")].composite - 0.4666666666666667) < 1e-9


def test_two_graded_runs_of_one_arm_still_show_no_composite():
    """contract 7.1: two graded RUNS of the same (harness, arm) pair are
    still one arm -- the composite needs two arms, so every row is None
    even though both runs are graded and costed."""
    from sdlc.benchmarks.runs import build_runs, composite_shown

    second = [
        r.model_copy(update={"run_id": "b2/c1#claude_code#a1", "bench_run_id": "b2"})
        for r in _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.6, usd=0.5, secs=50)
    ]
    recs = _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.8, usd=1.0, secs=100) + second
    assert all(s.composite is None for s in compute_summaries(recs))
    decision = composite_shown(build_runs(recs))["c1"]
    assert decision.shown is False
    assert decision.arms == 1


def test_three_arms_normalise_against_the_largest_arm_mean():
    """contract 7.3 + R-10: with three arms every row gets a composite,
    normalised against the largest ARM MEAN. opus's two records average to
    usd 2.0 / wall 150, so the record maxima (3.0 / 250) are never the
    normalisers:
    sonnet = 0.6*0.9 + 0.2*(1-1/2)   + 0.2*(1-100/150)
    opus   = 0.6*0.5 + 0.2*(1-2/2)   + 0.2*(1-150/150)
    haiku  = 0.6*0.2 + 0.2*(1-0.5/2) + 0.2*(1-75/150)."""
    recs = (
        _graded("c1", HarnessKind.CLAUDE_CODE, "sonnet", "a1", q=0.9, usd=1.0, secs=100)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.4, usd=3.0, secs=50)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "opus", "a2", q=0.6, usd=1.0, secs=250)
        + _graded("c1", HarnessKind.CLAUDE_CODE, "haiku", "a3", q=0.2, usd=0.5, secs=75)
    )
    s = _summarize(recs)
    sonnet = 0.6 * 0.9 + 0.2 * (1 - 1 / 2) + 0.2 * (1 - 100 / 150)
    opus = 0.6 * 0.5
    haiku = 0.6 * 0.2 + 0.2 * (1 - 0.5 / 2) + 0.2 * (1 - 75 / 150)
    assert abs(s[("architecture", "sonnet")].composite - sonnet) < 1e-9
    assert abs(s[("architecture", "opus")].composite - opus) < 1e-9
    assert abs(s[("architecture", "haiku")].composite - haiku) < 1e-9
