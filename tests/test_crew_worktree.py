# tests/test_crew_worktree.py
"""E-88 §2. The protocol lives inside the worktree because containment
checks _abs_under(path, worktree); it stays out of git because the round
checkpoint runs `git add -A`."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.crew.worktree import (
    ORCH_ROOT, exclude_file, orchestration_dir, prepare_orchestration,
    round_dir,
)


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_orchestration_dir_is_under_the_worktree(tmp_path):
    d = orchestration_dir(tmp_path, "code")
    assert d == tmp_path / ORCH_ROOT / "code"


def test_round_dir_is_named_by_its_round(tmp_path):
    assert round_dir(tmp_path, "code", 2).name == "round-2"


def test_exclude_file_comes_from_git_not_a_hardcoded_path(tmp_path):
    """In a LINKED worktree `.git` is a file and $GIT_DIR points into
    .git/worktrees/<name>/, so a hardcoded '.git/info/exclude' writes to the
    main repository's file and the exclusion silently does nothing."""
    repo = _repo(tmp_path)
    assert exclude_file(repo) == repo / ".git" / "info" / "exclude"


def test_prepare_creates_the_tree_and_excludes_it(tmp_path):
    repo = _repo(tmp_path)
    d = prepare_orchestration(repo, "code")
    assert d.is_dir()
    body = exclude_file(repo).read_text(encoding="utf-8")
    assert "/.workspace/orchestration/" in body.splitlines()


def test_prepare_is_idempotent(tmp_path):
    """A retried activity re-enters here; appending the line twice would be
    harmless but noisy."""
    repo = _repo(tmp_path)
    prepare_orchestration(repo, "code")
    prepare_orchestration(repo, "code")
    lines = exclude_file(repo).read_text(encoding="utf-8").splitlines()
    assert lines.count("/.workspace/orchestration/") == 1


def test_git_add_all_does_not_sweep_the_protocol(tmp_path):
    """The failure this whole mechanism exists to prevent."""
    repo = _repo(tmp_path)
    d = prepare_orchestration(repo, "code")
    (d / "brief.md").write_text("hello", encoding="utf-8")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True).stdout.split()
    assert staged == ["app.py"]


def test_exclude_file_raises_outside_a_repo(tmp_path):
    with pytest.raises(RuntimeError):
        exclude_file(tmp_path / "not-a-repo")
