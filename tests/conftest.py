"""Shared test fixtures."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Importing sdlc.worker (transitively, from many test modules) pulls in
# pydantic_ai agents that read ANTHROPIC_API_KEY / OPENAI_API_KEY at import
# time. conftest is imported before any test module, so set placeholders here
# at module load so collection-time agent construction succeeds. The autouse
# _llm_api_keys fixture below still monkeypatches per-test for hygiene.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")


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


_HARNESS_AGENT_YAML = (
    b"kind: harness\nharness: opencode\nmodel: zai-coding-plan/glm-5.2\n")
_PROPOSER_AGENT_YAML = b"kind: proposer\nmodel: anthropic:glm-5.2\n"

HARNESS_ROLE_NAMES = ("dev", "test", "devops")
PROPOSER_ROLE_NAMES = ("clarify", "architect", "planner", "qa", "reviewer",
                       "analyst", "merge_verdict", "devops_planner")


def write_registry_dir(root, version=1):
    """Materialise a VALID agents/ tree. Tests perturb exactly one thing after
    calling this, so each assertion fails for the reason under test.

    Grows with the increment: Task 2 adds instructions.md, Task 3 adds
    agent.py. Keep it valid or every caller breaks at once.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "registry.yaml").write_bytes(f"version: {version}\n".encode())
    for name in HARNESS_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_HARNESS_AGENT_YAML)
    for name in PROPOSER_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_PROPOSER_AGENT_YAML)
        (d / "instructions.md").write_bytes(b"do the thing")   # Task 2
    return root
