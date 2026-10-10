"""013 T007 (RED): the layered heatmap, `sdlc.benchmarks.heatmap`.

Contract section 3 (`.specify/specs/013-benchmark-scoring-output/
contracts/scoring-output.md`): rows and columns (3.1), the attrition layer
(3.2), the first-attempt layer (3.3), the wasted-tokens layer (3.4), oracle
marks (3.5), the no-double-count invariant (3.6). Names are in
`data-model.md` section 3. The `CANONICAL_STAGES` pin (contract 11.6)
copies the 18 base names and passes on first run. Every test imports its
`sdlc.benchmarks.heatmap` symbol function-local (the repo's RED
convention) so each missing name fails its own test instead of breaking
collection. The record factories copy `tests/test_benchmark_grid.py`.
"""

from datetime import datetime

from pytest import approx

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CellStatus,
    CostBag,
    QualityScore,
    SpeedBag,
)

_T0 = datetime(2026, 7, 4, 10, 0)
_T1 = datetime(2026, 7, 4, 10, 30)
_T2 = datetime(2026, 7, 4, 11, 0)


def _record(**kw):
    base = dict(
        run_id="b1/c1#opencode#a1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="architecture",
        role="architect",
        model="anthropic:claude-sonnet-4-6",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=_T0,
            ended_at=_T0.replace(minute=12),
        ),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


def _stage(run_id, stage, start, outcome=BenchmarkOutcome.PASS, wall=12.0, **kw):
    """A run-level (no task) stage record."""
    return _record(
        run_id=run_id,
        stage=stage,
        role=stage,
        scope=BenchmarkScope.STAGE,
        outcome=outcome,
        speed=SpeedBag(wall_clock_s=wall, started_at=start, ended_at=start),
        **kw,
    )


def _task(run_id, stage, task_id, attempt, start, outcome, wall=10.0, **kw):
    """A task-attempt record (code attempts, per-task qa)."""
    return _record(
        run_id=run_id,
        stage=stage,
        role=stage,
        scope=BenchmarkScope.TASK_ATTEMPT,
        task_id=task_id,
        attempt=attempt,
        outcome=outcome,
        speed=SpeedBag(wall_clock_s=wall, started_at=start, ended_at=start),
        **kw,
    )


def _oracle(run_id, passed, total, start=_T2, **kw):
    """An oracle-scope record; `passed`/`total` ride quality.components."""
    kw.setdefault("scope", BenchmarkScope.ORACLE)
    return _record(
        run_id=run_id,
        stage="oracle",
        role="oracle",
        model="openai/gpt-5.2",
        quality=QualityScore(
            score=passed / total, judge="oracle", components={"passed": passed, "total": total}
        ),
        speed=SpeedBag(wall_clock_s=1.0, started_at=start, ended_at=start),
        **kw,
    )


def _cell(
    run_id, start, last_stage, *, code_finished=True, pipeline_finished=True, grading="graded"
):
    """A 012 cell record carrying the recorded status."""
    return _record(
        run_id=run_id,
        stage="cell",
        role="cell",
        scope=BenchmarkScope.CELL,
        model="deterministic",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=start, ended_at=start),
        cell=CellStatus(
            pipeline_finished=pipeline_finished,
            code_finished=code_finished,
            completed=pipeline_finished and code_finished,
            last_stage=last_stage,
            grading=grading,
        ),
    )


def _graded(run_id, start, passed=3, total=4, commit=None, arm="a1"):
    """A minimal derived graded run: analyze (code finished) + oracle."""
    extra = {}
    if commit is not None:
        extra["kroker_commit"] = commit
    if arm is not None:
        extra["arm"] = arm
    return [
        _stage(run_id, "analyze", start, wall=12.0, **extra),
        _oracle(run_id, passed, total, start, **extra),
    ]


def _ids(commit="x", arm="a1"):
    """Extra record fields pinning the run to one generation and arm."""
    extra = {}
    if commit is not None:
        extra["kroker_commit"] = commit
    if arm is not None:
        extra["arm"] = arm
    return extra


def _lost(run_id, start, last_stage, stage_records):
    """A lost run: a cell record says code did not finish (contract 1.2)."""
    return stage_records + [
        _cell(
            run_id,
            start,
            last_stage,
            code_finished=False,
            pipeline_finished=False,
            grading="not_graded",
        )
    ]


