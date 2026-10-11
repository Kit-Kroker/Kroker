"""015 T007 (post-rebase split): the run model reads the axis.

Split out of test_benchmark_runs.py when the 015-erosion-verbosity
rebase onto the 015-corpus-acceptance main pushed the combined file
past the 1000-line ceiling; the seam is the axis-reader block.
Helpers copied verbatim from the parent file.
"""

"""013 T003 (RED): the run model, `sdlc.benchmarks.runs`.

Names: .specify/specs/013-benchmark-scoring-output/data-model.md §1; the
status table and arm order are research.md R-2 and R-3; the cell id is
formed exactly as ``B/workflow.py:308`` does. Every test imports its
`sdlc.benchmarks.runs` symbol function-local (the repo's RED convention)
so each missing name fails its own test instead of breaking collection.
"""

from datetime import datetime

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)


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


# --- 015 T007: the run model reads the axis (US2, research R-6) ---


def _axis_bag(erosion=0.42, verbosity=0.18, **kw):
    from sdlc.benchmarks.models import AxisBag

    base = dict(
        erosion=erosion,
        verbosity=verbosity,
        functions_total=9,
        functions_over=2,
        mass_total=90.0,
        mass_over=37.8,
        flagged_lines=4,
        loc=22,
        files=3,
        head="f00dcafe",
        ruleset_version="1",
        tools={"radon": "6.0.1", "ast-grep": "0.50.0"},
    )
    base.update(kw)
    return AxisBag(**base)


def _axis_record(**kw):
    base = dict(
        stage="axis",
        role="axis",
        scope=BenchmarkScope.AXIS,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="axis"),
        outcome=BenchmarkOutcome.NOT_EVALUATED,
    )
    base.update(kw)
    return _record(**base)


def _graded_cell_records(run_id="b1/case#opencode#a1"):
    """A finished graded cell: a code record, the cell record, an oracle."""
    cell = _record(
        run_id=run_id,
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
    return [_record(run_id=run_id, stage="code"), cell, _oracle_record(run_id=run_id)]


def test_run_takes_its_axis_from_the_last_axis_record():
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/case#opencode#a1"
    records = _graded_cell_records(run_id) + [
        _axis_record(run_id=run_id, axis=_axis_bag(erosion=0.42, verbosity=0.18)),
        _axis_record(run_id=run_id, axis=_axis_bag(erosion=0.9, verbosity=0.5)),
    ]
    (run,) = build_runs(records)
    assert run.axis is not None
    assert run.axis.erosion == 0.9  # the last one wins
    assert run.axis.verbosity == 0.5


def test_run_without_axis_record_reads_none():
    from sdlc.benchmarks.runs import build_runs

    (run,) = build_runs(_graded_cell_records())
    assert run.axis is None


def test_group_means_are_over_measured_runs_of_one_version():
    from sdlc.benchmarks.runs import build_runs, group_runs

    runs = []
    for i, (e, v) in enumerate([(0.4, 0.1), (0.6, 0.3), (0.8, 0.2)]):
        run_id = f"b{i}/case#opencode#a1"
        records = _graded_cell_records(run_id)
        records.append(_axis_record(run_id=run_id, axis=_axis_bag(erosion=e, verbosity=v)))
        runs.extend(records)
    (group,) = group_runs(build_runs(runs))
    assert group.axis_n == 3
    assert group.mean_erosion == pytest.approx((0.4 + 0.6 + 0.8) / 3)
    assert group.mean_verbosity == pytest.approx((0.1 + 0.3 + 0.2) / 3)
    assert group.axis_versions == ("1",)


def test_group_with_mixed_ruleset_versions_withholds_the_means():
    from sdlc.benchmarks.runs import build_runs, group_runs

    runs = []
    for i, version in enumerate(["1", "2"]):
        run_id = f"b{i}/case#opencode#a1"
        records = _graded_cell_records(run_id)
        records.append(_axis_record(run_id=run_id, axis=_axis_bag(ruleset_version=version)))
        runs.extend(records)
    (group,) = group_runs(build_runs(runs))
    assert group.axis_n == 2
    assert group.mean_erosion is None  # never averaged across versions (FR-010)
    assert group.mean_verbosity is None
    assert group.axis_versions == ("1", "2")


def test_group_reason_bag_enters_no_mean_but_counts_not_measured():
    from sdlc.benchmarks.runs import build_runs, group_runs, totals

    runs = []
    reason_run = "b0/case#opencode#a1"
    records = _graded_cell_records(reason_run)
    records.append(
        _axis_record(
            run_id=reason_run,
            axis=_axis_bag(
                erosion=None, verbosity=None, reason="no functions", head=None, tools={}
            ),
        )
    )
    runs.extend(records)
    measured_run = "b1/case#opencode#a1"
    records2 = _graded_cell_records(measured_run)
    records2.append(_axis_record(run_id=measured_run, axis=_axis_bag()))
    runs.extend(records2)
    (group,) = group_runs(build_runs(runs))
    assert group.axis_n == 1  # only the run with figures
    assert group.mean_erosion == 0.42
    t = totals(build_runs(runs))
    assert t.axis_measured == 1
    assert t.axis_not_measured == 1


def test_totals_count_absent_axis_as_not_measured():
    from sdlc.benchmarks.runs import build_runs, totals

    runs = _graded_cell_records("b0/case#opencode#a1") + _graded_cell_records("b1/case#opencode#a1")
    t = totals(build_runs(runs))
    assert t.axis_measured == 0
    assert t.axis_not_measured == 2  # every stored run, forever (R-10)
