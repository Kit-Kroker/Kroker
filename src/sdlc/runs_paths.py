"""One resolver for both run-evidence roots (026 FR-001, research R1).

`SDLC_RUNS_ROOT` used to drive neither evidence store: records came from
`SDLC_BENCHMARKS_ROOT` (default ``runs/benchmarks``) and summaries from
`SDLC_EXPORT_ROOT` (default ``./runs/pipeline``), each resolved by its own
inline copy. A fleet host that exported only ``SDLC_RUNS_ROOT`` was read by
the scorer only when its CWD happened to be the fleet root. This module is
the single resolution point every writer and reader calls:

- an explicit ``SDLC_BENCHMARKS_ROOT`` / ``SDLC_EXPORT_ROOT`` wins;
- else ``$SDLC_RUNS_ROOT/benchmarks`` / ``$SDLC_RUNS_ROOT/pipeline``;
- else today's CWD defaults, unchanged.

A test-source guard (tests/test_runs_paths.py) fails if any other module
under ``sdlc`` reads those two variables from ``os.environ`` again; the one
sanctioned write (demo ``__main__`` setting ``SDLC_EXPORT_ROOT`` for its
child) stays. Workers are unaffected: the containers set no ``SDLC_*_ROOT``
and run at ``/app`` with ``/app/runs`` bind-mounted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

BENCHMARKS_DEFAULT = "runs/benchmarks"
EXPORT_DEFAULT = "./runs/pipeline"


def _set(name: str) -> str | None:
    """A set, non-empty variable value, or None.

    An exported-but-empty variable is *unset*, not "explicit ``''``":
    ``Path("")`` is the CWD, so honoring an empty value would silently
    read (or write) whatever directory the process happens to run in.
    """
    value = os.environ.get(name)
    return value if value else None


@dataclass(frozen=True)
class RootsReport:
    """Both roots plus how each was chosen, for the scorer's roots line."""

    records: str
    export: str
    records_how: str  # explicit | runs_root | default
    export_how: str  # explicit | runs_root | default


def explicit_export_root() -> str | None:
    """The explicit ``SDLC_EXPORT_ROOT``, or None.

    Callers that treat an explicit export root specially (graph/store.py's
    ``graphs``-sibling rule) must not start firing merely because a fleet
    runs root is exported, so ``SDLC_RUNS_ROOT`` never shows up here.
    """
    return _set("SDLC_EXPORT_ROOT")


def benchmarks_root() -> str:
    """Where the recorder writes its ``records.jsonl`` trees."""
    explicit = _set("SDLC_BENCHMARKS_ROOT")
    if explicit is not None:
        return explicit
    runs = _set("SDLC_RUNS_ROOT")
    if runs is not None:
        return f"{runs}/benchmarks"
    return BENCHMARKS_DEFAULT


def export_root() -> str:
    """Where run exports (``summary.json`` et al.) live."""
    explicit = _set("SDLC_EXPORT_ROOT")
    if explicit is not None:
        return explicit
    runs = _set("SDLC_RUNS_ROOT")
    if runs is not None:
        return f"{runs}/pipeline"
    return EXPORT_DEFAULT


def roots_report() -> RootsReport:
    """Both roots and the precedence branch each one took."""
    return RootsReport(
        records=benchmarks_root(),
        export=export_root(),
        records_how="explicit"
        if _set("SDLC_BENCHMARKS_ROOT")
        else ("runs_root" if _set("SDLC_RUNS_ROOT") else "default"),
        export_how="explicit"
        if _set("SDLC_EXPORT_ROOT")
        else ("runs_root" if _set("SDLC_RUNS_ROOT") else "default"),
    )
