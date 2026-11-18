"""026 T012 (FR-011, research R4 part 2, skeptic 4): safe lint autofix runs
inside run_coding_task, BEFORE the checkpoint commit.

Contract (T013 implements):
- `PythonToolchain.lint_fix_cmd(files)` is
  `ruff check --fix --force-exclude --exit-zero --no-cache -- <files>`
  (never `--unsafe-fixes`); the base adapter returns None.
- run_coding_task lists the `*.py` files the attempt changed
  (`git status --porcelain`), drops fenced paths (`repair_patterns(policy)`)
  on a repair attempt, runs the command in the worktree with a bounded
  shell, and commits the result in the SAME checkpoint commit.
- `HarnessRunResult.lint_autofix: LintAutofix(files, rules) | None`.
- An autofix failure logs WARNING and never blocks the checkpoint.

Fixtures run the real ruff (0.16.x flags I001 with no config) in a
worktree under tmp_path; the harness is a stub whose "work" writes files.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

import sdlc.stages.code.activities
from sdlc.core.models import HarnessKind
from sdlc.harness.claude_code import ClaudeCodeHarness
from sdlc.harness.models import HarnessRunResult
from sdlc.stages.code.activities import CodingTaskInput, run_coding_task
from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter
from sdlc.vcs import IntegrationInput, WorktreeInput, create_worktree, setup_integration_branch
from sdlc.vcs.git import DriftInput, _git, check_test_drift
from tests.conftest import run_git

_ACTIVITIES_LOGGER = "sdlc.stages.code.activities"
FIX_PREFIX = "ruff check --fix --force-exclude --exit-zero --no-cache -- "

UNSORTED = "import json\nimport asyncio\n\nprint(json.dumps({}), asyncio.sleep)\n"
SORTED = "import asyncio\nimport json\n\nprint(json.dumps({}), asyncio.sleep)\n"
UNSORTED_TEST = "import json\nimport asyncio\n\n\ndef test_x():\n    assert json and asyncio\n"

FENCE_POLICY = (
    "version: 1\n"
    "rules:\n"
    "  - id: freeze\n"
    "    layer: native\n"
    "    phase: repair\n"
    "    tools: [Write, Edit]\n"
    "    predicate: path_matches\n"
    "    patterns: ['tests/**']\n"
    "    reason: frozen\n"
)


class _WritingHarness(ClaudeCodeHarness):
    """A real ClaudeCodeHarness (so containment compiles) whose run() only
    writes `files` into the worktree, standing in for the agent's edits."""

    def __init__(self, files: dict[str, str]):
        super().__init__()
        self._files = files

    async def run(self, req, heartbeat=None):
        for rel, text in self._files.items():
            p = Path(req.cwd, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return HarnessRunResult(harness=self.kind, exit_code=0, summary="stub")


@pytest.fixture
def py_repo(git_repo):
    """git_repo plus a Python marker, a committed I001 file the attempt will
    NOT touch, and a committed test file under the fenced glob."""
    repo = Path(git_repo)
    (repo / "requirements.txt").write_text("\n", encoding="utf-8")
    (repo / "legacy.py").write_text(UNSORTED, encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "python seed"], repo)
    return git_repo


def _worktree(repo: str, run_id: str) -> str:
    setup = asyncio.run(
        setup_integration_branch(
            IntegrationInput(repo_path=repo, run_id=run_id, base_branch="main")
        )
    )
    wt = asyncio.run(
        create_worktree(
            WorktreeInput(repo_path=repo, run_id=run_id, task_id="T", from_ref=setup.head_sha)
        )
    )
    return wt.path


def _run(monkeypatch, wt: str, files: dict[str, str], **inp):
    monkeypatch.setitem(
        sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, _WritingHarness(files)
    )
    return asyncio.run(
        run_coding_task(
            CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="p", worktree=wt, **inp)
        )
    )


def _show(wt: str, rev: str, path: str) -> str:
    return _git(["show", f"{rev}:{path}"], wt).stdout


def _porcelain(wt: str) -> str:
    return _git(["status", "--porcelain"], wt).stdout


def _changed_in_head(wt: str) -> set[str]:
    out = _git(["diff", "--name-only", "HEAD~1", "HEAD"], wt).stdout
    return {ln for ln in out.splitlines() if ln}


