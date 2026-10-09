"""013 T003 (RED): the run model, `sdlc.benchmarks.runs`.

Names: .specify/specs/013-benchmark-scoring-output/data-model.md §1; the
status table and arm order are research.md R-2 and R-3; the cell id is
formed exactly as ``B/workflow.py:308`` does. Every test imports its
`sdlc.benchmarks.runs` symbol function-local (the repo's RED convention)
so each missing name fails its own test instead of breaking collection.
"""

from datetime import datetime

from sdlc.benchmarks.models import (
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import HarnessKind


def _record(**kw):
    base = dict(
        run_id="b1/add-login#opencode#a1",
        bench_run_id="b1",
        case_id="add-login",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=datetime(2026, 7, 4, 10),
            ended_at=datetime(2026, 7, 4, 10, 0, 12),
        ),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


def _oracle_record(**kw):
    """An oracle-scope record; `passed`/`total` ride quality.components."""
    base = dict(
        stage="oracle",
        role="oracle",
        scope=BenchmarkScope.ORACLE,
        model="openai/gpt-5.2",
        quality=QualityScore(score=1.0, judge="oracle"),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return _record(**base)


# --- §1.1 one run per run_id; drift produces no run --------------------------


def test_build_runs_one_run_per_distinct_run_id():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="b1/c1#opencode#a1"),
        _record(run_id="b1/c1#opencode#a1", stage="code"),
        _record(run_id="b1/c2#opencode#a1"),
    ]
    runs = build_runs(records)
    assert sorted(r.run_id for r in runs) == ["b1/c1#opencode#a1", "b1/c2#opencode#a1"]


def test_build_runs_records_of_several_models_under_one_run_id_land_in_one_run():
    """Pre-012 records of one run carry per-role model strings; they are
    one run, never three (R-3)."""
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="b1/c#opencode#a", model="zai-coding-plan/glm-5.2"),
        _record(run_id="b1/c#opencode#a", stage="code", model="anthropic:claude-sonnet-4-6"),
        _record(run_id="b1/c#opencode#a", stage="qa", model="openai/gpt-5.2"),
    ]
    runs = build_runs(records)
    assert len(runs) == 1
    assert len(runs[0].records) == 3


def test_build_runs_drift_records_produce_no_run():
    from sdlc.benchmarks.runs import build_runs

    drift = _record(
        case_id="_production",
        bench_run_id="_drift/2026-10-10",
        run_id="_drift/2026-10-10/prod",
    )
    assert build_runs([drift]) == []


# --- §1.2 status from the cell record, or derived ----------------------------


def test_run_with_cell_record_takes_recorded_status_and_is_not_derived():
    from sdlc.benchmarks.runs import build_runs

    cell = _record(
        scope=BenchmarkScope.CELL,
        stage="cell",
        role="cell",
        model="deterministic",
        outcome=BenchmarkOutcome.PASS,
        quality=QualityScore(score=None, judge="contract"),
        cell=CellStatus(
            pipeline_finished=True,
            code_finished=True,
            completed=True,
            last_stage="merge",
            grading="graded",
            child_result=None,
        ),
    )
    records = [
        _record(run_id=cell.run_id, stage="code"),
        cell,
        _oracle_record(run_id=cell.run_id),
    ]
    (run,) = build_runs(records)
    assert run.status == "graded"
    assert run.status_derived is False
    assert run.last_stage == "merge"
    assert run.pipeline_finished is True


def test_run_without_cell_record_derives_status():
    from sdlc.benchmarks.runs import build_runs

    records = [_record(stage="research"), _record(stage="clarify")]
    (run,) = build_runs(records)
    assert run.status == "lost"
    assert run.status_derived is True
    assert run.last_stage == "clarify"
    assert run.pipeline_finished is None


# --- §1.3 the R-2 status table -----------------------------------------------


