import os

# Importing sdlc.benchmarks.cli pulls in sdlc.worker -> agents.roles, which
# instantiate pydantic_ai Agents at module load time and require these keys.
# The autouse _llm_api_keys fixture runs at test-time, not collection-time, so
# bootstrap the same placeholders here (mirrors conftest.py / test_benchmark_
# workflow.py).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

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
    out = dispatch_report("b1", source="golden", root=str(tmp_path))
    assert "No records" in out or "case" in out.lower()
