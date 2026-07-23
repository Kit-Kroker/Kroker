from sdlc.benchmarks.cli import load_case_spec, build_parser, dispatch_report


def test_load_case_spec_reads_yaml(tmp_path):
    case = tmp_path / "case.yaml"
    case.write_text(
        "case_id: add-login\n"
        "idea_summary: add login\n"
        "description: login page\n"
        "mode: greenfield\n"
        "harnesses: [claude_code, opencode]\n"
        "models: [anthropic:claude-sonnet-4-6]\n"
        "judge_model: openai/gpt-5.2\n"
        "rubrics:\n  architect: rubric-architect.md\n",
        encoding="utf-8")
    spec = load_case_spec(str(case))
    assert spec.case_id == "add-login"
    assert len(spec.harnesses) == 2
    assert spec.judge_model == "openai/gpt-5.2"


def test_parser_accepts_benchmark_subcommands():
    p = build_parser()
    args = p.parse_args(["benchmark", "report", "--bench", "b1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "report"
    assert args.bench == "b1"


def test_dispatch_report_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    # no records → empty report, but no crash
    out = dispatch_report("b1", root=str(tmp_path))
    assert "No records" in out or "case" in out.lower()


def test_dispatch_report_does_not_require_temporal_client(tmp_path):
    # The report path is a pure offline file operation: it must succeed
    # without constructing or connecting a Temporal Client. This locks in
    # the invariant that `sdlc.cli benchmark report` can run offline.
    out = dispatch_report("nonexistent-bench", root=str(tmp_path))
    assert "No records" in out


def test_dispatch_report_also_writes_heatmap(tmp_path):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.cli import dispatch_report
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.models import HarnessKind
    t = datetime(2026, 7, 24, 10)
    rec = BenchmarkRecord(
        run_id="r1", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.CLAUDE_CODE, model="m",
        quality=QualityScore(score=0.9, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL, fix_attempts=1)
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)
    dispatch_report("b1", root=str(tmp_path))
    assert (tmp_path / "b1" / "heatmap.html").exists()
    assert (tmp_path / "b1" / "heatmap.json").exists()
