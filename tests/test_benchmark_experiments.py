from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.evidence import Evidence
from sdlc.benchmarks.experiments import (
    NOISE_FLOOR,
    compute_deltas,
    load_experiment,
    new_experiment,
    render_deltas_markdown,
    save_experiment,
)
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CompositeWeights,
    CostBag,
    QualityScore,
    SpeedBag,
    WasteBag,
)
from sdlc.core.models import (
    HarnessKind,
)

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _rec(*, q=1.0, usd=1.0, secs=10.0, waste=None, bench="b1", run="r1"):
    # 013 (R-11): the judge must be a rubric judge and the stage a
    # quality-bearing one -- a `contract` verdict is no longer a quality
    # score and the code row shows task scores, not quality.
    return BenchmarkRecord(
        run_id=run,
        bench_run_id=bench,
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="review",
        task_id="t01",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=q, judge="llm_judge"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=secs, started_at=T, ended_at=T + timedelta(seconds=secs)),
        outcome=BenchmarkOutcome.PASS,
        waste=waste,
    )


def _ev(records, selector="b1"):
    return Evidence(records=records, selector=selector)


def test_new_experiment_scaffolds_with_empty_verdict():
    """The tool computes deltas; the human writes the verdict (ADR-11)."""
    exp = new_experiment(
        name="planner-decompose-prompt",
        axis="prompt",
        change="require inter-task contracts",
        baseline="bench-1",
    )
    assert exp.verdict == ""
    assert exp.baseline == "bench-1"
    assert exp.candidate == ""
    assert exp.deltas == []
    assert exp.id.endswith("planner-decompose-prompt")


def test_new_experiment_rejects_unknown_axis():
    with pytest.raises(ValueError, match="axis"):
        new_experiment(name="x", axis="vibes", change="c", baseline="b")


def test_compute_deltas_reports_quality_cost_and_wall():
    base = _ev([_rec(q=0.5, usd=1.0, secs=10.0)])
    cand = _ev([_rec(q=0.9, usd=1.5, secs=8.0)], selector="b2")
    rows = compute_deltas(base, cand, CompositeWeights())
    assert len(rows) == 1
    row = rows[0]
    assert row.quality == pytest.approx(0.4)
    assert row.cost_usd == pytest.approx(0.5)
    assert row.wall_s == pytest.approx(-2.0)


def test_compute_deltas_includes_every_waste_metric():
    base = _ev([_rec(waste=WasteBag(tool_calls=10, file_rereads=2))])
    cand = _ev([_rec(waste=WasteBag(tool_calls=48, file_rereads=6), bench="b2")], selector="b2")
    row = compute_deltas(base, cand, CompositeWeights())[0]
    assert row.waste["tool_calls"] == pytest.approx(38.0)
    assert row.waste["file_rereads"] == pytest.approx(4.0)


def test_low_n_cells_are_marked_within_noise():
    base = _ev([_rec(q=0.5)])
    cand = _ev([_rec(q=0.9, bench="b2")], selector="b2")
    assert compute_deltas(base, cand, CompositeWeights())[0].note == "within-noise"


def test_sufficient_n_is_not_marked_noise():
    base = _ev([_rec(q=0.5, run=f"r{i}") for i in range(NOISE_FLOOR)])
    cand = _ev([_rec(q=0.9, run=f"r{i}", bench="b2") for i in range(NOISE_FLOOR)], selector="b2")
    assert compute_deltas(base, cand, CompositeWeights())[0].note == ""


def test_noise_floor_is_three():
    assert NOISE_FLOOR == 3


def test_cell_only_in_candidate_is_reported_with_none_baseline():
    base = _ev([])
    cand = _ev([_rec(q=0.9, bench="b2")], selector="b2")
    rows = compute_deltas(base, cand, CompositeWeights())
    assert len(rows) == 1 and rows[0].quality is None


def test_save_and_load_round_trip(tmp_path):
    exp = new_experiment(name="x", axis="model", change="swap dev model", baseline="b1")
    exp.deltas = compute_deltas(
        _ev([_rec(q=0.5)]), _ev([_rec(q=0.9, bench="b2")], "b2"), CompositeWeights()
    )
    p = save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    again = load_experiment(p)
    assert again.id == exp.id
    assert again.verdict == ""
    assert again.deltas[0].quality == pytest.approx(0.4)


