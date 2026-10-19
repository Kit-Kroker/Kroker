"""DS2/DS3: the disposable detached base worktree, and rename pairs."""

import os
import pathlib
import re
import subprocess

import pytest

from sdlc.vcs import BaseWorktreeInput, DiffInput, get_task_diff, prepare_base_worktree

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


def _git(cwd, *args) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout.strip()


def _repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.py").write_text("v2\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "head")
    return repo, base


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))


@pytest.mark.asyncio
async def test_materializes_the_base_commit_detached(tmp_path):
    repo, base = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert wt.path is not None, wt.reason
    assert (pathlib.Path(wt.path) / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert _git(wt.path, "rev-parse", "HEAD") == base


@pytest.mark.asyncio
async def test_a_retry_reuses_and_resets_but_keeps_the_provisioned_venv(tmp_path):
    repo, base = _repo(tmp_path)
    first = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    p = pathlib.Path(first.path)
    (p / "a.py").write_text("dirty\n", encoding="utf-8")
    (p / "stray.py").write_text("x\n", encoding="utf-8")
    (p / ".sdlc-venv").mkdir()
    again = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", base))
    assert os.path.normpath(again.path) == os.path.normpath(first.path)
    assert (p / "a.py").read_text(encoding="utf-8") == "v1\n"
    assert not (p / "stray.py").exists()
    assert (p / ".sdlc-venv").is_dir()


@pytest.mark.asyncio
async def test_no_base_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", ""))
    assert wt.path is None and "base_sha" in wt.reason


@pytest.mark.asyncio
async def test_an_unknown_sha_is_reported_not_raised(tmp_path):
    repo, _ = _repo(tmp_path)
    wt = await prepare_base_worktree(BaseWorktreeInput(str(repo), "run1", "0" * 40))
    assert wt.path is None and wt.reason


@pytest.mark.asyncio
async def test_get_task_diff_reports_rename_pairs(tmp_path):
    repo, _ = _repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "rename")
    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    assert d["renames"] == [["a.py", "b.py"]]
    assert "b.py" in d["files"]


# --- T3 (sbatch-2026-10-19): the max_chars cut carries a visible marker -----
#
# get_task_diff silently slices the patch at max_chars (default 60_000) and
# all four callers use the default — a reviewer can approve a diff whose
# tail it never saw, and nothing records that a cut happened. The benchmark
# oracle's equivalent cut appends a marker naming the omitted count
# (benchmarks/oracle.py _truncate_diff); get_task_diff must adopt the same
# shape, changing ONLY the over-budget case: the kept prefix is exactly the
# first max_chars chars, and the under-budget return stays byte-identical
# (task 2026-10-03-silent-patch-cut-no-marker).


def _big_diff_repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    """A repo whose head diff comfortably overflows any small max_chars."""
    repo = tmp_path / "big"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "big.txt").write_text("", encoding="utf-8")
    _git(repo, "add", "big.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "big.txt").write_text(
        "".join(f"line-{i:03d} {'x' * 24}\n" for i in range(30)), encoding="utf-8"
    )
    _git(repo, "commit", "-q", "-am", "big")
    return repo, base


def _raw_patch(repo: pathlib.Path, rng: str) -> str:
    """The activity's own diff text: the same git invocation get_task_diff
    runs (safe.directory bypass, utf-8), stdout unstripped."""
    return subprocess.run(
        ["git", "-c", "safe.directory=*", "diff", rng],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


@pytest.mark.asyncio
async def test_cut_patch_carries_a_visible_truncation_marker(tmp_path):
    repo, base = _big_diff_repo(tmp_path)
    max_chars = 100
    full = _raw_patch(repo, f"{base}...HEAD")
    assert len(full) > max_chars, "fixture guard: the head diff must overflow max_chars"

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, max_chars=max_chars))

    omitted = len(full) - max_chars
    assert d["patch"].startswith(full[:max_chars]), (
        "the cut must keep exactly the first max_chars chars of the real patch"
    )
    assert d["patch"].endswith(f"\n...[diff truncated, {omitted} chars omitted]"), (
        f"the cut patch must end with the oracle-shaped marker naming the "
        f"omitted count ({omitted}); tail was {d['patch'][-60:]!r} — today the "
        "cut is silent, so a reviewer never learns the diff continued"
    )


@pytest.mark.asyncio
async def test_uncut_patch_is_byte_identical_with_no_marker(tmp_path):
    repo, base = _repo(tmp_path)  # the tiny v1 -> v2 edit, far under 60_000
    full = _raw_patch(repo, f"{base}...HEAD")

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))

    assert len(full) <= 60_000, "fixture guard: the small diff must not be cut"
    assert d["patch"] == full, (
        "under-budget diffs must return byte-identical: the marker work must "
        "not touch the no-cut path or change what is kept"
    )
    assert "diff truncated" not in d["patch"], "no marker may appear when nothing was cut"


@pytest.mark.asyncio
async def test_marker_wording_follows_the_oracle_shape(tmp_path):
    repo, base = _big_diff_repo(tmp_path)
    max_chars = 60  # a second, different cut point than the marker test above
    full = _raw_patch(repo, f"{base}...HEAD")
    assert len(full) > max_chars, "fixture guard: the head diff must overflow max_chars"

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, max_chars=max_chars))

    omitted = len(full) - max_chars
    m = re.search(r"(?m)^\.\.\.\[diff truncated, (\d+) chars omitted\]$", d["patch"])
    assert m is not None, (
        "no line matches the oracle marker shape "
        f"'...[diff truncated, <count> chars omitted]'; tail was {d['patch'][-60:]!r}"
    )
    assert m.group(1) == str(omitted), (
        f"the marker must name the exact omitted count {omitted}, got {m.group(1)}"
    )