def _row_a():
    """One 012 row of case c1: lost at research, lost at clarify, lost at
    code, two graded runs -- the contract 3.2 walkthrough."""
    x = _ids()
    return [
        *_lost(
            "b1/c1#opencode#a1",
            _T0,
            "research",
            [_stage("b1/c1#opencode#a1", "research", _T0, BenchmarkOutcome.FAIL, 1.0, **x)],
        ),
        *_lost(
            "b2/c1#opencode#a1",
            _T1,
            "clarify",
            [_stage("b2/c1#opencode#a1", "clarify", _T1, BenchmarkOutcome.FAIL, 1.0, **x)],
        ),
        *_lost(
            "b3/c1#opencode#a1",
            _T1,
            "code",
            [_task("b3/c1#opencode#a1", "code", "t1", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x)],
        ),
        *_graded("b4/c1#opencode#a1", _T1, commit="x"),
        *_graded("b5/c1#opencode#a1", _T2, commit="x"),
    ]


def _one(hm, layer, stage):
    """The single cell of one layer and stage on a one-row heatmap."""
    got = [c for c in hm.cells if c.layer == layer and c.stage == stage]
    assert len(got) == 1, f"expected one {layer}/{stage} cell, got {len(got)}"
    return got[0]


# --- 3.1 rows and columns --------------------------------------------------------


def test_layers_and_oracle_column_constants():
    from sdlc.benchmarks.heatmap import LAYERS, ORACLE_COLUMN

    assert LAYERS == ("attrition", "first_attempt", "wasted_tokens", "oracle")
    assert ORACLE_COLUMN == "oracle"


def test_canonical_stages_pinned_byte_for_byte():
    from sdlc.benchmarks.heatmap import CANONICAL_STAGES

    assert CANONICAL_STAGES == [
        "intake",
        "constitution",
        "context",
        "requirements",
        "research",
        "clarify",
        "architecture",
        "planning",
        "code",
        "review",
        "adversary",
        "handoff",
        "deep_review",
        "analyze",
        "qa",
        "quality_gate",
        "deploy",
        "retro",
    ]


def test_columns_are_only_the_stages_some_layer_fills():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_row_a()))

    # present: research, clarify, code, analyze (records + attrition) and
    # oracle (marks); architecture and plan were written by no run -> blank
    # in every layer -> no column
    assert hm.stages == ("research", "clarify", "code", "analyze", "oracle")
    assert "plan" not in hm.stages
    assert "tool_approval" not in hm.stages


def test_one_row_per_case_harness_arm_generation_commits_merge():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    records = (
        _graded("b1/c1#opencode#a1", _T0, commit="aaa")
        + _graded("b2/c1#opencode#a1", _T1, commit="bbb")  # other commit, same row
        + _graded("b3/c2#opencode#a1", _T0, commit="aaa")  # other case, other row
    )
    hm = build_layers(build_runs(records))

    assert len(hm.rows) == 2
    by_case = {r.case_id: r for r in hm.rows}
    assert by_case["c1"].started == 2  # both commits, one (case, harness, arm, generation)
    assert by_case["c1"].generation == "012"
    assert by_case["c2"].started == 1


def test_extra_stages_trail_by_name_then_the_oracle_column():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = _graded(run_id, _T0, commit="x") + [
        _stage(run_id, "zed", _T1, wall=1.0, **_ids()),
        _stage(run_id, "alpha", _T1, wall=1.0, **_ids()),
    ]
    hm = build_layers(build_runs(records))

    assert hm.stages == ("analyze", "alpha", "zed", "oracle")


def test_language_by_case_sets_the_row_language():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_graded("b1/c1#opencode#a1", _T0, commit="x")), {"c1": "python"})

    assert len(hm.rows) == 1
    assert hm.rows[0].language == "python"


# --- 3.2 attrition ---------------------------------------------------------------


