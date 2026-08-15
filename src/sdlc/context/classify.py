"""E-84 D3: verify the declared mode against the repository.

Deterministic and no-LLM, which is what SDLC-spec-v2's stage 0 row
("mode in {greenfield, brownfield} resolved") can mean when IdeaBrief.mode is
already a required field: the mode is declared, and this decides whether the
declaration survives contact with the tree.
"""
from __future__ import annotations

from ..models import ProjectMode
from .models import IntakeVerdict, RepoObservation


def classify(observed: RepoObservation,
             declared: ProjectMode) -> IntakeVerdict:
    """The verdict for a declared mode against an observed repository.

    The asymmetry between the two modes is deliberate (D3). A brownfield run
    without a tree is not a weaker run but an ungrounded one -- the map, the
    delta and the check all rest on it, so it fails closed. Greenfield means
    only that "the Architect owns stack + file tree" (ARCHITECTURE.md:85),
    which stays coherent against a repository holding a README, a licence, CI
    config, or a previous run's work. Failing that would break existing runs
    for no invariant, so it warns.
    """
    if declared is ProjectMode.BROWNFIELD:
        if not observed.is_git_repo:
            return IntakeVerdict(
                mode=declared, ok=False,
                reason=f"brownfield declared, but the path is not a git "
                       f"repository{_because(observed)}")
        if not observed.base_branch_resolves:
            return IntakeVerdict(
                mode=declared, ok=False,
                reason=f"brownfield declared, but the base branch does not "
                       f"resolve{_because(observed)}")
        if observed.source_file_count == 0:
            return IntakeVerdict(
                mode=declared, ok=False,
                reason="brownfield declared, but the tree has no source files "
                       "-- there is nothing to map")
        return IntakeVerdict(mode=declared, ok=True)

    warning = ""
    if observed.is_git_repo and observed.source_file_count > 0:
        warning = (f"greenfield declared against a tree holding "
                   f"{observed.source_file_count} source file(s); the "
                   f"Architect owns the file tree and will not see them")
    return IntakeVerdict(mode=declared, ok=True, warning=warning)


def _because(observed: RepoObservation) -> str:
    return f": {observed.reason}" if observed.reason.strip() else ""
