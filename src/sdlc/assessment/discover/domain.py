# src/sdlc/assessment/discover/domain.py
"""FR-913 (E-48 DD12, clause D7): the consolidated domain model.

DERIVED from assign()'s OwnershipReport, never re-judged. The proposer's
standing to override a conflict is exercised through a disposition on the
CAPABILITY -- which changes the member set assign() runs over -- not by
editing this table.

Pure by design.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...measurement import CollectionState, Measurement
from .map import Capability, DomainEntity, DomainModel
from .models import OwnershipOutcome, OwnershipReport


def consolidate(ownership: OwnershipReport, capabilities: Iterable[Capability]) -> DomainModel:
    """One DomainEntity per ownership row, sorted by entity name.

    `capabilities` is accepted and currently unused for row construction: it
    is the set the bc_ids resolve against, and E-52's reports join on it. It
    stays in the signature rather than being added later because a consumer
    that has to re-derive the join is how two joins that must agree start
    disagreeing.
    """
    if ownership.collected.state is not CollectionState.MEASURED:
        # P3-D5. An empty table would claim the repository has no entities,
        # which is the FR-915 conflation this codebase refuses everywhere
        # else.
        return DomainModel(
            collected=Measurement.not_collected(
                f"ownership did not collect: {ownership.collected.reason}"
            )
        )

    rows = tuple(
        sorted(
            (
                DomainEntity(
                    entity=e.entity,
                    outcome=e.outcome,
                    owner=e.owner,
                    verb=e.verb,
                    # The owner is not its own reader. Sorted here because
                    # EntityOwnership.claimants is already sorted and set difference
                    # is not order-preserving.
                    readers=tuple(
                        sorted(set(e.claimants) - {e.owner} if e.owner else set(e.claimants))
                    ),
                )
                for e in ownership.entities
            ),
            key=lambda d: d.entity,
        )
    )

    return DomainModel(
        entities=rows,
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))),
    )
