"""The code-computed confidence floor (023a T012, FR-010 / R8).

Pure: the floor is derived only from deterministic facts — the finding's
fix class, reproduction, reopen count and action count. The proposer's
self-rating is never trusted alone: ``effective = min(self_confidence,
floor)`` is computed by the caller (the workflow, onto the RepairPlan).

The floor table (research.md R8), documented and unit-tested:

    fix class   ceiling   subtract                                          floored at
    MECHANICAL  0.95      0.15 if not reproduced, 0.20/reopen, 0.05/action>1  0
    JUDGEMENT   0.6       same                                              0
    STRUCTURAL  0.0       —                                                 0

Consequence, stated in the spec: at the default threshold 0.8 only
MECHANICAL findings reproduced on a second consecutive detect clear
policy; advisory and credential plans (JUDGEMENT) are human-gated by
construction.
"""

from __future__ import annotations

from ..triage.models import FixClass, TriageFinding

CEILING_MECHANICAL = 0.95
CEILING_JUDGEMENT = 0.6
CEILING_STRUCTURAL = 0.0

PENALTY_NOT_REPRODUCED = 0.15
PENALTY_PER_REOPEN = 0.2
PENALTY_PER_EXTRA_ACTION = 0.05


def confidence_floor(
    finding: TriageFinding,
    *,
    reproduced: bool,
    reopens: int,
    n_actions: int,
) -> float:
    """The deterministic cap for a repair plan of this finding.

    `reproduced` is a fact the workflow tracks across cycles (seen on two
    consecutive detects); `reopens` is 0 everywhere in 023a (reopen is a
    023b state) but priced now so the table cannot silently change;
    `n_actions` is the proposal's action count.
    """
    if finding.fix_class is FixClass.MECHANICAL:
        ceiling = CEILING_MECHANICAL
    elif finding.fix_class is FixClass.JUDGEMENT:
        ceiling = CEILING_JUDGEMENT
    else:
        return 0.0

    penalty = 0.0
    if not reproduced:
        penalty += PENALTY_NOT_REPRODUCED
    penalty += PENALTY_PER_REOPEN * max(reopens, 0)
    penalty += PENALTY_PER_EXTRA_ACTION * max(n_actions - 1, 0)
    return round(max(ceiling - penalty, 0.0), 10)
