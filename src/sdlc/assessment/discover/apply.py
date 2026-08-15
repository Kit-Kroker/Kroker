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
    REJECTING_ACTIONS, Capability, CandidateContext, CandidateDisposition,
    CapabilityMap, DiscoverAction, DiscoverContext, DiscoverProposal,
    DispositionSource, ProposedDisposition,
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
               known: Mapping[str, CandidateContext]) -> CandidateDisposition:
    cid = context.candidate_id
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
        refusal = _split_refusal(context, proposed)
        if refusal:
            return _dropped(
                cid, refusal,
                "the split does not partition this candidate's own members")
    if proposed.action is DiscoverAction.MERGE:
        refusal = _merge_refusal(context, proposed, known)
        if refusal:
            return _dropped(
                cid, refusal,
                f"merge_into={proposed.merge_into!r} does not name another "
                f"candidate in this context")
    try:
        return CandidateDisposition(
            candidate_id=cid, action=proposed.action,
            source=DispositionSource.PROPOSER, rule="proposer",
            rationale=proposed.rationale, merge_into=proposed.merge_into,
            partitions=proposed.partitions, evidence=proposed.evidence)
    except ValidationError as exc:
        return _dropped(cid, "dropped_malformed",
                        f"the disposition did not validate: {exc}"[:300])


def stamp(context: DiscoverContext,
          proposal: DiscoverProposal | None) -> StampedProposal:
    """DD8 items 1-3 and DD7's two fallbacks.

    `proposal is None` is the proposer-ABSENT case (the role is not shipped
    or the stage is off) and yields DD6's baseline. A proposal that is
    present but missing a row is the proposer-FAILED case and yields FLAG.
    The two must not converge -- unbuilt_signal vs failed_signal states the
    rule, and "the reason strings must not converge".

    Items 4 and 5 (an EvidenceRef path resolving at the pinned commit, a
    quote byte-verifying) need the tree and land in plan 3's
    verify_discover_refs, in front of this function.
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

    first = [_stamp_one(c, by_candidate.get(c.candidate_id, ()), known)
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
