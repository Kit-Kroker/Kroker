"""One cases location for every reader (012, R-1 / data-model §2.1).

Before 012 the cases location was derived five separate ways: the oracle
and the task loader honoured ``SDLC_CASES_ROOT`` (the worker image sets
it) while the judge, the report and the CLI derived it from this
module's own file path — so a rubric registered in a manifest could be
invisible to the very judge meant to read it. This leaf module is the
single resolution point: every reader of case files goes through
``cases_dir()``; calibration lives at its sibling so one override moves
both. Leaf by construction: imports nothing from the benchmark package.
"""

from __future__ import annotations

import os
from pathlib import Path

CASES_ENV = "SDLC_CASES_ROOT"
_CHECKOUT_CASES = Path(__file__).resolve().parents[3] / "benchmarks" / "cases"


def cases_dir() -> Path:
    """The cases root. Reads ``SDLC_CASES_ROOT`` at call time (never at
    import) and falls back to the checkout's ``benchmarks/cases`` — the
    editable install resolves ``__file__`` to the worktree source."""
    return Path(os.environ.get(CASES_ENV, str(_CHECKOUT_CASES)))


def calibration_dir() -> Path:
    """The calibration root: the sibling of the cases directory, so the
    one override moves both trees together."""
    return cases_dir().parent / "calibration"


# 012 (data-model §2.1): the `type` of the non-retryable ApplicationError
# `load_case_assets` raises for a missing or empty registered file. No
# exception class is added — the constant is the wire name.
MISSING_CASE_ASSET = "MissingCaseAsset"


def check_case_assets(rubrics: dict[str, str], vetoes: dict[str, str], case_dir: Path) -> list[str]:
    """012 (contract §1.2): every file a case manifest registers must exist
    and hold non-whitespace text. Returns one message per problem, in
    registration order (the rubrics map first, then the vetoes map, each in
    its own insertion order):

        <kind> '<key>': <path> is missing
        <kind> '<key>': <path> is empty

    where kind is ``rubric`` or ``veto``. An absolute registered path is
    checked as given; a relative one resolves against ``case_dir``. A case
    with empty maps passes (contract §1.5). Reads the file system, nothing
    else — the CLI calls it before contacting Temporal, and the corpus test
    keeps the shipped manifests clean."""
    problems: list[str] = []
    for kind, mapping in (("rubric", rubrics), ("veto", vetoes)):
        for key, rel in mapping.items():
            p = Path(rel) if Path(rel).is_absolute() else case_dir / rel
            if not p.exists():
                problems.append(f"{kind} '{key}': {p} is missing")
            elif not p.read_text(encoding="utf-8").strip():
                problems.append(f"{kind} '{key}': {p} is empty")
    return problems
