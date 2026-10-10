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


# --- 013 T012: one writer for both paths (contract 11) -------------------------


def _cases_root_with_tasks(tmp_path, case="c1"):
    cases = tmp_path / "cases"
    (cases / case).mkdir(parents=True)
    (cases / case / "tasks.yaml").write_text(
        'tasks:\n  - id: t01\n    error_class: functional\n    oracle_tests: ["x::y"]\n',
        encoding="utf-8",
    )
    return cases


def _arm_records(arm, q=0.9, commit="abc123"):
    """One graded 012 run under a stored-shape run id: a rubric-judged
    architecture record, a merge record and an oracle record."""
    rid = f"b1/c1#opencode#{arm}"
    recs = [
        _rec(stage="architecture").model_copy(
            update={"run_id": rid, "quality": QualityScore(score=q, judge="llm_judge")}
        ),
        _rec(stage="merge", usd=None).model_copy(update={"run_id": rid}),
        _rec().model_copy(
            update={
                "run_id": rid,
                "scope": BenchmarkScope.ORACLE,
                "stage": "oracle",
                "role": "oracle",
                "quality": QualityScore(
                    score=1.0, judge="oracle", components={"passed": 5.0, "total": 5.0}
                ),
            }
        ),
    ]
    if commit is None:
        return recs
    return [r.model_copy(update={"kroker_commit": commit}) for r in recs]


_SCORE_FILES = {
    "report.md",
    "grid.html",
    "grid.json",
    "heatmap.html",
    "heatmap.json",
    "gate-oracle.html",
    "gate-oracle.json",
    "sc-rollup.html",
    "sc-rollup.json",
    "waste-matrix.html",
    "waste-matrix.json",
    "agreement-matrix.html",
    "agreement-matrix.json",
    "task-matrix.html",
    "task-matrix.json",
    "error-matrix.html",
    "error-matrix.json",
}


def test_write_score_writes_exactly_the_files_of_contract_11_1(tmp_path, monkeypatch):
    """One case: every file of contract 11.1 lands flat in the output
    directory, and nothing else is written anywhere."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_cases_root_with_tasks(tmp_path)))
    ev = Evidence(records=_arm_records("a1"), selector="b1")
    written = write_score(ev, tmp_path / "out", CompositeWeights())
    assert {p.name for p in written} == _SCORE_FILES
    assert {p.name for p in (tmp_path / "out").iterdir()} == _SCORE_FILES


def test_write_score_report_sections_in_contract_order(tmp_path, monkeypatch):
    """The report the score command writes carries the contract-8 sections
    in order, each heading exactly once."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_cases_root_with_tasks(tmp_path)))
    recs = (
        _arm_records("a1") + _arm_records("a2", commit="def456") + _arm_records("a3", commit=None)
    )
    ev = Evidence(records=recs, selector="b1")
    write_score(ev, tmp_path / "out", CompositeWeights())
    md = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    headings = [
        "# Benchmark report",
        "## Runs",
        "## Stages",
        "## Pre-012 records (untrusted)",
        "## Gate versus oracle",
        "## Success criteria",
        "## Notes",
    ]
    positions = [md.index(h) for h in headings]
    assert positions == sorted(positions)
    for h in headings:
        assert md.count(h) == 1


def test_weights_note_when_no_composite_shown(tmp_path, monkeypatch):
    """--weights on a one-arm selection: the command succeeds and the
    report says the weights were not used (contract 7.4)."""
    from sdlc.benchmarks.cli import dispatch_score
    from sdlc.benchmarks.recorder import RecordStore

    monkeypatch.setenv("SDLC_CASES_ROOT", str(_cases_root_with_tasks(tmp_path)))
    export = tmp_path / "export"
    export.mkdir()
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(export))
    for rec in _arm_records("a1"):
        RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)

    dispatch_score(bench="b1", root=str(tmp_path), weights="0.5,0.3,0.2")  # exits 0
    md = (tmp_path / "b1" / "score" / "report.md").read_text(encoding="utf-8")
    assert "weights not used: no composite shown" in md


def test_weights_note_absent_when_composite_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_cases_root_with_tasks(tmp_path)))
    ev = Evidence(records=_arm_records("a1") + _arm_records("a2", commit="def456"), selector="b1")
    write_score(ev, tmp_path / "out", parse_weights("0.5,0.3,0.2"))
    md = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "weights not used" not in md


def test_view_modules_leave_temporalio_out_of_sys_modules():
    """Contract 11.4, in a fresh interpreter: importing the five view
    modules pulls in no Temporal client (the score path runs offline)."""
    import subprocess
    import sys

    code = (
        "import sys\n"
        "import sdlc.benchmarks.runs, sdlc.benchmarks.grid, "
        "sdlc.benchmarks.gate_oracle, sdlc.benchmarks.heatmap, "
        "sdlc.benchmarks.heatmap_render\n"
        "sys.exit(0 if 'temporalio' not in sys.modules else 1)\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
