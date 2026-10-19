"""Edge/pin tests for the visible cut marker on get_task_diff's patch
(sbatch-2026-10-19 T3; task .workspace/tasks/2026-10-03-silent-patch-cut-no-marker.md).

``src/sdlc/vcs/git.py`` caps ``patch`` at ``max_chars`` with a bare slice —
a validator reading the tail cannot tell a whole diff from a cut one. The
planned fix copies the oracle's pattern (``benchmarks/oracle.py``,
``_truncate_diff``): ``<= max_chars`` passes through unchanged; longer
patches keep their exact first ``max_chars`` characters and gain a final
marker naming the omitted count. What is KEPT must not change.

These tests build a real git repo and reproduce the activity's own
``git diff <branch_point>...HEAD`` output in-test, so the kept-prefix
assertion is a byte compare against ground truth, not a paraphrase.
``check_test_drift``'s own silent cut (git.py:~225) is OUT OF SCOPE for
T3 and deliberately untested here.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

from sdlc.benchmarks.oracle import _truncate_diff
from sdlc.vcs import DiffInput, get_task_diff

GIT = ["git", "-c", "user.email=t@example.test", "-c", "user.name=t"]
_MARKER = re.compile(r"truncated, (\d+) chars omitted")


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


async def _diff(worktree: str, base: str, max_chars: int) -> dict:
    return await get_task_diff(DiffInput(worktree=worktree, branch_point=base, max_chars=max_chars))


@pytest.mark.asyncio
async def test_at_exactly_max_chars_the_patch_passes_through_uncut(tmp_path):
    """PIN (green on main; must stay green): the cut boundary is EXCLUSIVE,
    oracle semantics — len(patch) == max_chars returns the whole patch with
    no marker. An inclusive boundary would cut the final character and mark
    a complete diff as truncated."""
    wt, base, real = _repo_with_diff(tmp_path)
    assert len(real) > 100, "fixture diff unexpectedly small; boundary tests would be vacuous"
    out = await _diff(wt, base, len(real))
    assert out["patch"] == real
    assert "truncated" not in out["patch"]


@pytest.mark.asyncio
async def test_one_char_over_max_carries_a_marker_naming_exactly_one(tmp_path):
    """RED on main (the cut is silent today): len(patch) == max_chars + 1 is
    the smallest cut that can exist, and its marker must name the exact
    omitted count — 1."""
    wt, base, real = _repo_with_diff(tmp_path)
    out = await _diff(wt, base, len(real) - 1)
    m = _MARKER.search(out["patch"])
    assert m is not None, (
        f"patch cut at {len(real) - 1} of {len(real)} carries no truncation "
        f"marker — a validator cannot tell a cut diff from a whole one"
    )
    assert int(m.group(1)) == 1, f"omitted must be exactly 1, marker said {m.group(1)}"


@pytest.mark.asyncio
async def test_cut_keeps_the_exact_prefix_and_appends_the_oracle_marker(tmp_path):
    """RED on main (marker missing; the prefix half already holds): with a
    mid-diff cut, the returned patch must equal the oracle's own
    ``_truncate_diff`` over the reproduced git output — exact first
    max_chars characters byte-for-byte, then the oracle-shaped marker
    naming len(real) - max_chars omitted chars. A fix that trims
    differently, re-wraps, or moves the cut point fails here."""
    wt, base, real = _repo_with_diff(tmp_path)
    max_chars = len(real) // 2
    out = await _diff(wt, base, max_chars)
    assert out["patch"] == _truncate_diff(real, max_chars), (
        f"expected patch == _truncate_diff(real, {max_chars}); what is KEPT "
        f"must be the diff's exact first {max_chars} characters plus the "
        f"oracle marker (benchmarks/oracle.py pattern the fix copies)"
    )


@pytest.mark.asyncio
async def test_sibling_keys_are_identical_with_and_without_the_cut(tmp_path):
    """PIN (green on main; must stay green): the marker lives in ``patch``
    only — stat, files and renames are identical whether the cut fired or
    not (same repo, two max_chars values)."""
    wt, base, real = _repo_with_diff(tmp_path)
    whole = await _diff(wt, base, len(real))
    cut = await _diff(wt, base, max(1, len(real) // 3))
    for key in ("stat", "files", "renames"):
        assert cut[key] == whole[key], f"key {key!r} changed when the cut fired"


@pytest.mark.asyncio
async def test_the_marker_is_terminal_and_solitary(tmp_path):
    """RED on main (no marker exists): the marker is the LAST line of the
    returned patch and appears exactly once — a marker injected mid-diff or
    duplicated misleads a reviewer reading the tail."""
    wt, base, real = _repo_with_diff(tmp_path)
    out = await _diff(wt, base, len(real) - 1)
    lines = out["patch"].splitlines()
    marker_lines = [ln for ln in lines if "truncated" in ln]
    assert len(marker_lines) == 1, (
        f"expected exactly one marker line, found {len(marker_lines)}; a "
        f"duplicated marker double-counts the omission"
    )
    assert "truncated" in lines[-1], (
        f"the marker must be the final line; last line was {lines[-1]!r}"
    )