def test_saved_yaml_carries_the_verdict_key_for_a_human_to_fill(tmp_path):
    exp = new_experiment(name="x", axis="harness", change="c", baseline="b1")
    p = save_experiment(exp, tmp_path / "x.yaml")
    text = p.read_text(encoding="utf-8")
    assert "verdict:" in text


def test_load_preserves_a_human_written_verdict(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(
        "id: 2026-08-04-x\naxis: prompt\nchange: c\nbaseline: b1\n"
        "candidate: b2\nverdict: rollback\nnotes: not worth the tokens\n",
        encoding="utf-8",
    )
    assert load_experiment(p).verdict == "rollback"


def test_render_deltas_markdown_shows_n_and_is_ascii():
    rows = compute_deltas(
        _ev([_rec(q=0.5)]), _ev([_rec(q=0.9, bench="b2")], "b2"), CompositeWeights()
    )
    md = render_deltas_markdown(rows)
    assert "n" in md and "within-noise" in md
    md.encode("ascii")


def test_render_deltas_markdown_handles_empty():
    assert "no overlapping cells" in render_deltas_markdown([]).lower()


def test_compare_hard_errors_on_a_missing_experiment(tmp_path):
    from sdlc.benchmarks.cli import dispatch_experiment_compare

    with pytest.raises(SystemExit, match="no experiment"):
        dispatch_experiment_compare(experiment="nope", candidate="b2", exp_dir=str(tmp_path))


def test_compare_hard_errors_on_an_empty_bench(tmp_path):
    """Reporting degrades; comparison does not."""
    from sdlc.benchmarks.cli import dispatch_experiment_compare
    from sdlc.benchmarks.experiments import new_experiment, save_experiment

    exp = new_experiment(name="x", axis="prompt", change="c", baseline="b1")
    save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    with pytest.raises(SystemExit, match="refusing to compare"):
        dispatch_experiment_compare(
            experiment=exp.id,
            candidate="b2",
            exp_dir=str(tmp_path),
            root=str(tmp_path / "empty-records"),
        )


# --- 012 T010 (RED): delta immunity, cell keying, the pre-012 line ----------
# contract §7.6/§7.7/§7.8, data-model §2.3 (cell_key / arm_label / is_pre012).


def _cell_scope_rec(bench="b2"):
    from sdlc.benchmarks.models import CellStatus

    r = _rec(bench=bench)
    return r.model_copy(
        update={
            "scope": BenchmarkScope.CELL,
            "stage": "cell",
            "role": "cell",
            "task_id": None,
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
            "cell_id": "c1#opencode#a1",
            "arm": "a1",
            # 013 (R-11, orchestrator-cleared): the cell record rides its
            # own stored-shape run id, not the id of a pre-012 record -- a
            # shared id would flip that run to generation 012.
            "run_id": f"{bench}/c1#opencode#a1",
        }
    )


def _not_evaluated_rec(bench="b2"):
    r = _rec(bench=bench)
    return r.model_copy(
        update={
            "outcome": BenchmarkOutcome.NOT_EVALUATED,
            "quality": QualityScore(score=None, judge="contract"),
        }
    )


def test_cell_and_not_evaluated_records_change_no_delta_row():
    """Cell records ride the candidate evidence and the not_evaluated
    record rides its code group: neither may move any delta value, count
    or note."""
    base_recs = [_rec(q=0.5, run=f"r{i}") for i in range(3)]
    cand_recs = [_rec(q=0.9, run=f"r{i}", bench="b2") for i in range(3)]
    base = compute_deltas(_ev(base_recs), _ev(cand_recs, "b2"), CompositeWeights())
    with_extra = compute_deltas(
        _ev(base_recs + [_cell_scope_rec("b1")]),
        _ev(cand_recs + [_not_evaluated_rec()], "b2"),
        CompositeWeights(),
    )
    assert [r.model_dump() for r in with_extra] == [r.model_dump() for r in base]


def test_012_cells_label_by_arm_and_pre012_cells_keep_the_model_key():
    """contract §7.7: a 012 record's cell third component is the arm label
    (the summary join reads BenchmarkSummary.arm); a pre-012 record keeps
    exactly the base `harness#model` key."""
    cand = _ev(
        [
            _rec(q=0.9, bench="b2").model_copy(
                update={
                    "task_id": None,
                    "harness": None,
                    "model": "anthropic:glm-5.2",
                    "kroker_commit": "abc123",
                    "cell_id": "c1#opencode#a1",
                    "arm": "a1",
                    # 013 (R-11, orchestrator-cleared): its own stored-shape
                    # run id, so the 012 cell is its own run beside the
                    # pre-012 one instead of merging with it.
                    "run_id": "b2/c1#opencode#a1",
                }
            ),
            _rec(q=0.7, bench="b2"),
        ],
        "b2",
    )
    rows = compute_deltas(_ev([]), cand, CompositeWeights())
    arms = {r.arm for r in rows}
    assert "a1" in arms, "the 012 cell must be labelled by its arm"
    assert "opencode#m" in arms, "the pre-012 cell keeps its base key"


def test_render_deltas_markdown_states_the_pre012_count_when_given():
    """The count is the caller's to compute (is_pre012 over its records,
    cell-scope records excluded): render_deltas_markdown gains an optional
    pre012_records keyword. Default and 0 render no line; N>0 renders it
    exactly."""
    rows = compute_deltas(
        _ev([_rec(q=0.5)]), _ev([_rec(q=0.9, bench="b2")], "b2"), CompositeWeights()
    )
    line = "includes 2 pre-012 records (untrusted)"
    assert line in render_deltas_markdown(rows, pre012_records=2)
    assert "pre-012" not in render_deltas_markdown(rows)
    assert "pre-012" not in render_deltas_markdown(rows, pre012_records=0)


def test_compare_output_states_the_pre012_count(tmp_path):
    """The T010-deferred hook (contract §7.6): dispatch_experiment_compare
    computes is_pre012 over both evidence sets and the rendered comparison
    carries the untrusted line."""
    from sdlc.benchmarks.cli import dispatch_experiment_compare
    from sdlc.benchmarks.recorder import RecordStore

    pre = _rec(q=0.5)  # no kroker_commit -> pre-012
    new = _rec(q=0.9, bench="b2").model_copy(
        update={"kroker_commit": "abc123", "tree_dirty": False}
    )
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(pre)
    RecordStore(root=str(tmp_path), bench_run_id="b2").append(new)

    exp = new_experiment(name="x", axis="prompt", change="c", baseline="b1")
    save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    out = dispatch_experiment_compare(
        experiment=exp.id, candidate="b2", exp_dir=str(tmp_path), root=str(tmp_path)
    )
    assert "includes 1 pre-012 records (untrusted)" in out


# --- 013 T012: the composite column behind the decision (contract 7.2) ---------


def test_render_deltas_markdown_composite_column_behind_the_decision():
    """No composite column unless the decision says a compared case shows
    one; show_composite=True prints it."""
    rows = compute_deltas(
        _ev([_rec(q=0.5)]), _ev([_rec(q=0.9, bench="b2")], "b2"), CompositeWeights()
    )
    header = render_deltas_markdown(rows).splitlines()[0]
    assert "composite" not in header
    header_shown = render_deltas_markdown(rows, show_composite=True).splitlines()[0]
    assert "composite" in header_shown


def _graded_arm(arm, bench):
    """One graded 012 run under a stored-shape run id: a stage record, a
    merge record and an oracle record (the shape composite_shown needs)."""
    rid = f"{bench}/c1#opencode#{arm}"
    base = _rec(bench=bench).model_copy(update={"run_id": rid, "task_id": None})
    merge = base.model_copy(update={"stage": "merge"})
    oracle = base.model_copy(
        update={
            "scope": BenchmarkScope.ORACLE,
            "stage": "oracle",
            "role": "oracle",
            "quality": QualityScore(
                score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
            ),
        }
    )
    return [r.model_copy(update={"kroker_commit": "abc123"}) for r in (base, merge, oracle)]


def test_compare_passes_the_composite_decision_through(tmp_path):
    """dispatch_experiment_compare shows the composite column exactly when
    a case on either side has two graded arms in one generation."""
    from sdlc.benchmarks.cli import dispatch_experiment_compare
    from sdlc.benchmarks.recorder import RecordStore

    for r in _graded_arm("a1", "b1") + _graded_arm("a2", "b1"):
        RecordStore(root=str(tmp_path), bench_run_id="b1").append(r)
    for r in _graded_arm("a1", "b2"):
        RecordStore(root=str(tmp_path), bench_run_id="b2").append(r)

    exp = new_experiment(name="x", axis="prompt", change="c", baseline="b1")
    save_experiment(exp, tmp_path / f"{exp.id}.yaml")
    out = dispatch_experiment_compare(
        experiment=exp.id, candidate="b2", exp_dir=str(tmp_path), root=str(tmp_path)
    )
    assert "composite" in out.splitlines()[0]