def test_attrition_positions_reached_and_the_row_header():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_row_a()))
    assert len(hm.rows) == 1
    row = hm.rows[0]

    # lost at research 1/5; lost at clarify 1/4 (the research run never got
    # there); lost inside the task loop 1/3; no lost run at analyze 0/2
    research = _one(hm, "attrition", "research")
    assert (research.num, research.den, research.observations) == (1.0, 5.0, 5)
    assert research.value == approx(0.2)

    clarify = _one(hm, "attrition", "clarify")
    assert (clarify.num, clarify.den, clarify.observations) == (1.0, 4.0, 4)
    assert clarify.value == approx(0.25)

    code = _one(hm, "attrition", "code")
    assert (code.num, code.den, code.observations) == (1.0, 3.0, 3)
    assert code.value == approx(1 / 3)

    analyze = _one(hm, "attrition", "analyze")
    assert (analyze.num, analyze.den, analyze.observations) == (0.0, 2.0, 2)
    assert analyze.value == approx(0.0)

    assert row.started == 5
    assert row.lost_before_code == 2  # research and clarify; the code one sits at code
    assert row.no_stage_recorded == 0
    assert row.lost_tokens == 900  # three lost runs x (stage record + cell record) x 150


def test_attrition_code_cell_non_blank_when_a_lost_run_is_positioned_there():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    # lost inside the task loop at handoff, but it never wrote a code record
    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = _lost(
        run_id,
        _T1,
        "handoff",
        [
            _stage(run_id, "research", _T0, wall=1.0, **x),
            _stage(run_id, "handoff", _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        ],
    )
    hm = build_layers(build_runs(records))

    # the exception of 3.2: code is non-blank although no run recorded there
    assert hm.stages == ("research", "code", "handoff")  # no oracle: nothing is graded
    code = _one(hm, "attrition", "code")
    assert (code.num, code.den, code.observations) == (1.0, 1.0, 1)

    research = _one(hm, "attrition", "research")
    assert (research.num, research.den, research.observations) == (0.0, 1.0, 1)

    handoff = _one(hm, "first_attempt", "handoff")  # the column lives through this cell
    assert (handoff.num, handoff.den) == (1.0, 1.0)


def test_a_lost_run_with_no_stage_record_counts_only_in_the_header():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    records = _graded("b1/c1#opencode#a1", _T0, commit="x") + [
        _oracle("b2/c1#opencode#a1", 4, 4, _T1, kroker_commit="x", arm="a1")
    ]
    hm = build_layers(build_runs(records))
    assert len(hm.rows) == 1
    row = hm.rows[0]

    assert row.started == 2
    assert row.no_stage_recorded == 1
    assert row.lost_before_code == 1  # the no-stage-record run is lost before code
    # the bare run reached nothing: analyze is the graded sibling only
    analyze = _one(hm, "attrition", "analyze")
    assert (analyze.num, analyze.den) == (0.0, 1.0)


# --- 3.3 first-attempt failure ---------------------------------------------------


def test_first_attempt_task_units_first_by_attempt_not_evaluated_left_out():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    a = "b1/c1#opencode#a1"
    b = "b2/c1#opencode#a1"
    c = "b3/c1#opencode#a1"
    records = [
        _task(a, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL, 1.0),
        _task(a, "code", "t1", 2, _T1, BenchmarkOutcome.PASS, 1.0),  # repair: still a failed unit
        _task(b, "code", "t1", 1, _T1, BenchmarkOutcome.PASS, 1.0),
        _task(b, "code", "t2", 1, _T1, BenchmarkOutcome.FAIL, 1.0),
        _task(c, "code", "t1", 1, _T1, BenchmarkOutcome.NOT_EVALUATED, 1.0),  # left out
        *_graded(a, _T2, commit="x", arm=None),
        *_graded(b, _T2, commit="x", arm=None),
        *_graded(c, _T2, commit="x", arm=None),
    ]
    hm = build_layers(build_runs(records))

    cell = _one(hm, "first_attempt", "code")
    assert (cell.num, cell.den, cell.observations) == (2.0, 3.0, 3)
    assert cell.value == approx(2 / 3)


def test_first_attempt_run_stage_units_first_by_start_not_evaluated_left_out():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    a = "b1/c1#opencode#a1"
    b = "b2/c1#opencode#a1"
    records = [
        _stage(a, "research", _T0, BenchmarkOutcome.FAIL, 1.0),
        _stage(a, "research", _T1, BenchmarkOutcome.PASS, 1.0),  # later pass: unit stays failed
        _stage(b, "research", _T1, BenchmarkOutcome.NOT_EVALUATED, 1.0),  # left out
        *_graded(a, _T2, commit="x", arm=None),
        *_graded(b, _T2, commit="x", arm=None),
    ]
    hm = build_layers(build_runs(records))

    cell = _one(hm, "first_attempt", "research")
    assert (cell.num, cell.den, cell.observations) == (1.0, 1.0, 1)


def test_first_attempt_qa_cell_of_an_all_copy_row_is_copy():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b0/c1#opencode#m"  # pre-012: no record carries kroker_commit
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "qa", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=1.0),  # copies code
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 4, 4),
    ]
    hm = build_layers(build_runs(records))

    assert _one(hm, "first_attempt", "qa").state == "copy"
    code = _one(hm, "first_attempt", "code")  # the copy state is qa's alone
    assert code.state != "copy"
    assert (code.num, code.den) == (0.0, 1.0)


