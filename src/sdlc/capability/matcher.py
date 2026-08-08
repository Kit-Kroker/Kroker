"""FR-913 (E-47a): greedy one-to-one assignment.

The Hungarian algorithm is deliberately NOT used. Global optimality means an
unrelated third capability's score can move a pair that matched perfectly
well onto a different id -- indefensible for an identifier a client cites in
a delivered document, because there is no way to explain why BC-003 moved
because of a change somewhere else.

Greedy is locally stable: a strong pair matches regardless of what else is
in the set, and the rule states in one sentence. Capability counts are in
the tens, so O(n^2) scoring is not a constraint.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import NamedTuple

from .fingerprint import score as score_pair
from .models import (
    Advisory, AdvisoryKind, AttachMethod, CapabilityIdentity,
    DEFAULT_TIER_WEIGHTS, EPSILON, IdentityAttachment, IdentityStatus,
    ProposedCapability, ResolutionResult, SignalTier, T_MATCH,
)


class Pair(NamedTuple):
    score: float
    bc_id: str
    local_key: str


def assign(pairs: Iterable[Pair]) -> dict[str, str]:
    """local_key -> bc_id, one-to-one.

    Sorting on (-score, bc_id, local_key) is a total order over distinct
    pairs, so the result is independent of input order (NFR-10). Both sides
    are consumed on a claim, which is what stops two capabilities taking one
    id -- the failure a per-capability argmax would produce.
    """
    claimed_ids: set[str] = set()
    claimed_locals: set[str] = set()
    out: dict[str, str] = {}
    for p in sorted(pairs, key=lambda p: (-p.score, p.bc_id, p.local_key)):
        if p.bc_id in claimed_ids or p.local_key in claimed_locals:
            continue
        claimed_ids.add(p.bc_id)
        claimed_locals.add(p.local_key)
        out[p.local_key] = p.bc_id
    return out


def resolve(proposed: Sequence[ProposedCapability],
            registry: Sequence[CapabilityIdentity],
            *,
            allocate: Callable[[], str],
            weights: Mapping[SignalTier, float] = DEFAULT_TIER_WEIGHTS,
            t_match: float = T_MATCH,
            epsilon: float = EPSILON) -> ResolutionResult:
    """Attach an id to every proposed capability.

    `allocate` is injected, not derived: id allocation is store state and
    this function is pure. Task 5's BoardIdentityStore supplies the real
    counter; tests supply a deterministic one.

    MERGED rows are excluded from candidacy -- a merged id has been absorbed
    and must never be handed back out. RETIRED rows ARE candidates: a scan
    that matches one revives it, which is re-attachment to the same
    capability, not reuse by a different one.
    """
    candidates = [r for r in registry if r.status is not IdentityStatus.MERGED]

    scored: dict[tuple[str, str], tuple[float, dict[SignalTier, float]]] = {}
    uncomputable: list[str] = []
    for p in proposed:
        comparable = False
        for c in candidates:
            got = score_pair(p.fingerprint, c.fingerprint, weights)
            if got is None:
                continue
            comparable = True
            scored[(p.local_key, c.bc_id)] = got
        if not comparable and not _is_measured(p):
            uncomputable.append(p.local_key)

    eligible = [Pair(total, bc_id, local_key)
                for (local_key, bc_id), (total, _) in scored.items()
                if total >= t_match]
    assigned = assign(eligible)

    result = ResolutionResult()
    claimed_ids = set(assigned.values())

    for p in proposed:
        bc_id = assigned.get(p.local_key)
        if bc_id is not None:
            total, contributions = scored[(p.local_key, bc_id)]
            result.attachments.append(IdentityAttachment(
                local_key=p.local_key, bc_id=bc_id,
                method=AttachMethod.MATCHED, match_score=total,
                contributions=contributions))
            _maybe_ambiguous(result, p.local_key, bc_id, scored, eligible,
                             epsilon)
            continue

        new_id = allocate()
        lost_to = _lost_above_threshold(p.local_key, scored, claimed_ids,
                                        t_match)
        result.attachments.append(IdentityAttachment(
            local_key=p.local_key, bc_id=new_id,
            method=AttachMethod.FIRST_DISCOVERY))

        if p.local_key in uncomputable:
            result.advisories.append(Advisory(
                kind=AdvisoryKind.IDENTITY_NOT_ASSESSED,
                local_key=p.local_key,
                detail=(f"fingerprint not collected "
                        f"({p.fingerprint.collected.reason}); identity was "
                        f"not assessed and {new_id} was minted")))
        elif lost_to is not None:
            result.advisories.append(Advisory(
                kind=AdvisoryKind.SPLIT, local_key=p.local_key,
                related_bc_id=lost_to, score=scored[(p.local_key, lost_to)][0],
                detail=(f"{lost_to} also matched this capability above "
                        f"threshold but was claimed by a stronger match; "
                        f"{new_id} minted as a split of {lost_to}")))
        elif candidates:
            near = _best_near_miss(p.local_key, scored)
            if near is not None:
                near_id, near_score = near
                result.advisories.append(Advisory(
                    kind=AdvisoryKind.POSSIBLE_RENAME, local_key=p.local_key,
                    related_bc_id=near_id, score=near_score,
                    detail=(f"closest stored capability {near_id} scored "
                            f"{near_score:.3f}, below t_match={t_match}; "
                            f"{new_id} minted")))

    for c in candidates:
        if c.bc_id in claimed_ids:
            continue
        absorbed_by = _absorbed_by(c.bc_id, scored, assigned, t_match)
        if absorbed_by is not None:
            result.merged[c.bc_id] = absorbed_by
        elif c.status is IdentityStatus.ACTIVE:
            result.retired.append(c.bc_id)

    result.retired.sort()
    return result


def _is_measured(p: ProposedCapability) -> bool:
    from ..measurement import CollectionState
    return p.fingerprint.collected.state is CollectionState.MEASURED


def _best_near_miss(local_key: str, scored) -> tuple[str, float] | None:
    """Highest sub-threshold candidate for this local_key, for the advisory.
    Ties break on bc_id so the reported near-miss is deterministic."""
    misses = [(bc_id, total) for (lk, bc_id), (total, _) in scored.items()
              if lk == local_key]
    if not misses:
        return None
    return sorted(misses, key=lambda m: (-m[1], m[0]))[0]


def _lost_above_threshold(local_key: str, scored, claimed_ids: set[str],
                          t_match: float) -> str | None:
    """An id this capability matched above threshold that another capability
    claimed -- i.e. a DETECTED split. Distinct from the `split` correction."""
    losses = [(bc_id, total) for (lk, bc_id), (total, _) in scored.items()
              if lk == local_key and total >= t_match and bc_id in claimed_ids]
    if not losses:
        return None
    return sorted(losses, key=lambda m: (-m[1], m[0]))[0][0]


def _absorbed_by(bc_id: str, scored, assigned: dict[str, str],
                 t_match: float) -> str | None:
    """The id that took the capability this one also matched above threshold
    -- a DETECTED merge. None means it simply was not observed."""
    rivals = [(lk, total) for (lk, cid), (total, _) in scored.items()
              if cid == bc_id and total >= t_match and lk in assigned]
    if not rivals:
        return None
    winner_local = sorted(rivals, key=lambda m: (-m[1], m[0]))[0][0]
    return assigned[winner_local]


def _maybe_ambiguous(result: ResolutionResult, local_key: str, bc_id: str,
                     scored, eligible, epsilon: float) -> None:
    winner = scored[(local_key, bc_id)][0]
    runners = sorted((p.score for p in eligible
                      if p.local_key == local_key and p.bc_id != bc_id),
                     reverse=True)
    if runners and (winner - runners[0]) < epsilon:
        result.advisories.append(Advisory(
            kind=AdvisoryKind.AMBIGUOUS_MATCH, local_key=local_key,
            related_bc_id=bc_id, score=winner,
            detail=(f"runner-up scored {runners[0]:.3f} against winner "
                    f"{winner:.3f}, within epsilon={epsilon}; decided "
                    f"deterministically and reversible by correction")))
