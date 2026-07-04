"""Shared test fixtures."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def run_git(args: list[str], cwd: str | Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True,
    ).stdout


@pytest.fixture(autouse=True)
def _llm_api_keys(monkeypatch):
    """Importing ``sdlc.worker`` pulls in pydantic_ai agents that read
    ANTHROPIC_API_KEY / OPENAI_API_KEY at import time. Set placeholder
    values so deferred in-package imports inside tests never fail."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A fresh git repo with one commit on `main`, plus a writable
    worktrees root so the activities never touch /var."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(["init", "-b", "main"], repo)
    run_git(["config", "user.email", "t@t.co"], repo)
    run_git(["config", "user.name", "sdlc-test"], repo)
    (repo / "README.md").write_text("seed\n")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "seed"], repo)
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    return str(repo)