# --- 3.4 wasted tokens -----------------------------------------------------------


def _waste_run():
    """A graded-by-cell run: t1 repaired, t2 never passed, analyze, oracle."""
    run_id = "b1/c1#opencode#a1"
    x = _ids()
    return [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL, 1.0, **x),
        _task(run_id, "code", "t1", 2, _T1, BenchmarkOutcome.PASS, 1.0, **x),
        _task(run_id, "code", "t2", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        _stage(run_id, "analyze", _T2, wall=1.0, **x),
        _oracle(run_id, 3, 4, _T2, **x),
        _cell(run_id, _T2, "analyze"),
    ]


def test_wasted_tokens_superseded_attempt_and_task_that_never_passed():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    hm = build_layers(build_runs(_waste_run()))

    # t1 attempt 1 (a later code attempt exists) and all of t2 (its last
    # code attempt did not pass) are wasted; t1 attempt 2 is not
    cell = _one(hm, "wasted_tokens", "code")
    assert (cell.num, cell.den, cell.observations, cell.not_measured) == (300.0, 450.0, 3, 0)

    analyze = _one(hm, "wasted_tokens", "analyze")
    assert (analyze.num, analyze.den, analyze.observations) == (0.0, 150.0, 1)

    # the cell-scope and oracle records (150 tokens each) are in no cell
    assert _one(hm, "wasted_tokens", "code").den == 450.0


def test_wasted_tokens_a_lost_run_wastes_every_measured_record():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = _lost(
        run_id,
        _T2,
        "code",
        [
            _stage(run_id, "research", _T0, wall=1.0, **x),  # no task: only the lost rule hits it
            _task(run_id, "code", "t1", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        ],
    )
    hm = build_layers(build_runs(records))

    research = _one(hm, "wasted_tokens", "research")
    assert (research.num, research.den, research.observations) == (150.0, 150.0, 1)

    code = _one(hm, "wasted_tokens", "code")
    assert (code.num, code.den, code.observations) == (150.0, 150.0, 1)  # cell record stays out


def test_wasted_tokens_unmeasured_records_count_as_not_measured():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, 1.0, **x),
        _task(
            run_id,
            "code",
            "t1",
            2,
            _T1,
            BenchmarkOutcome.PASS,
            1.0,
            cost=CostBag(),  # no tokens: present at the stage, not measured
            **x,
        ),
        _stage(run_id, "analyze", _T2, wall=1.0, **x),
        _oracle(run_id, 3, 4, _T2, **x),
    ]
    hm = build_layers(build_runs(records))

    cell = _one(hm, "wasted_tokens", "code")
    assert (cell.num, cell.den, cell.observations, cell.not_measured) == (150.0, 150.0, 1, 1)


# --- 3.5 oracle marks ------------------------------------------------------------


def test_oracle_marks_one_per_graded_run_in_start_order_other_layers_blank():
    from sdlc.benchmarks.heatmap import LAYERS, ORACLE_COLUMN, OracleMark, build_layers
    from sdlc.benchmarks.runs import build_runs

    x = _ids()
    records = [
        *_graded("b1/c1#opencode#a1", _T0, passed=3, total=4, commit="x"),
        *[_task("b2/c1#opencode#a1", "code", "t1", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x)],
        *[_oracle("b2/c1#opencode#a1", 4, 4, _T1, **x)],  # lost run: no mark
        *_graded("b3/c1#opencode#a1", _T2, passed=4, total=4, commit="x"),
    ]
    hm = build_layers(build_runs(records))

    marks = [m for m in hm.oracle_marks if isinstance(m, OracleMark)]
    assert [m.run_id for m in marks] == ["b1/c1#opencode#a1", "b3/c1#opencode#a1"]
    assert [(m.passed, m.total) for m in marks] == [(3, 4), (4, 4)]

    for layer in LAYERS[:3]:
        assert _one(hm, layer, ORACLE_COLUMN).state == "blank"


