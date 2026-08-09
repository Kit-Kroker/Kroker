from sdlc.benchmarks.cli import load_case_spec, build_parser, dispatch_score


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


def test_parser_accepts_benchmark_score_bench():
    p = build_parser()
    args = p.parse_args(["benchmark", "score", "--bench", "b1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "score"
    assert args.bench == "b1"
    assert args.all_ is False


def test_parser_accepts_benchmark_score_case():
    p = build_parser()
    args = p.parse_args(["benchmark", "score", "--case", "c1"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "score"
    assert args.case == "c1"


def test_parser_accepts_benchmark_score_all():
    p = build_parser()
    args = p.parse_args(["benchmark", "score", "--all"])
    assert args.bench_cmd == "score"
    assert args.all_ is True


def test_dispatch_score_writes_report_when_no_records(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    # no records -> empty report, but no crash; returns one path per file.
    out = dispatch_score(bench="b1", root=str(tmp_path))
    assert "report.md" in out
    md = (tmp_path / "b1" / "score" / "report.md").read_text(encoding="utf-8")
    assert "no benchmark records" in md


def test_dispatch_score_does_not_require_temporal_client(tmp_path):
    # The score path is a pure offline file operation: it must succeed
    # without constructing or connecting a Temporal Client. This locks in
    # the invariant that `sdlc.cli benchmark score` can run offline.
    out = dispatch_score(bench="nonexistent-bench", root=str(tmp_path))
    assert "report.md" in out


def test_dispatch_score_also_writes_heatmap(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
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
    out = dispatch_score(bench="b1", root=str(tmp_path))
    out_dir = tmp_path / "b1" / "score"
    assert (out_dir / "heatmap.html").exists()
    assert (out_dir / "heatmap.json").exists()
    assert "heatmap.html" in out and "heatmap.json" in out


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

    # Client is imported lazily inside _run_matrix, so patch it on the
    # temporalio module it is bound to.
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)
    import asyncio
    asyncio.run(_run_matrix(str(case), "hard"))
    assert '"gate_policy":"hard"' in captured["spec_json"]


def test_dispatch_score_case_degrades_without_tasks_yaml(tmp_path, monkeypatch):
    """A case with no tasks.yaml used to raise under dispatch_history; under
    score it degrades with a note in report.md and exits cleanly."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "no-cases"))
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(tmp_path))
    out = dispatch_score(case="no-such-case", root=str(tmp_path))
    assert "report.md" in out
    out_dir = tmp_path / "_case" / "no-such-case" / "score"
    md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "no benchmark records" in md
    assert not (out_dir / "task-matrix.html").exists()


def test_dispatch_score_case_writes_all_four_matrices(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
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

    out = dispatch_score(case="c1", root=str(runs_root))
    out_dir = runs_root / "_case" / "c1" / "score"
    assert (out_dir / "task-matrix.html").exists()
    assert (out_dir / "task-matrix.json").exists()
    assert (out_dir / "error-matrix.html").exists()
    assert (out_dir / "error-matrix.json").exists()
    assert "task-matrix.html" in out
    assert "error-matrix.html" in out


def test_import_deveval_converts_every_repo_under_a_language_root(tmp_path):
    """The CLI walks benchmark_data/<language>/<repo> and reports per repo."""
    import shutil
    from pathlib import Path

    from sdlc.benchmarks.cli import dispatch_import_deveval

    fixture = (Path(__file__).resolve().parent / "fixtures" / "mini_calc")
    src_root = tmp_path / "src" / "python"
    src_root.mkdir(parents=True)
    shutil.copytree(fixture, src_root / "mini_calc")
    out = tmp_path / "cases"
    out.mkdir()

    report = dispatch_import_deveval(src=str(src_root), out=str(out))
    assert "deveval-mini-calc" in report
    assert (out / "deveval-mini-calc" / "case.yaml").is_file()


def test_import_deveval_reports_network_quarantine(tmp_path):
    import shutil
    from pathlib import Path

    from sdlc.benchmarks.cli import dispatch_import_deveval

    fixture = (Path(__file__).resolve().parent / "fixtures" / "mini_calc")
    src_root = tmp_path / "src" / "python"
    src_root.mkdir(parents=True)
    shutil.copytree(fixture, src_root / "mini_calc")
    (src_root / "mini_calc" / "calc.py").write_text(
        "import requests\n\n\ndef add(a, b):\n    return a + b\n",
        encoding="utf-8")
    out = tmp_path / "cases"
    out.mkdir()

    report = dispatch_import_deveval(src=str(src_root), out=str(out))
    assert "QUARANTINED" in report
