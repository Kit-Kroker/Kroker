"""Deterministic freeze of a DraftOutput into a Constitution (FR-112, plan
Task 2). The model proposes; code validates — offending principles are
dropped, never retried or repaired, and the survivors are frozen with
code-assigned ids. Pure function: no I/O, no model calls; the same draft and
mode always produce the same FreezeResult, and model noise (empty statements,
odd whitespace, duplicates) is handled by rules rather than exceptions.

The rules (spec §5, freeze semantics RESOLVED: partial freeze):

- ids `CP-1`, `CP-2`, … are assigned in surviving order — the
  `_PlannerOutput` precedent: the model never names the artifact's ids.
- brownfield drafts require a `source_ref`: items with an empty ref (None
  or "") are dropped. Greenfield drafts are exempt — an idea-alone draft
  has nothing to cite.
- exact-duplicate statements collapse to the first occurrence
  (case-sensitive match on the verbatim statement; no normalization, so
  whitespace variants are distinct principles, not duplicates).
- statements that are empty or whitespace-only are dropped as noise.
- zero survivors degrade the stage: `drafted_by="empty"`, `digest=""` (the
  research ungrounded sentinel), `degraded=True` — the FAIL is noted by the
  caller; verify itself never raises, and the opt-in flag can never kill a
  run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import Constitution, DraftOutput, Principle, constitution_digest

FreezeMode = Literal["greenfield", "brownfield"]


class FreezeResult(BaseModel):
    """The outcome of freezing one draft: the frozen constitution plus an
    audit trail of what verify dropped and whether the stage degraded."""

    frozen: Constitution
    dropped: list[str] = Field(default_factory=list)  # dropped statements, draft order
    degraded: bool  # True iff nothing survived — the caller records FAIL


def freeze(draft: DraftOutput, *, mode: FreezeMode) -> FreezeResult:
    """Turn the drafter's raw proposals into a Constitution, dropping the
    offenders and freezing the rest (partial freeze — see module docstring
    for the rules). `dropped` lists each dropped item's statement in draft
    order; ids on survivors renumber densely from CP-1."""
    frozen: list[Principle] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in draft.principles:
        statement = item.statement
        if not statement.strip():
            dropped.append(statement)
            continue
        if mode == "brownfield" and not item.source_ref:
            dropped.append(statement)
            continue
        if statement in seen:  # exact, case-sensitive match
            dropped.append(statement)
            continue
        seen.add(statement)
        frozen.append(
            Principle(
                id=f"CP-{len(frozen) + 1}",
                statement=statement,
                normative=item.normative,
                rationale=item.rationale,
                source_ref=item.source_ref,
            )
        )
    if frozen:
        constitution = Constitution(
            principles=frozen, digest=constitution_digest(frozen), drafted_by="agent"
        )
        degraded = False
    else:
        constitution = Constitution(principles=[], digest="", drafted_by="empty")
        degraded = True
    return FreezeResult(frozen=constitution, dropped=dropped, degraded=degraded)
