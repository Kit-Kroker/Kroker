"""compare() orchestration, with a fake judge (no model calls). git-ref and
rubric IO exercised against tmp dirs."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdlc.benchmarks.judge import _set_judge_fn
from sdlc.eval.compare import (
    EvalError, RUBRIC_KEY, compare, load_rubric, read_ref_text,
)
from sdlc.eval.fixtures import EvalFixture, write_fixtures


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


def _repo_with_instructions(root: Path, role: str, committed: str, working: str):
    role_dir = root / "agents" / role
    role_dir.mkdir(parents=True)
    (role_dir / "instructions.md").write_bytes(committed.encode())
    _git(root, "init"); _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    (role_dir / "instructions.md").write_bytes(working.encode())   # dirty tree


def _case_with_rubric(cases_root: Path, case: str, role: str, rubric_body: str):
    cdir = cases_root / case
    cdir.mkdir(parents=True)
    key = RUBRIC_KEY[role]
    (cdir / f"rubric-{key}.md").write_bytes(rubric_body.encode())
    (cdir / "case.yaml").write_text(
        f"case_id: {case}\nrubrics:\n  {key}: rubric-{key}.md\n", encoding="utf-8")


def test_read_ref_text_reads_committed_version(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "COMMITTED", "WORKING")
    got = read_ref_text("HEAD", "agents/reviewer/instructions.md", tmp_path)
    assert got == "COMMITTED"


def test_read_ref_text_none_when_missing(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "X", "Y")
    assert read_ref_text("HEAD", "agents/reviewer/fixtures/nope.md", tmp_path) is None


def test_load_rubric_from_case_yaml(tmp_path):
    _case_with_rubric(tmp_path, "c1", "clarify", "RUBRIC TEXT")
    assert load_rubric("c1", "clarify", tmp_path) == "RUBRIC TEXT"


def test_load_rubric_missing_raises(tmp_path):
    (tmp_path / "c1").mkdir()
    (tmp_path / "c1" / "case.yaml").write_text("case_id: c1\nrubrics: {}\n",
                                               encoding="utf-8")
    with pytest.raises(EvalError, match="rubric"):
        load_rubric("c1", "reviewer", tmp_path)


def test_compare_scores_both_and_reports_delta(tmp_path, monkeypatch):
    _repo_with_instructions(tmp_path, "reviewer", "OLD PROMPT", "NEW PROMPT")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "be good")
    fx = EvalFixture(role="reviewer", case="c1", prompt="input",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")

    # runner returns the system prompt it saw, so the fake judge can score A!=B
    monkeypatch.setattr("sdlc.eval.compare.run_variant",
                        lambda role, text, fixture, agents_dir, **k: text)
    _set_judge_fn(lambda inp: '{"score": %s, "components": {}}'
                  % ("0.9" if "NEW" in inp.artifact_json else "0.5"))
    try:
        rep = compare("reviewer", "c1", against_ref="HEAD", k=1,
                      agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                      repo_root=tmp_path, judge_model="openai/gpt-5.2")
    finally:
        _set_judge_fn(None)
    assert rep.mean_a == 0.5 and rep.mean_b == 0.9
    assert round(rep.mean_delta, 2) == 0.4
    assert not rep.unchanged


def test_compare_short_circuits_when_unchanged(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "SAME", "SAME")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "r")
    fx = EvalFixture(role="reviewer", case="c1", prompt="i",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")
    rep = compare("reviewer", "c1", against_ref="HEAD", k=1,
                  agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                  repo_root=tmp_path, judge_model="openai/gpt-5.2")
    assert rep.unchanged and rep.runs == []


def test_compare_rejects_same_family_judge(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "A", "B")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "r")
    fx = EvalFixture(role="reviewer", case="c1", prompt="i",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")
    with pytest.raises(EvalError, match="family"):
        compare("reviewer", "c1", against_ref="HEAD", k=1,
                agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                repo_root=tmp_path, judge_model="anthropic:other")  # same family