def test_status_no_oracle_case_stopped_at_plan_is_lost():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="research"),
        _record(stage="clarify"),
        _record(stage="architecture"),
        _record(stage="plan"),
    ]
    (run,) = build_runs(records)
    assert run.status == "lost"


def test_status_code_finished_without_oracle_record_is_no_oracle():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="code"),
        _record(stage="qa"),
        _record(stage="review"),
        _record(stage="handoff"),
        _record(stage="analyze"),
    ]
    (run,) = build_runs(records)
    assert run.status == "no_oracle"


def test_status_code_finished_with_scored_oracle_is_graded():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="code"),
        _record(stage="merge"),
        _oracle_record(quality=QualityScore(score=1.0, judge="oracle")),
    ]
    (run,) = build_runs(records)
    assert run.status == "graded"


def test_status_code_finished_with_scoreless_oracle_is_grading_failed():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="code"),
        _record(stage="merge"),
        _oracle_record(quality=QualityScore(score=None, judge="oracle")),
    ]
    (run,) = build_runs(records)
    assert run.status == "grading_failed"


def test_status_code_not_finished_with_oracle_record_is_lost():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="research"),
        _oracle_record(),
    ]
    (run,) = build_runs(records)
    assert run.status == "lost"


# --- §1.4 oracle components on graded runs; discarded on lost ----------------


def test_lost_run_discards_oracle_records():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="research"),
        _oracle_record(),
        _oracle_record(scope=BenchmarkScope.ORACLE_TASK, task_id="T1"),
        _oracle_record(scope=BenchmarkScope.ORACLE_TASK, task_id="T2"),
    ]
    (run,) = build_runs(records)
    assert run.status == "lost"
    assert run.oracle_passed is None
    assert run.oracle_total is None
    assert run.discarded_oracle_records == 1  # oracle-scope only


def test_graded_run_takes_passed_and_total_from_oracle_components():
    """Components are floats on the record; `oracle_passed`/`oracle_total`
    are ints on the run (data-model §1.1)."""
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(stage="code"),
        _record(stage="merge"),
        _oracle_record(
            quality=QualityScore(
                score=0.8,
                judge="oracle",
                components={"passed": 4.0, "total": 5.0},
            )
        ),
    ]
    (run,) = build_runs(records)
    assert run.status == "graded"
    assert run.oracle_passed == 4
    assert run.oracle_total == 5


# --- §1.5 arm order of R-3 ----------------------------------------------------


def test_arm_from_012_record_field_not_recovered():
    from sdlc.benchmarks.runs import build_runs

    records = [_record(kroker_commit="deadbeef", arm="zai-coding-plan-glm-5.2")]
    (run,) = build_runs(records)
    assert run.arm == "zai-coding-plan-glm-5.2"
    assert run.arm_recovered is False
    assert run.generation == "012"
    assert run.commit == "deadbeef"


def test_arm_recovered_from_run_id_for_pre012_run():
    """A pre-012 run whose records carry three different model strings still
    has one arm, taken from the run id (R-3)."""
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="b1/c#opencode#a-1", model="zai-coding-plan/glm-5.2"),
        _record(run_id="b1/c#opencode#a-1", stage="code", model="anthropic:claude-sonnet-4-6"),
        _record(run_id="b1/c#opencode#a-1", stage="qa", model="openai/gpt-5.2"),
    ]
    (run,) = build_runs(records)
    assert run.arm == "a-1"
    assert run.arm_recovered is True
    assert run.generation == "pre012"


def test_arm_recovered_from_oracle_model_when_run_id_shape_unexpected():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="weird-id", stage="code"),
        _oracle_record(run_id="weird-id", model="anthropic:claude-sonnet-4-6"),
    ]
    (run,) = build_runs(records)
    assert run.arm == "anthropic:claude-sonnet-4-6"
    assert run.arm_recovered is True


def test_arm_recovered_from_first_record_label_when_no_oracle():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="weird-id-2", stage="code", model="zai-coding-plan/glm-5.2"),
        _record(run_id="weird-id-2", stage="qa", model="openai/gpt-5.2"),
    ]
    (run,) = build_runs(records)
    assert run.arm == "zai-coding-plan/glm-5.2"  # arm_label of the first record
    assert run.arm_recovered is True


