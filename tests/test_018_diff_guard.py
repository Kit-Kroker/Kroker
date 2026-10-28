# tests/test_018_diff_guard.py
"""Read-routes rule 5 (018): the branch diff deny-list (FR-061, SC-007).

Runs only when KROKER_DIFF_GUARD=1 -- the slice gates set it, so a benchmark
worker never pays it. Subprocess git, no network: the diff is the branch's
own changes against its merge base with main.
"""

from __future__ import annotations

import os
import subprocess

import pytest

FORBIDDEN = (
    "src/sdlc/benchmarks/",
    "src/sdlc/stages/",
    "src/sdlc/workflows/",
    "src/sdlc/harness/",
    "src/sdlc/core/",
    "tests/test_compose_opencode_cache_mount_net.py",
    ".claude/settings.json",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


@pytest.mark.skipif(
    os.environ.get("KROKER_DIFF_GUARD") != "1",
    reason="only the slice gates set KROKER_DIFF_GUARD=1 (read-routes rule 5)",
)
def test_branch_diff_respects_the_deny_list() -> None:
    base = _git("merge-base", "HEAD", "main").strip()
    files = _git("diff", "--name-only", base).splitlines()
    touched = [f for f in files if f.replace("\\", "/").startswith(FORBIDDEN)]
    assert touched == [], f"forbidden paths touched on this branch: {touched}"
