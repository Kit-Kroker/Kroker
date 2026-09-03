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
    return BenchmarkRecord(
        run_id=run,
        bench_run_id=bench,
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        task_id="t01",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=q, judge="contract"),
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