# --- §1.2 parse_run_id on workflow-shaped ids (R-3 verify) --------------------


def test_parse_run_id_round_trips_a_real_cell_id():
    """The id is formed EXACTLY as B/workflow.py:308:
    f"{bench_run_id}/{cell.cell_id}"."""
    from sdlc.benchmarks.runs import parse_run_id

    cell = BenchmarkCell(
        case_id="add-login",
        harness=HarnessKind.OPENCODE,
        arm_name="zai-coding-plan/glm-5.2",
    )
    run_id = f"bench-2026/{cell.cell_id}"
    assert parse_run_id(run_id) == ("add-login", "opencode", "zai-coding-plan/glm-5.2")


def test_parse_run_id_handles_crew_lead_and_hash_in_arm():
    from sdlc.benchmarks.runs import parse_run_id

    cell = BenchmarkCell(
        case_id="add-login",
        harness=HarnessKind.CREW,
        lead_harness=HarnessKind.CLAUDE_CODE,
        arm_name="a#1",
    )
    run_id = f"bench-2026/{cell.cell_id}"
    assert parse_run_id(run_id) == ("add-login", "crew:claude_code", "a#1")


def test_parse_run_id_returns_none_for_unexpected_shapes():
    from sdlc.benchmarks.runs import parse_run_id

    assert parse_run_id("no-slash") is None
    assert parse_run_id("bench/x") is None


# --- tokens -------------------------------------------------------------------


def test_run_tokens_none_when_no_record_carries_tokens():
    from sdlc.benchmarks.runs import build_runs

    records = [_record(cost=CostBag()), _record(stage="code", cost=CostBag())]
    (run,) = build_runs(records)
    assert run.tokens is None


def test_run_tokens_sums_input_and_output_over_records():
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(),
        _record(stage="code", cost=CostBag(usd=0.2, input_tokens=30, output_tokens=20)),
    ]
    (run,) = build_runs(records)
    assert run.tokens == 100 + 50 + 30 + 20


# --- T003 chaos (RED) --------------------------------------------------------
# Edge angles on the §1.6-1.8 rules and the R-4/R-5/R-9/R-10 decisions:
# unknown-commit still 012, mixed generations under one run id, empty-ish
# totals (a lost run with no stage record), sample-deviation semantics,
# low-n boundary at exactly 4 vs 5, per-(task_id, attempt) qa equality, and
# the full gate_passed table. Every symbol is imported function-local so
# RED is an ImportError per test while qa-happy's section keeps its own
# result.


def _speed(dt):
    return SpeedBag(wall_clock_s=1.0, started_at=dt, ended_at=dt)


def _code_attempt(task_id, attempt, outcome, **kw):
    return _record(
        stage="code",
        role="dev",
        task_id=task_id,
        attempt=attempt,
        outcome=outcome,
        **kw,
    )


def _graded_run(run_id, passed, total, **kw):
    """A minimal graded run: code + merge (code finished) + a scored oracle."""
    return [
        _record(run_id=run_id, stage="code", harness=HarnessKind.OPENCODE, **kw),
        _record(run_id=run_id, stage="merge", harness=HarnessKind.OPENCODE, **kw),
        _oracle_record(
            run_id=run_id,
            quality=QualityScore(
                score=passed / total,
                judge="oracle",
                components={"passed": float(passed), "total": float(total)},
            ),
            **kw,
        ),
    ]


# --- §1.6 generation ----------------------------------------------------------


def test_generation_pre012_when_records_have_no_commit():
    from sdlc.benchmarks.runs import build_runs

    (run,) = build_runs([_record(), _record(stage="code")])
    assert run.generation == "pre012"


def test_generation_012_with_commit_string():
    from sdlc.benchmarks.runs import build_runs

    (run,) = build_runs([_record(kroker_commit="deadbeef")])
    assert run.generation == "012"