# --- 3.6 one record, one cell ----------------------------------------------------


def test_each_layer_counts_its_own_base_and_no_number_is_shared():
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    # one run, three code records, two tasks: attrition counts runs (1),
    # first_attempt counts task-units (2), wasted_tokens counts records'
    # tokens (3 records, 450) -- each record and unit counted exactly once
    hm = build_layers(build_runs(_waste_run()))

    attrition = _one(hm, "attrition", "code")
    assert (attrition.num, attrition.den, attrition.observations) == (0.0, 1.0, 1)

    first = _one(hm, "first_attempt", "code")
    assert (first.num, first.den, first.observations) == (2.0, 2.0, 2)
    assert first.value == approx(1.0)

    wasted = _one(hm, "wasted_tokens", "code")
    assert (wasted.num, wasted.den, wasted.observations) == (300.0, 450.0, 3)


# --- chaos: no runs --------------------------------------------------------------


def test_no_runs_give_an_empty_layered_heatmap():
    from sdlc.benchmarks.heatmap import LayeredHeatmap, build_layers

    hm = build_layers([])
    assert isinstance(hm, LayeredHeatmap)
    assert hm.rows == ()
    assert hm.stages == ()
    assert len(hm.cells) == 0
    assert len(hm.oracle_marks) == 0


# --- T007 gap closes: the six contract cases the first pass did not pin ------


def test_blank_in_every_layer_for_a_stage_no_run_of_the_row_wrote():
    """Contract 3.2: a stage at which no run of the row wrote a record has
    no value (amendment A3) -- the column exists because the OTHER row
    wrote research, but the research-disabled row's research cell is blank
    in each of the three counting layers."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    records = [
        _stage("b1/c1#opencode#a1", "research", _T0, wall=1.0, **_ids()),
        *_graded("b1/c1#opencode#a1", _T1, commit="x"),
        # case c2 runs with research disabled: its first record is analyze
        *_graded("b1/c2#opencode#a1", _T1, commit="x"),
    ]
    hm = build_layers(build_runs(records))

    assert len(hm.rows) == 2
    assert "research" in hm.stages  # the writing row filled the column
    keys = {r.case_id: r.key for r in hm.rows}
    for layer in ("attrition", "first_attempt", "wasted_tokens"):
        got = [c for c in hm.cells if c.layer == layer and c.stage == "research"]
        assert len(got) == 2, f"{layer}: expected one research cell per row"
        by_row = {c.row: c for c in got}
        assert by_row[keys["c2"]].state == "blank", layer
        assert by_row[keys["c1"]].state != "blank", layer


def test_first_attempt_merge_revise_is_not_a_failure():
    """Contract 3.3 + R-9: merge `revise` is a pass, so the first-attempt
    layer counts no failure for a revise-only merge record."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "merge", _T1, BenchmarkOutcome.REVISED, 1.0, **_ids()),
        *_graded(run_id, _T2, commit="x"),
    ]
    hm = build_layers(build_runs(records))

    cell = _one(hm, "first_attempt", "merge")
    assert (cell.num, cell.den) == (0.0, 1.0)


