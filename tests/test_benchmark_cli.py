import asyncio
from pathlib import Path

import pytest

from sdlc.benchmarks.cli import build_parser, dispatch_score, load_case_spec


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
        encoding="utf-8",
    )
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
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.core.models import (
        HarnessKind,
    )

    t = datetime(2026, 7, 24, 10)
    rec = BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.CLAUDE_CODE,
        model="m",
        quality=QualityScore(score=0.9, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
        fix_attempts=1,
    )
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)
    out = dispatch_score(bench="b1", root=str(tmp_path))
    out_dir = tmp_path / "b1" / "score"
    assert (out_dir / "heatmap.html").exists()
    assert (out_dir / "heatmap.json").exists()
    assert "heatmap.html" in out and "heatmap.json" in out
    # 013 (contract 11.1): the run grid and the gate-versus-oracle view are
    # part of the score directory.
    assert (out_dir / "grid.html").exists()
    assert (out_dir / "grid.json").exists()
    assert (out_dir / "gate-oracle.html").exists()
    assert (out_dir / "gate-oracle.json").exists()
    assert "grid.html" in out and "grid.json" in out
    assert "gate-oracle.html" in out and "gate-oracle.json" in out


def test_parser_run_gate_policy_defaults_to_none():
    p = build_parser()
    args = p.parse_args(["benchmark", "run", "--case", "c1.yaml"])
    assert args.gate_policy is None


def test_parser_run_accepts_gate_policy_override():
    p = build_parser()
    args = p.parse_args(["benchmark", "run", "--case", "c1.yaml", "--gate-policy", "hard"])
    assert args.gate_policy == "hard"