def test_generation_012_with_unknown_commit():
    """Edge: the literal `unknown` is a 012 record (is_pre012 excludes it),
    so a run of only `unknown`-commit records is still generation 012."""
    from sdlc.benchmarks.runs import build_runs

    (run,) = build_runs([_record(kroker_commit="unknown")])
    assert run.generation == "012"
    assert run.commit == "unknown"


def test_generation_mixed_kinds_under_one_run_id_classify_012():
    """Contract §1.6: a run never has records of both kinds; if one does it
    is `012`. The contract also wants a note naming the run, but data-model
    §1.2 gives build_runs no note channel (it returns list[Run] only), so
    this test pins the classification alone."""
    from sdlc.benchmarks.runs import build_runs

    records = [
        _record(run_id="b1/c#opencode#a1", kroker_commit="deadbeef"),
        _record(run_id="b1/c#opencode#a1", stage="code", kroker_commit=None),
    ]
    (run,) = build_runs(records)
    assert run.generation == "012"


# --- §1.7 totals ---------------------------------------------------------------


def _totals_corpus():
    """One graded, one lost at plan, one lost at research, one
    grading_failed, one no_oracle, and one oracle-only run (lost with no
    stage record)."""
    graded = _graded_run("b1/c#opencode#a1", 4, 5)
    lost_at_plan = [
        _record(run_id="b1/c#opencode#a2", stage="research", harness=HarnessKind.OPENCODE),
        _record(run_id="b1/c#opencode#a2", stage="plan", harness=HarnessKind.OPENCODE),
    ]
    lost_at_research = [
        _record(run_id="b1/c#opencode#a6", stage="research", harness=HarnessKind.OPENCODE)
    ]
    grading_failed = [
        _record(run_id="b1/c#opencode#a3", stage="code", harness=HarnessKind.OPENCODE),
        _record(run_id="b1/c#opencode#a3", stage="merge", harness=HarnessKind.OPENCODE),
        _oracle_record(run_id="b1/c#opencode#a3", quality=QualityScore(score=None, judge="oracle")),
    ]
    no_oracle = [
        _record(run_id="b1/c#opencode#a4", stage="code", harness=HarnessKind.OPENCODE),
        _record(run_id="b1/c#opencode#a4", stage="analyze", harness=HarnessKind.OPENCODE),
    ]
    oracle_only = [_oracle_record(run_id="b1/c#opencode#a5")]
    return graded + lost_at_plan + lost_at_research + grading_failed + no_oracle + oracle_only


def test_totals_statuses_count_and_sum_to_started():
    from sdlc.benchmarks.runs import build_runs, totals

    t = totals(build_runs(_totals_corpus()))
    assert (t.started, t.graded, t.lost, t.grading_failed, t.no_oracle) == (6, 1, 3, 1, 1)
    assert t.started == t.graded + t.lost + t.grading_failed + t.no_oracle


def test_totals_lost_by_stage_sums_to_lost():
    from sdlc.benchmarks.runs import build_runs, totals

    t = totals(build_runs(_totals_corpus()))
    assert t.lost_by_stage == {"plan": 1, "none": 1, "research": 1}
    assert sum(t.lost_by_stage.values()) == t.lost


def test_totals_lost_run_without_stage_record_lands_under_none():
    """Edge: a run whose only record is oracle-scope — lost, but no stage
    ever recorded, so its key in lost_by_stage is `none` (§1.7)."""
    from sdlc.benchmarks.runs import build_runs, totals

    t = totals(build_runs([_oracle_record(run_id="b1/x#opencode#a")]))
    assert t.lost == 1
    assert t.lost_by_stage == {"none": 1}


