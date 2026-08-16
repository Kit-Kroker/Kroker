"""The assess phase memo (FR-103, FR-916, E-49).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of build.py so that module stays pure -- discover/memo.py's shape
and scan/memo.py's reason.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from ...measurement import CollectionState
from ...memoization import cache
from .models import UnifiedRiskMap

_log = logging.getLogger(__name__)


def load(*, project: str, tree_hash: str, map_digest: str, rules_sha: str,
         prompt_sha: str, model: str) -> UnifiedRiskMap | None:
    """A cached map, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must
    cost a recompute, not an assessment (scan/memo.py's rule).
    """
    raw = cache.get(cache.risk_key(project, tree_hash, map_digest, rules_sha,
                                   prompt_sha, model))
    if raw is None:
        return None
    try:
        return UnifiedRiskMap.model_validate_json(raw)
    except ValidationError:
        _log.warning("risk memo for %s did not validate; recomputing",
                     project)
        return None


def store(*, project: str, tree_hash: str, map_digest: str, rules_sha: str,
          prompt_sha: str, model: str, out: UnifiedRiskMap) -> bool:
    """Cache `out` and report whether it was stored.

    Two refusals, both scan/memo.py's rule 1 -- a transient upstream failure
    must not freeze a permanently missing result into the cache:

    1. Only a MEASURED map is stored.
    2. Under a PROPOSER key, only a MEASURED judgment is stored (P2-D3).
       _discover fails its phase outright when its proposer fails, with the
       stated reason that laundering into baseline "would store a
       judgment-free map under the proposer's memo key". RD7 requires the
       opposite here -- the composites survive -- so the laundering is
       blocked at this end instead. Under the NO_PROPOSER key the degradation
       is permanent rather than transient, and caching it is correct.
    """
    if out.collected.state is not CollectionState.MEASURED:
        return False
    if (prompt_sha != cache.NO_PROPOSER
            and out.judgment.state is not CollectionState.MEASURED):
        return False
    cache.put(cache.risk_key(project, tree_hash, map_digest, rules_sha,
                            prompt_sha, model),
              out.model_dump_json())
    return True
