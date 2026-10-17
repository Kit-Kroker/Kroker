"""One cases location for every reader (012, R-1 / data-model §2.1).

Before 012 the cases location was derived five separate ways: the oracle
and the task loader honoured ``SDLC_CASES_ROOT`` (the worker image sets
it) while the judge, the report and the CLI derived it from this
module's own file path — so a rubric registered in a manifest could be
invisible to the very judge meant to read it. This leaf module is the
single resolution point: every reader of case files goes through
``cases_dir()``; calibration lives at its sibling so one override moves
both. Leaf by construction: imports nothing from the benchmark package.

016 (FR-017/FR-018): a second, private cases root — the store — is read
ALONGSIDE the first. ``SDLC_PRIVATE_CASES_ROOT`` names it; resolution
spans both roots, with duplicates refused and exposure derived from the
root a case was found under. ``cases_dir()`` and ``calibration_dir()``
keep their exact 012 meaning.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

CASES_ENV = "SDLC_CASES_ROOT"
PRIVATE_CASES_ENV = "SDLC_PRIVATE_CASES_ROOT"
_CHECKOUT_CASES = Path(__file__).resolve().parents[3] / "benchmarks" / "cases"

# 016 Names (Resolver): acceptance.Exposure restated as its own literal so
# this leaf imports nothing from the benchmark package.
Exposure = Literal["repo_public", "isolated"]


def cases_dir() -> Path:
    """The cases root. Reads ``SDLC_CASES_ROOT`` at call time (never at
    import) and falls back to the checkout's ``benchmarks/cases`` — the
    editable install resolves ``__file__`` to the worktree source."""
    return Path(os.environ.get(CASES_ENV, str(_CHECKOUT_CASES)))


def private_cases_dir() -> Path | None:
    """The private store's cases root, or None when
    ``SDLC_PRIVATE_CASES_ROOT`` is unset or empty. Read at call time,
    house style (``cases_dir``)."""
    value = os.environ.get(PRIVATE_CASES_ENV, "")
    return Path(value) if value else None


def case_roots() -> list[Path]:
    """Every cases root a reader must consult: ``cases_dir()`` alone, plus
    ``private_cases_dir()`` when configured — whether or not it exists on
    disk (configuration is not existence)."""
    roots = [cases_dir()]
    private = private_cases_dir()
    if private is not None:
        roots.append(private)
    return roots


class DuplicateCase(ValueError):
    """The same case id resolves in more than one root. The message names
    both case directories."""


class CaseNotFound(LookupError):
    """No root has the case id. The message names every root searched, and
    adds the unreadable-store line when the private root is configured but
    not a directory."""


def _duplicate_message(case_id: str, dirs: list[Path]) -> str:
    return f"case '{case_id}' exists in multiple roots: " + ", ".join(str(d) for d in dirs)


def case_dir(case_id: str) -> Path:
    """LENIENT resolution (D-2): the first root whose ``<root>/<case_id>``
    is a directory. Both roots having it raises :class:`DuplicateCase`;
    neither having it returns ``cases_dir() / case_id`` (today's path), so
    every caller that tolerates absence behaves as before."""
    hits = [root / case_id for root in case_roots() if (root / case_id).is_dir()]
    if len(hits) > 1:
        raise DuplicateCase(_duplicate_message(case_id, hits))
    return hits[0] if hits else cases_dir() / case_id


def require_case_dir(case_id: str) -> Path:
    """STRICT resolution (D-2): as ``case_dir``, but a case found in no
    root raises :class:`CaseNotFound` naming every root searched."""
    hits = [root / case_id for root in case_roots() if (root / case_id).is_dir()]
    if len(hits) > 1:
        raise DuplicateCase(_duplicate_message(case_id, hits))
    if hits:
        return hits[0]
    private = private_cases_dir()
    unreadable = private is not None and not private.is_dir()
    message = f"case '{case_id}' is in no cases root ({', '.join(str(r) for r in case_roots())})"
    if unreadable:
        message += f"; private store configured at {private} but not readable"
    raise CaseNotFound(message)


def iter_case_dirs() -> list[tuple[Path, Path]]:
    """``(root, case_dir)`` for every ``<root>/*/case.yaml`` across both
    roots, sorted by case id (one global sort, not per-root chunks). An id
    present in both roots raises :class:`DuplicateCase`."""
    found: dict[str, tuple[Path, Path]] = {}
    for root in case_roots():
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if not (entry / "case.yaml").is_file():
                continue
            if entry.name in found:
                other = found[entry.name][1]
                raise DuplicateCase(_duplicate_message(entry.name, [other, entry]))
            found[entry.name] = (root, entry)
    return [found[case_id] for case_id in sorted(found)]


def root_exposure(case_dir: Path) -> Exposure:
    """Where a case dir lives (016 D-4): ``isolated`` under the configured
    private root, ``repo_public`` everywhere else — including when no
    private root is configured."""
    private = private_cases_dir()
    if private is not None and case_dir.is_relative_to(private):
        return "isolated"
    return "repo_public"


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