def test_run_matrix_overrides_spec_gate_policy(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case = tmp_path / "case.yaml"
    case.write_text(
        "case_id: add-login\nidea_summary: add login\nmode: greenfield\n"
        "role: probe\n"
        "harnesses: [opencode]\nmodels: [anthropic:claude-sonnet-4-6]\n"
        "judge_model: openai/gpt-5.2\nrubrics: {}\n",
        encoding="utf-8",
    )

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


def test_run_matrix_missing_registered_rubric_exits_before_temporal(tmp_path, monkeypatch):
    """012 T004 (chaos seat): a case that registers a rubric file which is
    not on disk must be refused by the _run_matrix pre-flight (contract
    1.3) -- every 1.2 message printed via SystemExit, BEFORE any Temporal
    client is created or any workflow started."""
    import asyncio

    from sdlc.benchmarks.cli import _run_matrix

    # Modelled on benchmarks/cases/todo-api-greenfield/case.yaml but with
    # opencode only, one model, no crew entries (so preflight_crew never
    # runs) and one registered rubric that does not exist.
    case = tmp_path / "case.yaml"
    case.write_text(
        "case_id: preflight-case\n"
        "idea_summary: pre-flight probe\n"
        "mode: greenfield\n"
        "harnesses: [opencode]\n"
        "models: [anthropic:claude-sonnet-4-6]\n"
        "judge_model: openai/gpt-5.2\n"
        "rubrics:\n"
        "  architect: rubric-absent.md\n",
        encoding="utf-8",
    )

    connect_calls: list = []

    async def _recording_connect(*a, **kw):
        # Mandatory guard: a red or buggy run must never reach a real
        # Temporal server from this test.
        connect_calls.append((a, kw))
        raise AssertionError("Client.connect reached: pre-flight did not run first")

    monkeypatch.setattr("temporalio.client.Client.connect", _recording_connect)

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case)))
    message = str(excinfo.value)
    assert "rubric 'architect'" in message
    assert "is missing" in message
    assert "rubric-absent.md" in message
    assert connect_calls == []


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
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.core.models import (
        HarnessKind,
    )

    cases_dir = tmp_path / "cases"
    (cases_dir / "c1").mkdir(parents=True)
    (cases_dir / "c1" / "tasks.yaml").write_text(
        'tasks:\n  - id: t01\n    error_class: functional\n    oracle_tests: ["x::y"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases_dir))

    runs_root = tmp_path / "runs"
    t = datetime(2026, 7, 20, 10)
    rec = BenchmarkRecord(
        run_id="b1/c1#opencode#m1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.ORACLE_TASK,
        stage="oracle",
        task_id="t01",
        role="oracle",
        harness=HarnessKind.OPENCODE,
        model="m1",
        quality=QualityScore(score=1.0, judge="oracle"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )
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

    fixture = Path(__file__).resolve().parent / "fixtures" / "mini_calc"
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

    fixture = Path(__file__).resolve().parent / "fixtures" / "mini_calc"
    src_root = tmp_path / "src" / "python"
    src_root.mkdir(parents=True)
    shutil.copytree(fixture, src_root / "mini_calc")
    (src_root / "mini_calc" / "calc.py").write_text(
        "import requests\n\n\ndef add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    out = tmp_path / "cases"
    out.mkdir()

    report = dispatch_import_deveval(src=str(src_root), out=str(out))
    assert "QUARANTINED" in report


# --- benchmark accept (T006) --------------------------------------------------


def test_parser_accepts_benchmark_accept():
    from sdlc.cli import build_parser as root_build_parser

    p = root_build_parser()
    args = p.parse_args(["benchmark", "accept", "--case", "deveval-readtime", "--offline"])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "accept"
    assert args.case == "deveval-readtime"
    assert args.offline is True

    # also on benchmarks.cli build_parser
    p_b = build_parser()
    args_b = p_b.parse_args(["benchmark", "accept", "--case", "deveval-readtime", "--offline"])
    assert args_b.bench_cmd == "accept"
    assert args_b.case == "deveval-readtime"
    assert args_b.offline is True


def test_dispatch_accept_offline_writes_record_and_prints_verdict(tmp_path, capsys, monkeypatch):
    import shutil
    from pathlib import Path

    from sdlc.benchmarks.acceptance import Verdict, load_acceptance
    from sdlc.benchmarks.cli import dispatch_accept, dispatch_import_deveval

    # Create a fixture case deveval-mini-calc
    fixture = Path(__file__).resolve().parent / "fixtures" / "mini_calc"
    src_root = tmp_path / "src" / "python"
    src_root.mkdir(parents=True)
    shutil.copytree(fixture, src_root / "mini_calc")
    cases_dir = tmp_path / "cases"
    dispatch_import_deveval(src=str(src_root), out=str(cases_dir))
    c_yaml = cases_dir / "deveval-mini-calc" / "case.yaml"
    extra = "role: corpus\nvisibility: public\n"
    c_yaml.write_text(c_yaml.read_text(encoding="utf-8") + extra, encoding="utf-8")

    # Stub the environment provisioner for fast offline checks
    from sdlc.benchmarks import offline_checks

    async def _stub_prov(worktree: str, oracle_dir: str, timeout_s: int):
        import os
        import sys

        return {"PATH": os.environ.get("PATH", ""), "VIRTUAL_ENV": sys.prefix}, None

    monkeypatch.setattr(offline_checks, "_provision_oracle_env", _stub_prov)

    # Run dispatch_accept
    dispatch_accept(case="deveval-mini-calc", offline=True, cases_root=str(cases_dir))

    # Verify printed verdict line
    out = capsys.readouterr().out
    assert "deveval-mini-calc" in out
    assert "not_assessed" in out

    # Verify acceptance.yaml written
    rec = load_acceptance(cases_dir / "deveval-mini-calc")
    assert rec is not None
    assert rec.case_id == "deveval-mini-calc"
    assert rec.verdict == Verdict.NOT_ASSESSED
    assert rec.oracle_id is not None
    assert rec.oracle_id.startswith("sha256:")
    assert rec.oracle_tests == 3
    assert rec.role.value == "corpus"
    assert rec.visibility.value == "public"
    assert rec.exposure == "repo_public"
    assert rec.kroker_commit != ""
    assert rec.updated != ""


def test_dispatch_accept_case_without_language_gives_not_assessed_no_oracle(tmp_path, capsys):
    from sdlc.benchmarks.acceptance import Verdict, load_acceptance
    from sdlc.benchmarks.cli import dispatch_accept

    # probe case with no language
    c_dir = tmp_path / "cases" / "probe-no-lang"
    c_dir.mkdir(parents=True)
    (c_dir / "case.yaml").write_text(
        "case_id: probe-no-lang\n"
        "idea_summary: probe\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n"
        "role: probe\n"
        "visibility: private\n",
        encoding="utf-8",
    )

    dispatch_accept(case="probe-no-lang", offline=True, cases_root=str(tmp_path / "cases"))

    out = capsys.readouterr().out
    assert "probe-no-lang" in out
    assert "not_assessed" in out

    rec = load_acceptance(c_dir)
    assert rec is not None
    assert rec.verdict == Verdict.NOT_ASSESSED
    assert rec.note == "no oracle"


def test_dispatch_accept_smoke_case_with_oracle_and_no_reference_gives_rejected_reference(
    tmp_path, capsys, monkeypatch
):
    from sdlc.benchmarks import offline_checks
    from sdlc.benchmarks.acceptance import Reason, Verdict, load_acceptance
    from sdlc.benchmarks.cli import dispatch_accept

    # smoke case with oracle and no reference/ (like todo-api)
    c_dir = tmp_path / "cases" / "smoke-todo"
    c_dir.mkdir(parents=True)
    (c_dir / "oracle").mkdir()
    (c_dir / "oracle" / "test_api.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (c_dir / "case.yaml").write_text(
        "case_id: smoke-todo\n"
        "idea_summary: todo\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n"
        "language: python\n"
        "role: smoke\n"
        "visibility: public\n",
        encoding="utf-8",
    )

    async def _stub_prov(worktree: str, oracle_dir: str, timeout_s: int):
        import os
        import sys

        return {"PATH": os.environ.get("PATH", ""), "VIRTUAL_ENV": sys.prefix}, None

    monkeypatch.setattr(offline_checks, "_provision_oracle_env", _stub_prov)

    dispatch_accept(case="smoke-todo", offline=True, cases_root=str(tmp_path / "cases"))

    out = capsys.readouterr().out
    assert "smoke-todo" in out
    assert "rejected" in out
    assert "reference" in out

    rec = load_acceptance(c_dir)
    assert rec is not None
    assert rec.verdict == Verdict.REJECTED
    assert rec.reason == Reason.REFERENCE


def test_dispatch_accept_runs_inside_running_asyncio_event_loop(tmp_path, monkeypatch):
    """Regression test: root CLI runs under asyncio.run(main()).
    dispatch_accept and dispatch_benchmark_cmd must execute cleanly inside a running loop.
    """
    import argparse
    import asyncio

    from sdlc.benchmarks import offline_checks
    from sdlc.benchmarks.acceptance import Reason, Verdict, load_acceptance
    from sdlc.benchmarks.cli import dispatch_benchmark_cmd

    c_dir = tmp_path / "cases" / "smoke-todo"
    c_dir.mkdir(parents=True)
    (c_dir / "oracle").mkdir()
    (c_dir / "oracle" / "test_api.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (c_dir / "case.yaml").write_text(
        "case_id: smoke-todo\n"
        "idea_summary: todo\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n"
        "language: python\n"
        "role: smoke\n"
        "visibility: public\n",
        encoding="utf-8",
    )

    async def _stub_prov(worktree: str, oracle_dir: str, timeout_s: int):
        import os
        import sys

        return {"PATH": os.environ.get("PATH", ""), "VIRTUAL_ENV": sys.prefix}, None

    monkeypatch.setattr(offline_checks, "_provision_oracle_env", _stub_prov)

    args = argparse.Namespace(
        cmd="benchmark",
        bench_cmd="accept",
        case="smoke-todo",
        offline=True,
        cases_root=str(tmp_path / "cases"),
    )

    async def _main_entry():
        # Executes while an event loop is active (reproducing root CLI asyncio.run(main()))
        handled = dispatch_benchmark_cmd(args)
        assert handled is True

    asyncio.run(_main_entry())

    rec = load_acceptance(c_dir)
    assert rec is not None
    assert rec.verdict == Verdict.REJECTED
    assert rec.reason == Reason.REFERENCE


# --- benchmark run gate and smoke command (T008) -------------------------------


def _write_test_case(
    tmp_path: Path,
    case_id: str,
    *,
    role: str = "corpus",
    visibility: str = "public",
    arms: list[dict] | None = None,
    models: list[str] | None = None,
) -> Path:
    import yaml

    c_dir = tmp_path / "cases" / case_id
    c_dir.mkdir(parents=True, exist_ok=True)
    case_data: dict = {
        "case_id": case_id,
        "idea_summary": f"summary for {case_id}",
        "harnesses": ["opencode"],
        "models": models or ["anthropic:claude-sonnet-4-6"],
        "judge_model": "openai/gpt-5.2",
        "role": role,
        "visibility": visibility,
    }
    if arms is not None:
        case_data["arms"] = arms

    p = c_dir / "case.yaml"
    p.write_text(yaml.safe_dump(case_data), encoding="utf-8")
    return p


class _DummyHandle:
    async def result(self):
        return "bench-result"


class _DummyClient:
    async def start_workflow(self, *args, **kwargs):
        return _DummyHandle()


async def _fake_connect(*args, **kwargs):
    return _DummyClient()


async def _fail_connect(*args, **kwargs):
    raise AssertionError("Client.connect was reached")


def test_run_gate_corpus_without_stamp_refused_with_smoke_hint_and_commit(tmp_path, monkeypatch):
    import time

    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(tmp_path, "c-corpus", role="corpus")
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fail_connect)

    t0 = time.monotonic()
    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case_file)))
    assert time.monotonic() - t0 < 5.0
    msg = str(excinfo.value)
    assert "sdlc benchmark smoke" in msg
    assert "commit-1234" in msg


