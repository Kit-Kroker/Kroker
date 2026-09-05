"""The superpowers durability classes are tracked, not scratch (spec C, Risks).

`docs/documentation-rules.md` lists `specs/`, `plans/` and `reviews/` under
`docs/superpowers/` as three write-once documentation classes, but `.gitignore`
re-included only `specs/`. The other two were silently dropped: 29 plans
written between 2026-08-07 and 2026-09-02, and every review ever written.
Spec C's own plan was the one that surfaced it, being invisible to
`git status` the moment it was written.

These tests are the tripwire: they assert the negations exist without
asserting how `.gitignore` spells them, so reordering the file cannot break
them while deleting a negation does.
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


def test_reviews_directory_is_tracked():
    assert not _ignored("docs/superpowers/reviews/example.md"), (
        "docs/superpowers/reviews/ is git-ignored; new reviews would never be committed"
    )


def test_specs_directory_is_still_tracked():
    assert not _ignored("docs/superpowers/specs/example.md")


def test_superpowers_scratch_is_still_ignored():
    """The negations are per-directory, not a blanket un-ignore."""
    assert _ignored("docs/superpowers/scratch/notes.md")
