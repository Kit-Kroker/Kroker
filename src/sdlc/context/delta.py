"""E-84 D8/D9: is the architecture delta grounded in the real tree?

The roadmap's framing of the BrownKit port is that its value is
enforceability -- gates "graded by the model that produced the artifacts"
become "CheckResults computed by pure code". An affected_modules list the
Architect wrote about files it never read is the defect FR-914 and SC-7 exist
to prevent, one stage earlier.

Pure: the caller supplies the path set. The activity that reads git lives in
activities.py, so this stays testable against a frozenset.
"""

from __future__ import annotations

from ..gate import CheckClass, CheckResult, build_check
from ..stages.context.models import BrownfieldDelta

DELTA_CHECK = "brownfield_delta_grounded"


def normalize_path(path: str) -> str:
    """Repo-relative POSIX form.

    Conservative on purpose (D9). This never matches on basename or suffix:
    src/app.py and tests/app.py are different files, and a check that accepts
    either has stopped verifying the claim it reports on. The forward-slash
    rule is not incidental -- the development host is Windows and git reports
    POSIX paths, so a separator mismatch is the likeliest way this check fails
    for a reason that has nothing to do with the Architect.
    """
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def check_delta(delta: BrownfieldDelta | None, paths: frozenset[str]) -> CheckResult:
    """Resolve every claimed path against the tree at the pinned commit.

    `paths` is EVERY file in the tree, not the map's attributed files.
    Attribution is best-effort -- E-47b's floor defaults to 0.90 and its
    reference table has a pinned known false positive -- so resolving against
    it would fail the Architect for naming a real config file the scan never
    attributed. A false accusation of fabrication is the most expensive
    possible error for a check whose purpose is trust.
    """
    if delta is None:
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            "no delta proposed: a brownfield architecture must state what it "
            "adds, modifies and removes against the existing tree",
        )
    if not (delta.added or delta.modified or delta.removed):
        return build_check(
            DELTA_CHECK,
            False,
            CheckClass.ABSOLUTE,
            "the delta names no files: an architecture that changes nothing "
            "cannot be planned or implemented",
        )

    known = {normalize_path(p) for p in paths}
    problems: list[str] = []
    for label, claimed in (("modified", delta.modified), ("removed", delta.removed)):
        problems.extend(
            f"{label} {p!r} does not exist at the pinned commit"
            for p in claimed
            if normalize_path(p) not in known
        )
    problems.extend(
        f"added {p!r} already exists at the pinned commit"
        for p in delta.added
        if normalize_path(p) in known
    )

    if problems:
        return build_check(DELTA_CHECK, False, CheckClass.ABSOLUTE, "; ".join(sorted(problems)))
    return build_check(
        DELTA_CHECK,
        True,
        CheckClass.ABSOLUTE,
        f"{len(delta.added)} added, {len(delta.modified)} modified, "
        f"{len(delta.removed)} removed -- all resolve",
    )
