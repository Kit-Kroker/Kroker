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

from collections.abc import Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import CandidateMember, EvidenceRef, MemberKind
from ..scan.naming import head_token, normalize, route_object
from .models import (
    CONTRACT_KINDS, ROUTE_SHAPED_KINDS, DecompositionReport, L2Operation,
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
    """The entity key this operation is about, or "".

    Both branches end in normalize(head_token(...)) -- S2's _cluster_key --
    so an operation's object and an entity's key are comparable by
    construction rather than by two tables agreeing.
    """
    raw = member.value
    if member.kind in ROUTE_SHAPED_KINDS:
        segment = route_object(member.value)
        if segment is None:
            return ""
        raw = segment
    return normalize(head_token(raw))


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
        return DecompositionReport(
            by_capability={bc_id: 0 for bc_id in sorted(members)},
            collected=contract_collected)

    operations: list[L2Operation] = []
    for bc_id in sorted(members):
        contract = sorted(
            (m for m in members[bc_id] if m.kind in CONTRACT_KINDS),
            key=CandidateMember.sort_key)
        for index, member in enumerate(contract, start=1):
            verb, rule = _verb(member)
            obj = _object(member)
            operations.append(L2Operation(
                op_id=f"{bc_id}-OP-{index:02d}",
                capability=bc_id,
                verb=verb,
                name=f"{verb.value}_{obj}" if obj else verb.value,
                object=obj,
                binding=member.value,
                kind=member.kind,
                rule=rule,
                evidence=EvidenceRef(
                    path=member.path,
                    lines="" if member.line is None else str(member.line)),
            ))

    return DecompositionReport(
        operations=tuple(operations),
        by_capability={
            bc_id: sum(1 for o in operations if o.capability == bc_id)
            for bc_id in sorted(members)},
        # The value is the row count, following SS4's convention that a
        # Measurement carries something worth reading, not a bare flag.
        collected=Measurement.measured(float(len(operations))))
