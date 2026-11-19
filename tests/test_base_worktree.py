"""DS2/DS3: the disposable detached base worktree, and rename pairs."""

import hashlib
import os
import pathlib
import subprocess

import pytest

from sdlc.artifacts.store import ref_to_path
from sdlc.vcs import (
    BaseWorktreeInput,
    CodeArtifact,
    DiffInput,
    get_task_diff,
    prepare_base_worktree,
)

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
    assert d.renames == [["a.py", "b.py"]]
    assert "b.py" in d.files


# --- FR-702: the diff travels by claim-check ---------------------------------
#
# get_task_diff stores the FULL untruncated patch in the artifact store and
# returns a CodeArtifact; only the ref crosses workflow history. The T3
# truncation-marker semantics moved with the cut: they live in load_diff's
# bounded read-back (tests/test_task_diff_marker_edges.py), not at the
# source -- truncation is a prompt context budget now, never a storage
# limit.


def _big_diff_repo(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str]:
    """A repo whose head diff comfortably overflows any small size."""
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
async def test_full_patch_stored_untruncated_with_claim_check(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "store"))
    repo, base = _big_diff_repo(tmp_path)
    full = _raw_patch(repo, f"{base}...HEAD")
    assert len(full) > 1_000, "fixture guard: the head diff must be substantial"

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base, label="t1-a1"))

    assert isinstance(d, CodeArtifact)
    assert d.stat.startswith(" big.txt") and d.files == ["big.txt"] and d.renames == []
    assert d.patch_ref is not None and d.patch_ref.kind == "diff"
    stored = ref_to_path(d.patch_ref)
    assert stored.parent.name == "diffs"
    assert stored.name == "t1-a1.patch"
    assert stored.read_text(encoding="utf-8") == full, (
        "the stored bytes are the FULL patch -- no truncation exists at the source"
    )
    assert d.patch_ref.sha256 == hashlib.sha256(full.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_outside_worker_call_falls_back_to_run_id_local(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "store"))
    repo, base = _repo(tmp_path)

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))

    assert d.patch_ref is not None
    stored = ref_to_path(d.patch_ref)
    assert stored.parent.parent.name == "local", (
        f"a direct (non-worker) call stores under run id 'local', got {stored}"
    )


@pytest.mark.asyncio
async def test_label_slug_survives_unsafe_chars(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "store"))
    repo, base = _repo(tmp_path)

    d = await get_task_diff(
        DiffInput(worktree=str(repo), branch_point=base, label="task 1/attempt:2")
    )

    assert ref_to_path(d.patch_ref).name == "task_1_attempt_2.patch"


@pytest.mark.asyncio
async def test_default_label_derives_from_branch_point(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "store"))
    repo, base = _repo(tmp_path)

    d = await get_task_diff(DiffInput(worktree=str(repo), branch_point=base))

    assert ref_to_path(d.patch_ref).name == f"{base[:12]}.patch"
