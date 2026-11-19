"""DS2/DS3: the disposable detached base worktree, and rename pairs."""

import hashlib
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
    # FR-702: get_task_diff claim-checks via LocalFileStore() (env-resolved
    # root), so every store write in this module is pinned to tmp_path.
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))


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
    art = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    assert art.renames == [["a.py", "b.py"]]
    assert "b.py" in art.files
    assert art.stat, "the stat metadata must ride the artifact as before"


# --- FR-702 (E-38): get_task_diff claim-checks the FULL patch ----------------
#
# The patch no longer travels on the activity result and is never cut at the
# source: the whole diff is stored at <root>/<run_id>/diffs/<label>.patch and
# only the small CodeArtifact (files/renames/stat + patch_ref) is returned.
# The visible cut marker is the read-back's job (load_diff), not the source's.


def _big_diff_repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    """A repo whose head diff comfortably overflows the old 60_000-char cut."""
    repo = tmp_path / "big"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "big.txt").write_text("", encoding="utf-8")
    _git(repo, "add", "big.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "big.txt").write_text(
        "".join(f"line-{i:05d} {'x' * 50}\n" for i in range(2000)), encoding="utf-8"
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


def _stored(tmp_path: pathlib.Path, run_id: str, name: str) -> bytes:
    return (tmp_path / run_id / "diffs" / name).read_bytes()


@pytest.mark.asyncio
async def test_the_full_patch_is_stored_untruncated_regardless_of_size(tmp_path):
    repo, base = _big_diff_repo(tmp_path)
    full = _raw_patch(repo, f"{base}...HEAD")
    assert len(full) > 60_000, "fixture guard: the head diff must overflow the old default cut"

    art = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, label="big-a1"))

    assert art.patch_ref is not None
    stored = _stored(tmp_path, "local", "big-a1.patch")
    assert stored == full.encode("utf-8"), (
        "the claim-check must hold the whole patch, byte-identical with git's "
        "output — no cut, no marker injected at the source"
    )
    assert art.patch_ref.kind == "diff"
    assert art.patch_ref.sha256 == hashlib.sha256(stored).hexdigest()


@pytest.mark.asyncio
async def test_a_direct_call_claims_under_the_local_run_id(tmp_path):
    """Outside a worker `activity.info()` raises, so the run id falls back to
    the literal "local" — the artifact lands under <root>/local/diffs/."""
    repo, base = _repo(tmp_path)
    art = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, label="t1-a1"))
    assert art.patch_ref is not None
    assert (tmp_path / "local" / "diffs" / "t1-a1.patch").exists()
    assert "local" in art.patch_ref.uri


@pytest.mark.asyncio
async def test_the_label_slug_survives_unsafe_characters(tmp_path):
    repo, base = _repo(tmp_path)
    label = "task/07: a final pass?"
    expected = re.sub(r"[^A-Za-z0-9._-]", "_", label) + ".patch"  # artifacts/capture.py _safe
    art = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, label=label))
    assert art.patch_ref is not None
    assert (tmp_path / "local" / "diffs" / expected).exists(), (
        f"the label must be slugged with the _safe regex before it becomes a "
        f"file name; expected {expected!r}"
    )


@pytest.mark.asyncio
async def test_label_defaults_to_the_branch_point_prefix(tmp_path):
    repo, base = _repo(tmp_path)
    art = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))
    assert art.patch_ref is not None
    assert (tmp_path / "local" / "diffs" / f"{base[:12]}.patch").exists()
