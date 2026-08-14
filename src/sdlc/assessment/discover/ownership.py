"""FR-913 (E-47c): which capability owns each data entity.

D7's precedence -- declaration site, then write access, then read access --
is ordered by strength of evidence. Declaration is the strongest and the
cheapest to explain: the capability whose files declare the table is the one
a customer would name. Access ranks below it because it is a
name-normalization match, not a data-flow trace.

Nothing here decides consequences. An ownership conflict is a finding, not a
failure; E-50 owns gate checks and E-48 owns resolution (D11).

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...measurement import CollectionState, Measurement
from ..scan.models import EvidenceRef
from ..scan.naming import head_token, normalize
from .models import (
    DIRECTED_VERBS, READ_VERBS, WRITE_VERBS, EntityDeclaration,
    EntityOwnership, L2Operation, OperationVerb, OwnershipOutcome,
    OwnershipReport, OwnershipVerb,
)


def _key(name: str) -> str:
    """S2's _cluster_key: order_items and orders both reach 'order'. Both
    helpers are already public in naming.py, so nothing is promoted here."""
    return normalize(head_token(name)) or name.strip().lower()


def _empty(reason: str) -> OwnershipReport:
    """FR-915: ownership was not computed, so there are no rows -- not zero
    owners, and certainly not a map of unclaimed entities."""
    return OwnershipReport(
        entities=(), counts={o: 0 for o in OwnershipOutcome},
        collected=Measurement.not_collected(reason))


def _write_verb(verbs: set[OperationVerb]) -> OwnershipVerb:
    """CREATES only when every matching write creates; anything else is the
    broader MANAGES (D7 rule 2)."""
    return (OwnershipVerb.CREATES if verbs == {OperationVerb.CREATE}
            else OwnershipVerb.MANAGES)


def _resolve(entity: str, decls: Sequence[EntityDeclaration],
             declarers: set[str], ops: Sequence[L2Operation]) -> EntityOwnership:
    decl_evidence = tuple(EvidenceRef(path=d.path, lines=str(d.line))
                          for d in decls)
    op_evidence = tuple(o.evidence for o in ops)
    evidence = decl_evidence + op_evidence

    writers = {o.capability for o in ops if o.verb in WRITE_VERBS}
    readers = {o.capability for o in ops if o.verb in READ_VERBS}
    undirected = {o.capability for o in ops if o.verb not in DIRECTED_VERBS}
    # Every capability with ANY contact -- declaration, directed access, or
    # undirected touch -- is a claimant, whatever rule won (review finding
    # 3). Three reasons, in ascending order of importance: the row must not
    # understate contact; every claimant is backed by an evidence ref
    # beside it; and D7 accepts the shared-models limitation only because
    # E-48's proposer can override it -- which it cannot do if the row
    # never shows the capability that lost.
    claimants = tuple(sorted(declarers | writers | readers | undirected))

    # Rule 1 -- declaration site.
    if len(declarers) == 1:
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.OWNED,
            owner=next(iter(declarers)), verb=OwnershipVerb.OWNS,
            rule="declared_in_sole_member",
            claimants=claimants, evidence=evidence)
    if len(declarers) > 1:
        # 'declared_in_shared_file' is only true when one file carries two
        # capabilities; the same key declared in different files across
        # capabilities is a tie across files, and the rule must not
        # misname it (review finding 5).
        rule = ("declared_in_shared_file"
                if len({d.path for d in decls}) == 1 else "tied_declarers")
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.CONFLICT,
            rule=rule, claimants=claimants, evidence=evidence)

    # Rule 2 -- sole writer.
    if len(writers) == 1:
        owner = next(iter(writers))
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.OWNED, owner=owner,
            verb=_write_verb({o.verb for o in ops
                              if o.capability == owner
                              and o.verb in WRITE_VERBS}),
            rule="sole_writer", claimants=claimants, evidence=evidence)
    if len(writers) > 1:
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers", claimants=claimants, evidence=evidence)

    # Rule 3 -- sole reader.
    if len(readers) == 1:
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.OWNED,
            owner=next(iter(readers)), verb=OwnershipVerb.READS,
            rule="sole_reader", claimants=claimants, evidence=evidence)
    if len(readers) > 1:
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.CONFLICT,
            rule="tied_readers", claimants=claimants, evidence=evidence)

    # Rules 4/5 -- something touched it, but nothing readable said which way.
    if undirected:
        return EntityOwnership(
            entity=entity, outcome=OwnershipOutcome.UNDIRECTED,
            rule="undirected_only", claimants=claimants, evidence=evidence)
    return EntityOwnership(
        entity=entity, outcome=OwnershipOutcome.UNCLAIMED,
        rule="no_claimant", evidence=decl_evidence)


def assign(
    declarations: Sequence[EntityDeclaration],
    member_paths: Mapping[str, Sequence[str]],
    operations: Sequence[L2Operation],
    *,
    schema_collected: Measurement,
    contract_collected: Measurement,
) -> OwnershipReport:
    """Declarations + capability member paths + operations, in; one ownership
    row per distinct entity key, out.

    Fail closed on EITHER upstream (D9). Without S2 nothing declares, so every
    entity falls to the access fallback; without S3 nothing accesses, so every
    entity falls to declaration. Both produce a systematically different answer
    in the IDENTICAL shape, which a caller cannot tell from a healthy one.
    """
    if schema_collected.state is not CollectionState.MEASURED:
        return _empty(f"S2 did not collect: {schema_collected.reason}")
    if contract_collected.state is not CollectionState.MEASURED:
        return _empty(f"S3 did not collect: {contract_collected.reason}")

    owner_of: dict[str, set[str]] = {}
    for bc_id, paths in member_paths.items():
        for path in paths:
            owner_of.setdefault(path, set()).add(bc_id)

    grouped: dict[str, list[EntityDeclaration]] = {}
    for decl in sorted(declarations, key=lambda d: (d.path, d.line, d.name)):
        grouped.setdefault(_key(decl.name), []).append(decl)

    rows: list[EntityOwnership] = []
    for entity in sorted(grouped):
        decls = grouped[entity]
        declarers = {bc for d in decls for bc in owner_of.get(d.path, ())}
        # Matching reads entity_keys, never object: route kinds keep strict
        # single-key matching (only they carry directed verbs), undirected
        # kinds match on any reduced token of their binding (review F1).
        ops = sorted((o for o in operations if entity in o.entity_keys),
                     key=lambda o: o.op_id)
        rows.append(_resolve(entity, decls, declarers, ops))

    return OwnershipReport(
        entities=tuple(rows),
        counts={o: sum(1 for r in rows if r.outcome is o)
                for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))))
