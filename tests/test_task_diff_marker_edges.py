"""FR-702: the T3 cut lives at the read-back, never at the source.

Two contracts pinned here, one per side of the claim-check.

SOURCE side (get_task_diff): the stored patch is git's own output
byte-for-byte — no truncation, no marker text is ever injected at the
source; the metadata is a pure function of the diff; an empty diff still
claim-checks.

READ side (load_diff): the only place a patch is cut. The first
max_chars characters pass through clean — a patch of exactly max_chars
characters is NOT a cut (``<=`` semantics, no marker); one character
more appends the T3 marker ``\\n...[diff truncated, N chars omitted]``
with the exact omitted count; the slice is by characters (decode the
full patch first, ``errors="replace"``), so a cut landing at a
multi-byte codepoint decodes instead of raising. check_test_drift's own
silent cut (git.py:~225) stays OUT OF SCOPE here.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

import pytest

from sdlc.artifacts.read import LoadDiffInput, load_diff
from sdlc.artifacts.store import LocalFileStore
from sdlc.core.models import ArtifactRef
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


async def _read(ref: ArtifactRef, **kw):
    return await load_diff(LoadDiffInput(ref=ref, **kw))


# --- source side: get_task_diff stores the FULL patch, uncut --------------


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


# --- read side: load_diff cuts, and only load_diff cuts -------------------


@pytest.mark.asyncio
async def test_put_then_load_diff_round_trips_the_stored_text(tmp_path):
    """Store/read round-trip: what put("diff") wrote is what load_diff
    reads back — including the zero-byte patch an empty diff produces."""
    store = LocalFileStore(root=tmp_path)
    patch = "diff --git a/x.py b/x.py\n+the stored bytes come back verbatim\n"
    ref = store.put("diff", "run-1", "t1-a1.patch", patch.encode("utf-8"))
    out = await _read(ref)
    assert out.text == patch
    assert out.truncated is False

    empty = store.put("diff", "run-1", "empty.patch", b"")
    out = await _read(empty)
    assert out.text == "" and out.truncated is False


@pytest.mark.asyncio
async def test_load_diff_rejects_a_foreign_kind():
    ref = ArtifactRef(kind="harness_session", uri="file:///x", sha256=None)
    with pytest.raises(AssertionError, match="load_diff reads only diffs"):
        await _read(ref)


@pytest.mark.asyncio
async def test_cut_at_exactly_max_chars_is_not_a_cut(tmp_path):
    """``<=`` semantics: a patch of exactly max_chars characters passes
    through clean — no marker, truncated stays False."""
    store = LocalFileStore(root=tmp_path)
    patch = "a" * 60_000
    ref = store.put("diff", "run-1", "exact.patch", patch.encode("utf-8"))
    out = await _read(ref)
    assert out.text == patch
    assert out.truncated is False
    assert "omitted" not in out.text


@pytest.mark.asyncio
async def test_one_char_over_appends_marker_with_the_exact_omitted_count(tmp_path):
    store = LocalFileStore(root=tmp_path)
    patch = "b" * (60_000 + 7)
    ref = store.put("diff", "run-1", "over.patch", patch.encode("utf-8"))
    out = await _read(ref)
    assert out.truncated is True
    assert out.text == "b" * 60_000 + "\n...[diff truncated, 7 chars omitted]"


@pytest.mark.asyncio
async def test_multibyte_cut_lands_on_a_codepoint_without_raising(tmp_path):
    """€ is 3 bytes in UTF-8: a byte-wise cut at max_chars would slice the
    sequence mid-codepoint and raise on decode. Char semantics — decode the
    full patch, then slice characters — must come back without raising,
    without a replacement character in the kept text, and with the marker
    counting omitted characters (23), not bytes (69)."""
    store = LocalFileStore(root=tmp_path)
    full = "€" * 33
    ref = store.put("diff", "run-1", "mb.patch", full.encode("utf-8"))
    out = await _read(ref, max_chars=10)
    assert out.truncated is True
    assert out.text == "€" * 10 + "\n...[diff truncated, 23 chars omitted]"
    assert "\ufffd" not in out.text