@pytest.fixture
def spy(monkeypatch):
    """Capture every file list handed to PythonToolchain.lint_fix_cmd while
    still returning the contract's command (so the real ruff runs)."""
    calls: list[list[str]] = []

    def lint_fix_cmd(self, files):
        calls.append(list(files))
        return FIX_PREFIX + " ".join(files)

    monkeypatch.setattr(PythonToolchain, "lint_fix_cmd", lint_fix_cmd, raising=False)
    return calls


# --- (a) the adapter command ------------------------------------------------


def test_python_lint_fix_cmd_is_the_safe_fix_command():
    cmd = PythonToolchain().lint_fix_cmd(["a.py", "pkg/b.py"])
    assert cmd == FIX_PREFIX + "a.py pkg/b.py"
    assert "--unsafe-fixes" not in cmd


def test_base_adapter_lint_fix_cmd_is_none():
    """A concrete default on the base (not abstract): an adapter with no
    safe-fix tool opts out by inheriting None."""
    assert ToolchainAdapter.lint_fix_cmd(PythonToolchain(), ["a.py"]) is None
    assert "lint_fix_cmd" not in getattr(ToolchainAdapter, "__abstractmethods__", set())


def test_go_adapter_inherits_the_none_default():
    from sdlc.toolchain.adapters import GoToolchain

    assert GoToolchain().lint_fix_cmd(["main.go"]) is None


# --- (b) the fix lands inside the checkpoint commit -------------------------


def test_autofix_is_inside_the_checkpoint_commit(py_repo, monkeypatch):
    wt = _worktree(py_repo, "run-af-b")
    result = _run(monkeypatch, wt, {"app.py": UNSORTED})

    assert result.commit_sha
    assert _show(wt, "HEAD", "app.py") == SORTED
    assert _porcelain(wt) == ""  # nothing left dirty: the fix was committed


def test_lint_autofix_records_the_file_and_the_rule_count(py_repo, monkeypatch):
    from sdlc.toolchain.lint_scope import LintAutofix

    wt = _worktree(py_repo, "run-af-rec")
    result = _run(monkeypatch, wt, {"app.py": UNSORTED})

    assert isinstance(result.lint_autofix, LintAutofix)
    assert result.lint_autofix.files == ["app.py"]
    assert result.lint_autofix.rules == {"I001": 1}


def test_lint_autofix_round_trips_on_the_result(py_repo, monkeypatch):
    wt = _worktree(py_repo, "run-af-json")
    result = _run(monkeypatch, wt, {"app.py": UNSORTED})
    again = HarnessRunResult.model_validate_json(result.model_dump_json())
    assert again.lint_autofix == result.lint_autofix


def test_lint_autofix_defaults_to_none_on_the_model():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="")
    assert r.lint_autofix is None


# --- (c) a repair attempt never autofixes the fenced tests -----------------


def test_repair_attempt_leaves_fenced_test_files_unfixed(py_repo, monkeypatch, tmp_path, spy):
    policy = tmp_path / "containment.yaml"
    policy.write_text(FENCE_POLICY, encoding="utf-8")
    wt = _worktree(py_repo, "run-af-c")

    result = _run(
        monkeypatch,
        wt,
        {"app.py": UNSORTED, "tests/test_a.py": UNSORTED_TEST},
        repair=True,
        containment_enabled=True,
        containment_policy_path=str(policy),
    )

    assert result.commit_sha
    assert _show(wt, "HEAD", "tests/test_a.py") == UNSORTED_TEST  # as the harness wrote it
    assert _show(wt, "HEAD", "app.py") == SORTED  # the unfenced file still fixed
    assert all("tests/test_a.py" not in files for files in spy)
    assert result.lint_autofix is not None
    assert "tests/test_a.py" not in result.lint_autofix.files

    drift = asyncio.run(
        check_test_drift(
            DriftInput(
                worktree=wt, anchor=result.commit_sha, fence_globs=["tests/**"], report_globs=[]
            )
        )
    )
    assert drift.available
    assert drift.found is False


def test_non_repair_attempt_does_fix_test_files(py_repo, monkeypatch, tmp_path):
    """The fence applies to repair attempts only: a first attempt writing a
    test file gets the same safe fixes as any other file."""
    wt = _worktree(py_repo, "run-af-c2")
    _run(monkeypatch, wt, {"tests/test_a.py": UNSORTED_TEST})
    assert _show(wt, "HEAD", "tests/test_a.py").startswith("import asyncio\nimport json\n")


