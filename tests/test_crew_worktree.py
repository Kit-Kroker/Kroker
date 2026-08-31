# tests/test_crew_worktree.py
"""E-88 §2. The protocol lives inside the worktree because containment
checks _abs_under(path, worktree); it stays out of the diff because
checkpoint_round's add is pathspec-scoped (see test_crew_checkpoint.py),
not because of any exclude file."""
from __future__ import annotations

import subprocess

from sdlc.crew.worktree import (
    ORCH_ROOT, orchestration_dir, prepare_orchestration, round_dir,
)


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_orchestration_dir_is_under_the_worktree(tmp_path):
    d = orchestration_dir(tmp_path, "code")
    assert d == tmp_path / ORCH_ROOT / "code"


def test_round_dir_is_named_by_its_round(tmp_path):
    assert round_dir(tmp_path, "code", 2).name == "round-2"


def test_prepare_creates_the_tree(tmp_path):
    d = prepare_orchestration(tmp_path, "code")
    assert d.is_dir()


def test_prepare_touches_no_git_state(tmp_path):
    """info/exclude lives in the git COMMON dir: in a linked worktree (which
    create_worktree makes) it is the MAIN repo's file, shared across
    parallel tasks and persisted after the run. Preparing the tree must
    write nothing there."""
    repo = _repo(tmp_path)
    prepare_orchestration(repo, "code")
    exclude = repo / ".git" / "info" / "exclude"
    body = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    assert "/.workspace/orchestration/" not in body.splitlines()
