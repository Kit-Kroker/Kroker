"""Tests for build_trace_inventory activity (017 T009, US1)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sdlc.stages.analyze.activities import (
    InventoryInput,
    TaskBranchRef,
    build_trace_inventory,
)


def _run(args: list[str], cwd: Path | str) -> str:
    res = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        encoding="utf-8",
        check=True,
        stdin=subprocess.DEVNULL,
    )
    return res.stdout.strip()


def _init_git_repo(root: Path) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "tester@example.com"], root)
    _run(["git", "config", "user.name", "Tester"], root)
    # Write initial file and commit
    (root / "README.md").write_text("initial", encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "init"], root)
    return _run(["git", "rev-parse", "HEAD"], root)


@pytest.mark.asyncio
async def test_trace_inventory_diff_over_60k_lists_every_test(tmp_path: Path):
    """A tree whose diff exceeds 60,000 characters still lists every test name."""
    base_sha = _init_git_repo(tmp_path)

    # Create a large diff (> 60k chars) by writing 70k characters to a file
    large_content = "A" * 70000
    (tmp_path / "large_data.txt").write_text(large_content, encoding="utf-8")

    # Add several tests across files
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_alpha.py").write_text(
        "def test_one(): pass\ndef test_two(): pass\n", encoding="utf-8"
    )
    (tests_dir / "beta_test.py").write_text("def test_three(): pass\n", encoding="utf-8")

    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "large diff and tests"], tmp_path)

    diff_str = _run(["git", "diff", f"{base_sha}..HEAD"], tmp_path)
    assert len(diff_str) > 60000

    inp = InventoryInput(
        integration_wt=str(tmp_path),
        base_sha=base_sha,
        tasks=[],
    )
    inv = await build_trace_inventory(inp)

    assert "tests/test_alpha.py::test_one" in inv.tests
    assert "tests/test_alpha.py::test_two" in inv.tests
    assert "tests/beta_test.py::test_three" in inv.tests
    assert len(inv.tests) == 3


@pytest.mark.asyncio
async def test_trace_inventory_parametrized_and_class_method(tmp_path: Path):
    """Collects parametrized tests and class methods correctly, ignores helpers."""
    base_sha = _init_git_repo(tmp_path)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_methods.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.parametrize('x', [1, 2])\n"
        "def test_parametrized(x):\n"
        "    pass\n\n"
        "class TestSuite:\n"
        "    def test_case_a(self):\n"
        "        pass\n"
        "    def helper_b(self):\n"
        "        pass\n\n"
        "class HelperClass:\n"
        "    def test_ignored(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "add tests"], tmp_path)

    inp = InventoryInput(
        integration_wt=str(tmp_path),
        base_sha=base_sha,
        tasks=[],
    )
    inv = await build_trace_inventory(inp)

    assert "tests/test_methods.py::test_parametrized" in inv.tests
    assert "tests/test_methods.py::TestSuite::test_case_a" in inv.tests
    # helper_b does not start with test
    assert not any("helper_b" in t for t in inv.tests)
    # HelperClass does not start with Test
    assert not any("HelperClass" in t for t in inv.tests)


@pytest.mark.asyncio
async def test_trace_inventory_syntax_error_skipped(tmp_path: Path):
    """A syntax-error test file is skipped and counted, other tests still collected."""
    base_sha = _init_git_repo(tmp_path)

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_valid.py").write_text("def test_works(): pass\n", encoding="utf-8")
    (tests_dir / "test_invalid.py").write_text(
        "def test_broken( this is invalid syntax [[\n", encoding="utf-8"
    )

    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "add valid and broken tests"], tmp_path)

    inp = InventoryInput(
        integration_wt=str(tmp_path),
        base_sha=base_sha,
        tasks=[],
    )
    inv = await build_trace_inventory(inp)

    assert "tests/test_valid.py::test_works" in inv.tests
    assert not any("test_invalid.py" in t for t in inv.tests)


@pytest.mark.asyncio
async def test_trace_inventory_per_task_diffs_and_empty_and_missing(tmp_path: Path):
    """Task 2 diff excludes task 1's files, empty diff gives 0, missing branch gives None."""
    base_sha = _init_git_repo(tmp_path)

    # Task 1 branch
    _run(["git", "checkout", "-b", "branch-task-1"], tmp_path)
    (tmp_path / "file1.txt").write_text("task 1 work", encoding="utf-8")
    _run(["git", "add", "file1.txt"], tmp_path)
    _run(["git", "commit", "-q", "-m", "task 1"], tmp_path)
    t1_head = _run(["git", "rev-parse", "HEAD"], tmp_path)

    # Task 2 branch inherits Task 1's commits
    _run(["git", "checkout", "-b", "branch-task-2"], tmp_path)
    (tmp_path / "file2.txt").write_text("task 2 work", encoding="utf-8")
    _run(["git", "add", "file2.txt"], tmp_path)
    _run(["git", "commit", "-q", "-m", "task 2"], tmp_path)

    # Task 3 branch with empty diff from base
    _run(["git", "checkout", "-b", "branch-task-empty", base_sha], tmp_path)

    # Switch integration tree back to main/task-2
    _run(["git", "checkout", "branch-task-2"], tmp_path)

    inp = InventoryInput(
        integration_wt=str(tmp_path),
        base_sha=base_sha,
        tasks=[
            TaskBranchRef(task_id="t1", branch="branch-task-1", start_ref=base_sha),
            TaskBranchRef(task_id="t2", branch="branch-task-2", start_ref=t1_head),
            TaskBranchRef(task_id="t_empty", branch="branch-task-empty", start_ref=base_sha),
            TaskBranchRef(task_id="t_missing", branch="nonexistent-branch", start_ref=base_sha),
            TaskBranchRef(task_id="t_nostart", branch="branch-task-1", start_ref=None),
        ],
    )
    inv = await build_trace_inventory(inp)

    # t1 changed only file1.txt
    assert inv.task_changed["t1"] == 1
    assert inv.task_files["t1"] == ["file1.txt"]

    # t2 changed only file2.txt (excludes file1.txt inherited from t1)
    assert inv.task_changed["t2"] == 1
    assert inv.task_files["t2"] == ["file2.txt"]

    # t_empty has 0 changed files
    assert inv.task_changed["t_empty"] == 0
    assert inv.task_files["t_empty"] == []

    # missing branch gives None
    assert inv.task_changed["t_missing"] is None
    assert inv.task_files["t_missing"] == []

    # None start_ref gives None
    assert inv.task_changed["t_nostart"] is None
    assert inv.task_files["t_nostart"] == []