# --- (d) a failing autofix never blocks the checkpoint ----------------------


def test_failing_autofix_logs_warning_and_still_commits(py_repo, monkeypatch, caplog):
    monkeypatch.setattr(
        PythonToolchain,
        "lint_fix_cmd",
        lambda self, files: "exit 3",
        raising=False,
    )
    wt = _worktree(py_repo, "run-af-d")

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = _run(monkeypatch, wt, {"app.py": UNSORTED})

    warnings = [
        r for r in caplog.records if r.name == _ACTIVITIES_LOGGER and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert "autofix" in warnings[0].getMessage().lower()
    assert result.commit_sha
    assert _show(wt, "HEAD", "app.py") == UNSORTED  # committed as written, unfixed
    assert _porcelain(wt) == ""


def test_missing_fix_binary_logs_warning_and_still_commits(py_repo, monkeypatch, caplog):
    monkeypatch.setattr(
        PythonToolchain,
        "lint_fix_cmd",
        lambda self, files: "definitely-not-a-ruff-binary-026 " + " ".join(files),
        raising=False,
    )
    wt = _worktree(py_repo, "run-af-d2")

    with caplog.at_level(logging.WARNING, logger=_ACTIVITIES_LOGGER):
        result = _run(monkeypatch, wt, {"app.py": UNSORTED})

    assert any(
        r.name == _ACTIVITIES_LOGGER and r.levelno == logging.WARNING for r in caplog.records
    )
    assert result.commit_sha
    assert _show(wt, "HEAD", "app.py") == UNSORTED


# --- (e) only the attempt's own *.py files, and no new files -----------------


def test_only_changed_python_files_are_passed(py_repo, monkeypatch, spy):
    wt = _worktree(py_repo, "run-af-e")
    _run(
        monkeypatch,
        wt,
        {"app.py": UNSORTED, "pkg/mod.py": UNSORTED, "notes.md": "# n\n", "data.txt": "x\n"},
    )
    assert spy, "lint_fix_cmd was never called"
    passed = {f for files in spy for f in files}
    assert passed == {"app.py", "pkg/mod.py"}
    assert "legacy.py" not in passed  # committed I001, untouched by this attempt


def test_untouched_files_stay_unfixed(py_repo, monkeypatch):
    wt = _worktree(py_repo, "run-af-e2")
    _run(monkeypatch, wt, {"app.py": UNSORTED})
    assert _show(wt, "HEAD", "legacy.py") == UNSORTED


def test_autofix_adds_no_file_to_the_diff(py_repo, monkeypatch):
    wt = _worktree(py_repo, "run-af-e3")
    written = {"app.py": UNSORTED, "pkg/mod.py": UNSORTED, "notes.md": "# n\n"}
    _run(monkeypatch, wt, written)
    assert _changed_in_head(wt) == set(written)


def test_no_python_changes_means_no_autofix_call(py_repo, monkeypatch, spy):
    wt = _worktree(py_repo, "run-af-e4")
    result = _run(monkeypatch, wt, {"notes.md": "# n\n"})
    assert spy == []
    assert result.lint_autofix is None or result.lint_autofix.files == []
    assert result.commit_sha


# --- chaos / edge cases (026 T012, chaos QA) --------------------------------
#
# Measured on ruff 0.16.9, 2026-11-18: with the contract's `--exit-zero`, a
# syntactically broken file (`invalid-syntax`) and a non-UTF-8 file (E902)
# both exit 0. Ruff reports them, rewrites neither, and still fixes the
# valid files in the same batch. So a REAL broken file does not reach the
# WARNING path ((d) covers that with a failing command); the contract
# pinned for it here is "no crash, nothing rewritten, the rest still fixed".

BROKEN = "import json\nimport asyncio\ndef f(:\n"
NON_UTF8 = b'x = "\xff\xfe"\n'


class _ExitingHarness(_WritingHarness):
    """Writes files (text or bytes), then reports a chosen exit code."""

    def __init__(self, files: dict[str, str | bytes], exit_code: int = 0):
        super().__init__({})
        self._raw = files
        self._exit = exit_code

    async def run(self, req, heartbeat=None):
        for rel, data in self._raw.items():
            p = Path(req.cwd, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, bytes):
                p.write_bytes(data)
            else:
                p.write_text(data, encoding="utf-8")
        return HarnessRunResult(harness=self.kind, exit_code=self._exit, summary="stub")


def _run_with(monkeypatch, wt: str, harness, **inp):
    monkeypatch.setitem(sdlc.stages.code.activities.HARNESSES, HarnessKind.CLAUDE_CODE, harness)
    return asyncio.run(
        run_coding_task(
            CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="p", worktree=wt, **inp)
        )
    )


