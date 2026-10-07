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