def test_run_gate_corpus_with_passing_stamp_reaches_client(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix
    from sdlc.benchmarks.smoke import SmokeStamp, write_stamp

    case_file = _write_test_case(tmp_path, "c-corpus", role="corpus")
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)

    stamp = SmokeStamp(
        kroker_commit="commit-1234",
        bench_run_id="b1",
        passed=True,
        failed_conditions=[],
        written="2026-07-20T10:00:00Z",
    )
    write_stamp(stamp, root=tmp_path / "ops")

    res = asyncio.run(_run_matrix(str(case_file)))
    assert res == "bench-result"


def test_run_gate_skip_smoke_reaches_client_and_prints_message(tmp_path, capsys, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(tmp_path, "c-corpus", role="corpus")
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)

    res = asyncio.run(_run_matrix(str(case_file), skip_smoke=True))
    assert res == "bench-result"
    out = capsys.readouterr().out
    assert "smoke check skipped" in out


def test_run_gate_dirty_tree_refused_even_with_passing_stamp(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix
    from sdlc.benchmarks.smoke import SmokeStamp, write_stamp

    case_file = _write_test_case(tmp_path, "c-corpus", role="corpus")
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", True))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fail_connect)

    stamp = SmokeStamp(
        kroker_commit="commit-1234",
        bench_run_id="b1",
        passed=True,
        failed_conditions=[],
        written="2026-07-20T10:00:00Z",
    )
    write_stamp(stamp, root=tmp_path / "ops")

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case_file)))
    assert "dirty" in str(excinfo.value).lower()


