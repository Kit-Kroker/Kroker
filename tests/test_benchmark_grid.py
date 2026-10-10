"""013 T006 (RED): the run-by-run grid, `sdlc.benchmarks.grid`.

Contract section 2 (`.specify/specs/013-benchmark-scoring-output/
contracts/scoring-output.md`): group and row order, group header text,
row figures, every stage-cell mark, the markdown shape (header cells,
ASCII, no `---`), trailing columns for stages outside `CELL_STAGE_ORDER`,
and the JSON carrying the same figures and no raw records. Names are in
`data-model.md` section 5. Every test imports its
`sdlc.benchmarks.grid` symbol function-local (the repo's RED convention)
so each missing name fails its own test instead of breaking collection.
"""

from datetime import datetime

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
    return _record(
        run_id=run_id,
        stage="oracle",
        role="oracle",
        scope=BenchmarkScope.ORACLE,
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


def _header(md):
    for line in md.splitlines():
        if line.startswith("| run |"):
            return line
    raise AssertionError("no table header in grid markdown")


def _row_cells(md, run_id):
    for line in md.splitlines():
        if line.startswith(f"| {run_id} |"):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    raise AssertionError(f"no row for {run_id} in grid markdown")


def _cells_by_stage(md, run_id):
    header = [c.strip() for c in _header(md).strip("|").split("|")]
    return dict(zip(header, _row_cells(md, run_id), strict=True))


# --- 2.1 group order and row order -------------------------------------------


def test_two_commits_under_one_arm_give_two_groups_each_with_its_own_header():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    records = (
        _graded("b2/c1#opencode#a1", _T1, commit="aaa")  # group aaa, later run, listed first
        + _graded("b1/c1#opencode#a1", _T0, commit="aaa")  # group aaa, earlier run
        + _graded("b3/c1#opencode#a1", _T2, commit="bbb")  # group bbb
    )
    grid = build_grid(build_runs(records))

    assert len(grid.groups) == 2
    assert [g.commit for g in grid.groups] == ["aaa", "bbb"]  # by first run start
    assert [r.run.started_at for r in grid.groups[0].rows] == [_T0, _T1]  # rows by start
    assert len(grid.groups[1].rows) == 1

    assert render_grid_markdown(grid).count("### ") == 2  # each group has its own header


def test_groups_order_case_arm_generation_012_first_then_first_run_start():
    from sdlc.benchmarks.grid import build_grid
    from sdlc.benchmarks.runs import build_runs

    pre = _graded("b0/c1#opencode#a1", datetime(2026, 7, 1), arm=None)  # pre-012, starts first
    gen012 = _graded("b1/c1#opencode#a1", datetime(2026, 7, 4), commit="x")  # 012, starts later
    other = _graded("b1/c2#opencode#a1", datetime(2026, 7, 2), commit="y")  # other case, middle
    grid = build_grid(build_runs(pre + gen012 + other))

    assert [(g.case_id, g.generation) for g in grid.groups] == [
        ("c1", "012"),  # generation 012 before pre012 despite the later start
        ("c1", "pre012"),
        ("c2", "012"),
    ]


# --- 2.2 group header text -----------------------------------------------------


def test_header_commit_variants_recorded_unknown_and_not_recorded():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    with_id = build_grid(build_runs(_graded("b1/c1#opencode#a1", _T0, commit="b3344416")))
    unknown = build_grid(build_runs(_graded("b1/c1#opencode#a1", _T0, commit="unknown")))
    none_c = build_grid(build_runs(_graded("b0/c1#opencode#a1", _T0, arm="a1")))

    md = render_grid_markdown(with_id)
    assert "### c1 / opencode / a1 / commit b3344416\n" in md
    assert md.splitlines()[0] == "### c1 / opencode / a1 / commit b3344416"

    assert "### c1 / opencode / a1 / commit unknown\n" in render_grid_markdown(unknown)
    # commit not recorded only ever happens on a pre-012 group
    assert "### c1 / opencode / a1 / commit not recorded untrusted (pre-012)\n" in (
        render_grid_markdown(none_c)
    )


def test_pre012_group_is_marked_untrusted_and_recovered_arm_is_marked():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    pre = build_grid(build_runs(_graded("b0/c1#opencode#a1", _T0, arm="a1")))
    rec = build_grid(build_runs(_graded("b1/c1#opencode#a1", _T0, commit="x", arm=None)))

    # pre-012: no commit recorded, untrusted marker; arm comes from the run id
    assert render_grid_markdown(pre).splitlines()[0] == (
        "### c1 / opencode / a1 / commit not recorded untrusted (pre-012)"
    )
    # 012 with the arm recovered from the run id (no record carried `arm`)
    assert render_grid_markdown(rec).splitlines()[0] == (
        "### c1 / opencode / a1 / commit x arm recovered"
    )


def test_figures_line_under_low_n_carries_the_suffix_and_the_grey_class():
    from sdlc.benchmarks.grid import build_grid, render_grid_html, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    records = _graded("b1/c1#opencode#a1", _T0, passed=4, total=4, commit="x") + _graded(
        "b2/c1#opencode#a1", _T1, passed=2, total=4, commit="x"
    )
    grid = build_grid(build_runs(records))
    md = render_grid_markdown(grid)

    assert (
        "started 2, graded 2, lost 0, mean 0.750 (low n), sd 0.354 (low n), "
        "0.500 to 1.000 (low n), all-pass 1/2 (low n)" in md
    )
    assert 'class="low_n"' in render_grid_html(grid)


def test_figures_line_at_five_graded_runs_has_no_low_n_marks():
    from sdlc.benchmarks.grid import build_grid, render_grid_html, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    records = []
    for i in range(5):
        records += _graded(
            f"b{i + 1}/c1#opencode#a1", datetime(2026, 7, 4, 10, i), 4, 4, commit="x"
        )
    grid = build_grid(build_runs(records))
    md = render_grid_markdown(grid)

    assert "started 5, graded 5, lost 0, mean 1.000, sd 0.000, 1.000 to 1.000, all-pass 5/5" in md
    assert "(low n)" not in md
    assert 'class="low_n"' not in render_grid_html(grid)


def test_one_graded_run_reads_sd_na():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    grid = build_grid(build_runs(_graded("b1/c1#opencode#a1", _T0, passed=3, total=4, commit="x")))
    assert (
        "started 1, graded 1, lost 0, mean 0.750 (low n), sd n/a (low n)"
        in render_grid_markdown(grid)
    )


# --- 2.3 the row ----------------------------------------------------------------


def test_row_shows_derived_status_last_stage_scores_tokens_and_wall():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "research", _T0, outcome=BenchmarkOutcome.NOT_EVALUATED, wall=12.0),
        _task(run_id, "code", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=10.0),
        _stage(run_id, "analyze", _T2, wall=14.0),
        _oracle(run_id, 3, 4),
    ]
    cells = _row_cells(render_grid_markdown(build_grid(build_runs(records))), run_id)

    assert cells[0] == run_id
    assert cells[1] == "graded derived"  # no cell record: status derived
    assert cells[2] == "analyze"  # last stage as recorded
    assert cells[3] == "not_evaluated"  # s:research
    assert cells[4] == "first (1/1)"  # s:code
    assert cells[5] == "first"  # s:analyze
    assert cells[6] == "3/4"  # oracle passed/total
    assert cells[7] == "1/1"  # first attempt
    assert cells[8] == "1/1"  # after repair
    assert cells[9] == "600"  # tokens: 4 records x (100+50)
    assert cells[10] == "36.0"  # wall: 12 + 10 + 14
    assert cells[11] == ""  # flags


