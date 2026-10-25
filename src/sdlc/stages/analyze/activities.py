"""Analyze stage activities (spec A §5, 017 T009, US1)."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from pydantic import BaseModel, Field
from temporalio import activity

from ...vcs.git import _git
from .models import TraceInventory

logger = logging.getLogger(__name__)


class TaskBranchRef(BaseModel):
    task_id: str
    branch: str
    start_ref: str | None = None


class InventoryInput(BaseModel):
    integration_wt: str
    base_sha: str
    tasks: list[TaskBranchRef] = Field(default_factory=list)


def _scan_tests_ast(root: Path) -> tuple[list[str], int]:
    """Scan python files matching test_*.py or *_test.py for test definitions."""
    tests: list[str] = []
    parse_errors = 0
    if not root.is_dir():
        return tests, parse_errors

    for p in sorted(root.rglob("*.py")):
        if not (p.name.startswith("test_") or p.name.endswith("_test.py")):
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            rel = p.name
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=rel)
        except Exception as exc:
            parse_errors += 1
            logger.warning("parse error in %s: %s", rel, exc)
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test"
            ):
                tests.append(f"{rel}::{node.name}")
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for sub in node.body:
                    if isinstance(
                        sub, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) and sub.name.startswith("test"):
                        tests.append(f"{rel}::{node.name}::{sub.name}")

    return sorted(tests), parse_errors


@activity.defn
async def build_trace_inventory(inp: InventoryInput) -> TraceInventory:
    """Build static inventories for trace enforcement (contract C-1, research D-3)."""
    # 1. Inventory (a): changed_files via git diff --name-only <base_sha>
    diff_proc = _git(["diff", "--name-only", inp.base_sha], cwd=inp.integration_wt)
    if diff_proc.returncode == 0:
        raw_changed = [
            line.strip().replace("\\", "/")
            for line in diff_proc.stdout.splitlines()
            if line.strip()
        ]
    else:
        logger.warning("git diff failed for base_sha %s: %s", inp.base_sha, diff_proc.stderr)
        raw_changed = []

    truncated_changed = (len(raw_changed) > 2000) or any(len(p) > 300 for p in raw_changed)
    changed_files = [p[:300] for p in raw_changed[:2000]]

    # 2. Inventory (b): tests via ast scan
    raw_tests, parse_errors = _scan_tests_ast(Path(inp.integration_wt))
    if parse_errors > 0:
        logger.info("build_trace_inventory skipped %d unparseable test file(s)", parse_errors)
    truncated_tests = (len(raw_tests) > 2000) or any(len(t) > 200 for t in raw_tests)
    tests = [t[:200] for t in raw_tests[:2000]]

    # 3. Inventory (c): tree via git ls-files
    ls_proc = _git(["ls-files"], cwd=inp.integration_wt)
    if ls_proc.returncode == 0:
        raw_tree = sorted(
            line.strip().replace("\\", "/") for line in ls_proc.stdout.splitlines() if line.strip()
        )
    else:
        logger.warning("git ls-files failed: %s", ls_proc.stderr)
        raw_tree = []

    truncated_tree = (len(raw_tree) > 2000) or any(len(p) > 300 for p in raw_tree)
    tree = [p[:300] for p in raw_tree[:2000]]

    # 4. Inventory (d): task_changed and task_files
    task_changed: dict[str, int | None] = {}
    task_files: dict[str, list[str]] = {}
    truncated_task_changed = len(inp.tasks) > 2000

    for t in inp.tasks[:2000]:
        if not t.start_ref or not t.branch:
            task_changed[t.task_id] = None
            task_files[t.task_id] = []
            continue

        proc = _git(["diff", "--name-only", f"{t.start_ref}..{t.branch}"], cwd=inp.integration_wt)
        if proc.returncode != 0:
            task_changed[t.task_id] = None
            task_files[t.task_id] = []
        else:
            raw_files = [
                line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()
            ]
            task_changed[t.task_id] = len(raw_files)
            task_files[t.task_id] = [f[:300] for f in raw_files[:2000]]
            if len(raw_files) > 2000 or any(len(f) > 300 for f in raw_files):
                truncated_task_changed = True

    truncated = {
        "changed_files": truncated_changed,
        "tests": truncated_tests,
        "tree": truncated_tree,
        "task_changed": truncated_task_changed,
    }

    return TraceInventory(
        changed_files=changed_files,
        tests=tests,
        tree=tree,
        task_changed=task_changed,
        task_files=task_files,
        truncated=truncated,
    )


ACTIVITIES = [build_trace_inventory]
