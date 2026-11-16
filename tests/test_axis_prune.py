"""``measure_code_axis`` must not leak its worktree registration (024 T017; R10, skeptic L3).

The activity adds a detached worktree under ``tempfile.mkdtemp(prefix="axis-")`` and its
``finally`` ``rmtree``s the directory. That removes the files but not the registration in
the repo's ``.git/worktrees``, so every measurement leaves a stale (prunable) entry. After
the activity, ``git worktree list`` must show only the main worktree.

RED until the fix adds ``git worktree prune`` (via the module's git runner) in that
``finally``; the test lands failing first, in the same task as the fix.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

RUN_ID = "run-axis-prune"

PY_SOURCE = """\
def classify(n):
    if n < 0:
        return "negative"
    if n == 0:
        return "zero"
    return "positive"
"""


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "checkout", "-b", f"sdlc/{RUN_ID}/integration")
    (repo / "mod.py").write_text(PY_SOURCE)
    _git(repo, "add", "mod.py")
    _git(repo, "commit", "-m", "add mod")
    _git(repo, "checkout", "main")
    return repo


def _worktree_paths(repo: Path) -> list[Path]:
    out = _git(repo, "worktree", "list", "--porcelain")
    return [
        Path(line.removeprefix("worktree "))
        for line in out.splitlines()
        if line.startswith("worktree ")
    ]


def test_measure_code_axis_leaves_only_the_main_worktree(tmp_path: Path) -> None:
    from sdlc.benchmarks.axis import AxisInput, measure_code_axis

    repo = _make_repo(tmp_path)

    bag = asyncio.run(
        measure_code_axis(
            AxisInput(
                case_id="case-1",
                repo_url=str(repo),
                run_id=RUN_ID,
                language="python",
                base_branch="main",
                code_finished=True,
            )
        )
    )

    # Sanity: the worktree path was actually exercised (not the absent-branch short-circuit).
    assert bag.reason != "integration branch absent", bag.reason
    assert bag.head, f"expected a measured head, got reason={bag.reason!r}"

    listing = _git(repo, "worktree", "list", "--porcelain")
    paths = _worktree_paths(repo)
    assert [p.resolve() for p in paths] == [repo.resolve()], (
        "stale worktree registration(s) left behind:\n" + listing
    )
    assert "axis-" not in listing, listing


def test_the_axis_tmp_parent_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity pin, not the point: the files are already cleaned up today."""
    import tempfile

    from sdlc.benchmarks.axis import AxisInput, measure_code_axis

    repo = _make_repo(tmp_path)
    tmp_root = tmp_path / "tmp-root"
    tmp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_root))

    asyncio.run(
        measure_code_axis(
            AxisInput(
                case_id="case-1",
                repo_url=str(repo),
                run_id=RUN_ID,
                language="python",
                base_branch="main",
                code_finished=True,
            )
        )
    )

    assert list(tmp_root.glob("axis-*")) == []


# ------------------------------------------------- chaos pass (024 T017, edge cases)


def _porcelain_lines(repo: Path) -> list[str]:
    return _git(repo, "worktree", "list", "--porcelain").splitlines()


def _assert_only_main_worktree(repo: Path) -> None:
    """Compare parsed ``worktree <path>`` entries, never raw substrings of the listing."""
    lines = _porcelain_lines(repo)
    paths = [
        Path(ln.removeprefix("worktree ")).resolve() for ln in lines if ln.startswith("worktree ")
    ]
    stale = [ln for ln in lines if ln == "prunable" or ln.startswith("prunable ")]
    assert paths == [repo.resolve()], "stale worktree registration(s):\n" + "\n".join(lines)
    assert stale == [], "git flags a worktree as prunable:\n" + "\n".join(lines)


def _inp(repo: Path, *, run_id: str = RUN_ID) -> object:
    from sdlc.benchmarks.axis import AxisInput

    return AxisInput(
        case_id="case-1",
        repo_url=str(repo),
        run_id=run_id,
        language="python",
        base_branch="main",
        code_finished=True,
    )


def test_the_porcelain_check_itself_detects_a_stale_registration(tmp_path: Path) -> None:
    # Harness self-check (passes today): a removed-but-registered worktree must trip the helper,
    # so the chaos assertions below cannot vacuously pass.
    import shutil

    repo = _make_repo(tmp_path)
    gone = tmp_path / "axis-gone"
    _git(repo, "worktree", "add", "--detach", str(gone), "main")
    shutil.rmtree(gone)

    with pytest.raises(AssertionError):
        _assert_only_main_worktree(repo)

    _git(repo, "worktree", "prune")
    _assert_only_main_worktree(repo)


def test_repeated_measurements_do_not_accumulate_registrations(tmp_path: Path) -> None:
    from sdlc.benchmarks.axis import measure_code_axis

    repo = _make_repo(tmp_path)

    for attempt in range(3):
        bag = asyncio.run(measure_code_axis(_inp(repo)))  # type: ignore[arg-type]
        assert bag.head, f"attempt {attempt}: expected a measured head, got {bag.reason!r}"
        _assert_only_main_worktree(repo)


def test_absent_integration_branch_returns_its_reason_and_leaves_no_registration(
    tmp_path: Path,
) -> None:
    from sdlc.benchmarks.axis import measure_code_axis

    repo = _make_repo(tmp_path)

    bag = asyncio.run(measure_code_axis(_inp(repo, run_id="run-with-no-branch")))  # type: ignore[arg-type]

    assert bag.reason == "integration branch absent"
    assert bag.head is None
    _assert_only_main_worktree(repo)


def test_a_failing_measurement_is_reported_not_raised_and_still_prunes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.benchmarks import axis

    repo = _make_repo(tmp_path)
    calls: list[int] = []

    def broken(_files: object) -> object:
        calls.append(1)
        raise RuntimeError("measurement exploded")

    monkeypatch.setattr(axis, "measure_files", broken)

    bag = asyncio.run(axis.measure_code_axis(_inp(repo)))  # type: ignore[arg-type]

    assert calls == [1], "the worktree path was not exercised"
    assert bag.reason is not None and bag.reason.startswith("measurement failed")
    assert "measurement exploded" in bag.reason
    _assert_only_main_worktree(repo)