def test_row_flags_dirty_and_unfinished_and_never_unfinished_on_a_lost_run():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, tree_dirty=True),
        _stage(run_id, "analyze", _T1),
        _oracle(run_id, 3, 4, _T2),
        _cell(run_id, _T2, "analyze", code_finished=True, pipeline_finished=False),
    ]
    md = render_grid_markdown(build_grid(build_runs(records)))
    cells = _cells_by_stage(md, run_id)
    assert cells["status"] == "graded"  # cell record: not derived
    assert cells["flags"] == "dirty, unfinished"

    lost_id = "b1/c1#opencode#a2"
    lost = [
        _task(lost_id, "code", "t1", 1, _T0, BenchmarkOutcome.FAIL),
        _stage(lost_id, "handoff", _T1, outcome=BenchmarkOutcome.FAIL),
        _cell(
            lost_id,
            _T1,
            "handoff",
            code_finished=False,
            pipeline_finished=False,
            grading="not_graded",
        ),
    ]
    cells = _cells_by_stage(render_grid_markdown(build_grid(build_runs(lost))), lost_id)
    assert cells["status"] == "lost"
    assert cells["last"] == "handoff"  # lost in the task loop: handoff, not code
    assert cells["oracle"] == "n/a"  # no oracle grade on a lost run
    assert "unfinished" not in cells["flags"]  # unfinished never flags a lost run


