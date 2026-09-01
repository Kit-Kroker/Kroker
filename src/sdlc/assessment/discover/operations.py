"""FR-913 (E-47c): L2 decomposition -- one operation per contract member.

D3 chose the fine grain deliberately. Clustering members into coarser
operations is a judgment call, and a judgment made here is invisible: a wrong
merge looks exactly like a genuine operation. Made in E-48 it is a MERGE
disposition with a rationale, which is the form the methodology already has.

The payoff is that an operation resolves 1:1 to a byte range at the pinned
commit, so SC-7's "zero fabricated path/line refs" holds by construction.

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import CandidateMember, EvidenceRef, MemberKind
from ..scan.naming import head_token, normalize, route_object
from .models import (
    CONTRACT_KINDS,
    ROUTE_SHAPED_KINDS,
    DecompositionReport,
    L2Operation,
    OperationVerb,
)

_METHOD_VERBS: dict[str, OperationVerb] = {
    "POST": OperationVerb.CREATE,
    "PUT": OperationVerb.UPDATE,
    "PATCH": OperationVerb.UPDATE,
    "DELETE": OperationVerb.DELETE,
    "GET": OperationVerb.READ,
    "HEAD": OperationVerb.READ,
}

_KIND_VERBS: dict[MemberKind, OperationVerb] = {
    MemberKind.CLI_COMMAND: OperationVerb.INVOKE,
    MemberKind.GRPC_METHOD: OperationVerb.INVOKE,
    MemberKind.SCHEDULED_JOB: OperationVerb.SCHEDULE,
    MemberKind.QUEUE_TOPIC: OperationVerb.CONSUME,
    MemberKind.FRONTEND_ROUTE: OperationVerb.RENDER,
}


def _verb(member: CandidateMember) -> tuple[OperationVerb, str]:
    """(verb, rule). An unrecognized method reaches INVOKE and records the
    rule -- never dropped, because a route we extracted is a contract we
    observed, whatever its method (D6)."""
    if member.kind is MemberKind.HTTP_ROUTE:
        fields = member.value.split()
        method = fields[0].upper() if fields else ""
        verb = _METHOD_VERBS.get(method)
        if verb is None:
            return OperationVerb.INVOKE, "unrecognized_http_method"
        return verb, f"http_{method.lower()}"
    return _KIND_VERBS[member.kind], f"kind_{member.kind.value}"


def _object(member: CandidateMember) -> str:
    """The route's business object, reduced -- or "" for every other kind.

    Only route-shaped values have a deterministic object rule (D10's
    route_object). For everything else no single-position rule exists: a CLI
    name is verb-first ('sync_orders'), a topic is entity-first
    ('orders.created'), and a job name may carry no entity at all
    ('settle_nightly'), so head_token on those returns the verb or the whole
    string -- garbage stated as evidence (review finding 1). object stays ""
    and entity_keys carries the contact surface instead.
    """
    if member.kind not in ROUTE_SHAPED_KINDS:
        return ""
    segment = route_object(member.value)
    if segment is None:
        return ""
    return normalize(head_token(segment))


def _entity_keys(member: CandidateMember, obj: str) -> tuple[str, ...]:
    """The sorted, reduced entity keys this operation can claim contact on.

    Route-shaped: exactly the object -- only HTTP routes carry directed
    verbs, so their matching stays strict; a loose route match could
    fabricate a writer. Every other kind: the reduction of each separator
    token of the binding. Those kinds are undirected by construction (D6),
    so the most a token match can produce is an UNDIRECTED claimant --
    which is exactly the recall D8's UNDIRECTED outcome exists to provide
    for CLI- and queue-driven repositories.

    Known limit, same species as naming.py's OQ-12: camelCase inside a
    token ('syncOrders') is not split, so its reduction matches nothing.
    A missed key is a miss, not a fabrication.
    """
    if member.kind in ROUTE_SHAPED_KINDS:
        return (obj,) if obj else ()
    tokens = (normalize(token) for token in re.split(r"[._\-\s]+", member.value))
    return tuple(sorted({token for token in tokens if token}))


def decompose(
    members: Mapping[str, Sequence[CandidateMember]],
    *,
    contract_collected: Measurement,
) -> DecompositionReport:
    """bc_id -> its members, in; one operation per contract member, out.

    `contract_collected` is S3's (and S4's) collection state. Fail closed:
    a degraded contract tier must not read as a capability that genuinely
    exposes nothing (D9).
    """
    if contract_collected.state is not CollectionState.MEASURED:
        # No by_capability entries at all, not zero-filled: a zero count is
        # a MEASURED claim, and a gap is never a zero (FR-915, review
        # finding 7).
        return DecompositionReport(collected=contract_collected)

    operations: list[L2Operation] = []
    for bc_id in sorted(members):
        contract = sorted(
            (m for m in members[bc_id] if m.kind in CONTRACT_KINDS), key=CandidateMember.sort_key
        )
        for index, member in enumerate(contract, start=1):
            verb, rule = _verb(member)
            obj = _object(member)
            if obj:
                name = f"{verb.value}_{obj}"
            elif member.kind in ROUTE_SHAPED_KINDS:
                name = verb.value  # spec's pinned bare-verb fallback
            else:
                name = member.value  # a command's own name IS the name
            operations.append(
                L2Operation(
                    op_id=f"{bc_id}-OP-{index:02d}",
                    capability=bc_id,
                    verb=verb,
                    name=name,
                    object=obj,
                    binding=member.value,
                    kind=member.kind,
                    rule=rule,
                    entity_keys=_entity_keys(member, obj),
                    evidence=EvidenceRef(
                        path=member.path, lines="" if member.line is None else str(member.line)
                    ),
                )
            )

    return DecompositionReport(
        operations=tuple(operations),
        by_capability={
            bc_id: sum(1 for o in operations if o.capability == bc_id) for bc_id in sorted(members)
        },
        # The value is the row count, following SS4's convention that a
        # Measurement carries something worth reading, not a bare flag.
        collected=Measurement.measured(float(len(operations))),
    )
