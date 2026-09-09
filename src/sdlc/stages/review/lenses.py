"""C8: lens-absence tombstones.

A lens that did not run must not be spelled the same way as a lens that
approved. This module is the single place that decides which of those two
things happened, and the single place that says what each verdict admits.

Pure by construction -- no ``ctx``, no I/O, no cross-stage imports -- so the
rules are table-testable, exactly like ``code/freeze.py`` holds C2's decision
rules. The model invariant mirrors ``Measurement`` (``sdlc/measurement.py``):
a value we may not have, with the reason we do not have it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, model_validator

from .models import ReviewReport

# The lenses whose presence is graded. deep_review is deliberately absent: it
# is post-decision at every call site and gates nothing, so its absence cannot
# be read as approval.
GATING_LENSES: Final[frozenset[str]] = frozenset({"reviewer", "adversary"})


class LensPresence(StrEnum):
    PRESENT = "present"
    DECLARED_ABSENT = "declared_absent"
    NOT_REACHED = "not_reached"
    UNDECLARED_ABSENT = "undeclared_absent"


class LensOutcome(BaseModel):
    """What one lens did on one task attempt.

    Carries FACTS, not a verdict: the two lenses apply genuinely different
    admission rules (see ``primary_admits`` / ``backstop_admits``), and folding
    them into one pre-computed "blocking" boolean is how a silent semantic
    change gets in.
    """

    lens: str
    presence: LensPresence
    approved: bool | None = None
    has_blocking_findings: bool = False
    reason: str = ""

    @model_validator(mode="after")
    def _facts_match_presence(self) -> LensOutcome:
        if self.presence is LensPresence.PRESENT:
            if self.approved is None:
                raise ValueError("PRESENT requires an approved verdict")
            return self
        # Every absent state. An absence that claims approval is exactly the
        # defect C8 exists to end -- make it unconstructible, not merely
        # discouraged.
        if self.approved is not None:
            raise ValueError(f"{self.presence} cannot carry an approved verdict")
        if not self.reason:
            raise ValueError(f"{self.presence} requires a reason")
        return self


def classify_lens(
    lens: str,
    *,
    enabled: bool,
    agent_present: bool,
    reached: bool,
    report: ReviewReport | None,
) -> LensOutcome:
    """The single producer of a tombstone.

    Derived from exactly the facts the runner's own pre-check consults, plus
    one the call site already knows, so the tombstone cannot disagree with the
    predicate that gated the run. ``reached`` is a caller-supplied boolean, not
    an inspection of control flow -- that is what keeps this pure.

    Order carries reasoning: ``enabled`` first, because an operator's
    declaration is the truthful cause and makes geometry moot; then
    ``agent_present``, because a missing agent on an enabled lens is a real
    misconfiguration observable whether or not the run site was reached, and
    hiding it behind NOT_REACHED would suppress a wiring defect on exactly the
    runs (quarantined ones) where lens coverage matters most.
    """
    if report is not None and not reached:
        raise ValueError("a lens that was not reached cannot have produced a report")

    if not enabled:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.DECLARED_ABSENT,
            reason=f"{lens} disabled by configuration",
        )
    if not agent_present:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.UNDECLARED_ABSENT,
            reason=f"{lens} enabled but no agent is configured",
        )
    if not reached:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.NOT_REACHED,
            reason=f"{lens} run site was never reached on this task",
        )
    if report is None:
        return LensOutcome(
            lens=lens,
            presence=LensPresence.UNDECLARED_ABSENT,
            reason=f"{lens} ran but produced no report (raised, or returned nothing)",
        )
    return LensOutcome(
        lens=lens,
        presence=LensPresence.PRESENT,
        approved=bool(report.approve),
        has_blocking_findings=bool(report.blocking_findings),
    )


def primary_admits(outcome: LensOutcome) -> bool:
    """Transcribes ``review is None or review.approve`` (code/step.py:798).

    ANY rejection by a present primary fails the done path -- blocking findings
    or not. Deliberately NOT harmonized with ``backstop_admits``: loosening the
    primary's bar is a substantive change that belongs to its own register row.
    """
    return outcome.presence is not LensPresence.PRESENT or bool(outcome.approved)


def backstop_admits(outcome: LensOutcome) -> bool:
    """Transcribes ``adversary is None or adversary.approve or not
    adversary.blocking_findings`` (code/step.py:813)."""
    return (
        outcome.presence is not LensPresence.PRESENT
        or bool(outcome.approved)
        or not outcome.has_blocking_findings
    )