def test_totals_counts_discarded_oracle_records_and_derived_statuses():
    from sdlc.benchmarks.runs import build_runs, totals

    runs = build_runs(_totals_corpus())
    t = totals(runs)
    # the oracle-only lost run discards its 1 oracle record; the graded and
    # grading_failed runs keep theirs
    assert t.discarded_oracle_records == 1
    assert t.derived_statuses == len(runs) == 6  # no run in the corpus has a cell record


# --- §1.8 group_runs ------------------------------------------------------------


def test_groups_key_on_case_harness_arm_generation_commit():
    from sdlc.benchmarks.runs import build_runs, group_runs

    runs = build_runs(
        _graded_run("b1/c#opencode#a1", 4, 5, kroker_commit="deadbeef")
        + _graded_run("b2/c#opencode#a1", 3, 5, kroker_commit="beefdead")
    )
    groups = group_runs(runs)
    assert len(groups) == 2  # commit splits, everything else equal
    assert {g.commit for g in groups} == {"deadbeef", "beefdead"}


def test_group_runs_are_in_start_order():
    from datetime import datetime

    from sdlc.benchmarks.runs import build_runs, group_runs

    records = _graded_run(
        "b1/c#opencode#a1", 4, 5, speed=_speed(datetime(2026, 7, 4, 10))
    ) + _graded_run("b2/c#opencode#a1", 3, 5, speed=_speed(datetime(2026, 7, 4, 9)))
    (group,) = group_runs(build_runs(records))
    assert [r.run_id for r in group.runs] == ["b2/c#opencode#a1", "b1/c#opencode#a1"]


def test_group_figures_cover_graded_runs_only():
    from sdlc.benchmarks.runs import build_runs, group_runs

    records = (
        _graded_run("b1/c#opencode#a1", 6, 6)
        + _graded_run("b2/c#opencode#a1", 3, 6)
        + [_record(run_id="b3/c#opencode#a1", stage="research", harness=HarnessKind.OPENCODE)]
    )
    (group,) = group_runs(build_runs(records))
    assert group.graded == 2 and group.lost == 1
    assert group.mean == 0.75
    assert (group.lo, group.hi) == (0.5, 1.0)


def test_group_sd_is_none_with_one_graded_run():
    from sdlc.benchmarks.runs import build_runs, group_runs

    (group,) = group_runs(build_runs(_graded_run("b1/c#opencode#a1", 4, 5)))
    assert group.graded == 1
    assert group.sd is None


def test_group_sd_is_sample_deviation_with_three_graded_runs():
    import statistics

    from sdlc.benchmarks.runs import build_runs, group_runs

    records = (
        _graded_run("b1/c#opencode#a1", 6, 6)
        + _graded_run("b2/c#opencode#a1", 3, 6)
        + _graded_run("b3/c#opencode#a1", 0, 6)
    )
    (group,) = group_runs(build_runs(records))
    credits = [r.partial_credit for r in group.runs]
    assert group.sd == statistics.stdev(credits) == 0.5  # n-1, not population


def test_group_all_pass_is_k_of_n():
    from sdlc.benchmarks.runs import build_runs, group_runs

    records = (
        _graded_run("b1/c#opencode#a1", 6, 6)
        + _graded_run("b2/c#opencode#a1", 3, 6)
        + _graded_run("b3/c#opencode#a1", 0, 6)
    )
    (group,) = group_runs(build_runs(records))
    assert group.all_pass == (1, 3)


def test_group_low_n_true_at_four_graded_and_false_at_five():
    """Edge: MIN_OBSERVATIONS is the boundary — 4 graded is low_n, 5 is not."""
    from sdlc.benchmarks.runs import build_runs, group_runs

    four = build_runs(sum((_graded_run(f"b{i}/c#opencode#a1", 4, 5) for i in range(1, 5)), []))
    (group,) = group_runs(four)
    assert group.graded == 4
    assert group.low_n is True

    five = build_runs(sum((_graded_run(f"b{i}/c#opencode#a1", 4, 5) for i in range(1, 6)), []))
    (group5,) = group_runs(five)
    assert group5.graded == 5
    assert group5.low_n is False


