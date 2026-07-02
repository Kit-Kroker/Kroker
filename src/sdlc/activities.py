"""Temporal activities — all the non-deterministic work.

Activities run in the worker process; workflows never touch subprocesses,
the filesystem, or the network directly.
"""
from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass

from temporalio import activity

from .harness.adapters import HARNESSES, HarnessRequest
from .models import HarnessKind, HarnessRunResult, QAReport

WORKTREES_ROOT = "/var/sdlc/worktrees"


@dataclass
class WorktreeInput:
    repo_path: str
    task_id: str
    base_branch: str


@activity.defn
async def create_worktree(inp: WorktreeInput) -> str:
    """Isolated worktree + branch per task; returns worktree path."""
    path = f"{WORKTREES_ROOT}/{inp.task_id}"
    branch = f"sdlc/{inp.task_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, path, inp.base_branch],
        cwd=inp.repo_path, check=True, capture_output=True,
    )
    return path


@dataclass
class CodingTaskInput:
    harness: HarnessKind
    prompt: str
    worktree: str
    model: str | None = None
    session_id: str | None = None
    timeout_s: int = 3600


@activity.defn
async def run_coding_task(inp: CodingTaskInput) -> HarnessRunResult:
    """Execute claude -p / opencode run inside the task worktree.

    Long-running: heartbeats while the harness streams output so Temporal
    can detect a hung/dead worker and retry elsewhere.
    """
    harness = HARNESSES[inp.harness]
    result = await harness.run(
        HarnessRequest(
            prompt=inp.prompt, cwd=inp.worktree, model=inp.model,
            session_id=inp.session_id, timeout_s=inp.timeout_s,
        ),
        heartbeat=activity.heartbeat,
    )
    # Checkpoint commit — the resume point if anything downstream fails.
    subprocess.run(["git", "add", "-A"], cwd=inp.worktree, check=True)
    commit = subprocess.run(
        ["git", "commit", "-m", f"sdlc checkpoint (exit={result.exit_code})",
         "--allow-empty"],
        cwd=inp.worktree, capture_output=True, text=True,
    )
    if commit.returncode == 0:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=inp.worktree,
                             capture_output=True, text=True).stdout.strip()
        result.commit_sha = sha
    return result


@dataclass
class DiffInput:
    worktree: str
    base_branch: str
    max_chars: int = 60_000


@activity.defn
async def get_task_diff(inp: DiffInput) -> dict:
    """Materialized diff for clean-context validators (FR-804).

    Validators judge the diff + contract + test output — never the
    implementer's narrative. Large diffs are truncated here and should be
    claim-checked to the artifact store in production.
    """
    stat = subprocess.run(
        ["git", "diff", "--stat", f"{inp.base_branch}...HEAD"],
        cwd=inp.worktree, capture_output=True, text=True).stdout
    patch = subprocess.run(
        ["git", "diff", f"{inp.base_branch}...HEAD"],
        cwd=inp.worktree, capture_output=True, text=True).stdout
    files = subprocess.run(
        ["git", "diff", "--name-only", f"{inp.base_branch}...HEAD"],
        cwd=inp.worktree, capture_output=True, text=True).stdout.splitlines()
    return {"stat": stat, "patch": patch[:inp.max_chars], "files": files}


@dataclass
class QAInput:
    worktree: str
    test_cmd: str = "pytest -q --maxfail=25"


@activity.defn
async def run_test_suite(inp: QAInput) -> QAReport:
    proc = await asyncio.create_subprocess_shell(
        inp.test_cmd, cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    out = out_b.decode(errors="replace")
    failing = [ln.split(" ")[0] for ln in out.splitlines()
               if ln.startswith("FAILED")]
    return QAReport(tests_passed=proc.returncode == 0,
                    failing_tests=failing[:50],
                    issues=[] if proc.returncode == 0
                    else [out[-2000:]])


@dataclass
class PROpenInput:
    worktree: str
    title: str
    body: str
    base_branch: str


@activity.defn
async def open_pull_request(inp: PROpenInput) -> str:
    subprocess.run(["git", "push", "-u", "origin", "HEAD"],
                   cwd=inp.worktree, check=True)
    pr = subprocess.run(
        ["gh", "pr", "create", "--title", inp.title, "--body", inp.body,
         "--base", inp.base_branch],
        cwd=inp.worktree, check=True, capture_output=True, text=True,
    )
    return pr.stdout.strip()  # PR url


@dataclass
class DeployInput:
    environment: str
    version: str
    command: str  # e.g. "make deploy ENV=staging"
    cwd: str


@activity.defn
async def deploy(inp: DeployInput) -> str:
    proc = await asyncio.create_subprocess_shell(
        inp.command, cwd=inp.cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"deploy failed: {out_b.decode()[-2000:]}")
    return out_b.decode(errors="replace")[-2000:]