def test_run_gate_smoke_and_probe_cases_need_no_stamp(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)

    smoke_file = _write_test_case(tmp_path, "c-smoke", role="smoke")
    probe_file = _write_test_case(tmp_path, "c-probe", role="probe")

    res_smoke = asyncio.run(_run_matrix(str(smoke_file)))
    assert res_smoke == "bench-result"

    res_probe = asyncio.run(_run_matrix(str(probe_file)))
    assert res_probe == "bench-result"


def test_run_gate_parked_case_refused_without_allow_parked(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(tmp_path, "c-parked", role="parked")
    monkeypatch.setattr("temporalio.client.Client.connect", _fail_connect)

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case_file)))
    assert "parked" in str(excinfo.value).lower()

    # With allow_parked=True reaches client
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)
    res = asyncio.run(_run_matrix(str(case_file), allow_parked=True))
    assert res == "bench-result"


def test_run_gate_arm_flag_reduces_matrix_and_unknown_arm_fails(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(
        tmp_path,
        "c-two-arms",
        role="corpus",
        arms=[
            {"name": "arm-strong", "role_models": {}},
            {"name": "arm-weak", "role_models": {}},
        ],
    )
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fail_connect)

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case_file), arm="arm-unknown", skip_smoke=True))
    msg = str(excinfo.value)
    assert "arm-unknown" in msg
    assert "arm-strong" in msg
    assert "arm-weak" in msg

    # With valid arm reaches client
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)
    res = asyncio.run(_run_matrix(str(case_file), arm="arm-strong", skip_smoke=True))
    assert res == "bench-result"


def test_run_gate_multi_cell_corpus_refused_without_arm_or_all_arms(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(
        tmp_path,
        "c-multi",
        role="corpus",
        arms=[
            {"name": "arm-strong", "role_models": {}},
            {"name": "arm-weak", "role_models": {}},
        ],
    )
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fail_connect)

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(_run_matrix(str(case_file), skip_smoke=True))
    msg = str(excinfo.value)
    assert "arm-strong" in msg
    assert "arm-weak" in msg

    # With all_arms=True reaches client
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)
    res = asyncio.run(_run_matrix(str(case_file), all_arms=True, skip_smoke=True))
    assert res == "bench-result"