def test_runs_of_two_generations_never_share_a_group():
    from sdlc.benchmarks.runs import build_runs, group_runs

    records = (
        _graded_run("b1/c#opencode#a1", 4, 5)  # pre012 (no commit)
        + _graded_run("b2/c#opencode#a1", 3, 5, kroker_commit="deadbeef")  # 012
    )
    groups = group_runs(build_runs(records))
    assert len(groups) == 2
    assert {g.generation for g in groups} == {"pre012", "012"}


# --- R-5 task outcomes -----------------------------------------------------------


def _run_of(records):
    from sdlc.benchmarks.runs import build_runs

    (run,) = build_runs(records)
    return run


def test_task_outcome_first_attempt_passed():
    from datetime import datetime

    from sdlc.benchmarks.runs import build_runs

    run = build_runs(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.PASS, speed=_speed(datetime(2026, 7, 4, 10))),
        ]
    )[0]
    (task,) = run.tasks
    assert (task.task_id, task.attempts, task.first_passed, task.last_passed) == (
        "T1",
        1,
        True,
        True,
    )


def test_task_outcome_fail_then_pass_is_repaired():
    from datetime import datetime

    from sdlc.benchmarks.runs import build_runs

    run = build_runs(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.FAIL, speed=_speed(datetime(2026, 7, 4, 10))),
            _code_attempt(
                "T1", 1, BenchmarkOutcome.PASS, speed=_speed(datetime(2026, 7, 4, 10, 1))
            ),
        ]
    )[0]
    (task,) = run.tasks
    assert task.first_passed is False
    assert task.last_passed is True
    assert task.attempts == 2


def test_task_outcome_never_passes():
    run = _run_of(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.FAIL),
            _code_attempt("T1", 1, BenchmarkOutcome.FAIL),
        ]
    )
    (task,) = run.tasks
    assert task.first_passed is False
    assert task.last_passed is False


def test_task_attempts_without_numbers_ordered_by_started_at():
    """Edge: every attempt is None (pre-012 shape) — order falls to
    speed.started_at, so the earlier failure is the first attempt."""
    from datetime import datetime

    from sdlc.benchmarks.runs import build_runs

    run = build_runs(
        [
            _code_attempt(
                "T1", None, BenchmarkOutcome.PASS, speed=_speed(datetime(2026, 7, 4, 11))
            ),
            _code_attempt(
                "T1", None, BenchmarkOutcome.FAIL, speed=_speed(datetime(2026, 7, 4, 10))
            ),
        ]
    )[0]
    (task,) = run.tasks
    assert task.attempts == 2
    assert task.first_passed is False  # the 10:00 FAIL came first
    assert task.last_passed is True


def test_first_attempt_and_after_repair_counts_over_coded_tasks():
    run = _run_of(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.PASS),
            _code_attempt("T2", 0, BenchmarkOutcome.FAIL),
            _code_attempt("T2", 1, BenchmarkOutcome.PASS),
            _code_attempt("T3", 0, BenchmarkOutcome.FAIL),
        ]
    )
    assert run.first_attempt == (1, 3)
    assert run.after_repair == (2, 3)


def test_tasks_without_code_records_appear_in_no_task_outcome():
    """Edge: a qa record for a task that never has a code record (or a qa
    record with no task at all) produces no TaskOutcome."""
    from sdlc.benchmarks.runs import build_runs

    run = build_runs(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.PASS),
            _record(stage="qa", task_id="T9", outcome=BenchmarkOutcome.FAIL),
        ]
    )[0]
    assert [t.task_id for t in run.tasks] == ["T1"]


# --- R-5 qa_is_copy ---------------------------------------------------------------


def test_qa_is_copy_true_when_qa_outcomes_equal_code_per_task_attempt():
    run = _run_of(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.FAIL),
            _code_attempt("T2", 0, BenchmarkOutcome.PASS),
            _record(stage="qa", task_id="T1", attempt=0, outcome=BenchmarkOutcome.FAIL),
            _record(stage="qa", task_id="T2", attempt=0, outcome=BenchmarkOutcome.PASS),
        ]
    )
    assert run.qa_is_copy is True
    assert run.generation == "pre012"


