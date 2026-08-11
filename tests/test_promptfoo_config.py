from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from sdlc.eval.promptfoo.config import build_config

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"
AGENTS = ROOT / "agents"


@pytest.fixture
def tmp_path():
    """Scratch dir UNDER THE REPO, overriding pytest's built-in tmp_path.

    build_config emits provider paths relative to the config's directory
    (promptfoo joins the two), and a relative path cannot span Windows
    drives -- pytest's tmp_path lives on C: while the repo may be on D:.
    run_gate has the same constraint and solves it the same way, so this
    also keeps the tests faithful to production.
    """
    root = ROOT / "runs" / ".prompt_gate_tests"
    root.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=root))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _cfg(tmp_path: Path) -> dict:
    p = build_config("clarify", "add-login-greenfield", repo_root=ROOT,
                     cases_root=CASES, agents_dir=AGENTS,
                     judge_model="openai/gpt-5.2", out_dir=tmp_path)
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_emits_exactly_two_providers_labelled_baseline_and_working(tmp_path):
    labels = [p["label"] for p in _cfg(tmp_path)["providers"]]
    assert labels == ["baseline", "working"]


def test_providers_differ_only_in_instructions_ref(tmp_path):
    base, work = _cfg(tmp_path)["providers"]
    assert base["config"]["instructions_ref"] == "HEAD"
    assert work["config"]["instructions_ref"] == "worktree"
    assert base["id"] == work["id"]
    assert base["config"]["fixture_path"] == work["config"]["fixture_path"]


def test_carries_both_assertion_families(tmp_path):
    asserts = _cfg(tmp_path)["defaultTest"]["assert"]
    values = [str(a.get("value")) for a in asserts]
    assert any("absolute.py" in v for v in values)
    assert any("assertion.py" in v for v in values)


def test_carries_the_native_cost_and_latency_gates(tmp_path):
    """Spec 4.5 lists cost and latency as ABSOLUTE gating checks."""
    types = {a["type"] for a in _cfg(tmp_path)["defaultTest"]["assert"]}
    assert "cost" in types
    assert "latency" in types


def test_baseline_ref_is_threaded_not_hardcoded(tmp_path):
    p = build_config("clarify", "add-login-greenfield", repo_root=ROOT,
                     cases_root=CASES, agents_dir=AGENTS,
                     judge_model="openai/gpt-5.2", out_dir=tmp_path,
                     baseline_ref="main")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["providers"][0]["config"]["instructions_ref"] == "main"


def test_vars_carry_what_the_assertions_read(tmp_path):
    v = _cfg(tmp_path)["defaultTest"]["vars"]
    for key in ("role", "case", "author_model", "judge_model",
                "cases_root", "agents_dir"):
        assert key in v, key


def test_fixture_is_written_next_to_the_config(tmp_path):
    build_config("clarify", "add-login-greenfield", repo_root=ROOT,
                 cases_root=CASES, agents_dir=AGENTS,
                 judge_model="openai/gpt-5.2", out_dir=tmp_path)
    assert (tmp_path / "fixture.json").is_file()