def test_run_gate_probe_case_with_two_cells_needs_neither_flag(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import _run_matrix

    case_file = _write_test_case(
        tmp_path,
        "p-multi",
        role="probe",
        arms=[
            {"name": "arm-a", "role_models": {}},
            {"name": "arm-b", "role_models": {}},
        ],
    )
    monkeypatch.setattr("sdlc.benchmarks.cli.resolve_repo_status", lambda: ("commit-1234", False))
    monkeypatch.setenv("SDLC_OPS_ROOT", str(tmp_path / "ops"))
    monkeypatch.setattr("temporalio.client.Client.connect", _fake_connect)

    res = asyncio.run(_run_matrix(str(case_file)))
    assert res == "bench-result"


def test_dispatch_smoke_passing_and_failing(tmp_path, capsys, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sdlc.benchmarks.cli import dispatch_smoke
    from sdlc.benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        CostBag,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.smoke import passing_stamp
    from sdlc.core.models import HarnessKind

    cases_root = tmp_path / "cases"
    _write_test_case(tmp_path, "todo-api", role="smoke")

    ops_dir = tmp_path / "ops"
    bench_dir = tmp_path / "runs"
    monkeypatch.setenv("SDLC_OPS_ROOT", str(ops_dir))
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(bench_dir))

    t0 = datetime(2026, 7, 20, 10, tzinfo=UTC)

    def _make_records(oracle_ok: bool) -> list[BenchmarkRecord]:
        return [
            BenchmarkRecord(
                run_id="r1",
                bench_run_id="b-smoke-pass",
                case_id="todo-api",
                scope=BenchmarkScope.STAGE,
                stage="clarify",
                role="clarify",
                harness=HarnessKind.OPENCODE,
                model="m",
                quality=QualityScore(score=1.0, judge="staged_rubric"),
                cost=CostBag(),
                speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
                outcome=BenchmarkOutcome.PASS,
                kroker_commit="commit-smoke-1",
            ),
            BenchmarkRecord(
                run_id="r1",
                bench_run_id="b-smoke-pass",
                case_id="todo-api",
                scope=BenchmarkScope.STAGE,
                stage="architecture",
                role="architecture",
                harness=HarnessKind.OPENCODE,
                model="m",
                quality=QualityScore(score=1.0, judge="staged_rubric"),
                cost=CostBag(),
                speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
                outcome=BenchmarkOutcome.PASS,
                kroker_commit="commit-smoke-1",
            ),
            BenchmarkRecord(
                run_id="r1",
                bench_run_id="b-smoke-pass",
                case_id="todo-api",
                scope=BenchmarkScope.ORACLE,
                stage="oracle",
                role="oracle",
                harness=HarnessKind.OPENCODE,
                model="deterministic",
                quality=QualityScore(score=1.0 if oracle_ok else 0.0, judge="oracle"),
                cost=CostBag(),
                speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
                outcome=BenchmarkOutcome.PASS if oracle_ok else BenchmarkOutcome.FAIL,
                kroker_commit="commit-smoke-1",
            ),
        ]

    # Write passing records
    store = RecordStore(
        bench_run_id="b-smoke-pass", cell_id="todo-api#opencode#arm", root=str(bench_dir)
    )
    for r in _make_records(oracle_ok=True):
        store.append(r)

    def _stub_run_pass(case_path: str) -> str:
        return "b-smoke-pass"

    out = dispatch_smoke(cases_root=str(cases_root), ops_dir=str(ops_dir), run_fn=_stub_run_pass)
    assert "smoke: PASS commit-smoke-1" in out
    printed = capsys.readouterr().out
    assert "smoke: PASS commit-smoke-1" in printed
    stamp = passing_stamp("commit-smoke-1", root=ops_dir)
    assert stamp is not None
    assert stamp.passed is True

    # Write failing records
    store_fail = RecordStore(
        bench_run_id="b-smoke-fail", cell_id="todo-api#opencode#arm", root=str(bench_dir)
    )
    for r in _make_records(oracle_ok=False):
        store_fail.append(r)

    def _stub_run_fail(case_path: str) -> str:
        return "b-smoke-fail"

    with pytest.raises(SystemExit):
        dispatch_smoke(cases_root=str(cases_root), ops_dir=str(ops_dir), run_fn=_stub_run_fail)
    fail_printed = capsys.readouterr().out
    assert "oracle_all_pass" in fail_printed


def test_dispatch_smoke_runs_inside_running_asyncio_event_loop(tmp_path, monkeypatch):
    """Regression test: root CLI runs under asyncio.run(main()).
    dispatch_smoke and dispatch_benchmark_cmd(smoke) must execute cleanly inside a running loop
    without hitting 'RuntimeError: asyncio.run() cannot be called from a running event loop'.
    """
    import argparse
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sdlc.benchmarks import cli
    from sdlc.benchmarks.cli import dispatch_benchmark_cmd
    from sdlc.benchmarks.models import (
        BenchmarkOutcome,
        BenchmarkRecord,
        BenchmarkScope,
        CostBag,
        QualityScore,
        SpeedBag,
    )
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.benchmarks.smoke import passing_stamp
    from sdlc.core.models import HarnessKind

    cases_root = tmp_path / "cases"
    _write_test_case(tmp_path, "todo-smoke", role="smoke")

    ops_dir = tmp_path / "ops"
    bench_dir = tmp_path / "runs"
    monkeypatch.setenv("SDLC_OPS_ROOT", str(ops_dir))
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(bench_dir))

    t0 = datetime(2026, 7, 20, 10, tzinfo=UTC)
    records = [
        BenchmarkRecord(
            run_id="r1",
            bench_run_id="b-loop-pass",
            case_id="todo-smoke",
            scope=BenchmarkScope.STAGE,
            stage="clarify",
            role="clarify",
            harness=HarnessKind.OPENCODE,
            model="m",
            quality=QualityScore(score=1.0, judge="staged_rubric"),
            cost=CostBag(),
            speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
            outcome=BenchmarkOutcome.PASS,
            kroker_commit="commit-loop-1",
        ),
        BenchmarkRecord(
            run_id="r1",
            bench_run_id="b-loop-pass",
            case_id="todo-smoke",
            scope=BenchmarkScope.STAGE,
            stage="architecture",
            role="architecture",
            harness=HarnessKind.OPENCODE,
            model="m",
            quality=QualityScore(score=1.0, judge="staged_rubric"),
            cost=CostBag(),
            speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
            outcome=BenchmarkOutcome.PASS,
            kroker_commit="commit-loop-1",
        ),
        BenchmarkRecord(
            run_id="r1",
            bench_run_id="b-loop-pass",
            case_id="todo-smoke",
            scope=BenchmarkScope.ORACLE,
            stage="oracle",
            role="oracle",
            harness=HarnessKind.OPENCODE,
            model="deterministic",
            quality=QualityScore(score=1.0, judge="oracle"),
            cost=CostBag(),
            speed=SpeedBag(wall_clock_s=1.0, started_at=t0, ended_at=t0 + timedelta(seconds=1)),
            outcome=BenchmarkOutcome.PASS,
            kroker_commit="commit-loop-1",
        ),
    ]

    store = RecordStore(
        bench_run_id="b-loop-pass", cell_id="todo-smoke#opencode#arm", root=str(bench_dir)
    )
    for r in records:
        store.append(r)

    async def _stub_async_run_matrix(case_path: str, skip_smoke: bool = False) -> str:
        return "b-loop-pass"

    monkeypatch.setattr(cli, "_run_matrix", _stub_async_run_matrix)

    args = argparse.Namespace(
        cmd="benchmark",
        bench_cmd="smoke",
        cases_root=str(cases_root),
        ops_root=str(ops_dir),
    )

    async def _main_entry():
        handled = dispatch_benchmark_cmd(args)
        assert handled is True

    asyncio.run(_main_entry())

    stamp = passing_stamp("commit-loop-1", root=ops_dir)
    assert stamp is not None
    assert stamp.passed is True


def test_benchmark_corpus_cli(tmp_path: Path, capsys):
    from sdlc.benchmarks.cli import build_parser, dispatch_benchmark_cmd

    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    c1 = cases_root / "c1"
    c1.mkdir()
    (c1 / "case.yaml").write_text(
        "case_id: c1\n"
        "idea_summary: sum\n"
        "role: corpus\n"
        "visibility: public\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n",
        encoding="utf-8",
    )

    p = build_parser()
    args = p.parse_args(["benchmark", "corpus", "--cases-root", str(cases_root)])
    assert args.cmd == "benchmark"
    assert args.bench_cmd == "corpus"
    assert args.cases_root == str(cases_root)

    handled = dispatch_benchmark_cmd(args)
    assert handled is True

    captured = capsys.readouterr()
    assert "c1" in captured.out
    assert "0 of 8 accepted or provisional, 0 of 2 private" in captured.out