# --- 2.4 stage-cell marks -------------------------------------------------------


def test_every_mark_of_the_24_table():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "research", _T0, outcome=BenchmarkOutcome.FAIL, wall=1.0),
        _stage(run_id, "research", _T1, outcome=BenchmarkOutcome.PASS, wall=1.0),  # repaired
        _stage(run_id, "architecture", _T0, wall=1.0),  # first
        _stage(run_id, "plan", _T0, outcome=BenchmarkOutcome.FAIL, wall=1.0),  # failed
        _stage(run_id, "clarify", _T0, outcome=BenchmarkOutcome.NOT_EVALUATED, wall=1.0),
        _stage(run_id, "clarify", _T1, outcome=BenchmarkOutcome.NOT_EVALUATED, wall=1.0),
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "code", "t2", 1, _T0, BenchmarkOutcome.FAIL, wall=1.0),
        _task(run_id, "code", "t2", 2, _T1, BenchmarkOutcome.PASS, wall=1.0),
        _stage(run_id, "merge", _T2, outcome=BenchmarkOutcome.REVISED, wall=1.0),  # revise = pass
        _oracle(run_id, 3, 4),
        # a sibling run of the same group records deploy, so the column exists
        _stage("b2/c1#opencode#a1", "deploy", _T2, wall=1.0),
    ]
    cells = _cells_by_stage(render_grid_markdown(build_grid(build_runs(records))), run_id)

    assert cells["s:research"] == "repaired"
    assert cells["s:architecture"] == "first"
    assert cells["s:plan"] == "failed"
    assert cells["s:clarify"] == "not_evaluated"
    assert cells["s:code"] == "repaired (1/2)"  # one of two tasks first-passed
    assert cells["s:merge"] == "first"  # revise on merge is a pass
    assert cells["s:deploy"] == "not_reached"


def test_task_stage_failed_when_any_tasks_last_attempt_did_not_pass():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "code", "t2", 1, _T0, BenchmarkOutcome.FAIL, wall=1.0),
        _task(run_id, "code", "t2", 2, _T1, BenchmarkOutcome.FAIL, wall=1.0),  # never passes
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 1, 2),
    ]
    cells = _cells_by_stage(render_grid_markdown(build_grid(build_runs(records))), run_id)
    assert cells["s:code"] == "failed (1/2)"


def test_a_not_evaluated_verdict_beside_a_pass_does_not_make_the_stage_not_evaluated():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "plan", _T0, outcome=BenchmarkOutcome.PASS, wall=1.0),
        _stage(run_id, "plan", _T1, outcome=BenchmarkOutcome.NOT_EVALUATED, wall=1.0),
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 4, 4),
    ]
    cells = _cells_by_stage(render_grid_markdown(build_grid(build_runs(records))), run_id)
    assert cells["s:plan"] == "first"


def test_qa_under_a_copy_run_is_marked_copy_without_a_tasks_figure():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b0/c1#opencode#m"  # pre-012 (no commit on any record)
    records = [
        _task(run_id, "code", "t1", 1, _T0, BenchmarkOutcome.PASS, wall=1.0),
        _task(run_id, "qa", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=1.0),  # copies code
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 4, 4),
    ]
    md = render_grid_markdown(build_grid(build_runs(records)))
    assert _cells_by_stage(md, run_id)["s:qa"] == "copy"
    assert "copy (" not in md


# --- 2.5 the markdown shape -------------------------------------------------------


def test_header_cells_exactly_and_no_separator_row_and_ascii_only():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "research", _T0, wall=1.0),
        _task(run_id, "code", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=1.0),
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 3, 4),
    ]
    md = render_grid_markdown(build_grid(build_runs(records)))

    assert _header(md) == (
        "| run | status | last | s:research | s:code | s:analyze | oracle | "
        "first attempt | after repair | tokens | wall (s) | flags |"
    )
    header_cells = [c.strip() for c in _header(md).strip("|").split("|")]
    assert "case" not in header_cells
    assert "stage" not in header_cells
    assert "---" not in md  # no separator row anywhere
    assert md.isascii()


# --- 2.6 trailing columns for stages outside CELL_STAGE_ORDER ---------------------


