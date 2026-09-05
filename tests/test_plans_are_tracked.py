"""Plans are a durability class, not scratch (spec C, Risks).

`docs/documentation-rules.md` lists `docs/superpowers/plans/` as write-once
documentation alongside `specs/`, but `.gitignore` excluded it while 47 plans
were already committed and 76 existed on disk. Every plan written after the
rule landed was silently dropped -- spec C's own plan was the one that
surfaced it, being invisible to `git status` the moment it was written.

This test is the tripwire: it asserts the negation exists without asserting
how `.gitignore` spells it, so reordering the file cannot break it while
deleting the negation does.
"""

from __future__ import annotations

import subprocess


def _ignored(path: str) -> bool:
    """True when git would refuse to track `path`.

    `git check-ignore` exits 0 when a path IS ignored, 1 when it is not, so
    the return code is the answer rather than the output. The paths need not
    exist: check-ignore matches patterns, not the filesystem.
    """
    return subprocess.run(["git", "check-ignore", "-q", path], capture_output=True).returncode == 0


def test_plans_directory_is_tracked():
    assert not _ignored("docs/superpowers/plans/example.md"), (
        "docs/superpowers/plans/ is git-ignored; new plans would never be committed"
    )


def test_specs_directory_is_still_tracked():
    assert not _ignored("docs/superpowers/specs/example.md")


def test_superpowers_scratch_is_still_ignored():
    """The negations are per-directory, not a blanket un-ignore."""
    assert _ignored("docs/superpowers/scratch/notes.md")
