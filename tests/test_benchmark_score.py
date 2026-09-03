from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.evidence import Evidence
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
from sdlc.benchmarks.score import default_out_dir, load_config_weights, parse_weights, write_score
from sdlc.core.models import (
    HarnessKind,
)

T = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _rec(case="c1", task=None, scope=BenchmarkScope.STAGE, stage="code", usd=1.0, waste=None):
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id=case,
        scope=scope,
        stage=stage,
        task_id=task,
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        cost=CostBag(usd=usd),
        speed=SpeedBag(wall_clock_s=2.0, started_at=T, ended_at=T + timedelta(seconds=2)),
        outcome=BenchmarkOutcome.PASS,
        waste=waste,
    )


def test_parse_weights_accepts_three_floats():
    w = parse_weights("0.5,0.3,0.2")
    assert (w.quality, w.cost, w.speed) == (0.5, 0.3, 0.2)


def test_parse_weights_rejects_wrong_arity():
    with pytest.raises(ValueError, match="quality,cost,speed"):
        parse_weights("0.5,0.5")


def test_parse_weights_need_not_sum_to_one():
    """scoring.py renormalises over available axes, so 3,1,1 is legal."""
    w = parse_weights("3,1,1")
    assert w.quality == 3.0


def test_load_config_weights_reads_benchmarks_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("weights:\n  quality: 0.7\n  cost: 0.2\n  speed: 0.1\n", encoding="utf-8")
    w = load_config_weights(p)
    assert w.quality == 0.7 and w.speed == 0.1


def test_load_config_weights_defaults_when_absent(tmp_path):
    w = load_config_weights(tmp_path / "missing.yaml")
    assert w == CompositeWeights()


def test_default_out_dir_is_derived_from_selector(tmp_path):
    assert default_out_dir("b1", root=str(tmp_path)).name == "score"
    assert default_out_dir("b1", root=str(tmp_path)).parent.name == "b1"
    assert "c1" in str(default_out_dir("_case/c1", root=str(tmp_path)))


def test_write_score_emits_report_and_heatmap(tmp_path):
    ev = Evidence(records=[_rec()], selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    names = {p.name for p in written}
    assert {"report.md", "heatmap.html", "heatmap.json"} <= names
    assert (tmp_path / "report.md").read_text(encoding="utf-8")


def test_missing_tasks_yaml_skips_matrices_and_notes_it(tmp_path, monkeypatch):
    """cat-cafe-monitoring has no tasks.yaml; today dispatch_history RAISES.
    Under score it must degrade."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "no-cases"))
    ev = Evidence(
        records=[_rec(task="t01", scope=BenchmarkScope.ORACLE_TASK, stage="oracle")],
        selector="_case/c1",
    )
    written = write_score(ev, tmp_path, CompositeWeights())
    assert "task-matrix.html" not in {p.name for p in written}
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "tasks.yaml" in md


def test_empty_evidence_writes_a_report_and_does_not_raise(tmp_path):
    ev = Evidence(records=[], selector="_all", notes=["no benchmark records for selector _all"])
    written = write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "no benchmark records" in md
    assert any(p.name == "report.md" for p in written)


def test_notes_are_rendered_into_the_report(tmp_path):
    ev = Evidence(
        records=[_rec()],
        selector="b1",
        notes=["export root /x does not exist; no SC rates computed"],
    )
    write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "no SC rates computed" in md


def test_report_markdown_is_ascii_only(tmp_path):
    """report.py:70-74 -- a Windows cp1252 console mangles non-ASCII."""
    ev = Evidence(records=[_rec()], selector="b1", notes=["a note"])
    write_score(ev, tmp_path, CompositeWeights())
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    md.encode("ascii")


def test_waste_matrix_written_even_without_tasks_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "no-cases"))
    ev = Evidence(records=[_rec(task="t01", waste=WasteBag(tool_calls=9))], selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    assert "waste-matrix.html" in {p.name for p in written}
    assert "t01" in (tmp_path / "waste-matrix.html").read_text(encoding="utf-8")


def test_sc_rollup_written_and_appended_to_report(tmp_path):
    ev = Evidence(records=[_rec()], selector="b1")
    written = write_score(ev, tmp_path, CompositeWeights())
    assert {"sc-rollup.html", "sc-rollup.json"} <= {p.name for p in written}
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Success criteria" in md
    assert "SC-1" in md
