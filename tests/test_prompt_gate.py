from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdlc.eval.gate import GateUnavailable, prompt_sha, run_gate
from sdlc.eval.promptfoo import promptfoo_bin
from sdlc.eval.verdict import GateVerdict

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"
AGENTS = ROOT / "agents"

_OPT_IN = os.environ.get("SDLC_PROMPT_EVAL") == "1"


def test_prompt_sha_matches_the_registry_hash():
    """The join key to BenchmarkRecord.prompt_sha must be the same sha256
    over the same bytes (agents/roles.py:108-111)."""
    import hashlib
    text = (AGENTS / "clarify" / "instructions.md").read_text(
        encoding="utf-8")
    assert prompt_sha("clarify", "worktree", ROOT, AGENTS) == (
        hashlib.sha256(text.encode()).hexdigest())


def test_missing_promptfoo_raises_when_explicitly_opted_in(monkeypatch):
    """Opt-in means 'I intend to run this'. Silently skipping an explicitly
    requested gate is the worst outcome available (design doc 6)."""
    monkeypatch.setattr("sdlc.eval.gate.promptfoo_bin", lambda: None)
    with pytest.raises(GateUnavailable) as e:
        run_gate("clarify", "add-login-greenfield", repo_root=ROOT,
                 cases_root=CASES, agents_dir=AGENTS,
                 judge_model="openai/gpt-5.2")
    assert "eval" in str(e.value)


def test_unchanged_prompt_passes_without_calling_a_model(monkeypatch, tmp_path):
    """Working tree == HEAD -> early exit, zero model calls."""
    monkeypatch.setattr("sdlc.eval.gate.promptfoo_bin", lambda: "promptfoo")
    monkeypatch.setattr(
        "sdlc.eval.gate._run_promptfoo",
        lambda *a, **k: pytest.fail("must not run promptfoo"))
    res = run_gate("clarify", "add-login-greenfield", repo_root=ROOT,
                   cases_root=CASES, agents_dir=AGENTS,
                   judge_model="openai/gpt-5.2", out_dir=tmp_path)
    assert res.verdict is GateVerdict.PASS
    assert "unchanged" in res.reason.lower()


def test_planned_call_count_over_the_ceiling_is_refused(monkeypatch, tmp_path):
    """Spec 6 runaway guard: refuse BEFORE spending, not after."""
    monkeypatch.setattr("sdlc.eval.gate.promptfoo_bin", lambda: "promptfoo")
    monkeypatch.setattr("sdlc.eval.gate.prompt_sha",
                        lambda role, ref, *a: ref)   # force base != working
    monkeypatch.setattr(
        "sdlc.eval.gate._run_promptfoo",
        lambda *a, **k: pytest.fail("must not run promptfoo"))
    with pytest.raises(GateUnavailable) as e:
        run_gate("clarify", "add-login-greenfield", repo_root=ROOT,
                 cases_root=CASES, agents_dir=AGENTS,
                 judge_model="openai/gpt-5.2", repeat=50, max_calls=40,
                 out_dir=tmp_path)
    assert "200" in str(e.value)          # 50 * 2 providers * 2 calls


@pytest.mark.prompt_eval
@pytest.mark.skipif(not _OPT_IN, reason="set SDLC_PROMPT_EVAL=1 to run")
@pytest.mark.skipif(promptfoo_bin() is None,
                    reason="promptfoo not installed")
@pytest.mark.parametrize("role,case", [
    ("clarify", "add-login-greenfield"),
    ("clarify", "cat-cafe-monitoring"),
    ("clarify", "todo-api-greenfield"),
    ("planner", "cat-cafe-monitoring"),
    ("qa", "cat-cafe-monitoring"),
])
def test_prompt_gate(role, case, tmp_path):
    res = run_gate(role, case, repo_root=ROOT, cases_root=CASES,
                   agents_dir=AGENTS, judge_model="openai/gpt-5.2",
                   out_dir=tmp_path)
    assert res.verdict in (GateVerdict.PASS,), (
        f"{role}/{case}: {res.verdict.value} — {res.reason}")
