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


def test_parser_run_gate_policy_defaults_to_none():
    p = build_parser()
    args = p.parse_args(["benchmark", "run", "--case", "c1.yaml"])
    assert args.gate_policy is None


def test_parser_run_accepts_gate_policy_override():
    p = build_parser()
    args = p.parse_args(
        ["benchmark", "run", "--case", "c1.yaml", "--gate-policy", "hard"])
    assert args.gate_policy == "hard"


def test_run_matrix_overrides_spec_gate_policy(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix
    from sdlc.models import GatePolicy

    case = tmp_path / "case.yaml"
    case.write_text(
        "case_id: add-login\nidea_summary: add login\nmode: greenfield\n"
        "harnesses: [opencode]\nmodels: [anthropic:claude-sonnet-4-6]\n"
        "judge_model: openai/gpt-5.2\nrubrics: {}\n", encoding="utf-8")

    captured: dict = {}

    async def _fake_connect(*a, **kw):
        class _Client:
            async def start_workflow(self, _run, spec_json, **kw2):
                captured["spec_json"] = spec_json
                class _Handle:
                    async def result(self_inner):
                        return "ok"
                return _Handle()
        return _Client()

    monkeypatch.setattr("sdlc.benchmarks.cli.Client.connect", _fake_connect)
    import asyncio
    asyncio.run(_run_matrix(str(case), "hard"))
    assert '"gate_policy":"hard"' in captured["spec_json"]


def test_parser_accepts_history_subcommand():
    from sdlc.benchmarks.cli import build_parser
    p = build_parser()
    args = p.parse_args(["benchmark", "history", "--case", "c1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "history"
    assert args.case == "c1"


def test_dispatch_history_raises_without_tasks_yaml(tmp_path):
    from sdlc.benchmarks.cli import dispatch_history
    import pytest as _pytest
    with _pytest.raises(ValueError, match="no tasks.yaml"):
        dispatch_history("no-such-case", root=str(tmp_path))


def test_dispatch_history_writes_all_four_files(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.cli import dispatch_history
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.models import HarnessKind

    cases_dir = tmp_path / "cases"
    (cases_dir / "c1").mkdir(parents=True)
    (cases_dir / "c1" / "tasks.yaml").write_text(
        "tasks:\n  - id: t01\n    error_class: functional\n"
        "    oracle_tests: [\"x::y\"]\n", encoding="utf-8")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases_dir))

    runs_root = tmp_path / "runs"
    t = datetime(2026, 7, 20, 10)
    rec = BenchmarkRecord(
        run_id="b1/c1#opencode#m1", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK, stage="oracle", task_id="t01",
        role="oracle", harness=HarnessKind.OPENCODE, model="m1",
        quality=QualityScore(score=1.0, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t,
                      ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS)
    RecordStore(root=str(runs_root), bench_run_id="b1").append(rec)

    tm_path, em_path = dispatch_history("c1", root=str(runs_root))
    out_dir = runs_root / "_history" / "c1"
    assert (out_dir / "task-matrix.html").exists()
    assert (out_dir / "task-matrix.json").exists()
    assert (out_dir / "error-matrix.html").exists()
    assert (out_dir / "error-matrix.json").exists()
    assert tm_path == str(out_dir / "task-matrix.html")
    assert em_path == str(out_dir / "error-matrix.html")
