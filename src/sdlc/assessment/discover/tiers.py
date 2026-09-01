"""FR-913 (E-48 DD3): MemberKind -> SignalTier.

Pure by design -- Pydantic-free, in fact. This module must never import
models.py, activities.py, or temporalio, exactly as the rest of discover/
must not.

Two modules reserve this map for E-48 and forbid deriving it from its
neighbour. scan/models.py's MemberKind docstring (D13) requires it be TOTAL:
"the value set is chosen so every CapabilityFingerprint tier has members that
can populate it". discover/models.py's CONTRACT_KINDS comment (E-47c D4)
forbids deriving it from that set, because "two uses of the word 'contract'
that agree only by coincidence" is the defect PipelineConfig.roles' boot-time
mirror assertion exists to prevent.

The warning is correct on the merits. The CONTRACT tier and CONTRACT_KINDS
differ by exactly DB_TABLE: a table name is expensive to change and therefore
strong identity evidence, but a table is not an OPERATION -- an operation is
something the system does, reachable from outside the capability, and a table
is something the system has. ENTITY_NAME makes the point from outside both
sets. test_discover_tiers.py asserts the difference in both directions.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...capability.models import SignalTier
from ..scan.models import CandidateMember, MemberKind

MEMBER_TIERS: dict[MemberKind, SignalTier] = {
    MemberKind.HTTP_ROUTE: SignalTier.CONTRACT,
    MemberKind.CLI_COMMAND: SignalTier.CONTRACT,
    MemberKind.DB_TABLE: SignalTier.CONTRACT,
    MemberKind.QUEUE_TOPIC: SignalTier.CONTRACT,
    MemberKind.GRPC_METHOD: SignalTier.CONTRACT,
    MemberKind.SCHEDULED_JOB: SignalTier.CONTRACT,
    MemberKind.FRONTEND_ROUTE: SignalTier.CONTRACT,
    MemberKind.TEST_NAME: SignalTier.BEHAVIORAL,
    MemberKind.ENTITY_NAME: SignalTier.BEHAVIORAL,
    MemberKind.EXPORTED_SYMBOL: SignalTier.STRUCTURAL,
    MemberKind.PACKAGE_PATH: SignalTier.LOCATIONAL,
    MemberKind.FILE_PATH: SignalTier.LOCATIONAL,
}


def group_by_tier(members: Iterable[CandidateMember]) -> dict[SignalTier, list[str]]:
    """Member values grouped into the tiers CapabilityFingerprint takes.

    Every tier is present, including empty ones: an absent key and an empty
    list are different claims. Sorted and deduped so equal observations
    compare equal regardless of discovery order (NFR-10).
    """
    out: dict[SignalTier, set[str]] = {t: set() for t in SignalTier}
    for member in members:
        out[MEMBER_TIERS[member.kind]].add(member.value)
    return {tier: sorted(values) for tier, values in out.items()}