def _show_bytes(wt: str, rev: str, path: str) -> bytes:
    import subprocess

    return subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=wt, capture_output=True, check=True
    ).stdout


def test_edge_harness_changed_nothing_runs_no_autofix(py_repo, monkeypatch, spy):
    """Empty changed-set: no command at all (an empty `--` list would lint
    the whole worktree), lint_autofix is None, the empty checkpoint lands."""
    wt = _worktree(py_repo, "run-af-x1")
    result = _run(monkeypatch, wt, {})

    assert spy == []
    assert result.lint_autofix is None
    assert result.commit_sha
    assert (
        _git(["rev-parse", "HEAD^{tree}"], wt).stdout
        == _git(["rev-parse", "HEAD~1^{tree}"], wt).stdout
    )
    assert _show(wt, "HEAD", "legacy.py") == UNSORTED  # the committed I001 untouched


def test_edge_already_clean_file_runs_the_command_and_fixes_nothing(py_repo, monkeypatch, spy):
    wt = _worktree(py_repo, "run-af-x2")
    result = _run(monkeypatch, wt, {"app.py": SORTED})

    assert spy == [["app.py"]]
    assert result.lint_autofix is not None  # the command ran
    assert result.lint_autofix.rules == {}  # nothing was fixable
    assert _show(wt, "HEAD", "app.py") == SORTED


def test_edge_repair_with_only_fenced_changes_runs_no_autofix(py_repo, monkeypatch, tmp_path, spy):
    policy = tmp_path / "containment.yaml"
    policy.write_text(FENCE_POLICY, encoding="utf-8")
    wt = _worktree(py_repo, "run-af-x3")

    result = _run(
        monkeypatch,
        wt,
        {"tests/test_a.py": UNSORTED_TEST},
        repair=True,
        containment_enabled=True,
        containment_policy_path=str(policy),
    )

    assert spy == []  # every changed .py was fenced: nothing left to fix
    assert result.lint_autofix is None
    assert result.commit_sha
    assert _show(wt, "HEAD", "tests/test_a.py") == UNSORTED_TEST
    assert _porcelain(wt) == ""


def test_edge_broken_and_non_utf8_files_are_committed_untouched(py_repo, monkeypatch):
    wt = _worktree(py_repo, "run-af-x4")
    result = _run_with(
        monkeypatch,
        wt,
        _ExitingHarness({"broken.py": BROKEN, "latin.py": NON_UTF8, "app.py": UNSORTED}),
    )

    assert result.commit_sha
    assert _porcelain(wt) == ""
    assert _show(wt, "HEAD", "broken.py") == BROKEN  # never half-rewritten
    assert _show_bytes(wt, "HEAD", "latin.py") == NON_UTF8  # bytes preserved
    assert _show(wt, "HEAD", "app.py") == SORTED  # one bad file does not sink the batch
    assert result.lint_autofix is not None
    # Only APPLIED fixes count: invalid-syntax / E902 diagnostics are not fixes.
    assert result.lint_autofix.rules == {"I001": 1}


def test_edge_nonzero_harness_exit_still_autofixes_into_the_checkpoint(py_repo, monkeypatch):
    """run_coding_task checkpoints whatever the harness exit code (the commit
    message carries `exit=N`, `--allow-empty`); the autofix rides with it."""
    wt = _worktree(py_repo, "run-af-x5")
    result = _run_with(monkeypatch, wt, _ExitingHarness({"app.py": UNSORTED}, exit_code=1))

    assert result.exit_code == 1
    assert result.commit_sha
    assert "exit=1" in _git(["log", "-1", "--format=%s"], wt).stdout
    assert _show(wt, "HEAD", "app.py") == SORTED
    assert result.lint_autofix is not None
    assert result.lint_autofix.rules == {"I001": 1}