def test_qa_is_copy_false_when_one_attempt_differs():
    run = _run_of(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.FAIL),
            _record(stage="qa", task_id="T1", attempt=0, outcome=BenchmarkOutcome.PASS),
        ]
    )
    assert run.qa_is_copy is False


def test_qa_is_copy_false_for_012_run_even_when_identical():
    run = _run_of(
        [
            _code_attempt("T1", 0, BenchmarkOutcome.PASS, kroker_commit="deadbeef"),
            _record(
                stage="qa",
                task_id="T1",
                attempt=0,
                outcome=BenchmarkOutcome.PASS,
                kroker_commit="deadbeef",
            ),
        ]
    )
    assert run.generation == "012"
    assert run.qa_is_copy is False


# --- R-9 gate_passed ----------------------------------------------------------------


def test_gate_passed_full_table():
    from sdlc.benchmarks.runs import gate_passed

    assert gate_passed("qa", BenchmarkOutcome.PASS) is True
    assert gate_passed("merge", BenchmarkOutcome.REVISED) is True  # merge revise approves
    assert gate_passed("plan", BenchmarkOutcome.REVISED) is False
    assert gate_passed("qa", BenchmarkOutcome.FAIL) is False
    assert gate_passed("qa", BenchmarkOutcome.ESCALATED) is False
    assert gate_passed("qa", BenchmarkOutcome.NOT_EVALUATED) is None


# --- R-10 composite_shown ------------------------------------------------------------


def test_composite_not_shown_for_one_arm():
    from sdlc.benchmarks.runs import build_runs, composite_shown

    decision = composite_shown(build_runs(_graded_run("b1/c#opencode#a1", 4, 5)))["c"]
    assert decision.shown is False
    assert decision.arms == 1
    assert decision.reason


def test_composite_not_shown_when_only_one_arm_has_a_graded_run():
    from sdlc.benchmarks.runs import build_runs, composite_shown

    records = _graded_run("b1/c#opencode#a1", 4, 5) + [
        _record(run_id="b2/c#opencode#a2", stage="research", harness=HarnessKind.OPENCODE)
    ]
    decision = composite_shown(build_runs(records))["c"]
    assert decision.shown is False


def test_composite_shown_for_two_arms_each_graded_same_generation():
    from sdlc.benchmarks.runs import build_runs, composite_shown

    records = _graded_run("b1/c#opencode#a1", 4, 5) + _graded_run("b2/c#opencode#a2", 3, 5)
    decision = composite_shown(build_runs(records))["c"]
    assert decision.shown is True
    assert decision.arms == 2


def test_composite_not_shown_when_arms_are_of_different_generations():
    from sdlc.benchmarks.runs import build_runs, composite_shown

    records = _graded_run("b1/c#opencode#a1", 4, 5) + _graded_run(
        "b2/c#opencode#a2", 3, 5, kroker_commit="deadbeef"
    )
    decision = composite_shown(build_runs(records))["c"]
    assert decision.shown is False


# --- constants and the shared sort key -------------------------------------------------


def test_min_observations_is_five():
    from sdlc.benchmarks.runs import MIN_OBSERVATIONS

    assert MIN_OBSERVATIONS == 5


def test_attempt_sort_key_is_attempt_or_zero_then_started_at():
    """`attempt or 0` — None reads as 0, so unnumbered attempts sort before
    numbered ones at equal start times (sc_rollup's existing key)."""
    from datetime import datetime

    from sdlc.benchmarks.runs import attempt_sort_key

    when = datetime(2026, 7, 4, 10)
    assert attempt_sort_key(_record(attempt=2, speed=_speed(when))) == (2, when)
    assert attempt_sort_key(_record(attempt=None, speed=_speed(when))) == (0, when)