def test_wasted_tokens_qa_and_review_records_of_superseded_and_never_passed_tasks():
    """Contract 3.4: a task record with an attempt is wasted when a later
    code attempt of the task exists (t1: repaired) or when the task's last
    code attempt did not pass (t2: never passed) -- so both tasks' qa and
    review records land in their stage cells' numerators."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = [
        # t1: repaired -- the later code attempt makes attempt-1 qa/review wasted
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL, 1.0, **x),
        _task(run_id, "qa", "t1", 1, _T0, BenchmarkOutcome.PASS, 1.0, **x),
        _task(run_id, "review", "t1", 1, _T0, BenchmarkOutcome.PASS, 1.0, **x),
        _task(run_id, "code", "t1", 2, _T1, BenchmarkOutcome.PASS, 1.0, **x),
        # t2: its last code attempt never passed -- its qa/review are wasted
        _task(run_id, "code", "t2", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        _task(run_id, "qa", "t2", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        _task(run_id, "review", "t2", 1, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        _stage(run_id, "analyze", _T2, wall=1.0, **x),
        _oracle(run_id, 3, 4, _T2, **x),
    ]
    hm = build_layers(build_runs(records))

    # every record carries 150 tokens: two qa records, two review records
    qa = _one(hm, "wasted_tokens", "qa")
    assert (qa.num, qa.den, qa.observations) == (300.0, 300.0, 2)
    review = _one(hm, "wasted_tokens", "review")
    assert (review.num, review.den, review.observations) == (300.0, 300.0, 2)


def test_wasted_tokens_handoff_without_attempt_wasted_only_when_task_never_passed():
    """Contract 3.4: a task record with no attempt number (handoff) is
    wasted only by the lost rule or the never-passed rule -- the task that
    passed first try keeps its handoff tokens, the never-passed task's
    handoff tokens are wasted."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    a, b = "b1/c1#opencode#a1", "b2/c1#opencode#a1"
    x = _ids()
    records = [
        # task passed first try: its handoff record is not wasted
        _task(a, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, 1.0, **x),
        _task(a, "handoff", "t1", None, _T1, BenchmarkOutcome.PASS, 1.0, **x),
        *_graded(a, _T2, commit="x"),
        # the task's last code attempt did not pass: its handoff is wasted
        _task(b, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL, 1.0, **x),
        _task(b, "handoff", "t1", None, _T1, BenchmarkOutcome.FAIL, 1.0, **x),
        *_graded(b, _T2, commit="x"),
    ]
    hm = build_layers(build_runs(records))

    cell = _one(hm, "wasted_tokens", "handoff")
    assert (cell.num, cell.den, cell.observations) == (150.0, 300.0, 2)


def test_wasted_tokens_oracle_task_records_are_in_no_cell():
    """Contract 3.4: cell-scope, oracle and oracle-task records are in no
    cell -- an oracle-task record's tokens appear in no wasted_tokens den,
    and the oracle column of the three counting layers stays blank."""
    from sdlc.benchmarks.heatmap import LAYERS, build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, 1.0, **x),
        _stage(run_id, "analyze", _T2, wall=1.0, **x),
        _oracle(run_id, 4, 4, _T2, **x),
        _oracle(run_id, 1, 1, _T2, scope=BenchmarkScope.ORACLE_TASK, task_id="t1", **x),
    ]
    hm = build_layers(build_runs(records))

    # only the code and analyze records' tokens (2 x 150) reach any den
    wasted = [c for c in hm.cells if c.layer == "wasted_tokens"]
    assert sum(c.den for c in wasted) == 300.0
    for layer in LAYERS[:3]:
        assert _one(hm, layer, "oracle").state == "blank"


def test_us3_scenario_one_failed_then_repaired_attempt():
    """Spec US3 scenario 1 as one test (contract 3.6): one task that fails
    its first attempt and passes its second appears as one failed first
    attempt, as the first attempt's tokens in the wasted layer, and
    nowhere else."""
    from sdlc.benchmarks.heatmap import build_layers
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    x = _ids()
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL, 1.0, **x),  # 150 tokens
        _task(run_id, "code", "t1", 2, _T1, BenchmarkOutcome.PASS, 1.0, **x),  # 150 tokens
        _stage(run_id, "analyze", _T2, wall=1.0, **x),
        _oracle(run_id, 3, 4, _T2, **x),
    ]
    hm = build_layers(build_runs(records))

    first = _one(hm, "first_attempt", "code")
    assert (first.num, first.den) == (1.0, 1.0)

    wasted = _one(hm, "wasted_tokens", "code")
    assert (wasted.num, wasted.den) == (150.0, 300.0)  # attempt 1 only

    attrition = _one(hm, "attrition", "code")
    assert (attrition.num, attrition.den, attrition.observations) == (0.0, 1.0, 1)

    # and the failure appears in no other cell of any layer
    hot = [c for c in hm.cells if c.num > 0 and c is not first and c is not wasted]
    assert hot == []
    assert len(hm.oracle_marks) == 1
