# src/sdlc/assessment/discover/apply.py
"""FR-913 (E-48 DD6/DD7/DD8): dispositions in, the locked candidate set out.

Pure by design -- Pydantic, measurement.py and capability/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
the rest of discover/ must not.

Four things happen here and they are deliberately separate functions:
`baseline_dispositions` is DD6's code-computed verdict, `stamp` is DD8's
structural verification plus DD7's two fallbacks, `apply` turns verified
dispositions into the boundaries the lock will identify, and `build_map` is
the artifact's one constructor. Splitting them is what lets plan 3 insert a
proposer between the first and the second without touching either.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError, model_validator

from ...capability.models import Advisory, CapabilityFingerprint
from ...measurement import Measurement
from ..scan.models import CandidateMember, Confidence
from .map import (
    REJECTING_ACTIONS, BlueprintComparison, Capability, CandidateContext,
    CandidateDisposition, CapabilityMap, DiscoverAction, DiscoverContext,
    DiscoverProposal, DispositionSource, DomainModel, ProposedDisposition,
)
from .models import AttributionReport, DecompositionReport, OwnershipReport
from .tiers import group_by_tier


def baseline(context: CandidateContext) -> CandidateDisposition:
    """DD6's table, read top to bottom. Declaration order IS precedence
    order, following BUCKET_PRECEDENCE -- there is no second list to disagree
    with this one.

    The guardrail outranks the duplicate flag deliberately (P2-D1): a
    candidate named like a layer is not a capability whichever other
    candidate it overlaps, and FLAGging it would ask a human to adjudicate a
    boundary clause D2 already rejects.
    """
    row = dict(candidate_id=context.candidate_id,
               source=DispositionSource.BASELINE)
    if context.guardrail_only:
        return CandidateDisposition(
            **row, action=DiscoverAction.DE_SCOPE, rule="baseline_guardrail")
    if context.possible_duplicate_of:
        return CandidateDisposition(
            **row, action=DiscoverAction.FLAG,
            rule="baseline_possible_duplicate")
    return CandidateDisposition(
        **row, action=DiscoverAction.CONFIRM, rule="baseline_confirm")


def baseline_dispositions(
        context: DiscoverContext) -> tuple[CandidateDisposition, ...]:
    """One baseline per candidate, in the context's order -- which
    build_context already sorted by candidate_id (NFR-10)."""
    return tuple(baseline(c) for c in context.candidates)


class StampedProposal(BaseModel):
    """Every candidate's verified disposition, plus what verification refused.

    `unknown_candidate_ids` is deliberately not folded into `dropped`: a
    disposition naming a candidate that does not exist has no row to carry
    it, so the id itself is the only record verification leaves behind.
    Counting it and discarding the id would make the citation guard's input
    unauditable.
    """
    dispositions: tuple[CandidateDisposition, ...] = ()
    unknown_candidate_ids: tuple[str, ...] = ()
    dropped: int = 0

    @model_validator(mode="after")
    def _dropped_is_derived(self) -> "StampedProposal":
        actual = sum(1 for d in self.dispositions
                     if d.source is DispositionSource.DROPPED)
        if self.dropped != actual:
            raise ValueError(
                f"dropped={self.dropped} but {actual} disposition(s) carry "
                f"source=dropped -- counts are derived from rows, never "
                f"assigned")
        return self

    @model_validator(mode="after")
    def _one_row_per_candidate_sorted(self) -> "StampedProposal":
        ids = [d.candidate_id for d in self.dispositions]
        if ids != sorted(set(ids)):
            raise ValueError(
                f"candidate ids {ids} are not one-per-candidate and sorted "
                f"-- DD8 requires exactly one disposition per candidate, and "
                f"discovery order must not reach the artifact")
        return self

    @model_validator(mode="after")
    def _unknown_ids_are_sorted(self) -> "StampedProposal":
        if list(self.unknown_candidate_ids) != sorted(
                set(self.unknown_candidate_ids)):
            raise ValueError(
                f"unknown_candidate_ids {self.unknown_candidate_ids} are not "
                f"sorted and deduped")
        return self


def _dropped(candidate_id: str, rule: str, detail: str) -> CandidateDisposition:
    """DD7: a refused model verdict becomes FLAG for that candidate, never
    the baseline. "A model decided this and cited something that does not
    exist" is evidence about the candidate; laundering it into a
    code-computed CONFIRM would discard that evidence."""
    return CandidateDisposition(
        candidate_id=candidate_id, action=DiscoverAction.FLAG,
        source=DispositionSource.DROPPED, rule=rule, rationale=detail)


def _split_refusal(context: CandidateContext,
                   proposed: ProposedDisposition) -> str:
    """The rule naming why a SPLIT was refused, or "" when it stands.

    Coverage is NOT required: a partition that leaves members behind loses
    them from the capability set, but they then fall out of attribute()'s
    numerator and the coverage floor reports it. A silent loss would be worth
    refusing; a visible one is not.
    """
    parts = proposed.partitions
    if len(parts) < 2:
        return "dropped_split_partitions"
    names = [p.name for p in parts]
    if len(set(names)) != len(names):
        return "dropped_split_names"
    own = {m.value for m in context.members}
    seen: set[str] = set()
    for part in parts:
        values = set(part.member_values)
        if not values or not values <= own:
            return "dropped_split_members"
        if seen & values:
            return "dropped_split_overlap"
        seen |= values
    return ""


def _merge_refusal(context: CandidateContext, proposed: ProposedDisposition,
                   known: Mapping[str, CandidateContext]) -> str:
    if proposed.merge_into == context.candidate_id:
        return "dropped_merge_self"
    if proposed.merge_into is None or proposed.merge_into not in known:
        return "dropped_merge_target"
    return ""


def _stamp_one(context: CandidateContext,
               rows: Sequence[ProposedDisposition],
               known: Mapping[str, CandidateContext],
               refusal: tuple[str, str] | None = None) -> CandidateDisposition:
    cid = context.candidate_id
    if refusal is not None:
        # DD8 items 4-5 already refused this verdict. Checked BEFORE the
        # empty-rows branch: verify_refs removed the row, so `rows` is empty
        # here, and dropped_missing would report an omission the proposer did
        # not commit (P3-D1).
        return _dropped(cid, refusal[0], refusal[1])
    if not rows:
        return _dropped(
            cid, "dropped_missing",
            "the proposer returned no disposition for this candidate")
    if len(rows) > 1:
        return _dropped(
            cid, "dropped_duplicated",
            f"the proposer returned {len(rows)} dispositions for this "
            f"candidate; DD8 requires exactly one")
    proposed = rows[0]
    if proposed.action is DiscoverAction.SPLIT:
        refusal_rule = _split_refusal(context, proposed)
        if refusal_rule:
            return _dropped(
                cid, refusal_rule,
                "the split does not partition this candidate's own members")
    if proposed.action is DiscoverAction.MERGE:
        refusal_rule = _merge_refusal(context, proposed, known)
        if refusal_rule:
            return _dropped(
                cid, refusal_rule,
                f"merge_into={proposed.merge_into!r} does not name another "
                f"candidate in this context")
    try:
        return CandidateDisposition(
            candidate_id=cid, action=proposed.action,
            source=DispositionSource.PROPOSER, rule="proposer",
            rationale=proposed.rationale, merge_into=proposed.merge_into,
            partitions=proposed.partitions, evidence=proposed.evidence,
            quote=proposed.quote)
    except ValidationError as exc:
        return _dropped(cid, "dropped_malformed",
                        f"the disposition did not validate: {exc}"[:300])


def stamp(context: DiscoverContext,
          proposal: DiscoverProposal | None,
          *,
          refusals: Mapping[str, tuple[str, str]] = {}) -> StampedProposal:
    """DD8 items 1-3 and DD7's two fallbacks.

    `refusals` carries DD8 items 4-5's verdicts from verify_refs, which runs
    in front of this function because it needs the tree. Defaulting to empty
    keeps plan 2's callers and tests unchanged (P3-D1).

    `proposal is None` is the proposer-ABSENT case (the role is not shipped
    or the stage is off) and yields DD6's baseline. A proposal that is
    present but missing a row is the proposer-FAILED case and yields FLAG.
    The two must not converge -- unbuilt_signal vs failed_signal states the
    rule, and "the reason strings must not converge".
    """
    if proposal is None:
        return StampedProposal(dispositions=baseline_dispositions(context))

    known = {c.candidate_id: c for c in context.candidates}
    by_candidate: dict[str, list[ProposedDisposition]] = {}
    unknown: set[str] = set()
    for row in proposal.dispositions:
        if row.candidate_id in known:
            by_candidate.setdefault(row.candidate_id, []).append(row)
        else:
            unknown.add(row.candidate_id)

    first = [_stamp_one(c, by_candidate.get(c.candidate_id, ()), known,
                        refusals.get(c.candidate_id))
             for c in context.candidates]

    # Second pass. A MERGE whose target did not itself survive would fold the
    # loser's members into nothing, which is the silent-member-loss defect
    # _split_refusal's coverage note explains is worth refusing. Chains die
    # here too: in A->B->C, B's action is MERGE rather than CONFIRM.
    confirmed = {d.candidate_id for d in first
                 if d.action is DiscoverAction.CONFIRM}
    final = tuple(
        d if not (d.action is DiscoverAction.MERGE
                  and d.merge_into not in confirmed)
        else _dropped(
            d.candidate_id, "dropped_merge_target_not_confirmed",
            f"merge_into={d.merge_into!r} was not itself confirmed, so the "
            f"merge would fold these members into nothing")
        for d in first)

    return StampedProposal(
        dispositions=final,
        unknown_candidate_ids=tuple(sorted(unknown)),
        dropped=sum(1 for d in final
                    if d.source is DispositionSource.DROPPED))


# P2-D2. build_context computed cohesion and coupling over the candidate's
# ORIGINAL members and then discarded the reference graph (DD4), so a
# boundary whose member set changed cannot have them recomputed here.
# Reporting the old number would attach a measurement to a thing it does not
# describe, which is the FR-915 conflation.
_SPLIT_REASON = ("this boundary is one partition of a split candidate, and "
                 "the metric was computed over the whole candidate")
_MERGE_REASON = ("this boundary absorbed another candidate's members, and "
                 "the metric was computed before the merge")


class LockedCandidate(BaseModel):
    """A boundary that survived disposition, before it has a bc_id.

    Capability minus bc_id, deliberately: identity is the lock's to assign
    (D4), and a type that could hold one before the lock ran would let a
    caller mint capability identity in the wrong phase -- the confusion
    ScanCandidate's docstring already warns about for C-NN vs BC-NNN.
    """
    model_config = {"frozen": True}
    local_key: str
    name: str
    confidence: Confidence
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement
    coupling: Measurement
    disposition: CandidateDisposition


class ApplyResult(BaseModel):
    locked: tuple[LockedCandidate, ...] = ()
    stamped: StampedProposal

    @model_validator(mode="after")
    def _local_keys_are_unique_and_sorted(self) -> "ApplyResult":
        keys = [c.local_key for c in self.locked]
        if keys != sorted(set(keys)):
            raise ValueError(
                f"local_keys {keys} are not unique and sorted -- resolve() "
                f"raises on a duplicate local_key, and discovery order must "
                f"not reach the artifact")
        return self


def apply(context: DiscoverContext,
          stamped: StampedProposal) -> ApplyResult:
    """Verified dispositions in, the boundaries the lock will identify out.

    CONFIRM keeps its measured metrics; a merge winner and a split part lose
    theirs to not_collected (P2-D2). MERGE produces no boundary of its own --
    the loser's members fold into the winner, and only the winner is handed
    to resolve().
    """
    by_id = {c.candidate_id: c for c in context.candidates}
    disposition_of = {d.candidate_id: d for d in stamped.dispositions}

    absorbed: dict[str, list[CandidateContext]] = {}
    for d in stamped.dispositions:
        if d.action is DiscoverAction.MERGE and d.merge_into is not None:
            absorbed.setdefault(d.merge_into, []).append(
                by_id[d.candidate_id])

    locked: list[LockedCandidate] = []
    for context_row in context.candidates:
        d = disposition_of[context_row.candidate_id]
        if d.action in REJECTING_ACTIONS or d.action is DiscoverAction.MERGE:
            continue

        if d.action is DiscoverAction.SPLIT:
            for part in d.partitions:
                wanted = set(part.member_values)
                members = tuple(m for m in context_row.members
                                if m.value in wanted)
                locked.append(LockedCandidate(
                    local_key=f"{context_row.candidate_id}#{part.name}",
                    name=part.name, confidence=context_row.confidence,
                    members=members,
                    member_paths=tuple(sorted({m.path for m in members
                                               if m.path})),
                    cohesion=Measurement.not_collected(_SPLIT_REASON),
                    coupling=Measurement.not_collected(_SPLIT_REASON),
                    disposition=d))
            continue

        taken = absorbed.get(context_row.candidate_id, [])
        members = tuple(sorted(
            set(context_row.members) | {m for a in taken for m in a.members},
            key=CandidateMember.sort_key))
        locked.append(LockedCandidate(
            local_key=context_row.candidate_id, name=context_row.name,
            confidence=context_row.confidence, members=members,
            member_paths=tuple(sorted({m.path for m in members if m.path})),
            cohesion=(Measurement.not_collected(_MERGE_REASON) if taken
                      else context_row.cohesion),
            coupling=(Measurement.not_collected(_MERGE_REASON) if taken
                      else context_row.coupling),
            disposition=d))

    return ApplyResult(
        locked=tuple(sorted(locked, key=lambda c: c.local_key)),
        stamped=stamped)


def fingerprint_of(locked: LockedCandidate) -> CapabilityFingerprint:
    """DD3's MemberKind -> SignalTier map applied to one boundary.

    A boundary with no members yields not_collected, never an empty MEASURED
    fingerprint: score() returns None for a not_collected side, so resolve()
    mints a fresh id and files an IDENTITY_NOT_ASSESSED advisory rather than
    scoring it 0.0 against everything -- E-47a's rule, "never scored 0".
    """
    tiers = group_by_tier(locked.members)
    total = sum(len(values) for values in tiers.values())
    if not total:
        return CapabilityFingerprint(
            tiers=tiers,
            collected=Measurement.not_collected(
                f"{locked.local_key} carries no members, so no tier could be "
                f"populated and identity was not assessed"))
    return CapabilityFingerprint(
        tiers=tiers, collected=Measurement.measured(float(total)))


def capabilities_of(applied: ApplyResult,
                    bc_of: Mapping[str, str]) -> tuple[Capability, ...]:
    """The locked Capability rows. Extracted so both the blueprint activity
    and build_map share one construction (DD11)."""
    missing = sorted(c.local_key for c in applied.locked
                     if c.local_key not in bc_of)
    if missing:
        raise ValueError(
            f"no bc_id was attached to {missing} -- resolve() attaches every "
            f"proposed capability, so a missing one is a lock defect rather "
            f"than a degraded input")

    return tuple(
        Capability(bc_id=bc_of[c.local_key], local_key=c.local_key,
                   name=c.name, confidence=c.confidence, members=c.members,
                   member_paths=c.member_paths, cohesion=c.cohesion,
                   coupling=c.coupling, disposition=c.disposition)
        for c in applied.locked)


def build_map(applied: ApplyResult, bc_of: Mapping[str, str], *,
              advisories: Sequence[Advisory] = (),
              attribution: AttributionReport | None = None,
              decomposition: DecompositionReport | None = None,
              ownership: OwnershipReport | None = None,
              total_references: int = 0,
              blueprint: BlueprintComparison | None = None,
              domain_model: DomainModel | None = None) -> CapabilityMap:
    """The ONE constructor of a CapabilityMap, following assemble()'s rule:
    one place where the artifact is built means its derived counts cannot
    disagree with the rows they were derived from.

    `bc_of` is local_key -> bc_id, from the lock's attachments.

    Only ever MEASURED: a discover that could not run reports a not_collected
    PHASE row and carries no map at all, so a not_collected map has no
    producer and Assessment._discover_agrees_with_its_phase would refuse one.
    """
    capabilities = capabilities_of(applied, bc_of)

    return CapabilityMap(
        capabilities=capabilities,
        # Counted over CAPABILITIES, not over dispositions: de_scope, flag and
        # merge occur as verdicts but never as boundaries, and listing them
        # here as zeros would read as "no candidate was de-scoped". The full
        # verdict record is `dispositions`, which carries every one.
        by_action={action: sum(1 for c in capabilities
                               if c.disposition.action is action)
                   for action in DiscoverAction
                   if any(c.disposition.action is action
                          for c in capabilities)},
        dispositions=applied.stamped.dispositions,
        attribution=attribution, decomposition=decomposition,
        ownership=ownership, advisories=tuple(advisories),
        # The audit record of refused verdicts: one verification dropped, plus
        # one naming a candidate that does not exist. NOT the guard's
        # numerator -- DD8 measures a fabrication rate over REFERENCES, and
        # guard_tripped() divides unresolved_references by total_references
        # (P3-D2).
        dropped_dispositions=(applied.stamped.dropped
                              + len(applied.stamped.unknown_candidate_ids)),
        total_references=total_references,
        blueprint=blueprint,
        domain_model=domain_model,
        collected=Measurement.measured(float(len(capabilities))))
