"""Temporal activities — all the non-deterministic work.

Activities run in the worker process; workflows never touch subprocesses,
the filesystem, or the network directly.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass

from temporalio import activity

from .harness.adapters import HARNESSES, HarnessRequest
from .models import HarnessKind, HarnessRunResult, QAReport


def _worktrees_root() -> str:
    """Read at call time so tests can point it at a temp dir."""
    return os.environ.get("SDLC_WORKTREES_ROOT", "/var/sdlc/worktrees")


@dataclass
class WorktreeInput:
    repo_path: str
    run_id: str
    task_id: str
    from_ref: str          # integration head SHA (ADR-14) — NOT base_branch


@dataclass
class WorktreeHandle:
    path: str
    branch: str
    branch_point: str      # SHA the task branched from (diff anchor)


@activity.defn
async def create_worktree(inp: WorktreeInput) -> WorktreeHandle:
    """Run-scoped worktree + branch, cut from the integration head."""
    path = f"{_worktrees_root()}/{inp.run_id}/{inp.task_id}"
    branch = f"sdlc/{inp.run_id}/{inp.task_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, path, inp.from_ref],
        cwd=inp.repo_path, check=True, capture_output=True,
    )
    point = subprocess.run(
        ["git", "rev-parse", inp.from_ref], cwd=inp.repo_path,
        capture_output=True, text=True).stdout.strip()
    return WorktreeHandle(path=path, branch=branch, branch_point=point)


@dataclass
class IntegrationInput:
    repo_path: str
    run_id: str
    base_branch: str


@activity.defn
async def setup_integration_branch(inp: IntegrationInput) -> str:
    """Create sdlc/<run>/integration from base in its own worktree;
    return its head SHA. Task worktrees branch from this head."""
    branch = f"sdlc/{inp.run_id}/integration"
    path = f"{_worktrees_root()}/{inp.run_id}/integration"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, path, inp.base_branch],
        cwd=inp.repo_path, check=True, capture_output=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path,
        capture_output=True, text=True).stdout.strip()


@dataclass
class MergeInput:
    repo_path: str
    run_id: str
    task_branch: str


@dataclass
class MergeResult:
    merged: bool
    conflict: bool
    integration_head: str


@activity.defn
async def merge_into_integration(inp: MergeInput) -> MergeResult:
    """Merge a completed task branch into the run's integration branch.
    A merge conflict = a falsified `overlaps` declaration (Finding #1):
    abort cleanly and report it so the caller serializes/escalates."""
    ipath = f"{_worktrees_root()}/{inp.run_id}/integration"
    merge = subprocess.run(
        ["git", "merge", "--no-ff", "-m", f"merge {inp.task_branch}",
         inp.task_branch],
        cwd=ipath, capture_output=True, text=True)
    if merge.returncode != 0:
        # Distinguish a real conflict from an infra/config failure via the
        # git index's unmerged entries (locale-independent) — must be read
        # BEFORE `merge --abort`, which clears the unmerged state.
        unmerged = subprocess.run(["git", "ls-files", "--unmerged"], cwd=ipath,
                                  capture_output=True, text=True).stdout
        subprocess.run(["git", "merge", "--abort"], cwd=ipath,
                       capture_output=True)
        if not unmerged.strip():
            raise RuntimeError(
                f"git merge failed (not a conflict): {merge.stderr.strip()}")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ipath,
                              capture_output=True, text=True).stdout.strip()
        return MergeResult(merged=False, conflict=True, integration_head=head)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ipath,
                          capture_output=True, text=True).stdout.strip()
    return MergeResult(merged=True, conflict=False, integration_head=head)


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
    branch_point: str      # SHA the task branched from — NOT base_branch
    max_chars: int = 60_000


@activity.defn
async def get_task_diff(inp: DiffInput) -> dict:
    """Materialized diff for clean-context validators (FR-804), anchored to
    the task's branch point so a dependent task's diff shows only its own
    change — upstream work is invisible (Finding #1)."""
    rng = f"{inp.branch_point}...HEAD"
    stat = subprocess.run(
        ["git", "diff", "--stat", rng],
        cwd=inp.worktree, capture_output=True, text=True).stdout
    patch = subprocess.run(
        ["git", "diff", rng],
        cwd=inp.worktree, capture_output=True, text=True).stdout
    files = subprocess.run(
        ["git", "diff", "--name-only", rng],
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
