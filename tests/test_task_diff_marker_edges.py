"""FR-702 interim pins for get_task_diff's stored patch.

The sbatch-2026-10-19 T3 cut-and-marker semantics MOVED OFF THE SOURCE:
get_task_diff now claim-checks the FULL patch into the artifact store
(E-38, FR-702) and truncation never happens in the activity. The visible
marker is the read-back's job — `load_diff` (the FR-702 plan's next task)
rewrites this file against itself.

Until that lands, these tests pin the source side: the stored bytes are
git's own output with no marker text, the inline metadata is identical no
matter how often the diff is fetched, and an empty diff still claim-checks.
`check_test_drift`'s own silent cut (git.py:~225) stays OUT OF SCOPE here.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

import pytest

from sdlc.vcs import DiffInput, get_task_diff

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]


@pytest.fixture(autouse=True)
def _artifact_root(tmp_path, monkeypatch):
    # get_task_diff claim-checks via LocalFileStore() (env-resolved root);
    # direct calls fall back to run id "local".
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))


def _git(cwd, *args: str) -> str:
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, encoding="utf-8"
    ).stdout


def _repo_with_diff(tmp_path: pathlib.Path) -> tuple[str, str, str]:
    """(worktree, branch_point, real_patch): a repo whose base...HEAD patch
    is reproduced verbatim by the same ``git diff <range>`` invocation the
    activity runs. Payload lines avoid the words 'truncated'/'omitted' so
    marker detection cannot false-positive on diff content."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "a.py").write_text("v2 changed\n", encoding="utf-8")
    payload = "\n".join(f"payload line {i:03d} of the change" for i in range(12))
    (repo / "payload.txt").write_text(payload + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "head")
    real = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    return str(repo), base, real


async def _diff(worktree: str, base: str, label: str):
    return await get_task_diff(DiffInput(worktree=worktree, branch_point=base, label=label))


@pytest.mark.asyncio
async def test_the_stored_patch_is_gits_own_output_with_no_marker(tmp_path):
    wt, base, real = _repo_with_diff(tmp_path)
    art = await _diff(wt, base, "a1")
    stored = (tmp_path / "local" / "diffs" / "a1.patch").read_bytes()
    assert stored == real.encode("utf-8"), (
        "the claim-check must hold git's diff output byte-for-byte — the "
        "source must not inject a truncation marker (the cut moved to the "
        "read-back activity)"
    )
    assert art.patch_ref is not None
    assert art.patch_ref.sha256 == hashlib.sha256(stored).hexdigest()


@pytest.mark.asyncio
async def test_sibling_keys_and_stored_bytes_are_identical_across_calls(tmp_path):
    """Two fetches of the same repo produce the same files/renames/stat and
    the same stored patch — the store is a pure function of the diff."""
    wt, base, _ = _repo_with_diff(tmp_path)
    first = await _diff(wt, base, "first")
    second = await _diff(wt, base, "second")
    assert second.files == first.files
    assert second.renames == first.renames
    assert second.stat == first.stat
    d = tmp_path / "local" / "diffs"
    assert (d / "first.patch").read_bytes() == (d / "second.patch").read_bytes()


@pytest.mark.asyncio
async def test_an_empty_diff_still_claim_checks(tmp_path):
    """branch_point == HEAD: nothing changed, the patch is empty — the store
    still holds the (zero-byte) artifact and the metadata still rides."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    art = await _diff(str(repo), base, "empty")

    assert art.files == [] and art.renames == [] and art.stat == ""
    stored = (tmp_path / "local" / "diffs" / "empty.patch").read_bytes()
    assert stored == b""
    assert art.patch_ref is not None
    assert art.patch_ref.sha256 == hashlib.sha256(b"").hexdigest()
