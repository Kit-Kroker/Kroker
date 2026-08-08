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

from collections.abc import Iterable
from typing import NamedTuple


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