def test_a_stage_outside_the_order_gets_a_trailing_column_sorted_by_name():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "research", _T0, wall=1.0),
        _stage(run_id, "mystery", _T1, wall=1.0),
        _stage(run_id, "zed", _T1, wall=1.0),
        _stage(run_id, "alpha", _T1, wall=1.0),
        _stage(run_id, "analyze", _T2, wall=1.0),
        _oracle(run_id, 3, 4),
    ]
    md = render_grid_markdown(build_grid(build_runs(records)))
    cells = [c.strip() for c in _header(md).strip("|").split("|")]

    # ordered stages first, then the extras by name, then oracle
    assert cells[3:8] == ["s:research", "s:analyze", "s:alpha", "s:mystery", "s:zed"]
    assert cells[8] == "oracle"
    assert _row_cells(md, run_id)[cells.index("s:mystery")] == "first"


# --- the JSON carries the same figures and no raw records -------------------------


def test_json_carries_the_figures_and_no_raw_records():
    import json

    from sdlc.benchmarks.grid import build_grid, render_grid_json
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#opencode#a1"
    records = [
        _stage(run_id, "research", _T0, outcome=BenchmarkOutcome.NOT_EVALUATED, wall=12.0),
        _task(run_id, "code", "t1", 1, _T1, BenchmarkOutcome.PASS, wall=10.0),
        _stage(run_id, "analyze", _T2, wall=14.0),
        _oracle(run_id, 3, 4),
    ]
    text = render_grid_json(build_grid(build_runs(records)))

    assert '"records"' not in text  # no raw records ride along
    assert "prompt_sha" not in text
    payload = json.loads(text)
    assert payload["stages"] == ["research", "code", "analyze"]
    assert payload["totals"]["started"] == 1
    group = payload["groups"][0]
    assert group["started"] == 1 and group["graded"] == 1 and group["lost"] == 0
    row = group["rows"][0]
    assert row["run"]["run_id"] == run_id
    assert row["run"]["oracle_passed"] == 3 and row["run"]["oracle_total"] == 4
    assert {c["stage"]: c["mark"] for c in row["cells"]} == {
        "research": "not_evaluated",
        "code": "first",
        "analyze": "first",
    }
    tasks = {c["stage"]: c["tasks"] for c in row["cells"]}
    assert tasks["code"] == [1, 1] and tasks["research"] is None


# --- chaos: empty and degenerate inputs --------------------------------------------


def test_no_runs_give_an_empty_grid_that_still_renders():
    import json

    from sdlc.benchmarks.grid import (
        build_grid,
        render_grid_html,
        render_grid_json,
        render_grid_markdown,
    )

    grid = build_grid([])
    assert grid.groups == ()
    assert grid.totals.started == 0
    md = render_grid_markdown(grid)
    assert md == "" and md.isascii()
    assert "<h3>" not in render_grid_html(grid)
    assert json.loads(render_grid_json(grid))["groups"] == []


def test_a_column_recorded_by_one_group_is_not_reached_in_the_other():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    with_analyze = _graded("b1/c1#opencode#a1", _T0, commit="aaa")
    without = [
        _stage("b2/c1#opencode#a1", "research", _T2, wall=1.0, kroker_commit="bbb", arm="a1"),
    ]
    md = render_grid_markdown(build_grid(build_runs(with_analyze + without)))

    header = [c.strip() for c in _header(md).strip("|").split("|")]
    assert "s:analyze" in header  # the column exists: one group recorded it
    assert _row_cells(md, "b2/c1#opencode#a1")[header.index("s:analyze")] == "not_reached"


def test_a_run_with_no_stage_record_shows_last_none_and_is_lost():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    other = _graded("b1/c1#opencode#a1", _T0, commit="x")
    bare = [_oracle("b2/c1#opencode#a1", 4, 4, _T1, kroker_commit="x", arm="a1")]
    md = render_grid_markdown(build_grid(build_runs(other + bare)))
    cells = _cells_by_stage(md, "b2/c1#opencode#a1")

    assert cells["status"] == "lost derived"  # oracle present, code never finished
    assert cells["last"] == "none"  # no stage record at all
    assert cells["oracle"] == "n/a"  # lost: the oracle record is discarded


def test_run_ids_with_hashes_render_verbatim_and_ascii():
    from sdlc.benchmarks.grid import build_grid, render_grid_markdown
    from sdlc.benchmarks.runs import build_runs

    run_id = "b1/c1#crew:opencode#team#x"  # an arm that itself contains '#'
    records = [
        _stage(run_id, "analyze", _T0, wall=1.0, arm="team#x"),
        _oracle(run_id, 4, 4),
    ]
    md = render_grid_markdown(build_grid(build_runs(records)))
    assert run_id in md
    assert md.isascii()
    assert (
        md.splitlines()[0]
        == "### c1 / crew:opencode / team#x / commit not recorded untrusted (pre-012)"
    )
