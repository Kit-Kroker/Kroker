"""Mutations are injected, never written to the worktree.

run_gate resolves its baseline with `git show HEAD:agents/<role>/...`, so
editing the file on disk would move BOTH sides and measure nothing."""
import shutil as _shutil
import tempfile as _tf
from pathlib import Path

import pytest
import yaml

from sdlc.agents.loader import _resolve_agents_dir
from sdlc.eval.promptfoo.config import build_config
from sdlc.eval.promptfoo.provider import call_api

_REPO = Path(__file__).resolve().parents[1]
_CASES = _REPO / "benchmarks" / "cases"


@pytest.fixture
def repo_out_dir():
    # config.build_config's _rel_file_url uses os.path.relpath, which cannot
    # span drives on Windows. pytest's tmp_path is on C: while the repo is on
    # D:, so the out_dir MUST live under the repo -- the same discipline
    # gate.py applies to its runs/.prompt_gate scratch root.
    runs = _REPO / "runs"
    runs.mkdir(exist_ok=True)
    d = Path(_tf.mkdtemp(dir=str(runs)))
    yield d
    _shutil.rmtree(d, ignore_errors=True)


def test_mutation_lands_only_on_the_working_provider(repo_out_dir):
    cfg_path = build_config(
        "clarify", "add-login-greenfield", repo_root=_REPO,
        cases_root=_CASES, agents_dir=_resolve_agents_dir(),
        judge_model="google:gemini-3.5-flash", out_dir=repo_out_dir,
        mutation="Answer briefly.")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    baseline, working = cfg["providers"]
    assert baseline["label"] == "baseline"
    assert "instructions_text" not in baseline["config"]
    assert baseline["config"]["instructions_ref"] == "HEAD"
    assert working["config"]["instructions_text"] == "Answer briefly."


def test_no_mutation_leaves_the_config_unchanged(repo_out_dir):
    cfg_path = build_config(
        "clarify", "add-login-greenfield", repo_root=_REPO,
        cases_root=_CASES, agents_dir=_resolve_agents_dir(),
        judge_model="google:gemini-3.5-flash", out_dir=repo_out_dir)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    for p in cfg["providers"]:
        assert "instructions_text" not in p["config"]


def test_call_api_prefers_literal_text_over_the_git_ref(monkeypatch, tmp_path):
    """No model call and no `git show`: the literal body must win outright."""
    import sdlc.eval.promptfoo.provider as prov

    seen = {}

    class _Usage:
        input_tokens = 1
        output_tokens = 1
        cache_read_tokens = 0
        cache_write_tokens = 0

    def _fake_run_variant_detailed(role, instructions, fixture, agents_dir,
                                   *, model_override=None):
        seen["instructions"] = instructions
        return "{}", _Usage()

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("resolve_instructions must not be called when "
                             "instructions_text is supplied")

    monkeypatch.setattr(prov, "run_variant_detailed",
                        _fake_run_variant_detailed)
    monkeypatch.setattr(prov, "resolve_instructions", _must_not_be_called)

    # EvalFixture requires role, case, prompt, model, source_run_id.
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '{"role": "clarify", "case": "add-login-greenfield", '
        '"prompt": "p", "model": "anthropic:glm-5.2", '
        '"source_run_id": "test"}', encoding="utf-8")

    out = call_api("", {"config": {
        "role": "clarify", "fixture_path": str(fixture_path),
        "agents_dir": str(_resolve_agents_dir()), "repo_root": str(_REPO),
        "instructions_ref": "HEAD",
        "instructions_text": "Answer briefly."}}, {})
    assert out["error"] is None
    assert seen["instructions"] == "Answer briefly."
